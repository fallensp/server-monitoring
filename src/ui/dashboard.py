"""Main dashboard view with summary metrics."""

import streamlit as st
from src.services.inventory import get_inventory_summary
from src.services.alerts import get_all_alerts, get_alert_counts
from src.services.costs import get_cost_summary


def render_dashboard(
    ec2_instances: list[dict],
    rds_instances: list[dict],
    regions: tuple[str, ...],
):
    """Render the main dashboard view.

    Args:
        ec2_instances: List of EC2 instances
        rds_instances: List of RDS instances
        regions: Selected regions
    """
    st.title("📊 AWS Resource Dashboard")
    st.markdown(f"Monitoring **{len(regions)}** regions")

    # Get summary data
    inventory = get_inventory_summary(ec2_instances, rds_instances)
    alerts = get_all_alerts(ec2_instances, rds_instances, check_cpu=False)
    alert_counts = get_alert_counts(alerts)

    # Cost data (may fail if Cost Explorer not enabled)
    try:
        cost_summary = get_cost_summary()
        mtd_cost = cost_summary.get("mtd_cost", 0)
    except Exception:
        mtd_cost = None

    # Summary metrics row
    st.subheader("Summary")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="EC2 Instances",
            value=inventory["ec2_total"],
            delta=f"{inventory['ec2_running']} running",
        )

    with col2:
        st.metric(
            label="RDS Databases",
            value=inventory["rds_total"],
            delta=f"{inventory['rds_available']} available",
        )

    with col3:
        alert_color = "🔴" if alert_counts["critical"] > 0 else "🟡" if alert_counts["warning"] > 0 else "🟢"
        st.metric(
            label="Active Alerts",
            value=f"{alert_color} {alert_counts['total']}",
            delta=f"{alert_counts['critical']} critical" if alert_counts["critical"] > 0 else None,
            delta_color="inverse" if alert_counts["critical"] > 0 else "off",
        )

    with col4:
        if mtd_cost is not None:
            st.metric(
                label="MTD Cost",
                value=f"${mtd_cost:,.2f}",
            )
        else:
            st.metric(
                label="MTD Cost",
                value="N/A",
                help="Cost Explorer API access required",
            )

    st.markdown("---")

    # Resource breakdown
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("EC2 by State")
        if ec2_instances:
            states = {}
            for instance in ec2_instances:
                state = instance.get("state", "unknown")
                states[state] = states.get(state, 0) + 1

            for state, count in sorted(states.items()):
                color = "🟢" if state == "running" else "🔴" if state == "stopped" else "🟡"
                st.write(f"{color} **{state}**: {count}")
        else:
            st.info("No EC2 instances found")

    with col2:
        st.subheader("RDS by Status")
        if rds_instances:
            statuses = {}
            for instance in rds_instances:
                status = instance.get("status", "unknown")
                statuses[status] = statuses.get(status, 0) + 1

            for status, count in sorted(statuses.items()):
                color = "🟢" if status == "available" else "🟡"
                st.write(f"{color} **{status}**: {count}")
        else:
            st.info("No RDS instances found")

    st.markdown("---")

    # Regional distribution
    st.subheader("Regional Distribution")

    region_data = {}
    for instance in ec2_instances:
        region = instance.get("region", "unknown")
        if region not in region_data:
            region_data[region] = {"ec2": 0, "rds": 0}
        region_data[region]["ec2"] += 1

    for instance in rds_instances:
        region = instance.get("region", "unknown")
        if region not in region_data:
            region_data[region] = {"ec2": 0, "rds": 0}
        region_data[region]["rds"] += 1

    if region_data:
        cols = st.columns(min(4, len(region_data)))
        for idx, (region, counts) in enumerate(sorted(region_data.items())):
            with cols[idx % 4]:
                st.markdown(f"**{region}**")
                st.caption(f"EC2: {counts['ec2']} | RDS: {counts['rds']}")
    else:
        st.info("No resources found in selected regions")

    # Recent alerts preview
    if alerts:
        st.markdown("---")
        st.subheader("Recent Alerts")
        for alert in alerts[:5]:
            severity_icon = "🔴" if alert.severity.value == "critical" else "🟡"
            st.write(
                f"{severity_icon} **{alert.resource_type}** - "
                f"{alert.resource_name} ({alert.region}): {alert.message}"
            )
        if len(alerts) > 5:
            st.caption(f"... and {len(alerts) - 5} more alerts")
