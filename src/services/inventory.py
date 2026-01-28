"""Aggregated inventory service with caching."""

import streamlit as st
from src.aws.regions import query_regions, aggregate_results
from src.aws.ec2 import get_ec2_instances
from src.aws.rds import get_rds_instances


@st.cache_data(ttl=300)  # 5-minute cache
def get_all_ec2_instances(regions: tuple[str, ...]) -> list[dict]:
    """Fetch EC2 instances from all specified regions.

    Args:
        regions: Tuple of region names (tuple for hashability with cache)

    Returns:
        List of all EC2 instances across regions
    """
    region_results = query_regions(list(regions), get_ec2_instances)
    return aggregate_results(region_results, key="instances")


@st.cache_data(ttl=300)  # 5-minute cache
def get_all_rds_instances(regions: tuple[str, ...]) -> list[dict]:
    """Fetch RDS instances from all specified regions.

    Args:
        regions: Tuple of region names (tuple for hashability with cache)

    Returns:
        List of all RDS instances across regions
    """
    region_results = query_regions(list(regions), get_rds_instances)
    return aggregate_results(region_results, key="instances")


def get_inventory_summary(
    ec2_instances: list[dict],
    rds_instances: list[dict],
) -> dict:
    """Generate inventory summary statistics.

    Args:
        ec2_instances: List of EC2 instances
        rds_instances: List of RDS instances

    Returns:
        Dict with summary statistics
    """
    ec2_running = sum(1 for i in ec2_instances if i.get("state") == "running")
    ec2_stopped = sum(1 for i in ec2_instances if i.get("state") == "stopped")

    rds_available = sum(1 for i in rds_instances if i.get("status") == "available")

    regions_with_ec2 = len(set(i.get("region") for i in ec2_instances))
    regions_with_rds = len(set(i.get("region") for i in rds_instances))

    return {
        "ec2_total": len(ec2_instances),
        "ec2_running": ec2_running,
        "ec2_stopped": ec2_stopped,
        "rds_total": len(rds_instances),
        "rds_available": rds_available,
        "regions_with_ec2": regions_with_ec2,
        "regions_with_rds": regions_with_rds,
    }
