"""RDS inventory fetching."""

from src.aws.client import get_client


def get_rds_instances(region: str) -> list[dict]:
    """Fetch all RDS instances in a region.

    Args:
        region: AWS region name

    Returns:
        List of RDS instance dicts with id, engine, status, class, storage, region
    """
    rds = get_client("rds", region)
    instances = []

    paginator = rds.get_paginator("describe_db_instances")
    for page in paginator.paginate():
        for db in page["DBInstances"]:
            instances.append({
                "id": db["DBInstanceIdentifier"],
                "engine": db.get("Engine", ""),
                "engine_version": db.get("EngineVersion", ""),
                "status": db.get("DBInstanceStatus", ""),
                "instance_class": db.get("DBInstanceClass", ""),
                "storage_gb": db.get("AllocatedStorage", 0),
                "multi_az": db.get("MultiAZ", False),
                "endpoint": db.get("Endpoint", {}).get("Address", ""),
                "port": db.get("Endpoint", {}).get("Port", ""),
                "region": region,
            })

    return instances


def get_rds_count_by_status(instances: list[dict]) -> dict[str, int]:
    """Count RDS instances by status.

    Args:
        instances: List of RDS instance dicts

    Returns:
        Dict mapping status to count
    """
    counts = {}
    for instance in instances:
        status = instance.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts
