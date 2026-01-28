"""Alert display view."""

import streamlit as st
from src.services.alerts import (
    get_all_alerts,
    get_alert_counts,
    AlertSeverity,
)


def render_alerts_view(ec2_instances: list[dict], rds_instances: list[dict]):
    """Render the alerts view.

    Args:
        ec2_instances: List of EC2 instances
        rds_instances: List of RDS instances
    """
    st.title("🚨 Alerts")

    # Option to check CPU (slower)
    check_cpu = st.checkbox(
        "Check CPU utilization (slower)",
        value=False,
        help="Enable to detect high CPU alerts. This requires additional API calls.",
    )

    # Fetch alerts
    with st.spinner("Checking for alerts..."):
        alerts = get_all_alerts(ec2_instances, rds_instances, check_cpu=check_cpu)

    counts = get_alert_counts(alerts)

    # Summary metrics
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Total Alerts",
            counts["total"],
            delta=None,
        )

    with col2:
        st.metric(
            "🔴 Critical",
            counts["critical"],
            delta=None,
        )

    with col3:
        st.metric(
            "🟡 Warning",
            counts["warning"],
            delta=None,
        )

    st.markdown("---")

    if not alerts:
        st.success("✅ No alerts detected. All systems are healthy!")
        return

    # Filter options
    col1, col2, col3 = st.columns(3)

    with col1:
        severity_filter = st.selectbox(
            "Filter by Severity",
            ["All", "Critical", "Warning"],
        )

    with col2:
        resource_types = sorted(set(a.resource_type for a in alerts))
        type_filter = st.selectbox(
            "Filter by Resource Type",
            ["All"] + resource_types,
        )

    with col3:
        regions = sorted(set(a.region for a in alerts))
        region_filter = st.selectbox(
            "Filter by Region",
            ["All"] + regions,
        )

    # Apply filters
    filtered = alerts
    if severity_filter != "All":
        filtered = [a for a in filtered if a.severity.value == severity_filter.lower()]
    if type_filter != "All":
        filtered = [a for a in filtered if a.resource_type == type_filter]
    if region_filter != "All":
        filtered = [a for a in filtered if a.region == region_filter]

    st.markdown(f"**{len(filtered)}** alerts matching filters")
    st.markdown("---")

    # Display alerts
    for alert in filtered:
        render_alert_card(alert)


def render_alert_card(alert):
    """Render a single alert card.

    Args:
        alert: Alert object to render
    """
    if alert.severity == AlertSeverity.CRITICAL:
        color = "#f8d7da"
        border = "#f5c6cb"
        icon = "🔴"
        severity_text = "CRITICAL"
    else:
        color = "#fff3cd"
        border = "#ffeeba"
        icon = "🟡"
        severity_text = "WARNING"

    st.markdown(
        f"""
        <div style="
            background-color: {color};
            border: 1px solid {border};
            border-left: 4px solid {'#dc3545' if alert.severity == AlertSeverity.CRITICAL else '#ffc107'};
            border-radius: 4px;
            padding: 12px;
            margin-bottom: 10px;
        ">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <strong>{icon} {alert.resource_type}</strong> - {alert.resource_name}
                    <br>
                    <span style="color: #666; font-size: 0.9em;">{alert.region}</span>
                </div>
                <div style="text-align: right;">
                    <span style="
                        background-color: {'#dc3545' if alert.severity == AlertSeverity.CRITICAL else '#ffc107'};
                        color: {'white' if alert.severity == AlertSeverity.CRITICAL else 'black'};
                        padding: 2px 8px;
                        border-radius: 4px;
                        font-size: 0.8em;
                        font-weight: bold;
                    ">{severity_text}</span>
                </div>
            </div>
            <div style="margin-top: 8px;">
                {alert.message}
            </div>
            <div style="margin-top: 4px; color: #666; font-size: 0.85em;">
                Resource ID: {alert.resource_id}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
