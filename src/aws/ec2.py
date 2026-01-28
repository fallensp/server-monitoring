"""EC2 inventory fetching."""

from src.aws.client import get_client


def get_ec2_instances(region: str) -> list[dict]:
    """Fetch all EC2 instances in a region.

    Args:
        region: AWS region name

    Returns:
        List of EC2 instance dicts with id, type, state, name, IPs, region
    """
    ec2 = get_client("ec2", region)
    instances = []

    paginator = ec2.get_paginator("describe_instances")
    for page in paginator.paginate():
        for reservation in page["Reservations"]:
            for instance in reservation["Instances"]:
                # Extract name from tags
                name = ""
                for tag in instance.get("Tags", []):
                    if tag["Key"] == "Name":
                        name = tag["Value"]
                        break

                instances.append({
                    "id": instance["InstanceId"],
                    "type": instance.get("InstanceType", ""),
                    "state": instance["State"]["Name"],
                    "name": name,
                    "private_ip": instance.get("PrivateIpAddress", ""),
                    "public_ip": instance.get("PublicIpAddress", ""),
                    "launch_time": instance.get("LaunchTime"),
                    "region": region,
                })

    return instances


def get_ec2_count_by_state(instances: list[dict]) -> dict[str, int]:
    """Count instances by state.

    Args:
        instances: List of EC2 instance dicts

    Returns:
        Dict mapping state to count
    """
    counts = {}
    for instance in instances:
        state = instance.get("state", "unknown")
        counts[state] = counts.get(state, 0) + 1
    return counts
