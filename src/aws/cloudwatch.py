"""CloudWatch metrics fetching."""

from datetime import datetime, timedelta, timezone
from src.aws.client import get_client


def get_ec2_metrics(
    instance_id: str,
    region: str,
    hours: int = 24,
) -> dict[str, list[dict]]:
    """Fetch CloudWatch metrics for an EC2 instance.

    Args:
        instance_id: EC2 instance ID
        region: AWS region name
        hours: Number of hours of data to fetch

    Returns:
        Dict with CPUUtilization, NetworkIn, NetworkOut metrics
    """
    cw = get_client("cloudwatch", region)
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours)

    metrics = {}
    metric_names = ["CPUUtilization", "NetworkIn", "NetworkOut"]

    for metric_name in metric_names:
        try:
            response = cw.get_metric_statistics(
                Namespace="AWS/EC2",
                MetricName=metric_name,
                Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
                StartTime=start_time,
                EndTime=end_time,
                Period=300,  # 5-minute intervals
                Statistics=["Average"],
            )
            datapoints = sorted(
                response.get("Datapoints", []),
                key=lambda x: x["Timestamp"],
            )
            metrics[metric_name] = [
                {
                    "timestamp": dp["Timestamp"],
                    "value": dp["Average"],
                }
                for dp in datapoints
            ]
        except Exception as e:
            metrics[metric_name] = []

    return metrics


def get_rds_metrics(
    db_instance_id: str,
    region: str,
    hours: int = 24,
) -> dict[str, list[dict]]:
    """Fetch CloudWatch metrics for an RDS instance.

    Args:
        db_instance_id: RDS instance identifier
        region: AWS region name
        hours: Number of hours of data to fetch

    Returns:
        Dict with CPUUtilization, DatabaseConnections, FreeStorageSpace metrics
    """
    cw = get_client("cloudwatch", region)
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours)

    metrics = {}
    metric_names = ["CPUUtilization", "DatabaseConnections", "FreeStorageSpace"]

    for metric_name in metric_names:
        try:
            response = cw.get_metric_statistics(
                Namespace="AWS/RDS",
                MetricName=metric_name,
                Dimensions=[{"Name": "DBInstanceIdentifier", "Value": db_instance_id}],
                StartTime=start_time,
                EndTime=end_time,
                Period=300,  # 5-minute intervals
                Statistics=["Average"],
            )
            datapoints = sorted(
                response.get("Datapoints", []),
                key=lambda x: x["Timestamp"],
            )
            metrics[metric_name] = [
                {
                    "timestamp": dp["Timestamp"],
                    "value": dp["Average"],
                }
                for dp in datapoints
            ]
        except Exception as e:
            metrics[metric_name] = []

    return metrics


def get_latest_cpu_utilization(instance_id: str, region: str, namespace: str) -> float | None:
    """Get the most recent CPU utilization for an instance.

    Args:
        instance_id: Instance ID (EC2 or RDS identifier)
        region: AWS region name
        namespace: AWS/EC2 or AWS/RDS

    Returns:
        Latest CPU percentage or None if unavailable
    """
    cw = get_client("cloudwatch", region)
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=10)

    dimension_name = "InstanceId" if namespace == "AWS/EC2" else "DBInstanceIdentifier"

    try:
        response = cw.get_metric_statistics(
            Namespace=namespace,
            MetricName="CPUUtilization",
            Dimensions=[{"Name": dimension_name, "Value": instance_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=300,
            Statistics=["Average"],
        )
        datapoints = response.get("Datapoints", [])
        if datapoints:
            latest = max(datapoints, key=lambda x: x["Timestamp"])
            return latest["Average"]
    except Exception:
        pass

    return None


# RDS Health Monitoring metrics
RDS_HEALTH_METRICS = [
    "CPUUtilization",
    "FreeableMemory",
    "ReadLatency",
    "WriteLatency",
    "DiskQueueDepth",
    "DatabaseConnections",
]


def get_rds_health_metrics(
    db_instance_id: str,
    region: str,
    hours: int = 1,
) -> dict[str, list[dict]]:
    """Fetch health-related CloudWatch metrics for an RDS instance.

    Args:
        db_instance_id: RDS instance identifier
        region: AWS region name
        hours: Number of hours of data to fetch (default 1 for recent data)

    Returns:
        Dict with health metrics: CPUUtilization, FreeableMemory, ReadLatency,
        WriteLatency, DiskQueueDepth, DatabaseConnections
    """
    cw = get_client("cloudwatch", region)
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours)

    # Use 1-minute resolution for health monitoring
    period = 60

    metrics = {}

    for metric_name in RDS_HEALTH_METRICS:
        try:
            response = cw.get_metric_statistics(
                Namespace="AWS/RDS",
                MetricName=metric_name,
                Dimensions=[{"Name": "DBInstanceIdentifier", "Value": db_instance_id}],
                StartTime=start_time,
                EndTime=end_time,
                Period=period,
                Statistics=["Average"],
            )
            datapoints = sorted(
                response.get("Datapoints", []),
                key=lambda x: x["Timestamp"],
            )
            metrics[metric_name] = [
                {
                    "timestamp": dp["Timestamp"],
                    "value": dp["Average"],
                }
                for dp in datapoints
            ]
        except Exception:
            metrics[metric_name] = []

    return metrics


def get_latest_rds_health(db_instance_id: str, region: str) -> dict[str, float | None]:
    """Get the most recent health metrics for an RDS instance.

    Args:
        db_instance_id: RDS instance identifier
        region: AWS region name

    Returns:
        Dict with latest values for each health metric, None if unavailable
    """
    cw = get_client("cloudwatch", region)
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=10)

    latest_metrics = {}

    for metric_name in RDS_HEALTH_METRICS:
        try:
            response = cw.get_metric_statistics(
                Namespace="AWS/RDS",
                MetricName=metric_name,
                Dimensions=[{"Name": "DBInstanceIdentifier", "Value": db_instance_id}],
                StartTime=start_time,
                EndTime=end_time,
                Period=60,
                Statistics=["Average"],
            )
            datapoints = response.get("Datapoints", [])
            if datapoints:
                latest = max(datapoints, key=lambda x: x["Timestamp"])
                latest_metrics[metric_name] = latest["Average"]
            else:
                latest_metrics[metric_name] = None
        except Exception:
            latest_metrics[metric_name] = None

    return latest_metrics


def get_metric_data_bundle(
    region: str,
    queries: list[dict],
    hours: int = 24,
) -> dict[str, list[dict]]:
    """Fetch many CloudWatch metrics in a single GetMetricData call.

    Much cheaper than one GetMetricStatistics call per metric, and the
    queries may mix namespaces (AWS/EC2 + AWS/EBS + AWS/RDS).

    Args:
        region: AWS region name
        queries: List of query dicts with keys:
            key: result-dict key for this series
            namespace: e.g. "AWS/EC2"
            metric_name: e.g. "CPUUtilization"
            dimensions: e.g. [{"Name": "InstanceId", "Value": "i-..."}]
            stat: "Average" | "Maximum" | "Sum" (default "Average")
            period: datapoint period in seconds (default 300)
            per_second: if True, divide each value by the period —
                converts a Sum series (e.g. NetworkIn bytes) into a rate
        hours: lookback window

    Returns:
        Dict mapping each query's key to a sorted list of
        {"timestamp", "value"} datapoints (empty list for metrics that
        simply have no datapoints, e.g. a stopped instance).

    Raises:
        botocore exceptions on API failure. Deliberately NOT swallowed:
        GetMetricData is all-or-nothing, so a swallowed error would make
        every series look empty — on a monitoring page that renders as
        "everything healthy", which is the opposite of the truth.
    """
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours)

    metric_queries = []
    id_to_query = {}
    for i, q in enumerate(queries):
        qid = f"m{i}"
        id_to_query[qid] = q
        metric_queries.append({
            "Id": qid,
            "MetricStat": {
                "Metric": {
                    "Namespace": q["namespace"],
                    "MetricName": q["metric_name"],
                    "Dimensions": q["dimensions"],
                },
                "Period": int(q.get("period", 300)),
                "Stat": q.get("stat", "Average"),
            },
            "ReturnData": True,
        })

    results = {q["key"]: [] for q in queries}
    cw = get_client("cloudwatch", region)
    paginator = cw.get_paginator("get_metric_data")
    # GetMetricData accepts at most 500 queries per call
    for batch_start in range(0, len(metric_queries), 500):
        batch = metric_queries[batch_start:batch_start + 500]
        for page in paginator.paginate(
            MetricDataQueries=batch,
            StartTime=start_time,
            EndTime=end_time,
            ScanBy="TimestampAscending",
        ):
            for r in page.get("MetricDataResults", []):
                q = id_to_query.get(r["Id"])
                if q is None:
                    continue
                divisor = float(q.get("period", 300)) if q.get("per_second") else 1.0
                results[q["key"]].extend(
                    {"timestamp": t, "value": v / divisor}
                    for t, v in zip(r.get("Timestamps", []), r.get("Values", []))
                )

    for series in results.values():
        series.sort(key=lambda d: d["timestamp"])
    return results
