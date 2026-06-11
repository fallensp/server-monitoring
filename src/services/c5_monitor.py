"""C5 stack monitoring: resource discovery, metric queries, health evaluation.

The c5 stack (Project=titantech) lives in Singapore (ap-southeast-1):
  - EC2  c5-winlose-job  (i-0d01e008541224efc)
  - RDS  c5-sqlserver    (db.t3.small, sqlserver-ex)

Resources are discovered live by the "c5" name prefix so a replaced
instance shows up without a code change.
"""

from src.aws.client import get_client
from src.services.rds_health import (
    HealthStatus,
    get_max_connections_for_class,
    get_memory_for_class,
)

C5_REGION = "ap-southeast-1"
C5_NAME_PREFIX = "c5"


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_ec2() -> list[dict]:
    """Find c5-named EC2 instances in the c5 region (any non-terminated state)."""
    ec2 = get_client("ec2", C5_REGION)
    instances = []
    paginator = ec2.get_paginator("describe_instances")
    for page in paginator.paginate(
        Filters=[{"Name": "tag:Name", "Values": [f"{C5_NAME_PREFIX}*"]}]
    ):
        for res in page.get("Reservations", []):
            for inst in res.get("Instances", []):
                if inst["State"]["Name"] == "terminated":
                    continue
                tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
                instances.append({
                    "id": inst["InstanceId"],
                    "name": tags.get("Name", inst["InstanceId"]),
                    "type": inst.get("InstanceType", "-"),
                    "state": inst["State"]["Name"],
                    "az": inst.get("Placement", {}).get("AvailabilityZone", "-"),
                    "private_ip": inst.get("PrivateIpAddress", "-"),
                    "public_ip": inst.get("PublicIpAddress", "-"),
                    "launch_time": inst.get("LaunchTime"),
                })
    return sorted(instances, key=lambda i: i["name"])


def get_attached_volumes(instance_id: str) -> list[dict]:
    """EBS volumes attached to an instance (type/size/provisioned perf)."""
    ec2 = get_client("ec2", C5_REGION)
    vols = []
    paginator = ec2.get_paginator("describe_volumes")
    for page in paginator.paginate(
        Filters=[{"Name": "attachment.instance-id", "Values": [instance_id]}]
    ):
        for v in page.get("Volumes", []):
            device = next(
                (a.get("Device", "-") for a in v.get("Attachments", [])
                 if a.get("InstanceId") == instance_id),
                "-",
            )
            vols.append({
                "id": v["VolumeId"],
                "device": device,
                "type": v.get("VolumeType", "-"),
                "size_gb": v.get("Size", 0),
                "iops": v.get("Iops"),
                "throughput": v.get("Throughput"),
            })
    return sorted(vols, key=lambda v: v["device"])


def discover_rds() -> list[dict]:
    """Find c5-named RDS instances in the c5 region."""
    rds = get_client("rds", C5_REGION)
    out = []
    paginator = rds.get_paginator("describe_db_instances")
    for page in paginator.paginate():
        for db in page.get("DBInstances", []):
            if not db["DBInstanceIdentifier"].startswith(C5_NAME_PREFIX):
                continue
            out.append({
                "id": db["DBInstanceIdentifier"],
                "engine": db.get("Engine", "-"),
                "engine_version": db.get("EngineVersion", "-"),
                "status": db.get("DBInstanceStatus", "-"),
                "instance_class": db.get("DBInstanceClass", "-"),
                "storage_gb": db.get("AllocatedStorage", 0),
                "storage_type": db.get("StorageType", "-"),
                "endpoint": db.get("Endpoint", {}).get("Address", ""),
                "multi_az": db.get("MultiAZ", False),
            })
    return sorted(out, key=lambda d: d["id"])


# ---------------------------------------------------------------------------
# Metric queries (consumed by src.aws.cloudwatch.get_metric_data_bundle)
# ---------------------------------------------------------------------------

def periods_for_range(hours: int) -> tuple[int, int]:
    """(ec2_ebs_period, rds_period) in seconds for a lookback window.

    EC2 basic monitoring and gp2/gp3 EBS volumes publish at 5-minute
    resolution; RDS publishes at 1-minute resolution.
    """
    if hours <= 6:
        return 300, 60
    if hours <= 24:
        return 300, 300
    if hours <= 72:
        return 900, 900
    return 3600, 3600


def _is_burstable(instance_class: str) -> bool:
    family = instance_class.replace("db.", "").split(".")[0]
    return family.startswith("t")


