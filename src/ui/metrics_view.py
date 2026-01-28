"""CloudWatch metrics visualization."""

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from src.aws.cloudwatch import get_ec2_metrics, get_rds_metrics


@st.cache_data(ttl=120)  # 2-minute cache for metrics
def fetch_ec2_metrics(instance_id: str, region: str, hours: int = 24):
    """Fetch and cache EC2 metrics."""
    return get_ec2_metrics(instance_id, region, hours)


@st.cache_data(ttl=120)
def fetch_rds_metrics(db_id: str, region: str, hours: int = 24):
    """Fetch and cache RDS metrics."""
    return get_rds_metrics(db_id, region, hours)


def render_metrics_view(ec2_instances: list[dict], rds_instances: list[dict]):
    """Render metrics visualization page.

    Args:
        ec2_instances: List of EC2 instances
        rds_instances: List of RDS instances
    """
    st.title("📈 CloudWatch Metrics")

    # Resource type selection
    resource_type = st.radio(
        "Resource Type",
        ["EC2", "RDS"],
        horizontal=True,
    )

    # Time range selection
    hours = st.selectbox(
        "Time Range",
        [1, 6, 12, 24, 48, 72],
        index=3,
        format_func=lambda x: f"{x} hour{'s' if x > 1 else ''}",
    )

    st.markdown("---")

    if resource_type == "EC2":
        render_ec2_metrics(ec2_instances, hours)
    else:
        render_rds_metrics(rds_instances, hours)


def render_ec2_metrics(instances: list[dict], hours: int):
    """Render EC2 metrics charts."""
    if not instances:
        st.info("No EC2 instances available")
        return

    # Only show running instances
    running = [i for i in instances if i.get("state") == "running"]
    if not running:
        st.warning("No running EC2 instances to display metrics for")
        return

    # Instance selector
    instance_options = {
        f"{i.get('name') or i.get('id')} ({i.get('region')})": i
        for i in running
    }
    selected_name = st.selectbox("Select Instance", list(instance_options.keys()))
    selected = instance_options[selected_name]

    instance_id = selected.get("id")
    region = selected.get("region")

    # Fetch metrics
    with st.spinner("Loading metrics..."):
        metrics = fetch_ec2_metrics(instance_id, region, hours)

    # Create charts
    fig = make_subplots(
        rows=3, cols=1,
        subplot_titles=("CPU Utilization (%)", "Network In (bytes)", "Network Out (bytes)"),
        vertical_spacing=0.1,
    )

    # CPU Utilization
    cpu_data = metrics.get("CPUUtilization", [])
    if cpu_data:
        fig.add_trace(
            go.Scatter(
                x=[d["timestamp"] for d in cpu_data],
                y=[d["value"] for d in cpu_data],
                mode="lines",
                name="CPU",
                line=dict(color="#FF9900"),
            ),
            row=1, col=1,
        )

    # Network In
    net_in = metrics.get("NetworkIn", [])
    if net_in:
        fig.add_trace(
            go.Scatter(
                x=[d["timestamp"] for d in net_in],
                y=[d["value"] for d in net_in],
                mode="lines",
                name="Network In",
                line=dict(color="#146EB4"),
            ),
            row=2, col=1,
        )

    # Network Out
    net_out = metrics.get("NetworkOut", [])
    if net_out:
        fig.add_trace(
            go.Scatter(
                x=[d["timestamp"] for d in net_out],
                y=[d["value"] for d in net_out],
                mode="lines",
                name="Network Out",
                line=dict(color="#232F3E"),
            ),
            row=3, col=1,
        )

    fig.update_layout(
        height=700,
        showlegend=False,
        title_text=f"Metrics for {selected.get('name') or instance_id}",
    )

    if not any([cpu_data, net_in, net_out]):
        st.warning("No metric data available for this instance")
    else:
        st.plotly_chart(fig, use_container_width=True)


def render_rds_metrics(instances: list[dict], hours: int):
    """Render RDS metrics charts."""
    if not instances:
        st.info("No RDS instances available")
        return

    # Only show available instances
    available = [i for i in instances if i.get("status") == "available"]
    if not available:
        st.warning("No available RDS instances to display metrics for")
        return

    # Instance selector
    instance_options = {
        f"{i.get('id')} ({i.get('region')})": i
        for i in available
    }
    selected_name = st.selectbox("Select Database", list(instance_options.keys()))
    selected = instance_options[selected_name]

    db_id = selected.get("id")
    region = selected.get("region")

    # Fetch metrics
    with st.spinner("Loading metrics..."):
        metrics = fetch_rds_metrics(db_id, region, hours)

    # Create charts
    fig = make_subplots(
        rows=3, cols=1,
        subplot_titles=("CPU Utilization (%)", "Database Connections", "Free Storage Space (bytes)"),
        vertical_spacing=0.1,
    )

    # CPU Utilization
    cpu_data = metrics.get("CPUUtilization", [])
    if cpu_data:
        fig.add_trace(
            go.Scatter(
                x=[d["timestamp"] for d in cpu_data],
                y=[d["value"] for d in cpu_data],
                mode="lines",
                name="CPU",
                line=dict(color="#FF9900"),
            ),
            row=1, col=1,
        )

    # Database Connections
    connections = metrics.get("DatabaseConnections", [])
    if connections:
        fig.add_trace(
            go.Scatter(
                x=[d["timestamp"] for d in connections],
                y=[d["value"] for d in connections],
                mode="lines",
                name="Connections",
                line=dict(color="#146EB4"),
            ),
            row=2, col=1,
        )

    # Free Storage Space
    storage = metrics.get("FreeStorageSpace", [])
    if storage:
        fig.add_trace(
            go.Scatter(
                x=[d["timestamp"] for d in storage],
                y=[d["value"] for d in storage],
                mode="lines",
                name="Free Storage",
                line=dict(color="#232F3E"),
            ),
            row=3, col=1,
        )

    fig.update_layout(
        height=700,
        showlegend=False,
        title_text=f"Metrics for {db_id}",
    )

    if not any([cpu_data, connections, storage]):
        st.warning("No metric data available for this database")
    else:
        st.plotly_chart(fig, use_container_width=True)