def ec2_metric_queries(instance_id: str, instance_type: str, period: int) -> list[dict]:
    dims = [{"Name": "InstanceId", "Value": instance_id}]

    def q(key, metric, stat="Average", per_second=False):
        return {
            "key": f"ec2:{instance_id}:{key}", "namespace": "AWS/EC2",
            "metric_name": metric, "dimensions": dims, "stat": stat,
            "period": period, "per_second": per_second,
        }

    queries = [
        # Vitals / load
        q("cpu", "CPUUtilization"),
        q("cpu_max", "CPUUtilization", "Maximum"),
        q("net_in", "NetworkIn", "Sum", per_second=True),
        q("net_out", "NetworkOut", "Sum", per_second=True),
        q("status_failed", "StatusCheckFailed", "Maximum"),
        q("status_failed_system", "StatusCheckFailed_System", "Maximum"),
        q("status_failed_instance", "StatusCheckFailed_Instance", "Maximum"),
        # EBS usage (instance-level, Nitro) — Sums converted to per-second rates
        q("ebs_read_ops", "EBSReadOps", "Sum", per_second=True),
        q("ebs_write_ops", "EBSWriteOps", "Sum", per_second=True),
        q("ebs_read_bytes", "EBSReadBytes", "Sum", per_second=True),
        q("ebs_write_bytes", "EBSWriteBytes", "Sum", per_second=True),
        # EBS pressure — burst-bucket % remaining for the instance's EBS channel
        q("ebs_io_balance", "EBSIOBalance%"),
        q("ebs_byte_balance", "EBSByteBalance%"),
    ]
    if _is_burstable(instance_type):
        queries.append(q("cpu_credits", "CPUCreditBalance"))
    return queries


def volume_metric_queries(volume_id: str, period: int) -> list[dict]:
    dims = [{"Name": "VolumeId", "Value": volume_id}]

    def q(key, metric, stat="Average", per_second=False):
        return {
            "key": f"vol:{volume_id}:{key}", "namespace": "AWS/EBS",
            "metric_name": metric, "dimensions": dims, "stat": stat,
            "period": period, "per_second": per_second,
        }

    return [
        q("read_ops", "VolumeReadOps", "Sum", per_second=True),
        q("write_ops", "VolumeWriteOps", "Sum", per_second=True),
        q("read_bytes", "VolumeReadBytes", "Sum", per_second=True),
        q("write_bytes", "VolumeWriteBytes", "Sum", per_second=True),
        q("queue", "VolumeQueueLength"),
        q("burst", "BurstBalance"),  # gp2/st1/sc1 only — empty for gp3/io1
    ]


def rds_metric_queries(db_id: str, instance_class: str, period: int) -> list[dict]:
    dims = [{"Name": "DBInstanceIdentifier", "Value": db_id}]

    def q(key, metric, stat="Average"):
        return {
            "key": f"rds:{db_id}:{key}", "namespace": "AWS/RDS",
            "metric_name": metric, "dimensions": dims, "stat": stat,
            "period": period,
        }

    queries = [
        # Vitals / load
        q("cpu", "CPUUtilization"),
        q("cpu_max", "CPUUtilization", "Maximum"),
        q("freeable_memory", "FreeableMemory"),
        q("free_storage", "FreeStorageSpace"),
        q("connections", "DatabaseConnections"),
        # Disk usage — RDS publishes these as rates already (count/s, bytes/s)
        q("read_iops", "ReadIOPS"),
        q("write_iops", "WriteIOPS"),
        q("read_throughput", "ReadThroughput"),
        q("write_throughput", "WriteThroughput"),
        # Disk pressure
        q("read_latency", "ReadLatency"),
        q("write_latency", "WriteLatency"),
        q("disk_queue", "DiskQueueDepth"),
        q("burst_balance", "BurstBalance"),  # gp2 storage burst bucket
    ]
    if _is_burstable(instance_class):
        queries.append(q("cpu_credits", "CPUCreditBalance"))
    return queries


# ---------------------------------------------------------------------------
# Health evaluation
# ---------------------------------------------------------------------------

# Credits earned per hour, by family/size. Max accrual is 24h of earning.
_CREDIT_EARN_RATES = {
    "t2": {"nano": 3, "micro": 6, "small": 12, "medium": 24, "large": 36,
           "xlarge": 54, "2xlarge": 81.6},
    "t3": {"nano": 6, "micro": 12, "small": 24, "medium": 24, "large": 36,
           "xlarge": 96, "2xlarge": 192},
    "t3a": {"nano": 6, "micro": 12, "small": 24, "medium": 24, "large": 36,
            "xlarge": 96, "2xlarge": 192},
    "t4g": {"nano": 6, "micro": 12, "small": 24, "medium": 24, "large": 36,
            "xlarge": 96, "2xlarge": 192},
}


def max_cpu_credits(instance_class: str) -> float | None:
    """Maximum accruable CPU credits for a burstable class (EC2 or RDS)."""
    parts = instance_class.replace("db.", "").split(".")
    if len(parts) != 2:
        return None
    rate = _CREDIT_EARN_RATES.get(parts[0], {}).get(parts[1])
    return rate * 24 if rate else None


def _status_high(value: float, warn: float, crit: float) -> HealthStatus:
    """Higher is worse (CPU, latency, queue depth)."""
    if value >= crit:
        return HealthStatus.CRITICAL
    if value >= warn:
        return HealthStatus.WARNING
    return HealthStatus.HEALTHY


def _status_low(value: float, warn: float, crit: float) -> HealthStatus:
    """Lower is worse (burst balances, credits, free memory/storage)."""
    if value <= crit:
        return HealthStatus.CRITICAL
    if value <= warn:
        return HealthStatus.WARNING
    return HealthStatus.HEALTHY


def latest(series: list[dict]) -> float | None:
    """Most recent datapoint value of a (sorted) series."""
    return series[-1]["value"] if series else None


def collect_alerts(
    series: dict[str, list[dict]],
    ec2_inst: dict | None,
    rds_inst: dict | None,
    volumes: list[dict],
) -> list[dict]:
    """Evaluate the latest datapoints against thresholds.

    Returns a list of {resource, message, status} for everything in
    WARNING or CRITICAL, worst first.
    """
    alerts = []

    def check(resource, value, status_fn, warn, crit, message_fmt):
        if value is None:
            return
        status = status_fn(value, warn, crit)
        if status in (HealthStatus.WARNING, HealthStatus.CRITICAL):
            alerts.append({
                "resource": resource,
                "message": message_fmt.format(value=value),
                "status": status,
            })

    if ec2_inst:
        name = ec2_inst["name"]
        p = f"ec2:{ec2_inst['id']}"
        check(name, latest(series.get(f"{p}:cpu", [])), _status_high, 70, 90,
              "CPU at {value:.0f}%")
        check(name, latest(series.get(f"{p}:status_failed", [])), _status_high, 1, 1,
              "EC2 status check failing")
        check(name, latest(series.get(f"{p}:ebs_io_balance", [])), _status_low, 50, 20,
              "EBS IO burst balance at {value:.0f}%")
        check(name, latest(series.get(f"{p}:ebs_byte_balance", [])), _status_low, 50, 20,
              "EBS byte burst balance at {value:.0f}%")
        max_credits = max_cpu_credits(ec2_inst.get("type", ""))
        credits = latest(series.get(f"{p}:cpu_credits", []))
        if credits is not None and max_credits:
            check(name, credits / max_credits * 100, _status_low, 25, 10,
                  "CPU credits at {value:.0f}% of max")

    for vol in volumes:
        vid = vol["id"]
        label = f"{vid} ({vol['device']})"
        check(label, latest(series.get(f"vol:{vid}:burst", [])), _status_low, 50, 20,
              "volume burst balance at {value:.0f}%")
        check(label, latest(series.get(f"vol:{vid}:queue", [])), _status_high, 5, 20,
              "volume queue length at {value:.1f}")

    if rds_inst:
        name = rds_inst["id"]
        p = f"rds:{rds_inst['id']}"
        check(name, latest(series.get(f"{p}:cpu", [])), _status_high, 70, 90,
              "CPU at {value:.0f}%")
        check(name, latest(series.get(f"{p}:burst_balance", [])), _status_low, 50, 20,
              "storage burst balance at {value:.0f}%")
        check(name, latest(series.get(f"{p}:disk_queue", [])), _status_high, 10, 50,
              "disk queue depth at {value:.1f}")

        for key, label in ((f"{p}:read_latency", "read"), (f"{p}:write_latency", "write")):
            lat = latest(series.get(key, []))
            if lat is not None:
                check(name, lat * 1000, _status_high, 20, 50,
                      label + " latency at {value:.1f} ms")

        total_mem = get_memory_for_class(rds_inst.get("instance_class", ""))
        mem = latest(series.get(f"{p}:freeable_memory", []))
        if mem is not None and total_mem:
            check(name, mem / total_mem * 100, _status_low, 25, 10,
                  "freeable memory at {value:.0f}% of total")

        storage_gb = rds_inst.get("storage_gb") or 0
        free = latest(series.get(f"{p}:free_storage", []))
        if free is not None and storage_gb:
            check(name, free / (storage_gb * 1024 ** 3) * 100, _status_low, 20, 10,
                  "free storage at {value:.0f}% of allocated")

        max_conn = get_max_connections_for_class(rds_inst.get("instance_class", ""))
        conn = latest(series.get(f"{p}:connections", []))
        if conn is not None and max_conn:
            check(name, conn / max_conn * 100, _status_high, 80, 95,
                  "connections at {value:.0f}% of max")

        max_credits = max_cpu_credits(rds_inst.get("instance_class", ""))
        credits = latest(series.get(f"{p}:cpu_credits", []))
        if credits is not None and max_credits:
            check(name, credits / max_credits * 100, _status_low, 25, 10,
                  "CPU credits at {value:.0f}% of max")

    order = {HealthStatus.CRITICAL: 0, HealthStatus.WARNING: 1}
    alerts.sort(key=lambda a: order.get(a["status"], 2))
    return alerts
