"""RDS health monitoring UI components."""

import streamlit as st
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.aws.cloudwatch import get_latest_rds_health, get_rds_health_metrics
from src.services.rds_health import (
    HealthStatus,
    calculate_metric_status,
    format_metric_value,
    get_overall_health,
    get_status_color,
    get_status_dim_color,
    get_status_icon,
    get_max_connections_for_class,
)


@st.cache_data(ttl=60)
def fetch_health_for_instance(db_id: str, region: str, instance_class: str) -> dict:
    """Fetch health data for a single RDS instance.

    Args:
        db_id: RDS instance identifier
        region: AWS region
        instance_class: RDS instance class

    Returns:
        Dict with metrics, status, and metadata
    """
    metrics = get_latest_rds_health(db_id, region)
    max_conn = get_max_connections_for_class(instance_class)

    overall = get_overall_health(metrics, max_connections=max_conn)

    return {
        "db_id": db_id,
        "region": region,
        "instance_class": instance_class,
        "metrics": metrics,
        "overall_status": overall,
        "max_connections": max_conn,
    }


@st.cache_data(ttl=60)
def fetch_all_health(rds_instances: tuple) -> list[dict]:
    """Fetch health data for all RDS instances in parallel.

    Args:
        rds_instances: Tuple of RDS instance dicts (tuple for cache key)

    Returns:
        List of health data dicts
    """
    instances = list(rds_instances)
    results = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(
                fetch_health_for_instance,
                inst["Identifier"],
                inst["Region"],
                inst.get("Class", ""),
            ): inst
            for inst in instances
        }
        for future in as_completed(futures):
            inst = futures[future]
            try:
                health = future.result()
                health["engine"] = inst.get("Engine", "")
                results.append(health)
            except Exception:
                results.append({
                    "db_id": inst["Identifier"],
                    "region": inst["Region"],
                    "engine": inst.get("Engine", ""),
                    "instance_class": inst.get("Class", ""),
                    "metrics": {},
                    "overall_status": HealthStatus.UNKNOWN,
                    "max_connections": None,
                })

    return results


@st.cache_data(ttl=120)
def fetch_health_metrics_for_charts(db_id: str, region: str, hours: int = 1) -> dict:
    """Fetch time-series health metrics for charts.

    Args:
        db_id: RDS instance identifier
        region: AWS region
        hours: Hours of data to fetch

    Returns:
        Dict with time-series data for each metric
    """
    return get_rds_health_metrics(db_id, region, hours)


def render_summary_cards(health_data: list[dict]):
    """Render the summary row with health counts.

    Args:
        health_data: List of health data dicts for all instances
    """
    healthy = sum(1 for h in health_data if h["overall_status"] == HealthStatus.HEALTHY)
    warning = sum(1 for h in health_data if h["overall_status"] == HealthStatus.WARNING)
    critical = sum(1 for h in health_data if h["overall_status"] == HealthStatus.CRITICAL)
    total = len(health_data)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(f"""
        <div class="health-summary-card healthy">
            <div class="health-summary-icon">{get_status_icon(HealthStatus.HEALTHY)}</div>
            <div class="health-summary-label">Healthy</div>
            <div class="health-summary-value">{healthy}</div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="health-summary-card warning">
            <div class="health-summary-icon">{get_status_icon(HealthStatus.WARNING)}</div>
            <div class="health-summary-label">Warning</div>
            <div class="health-summary-value">{warning}</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
        <div class="health-summary-card critical">
            <div class="health-summary-icon">{get_status_icon(HealthStatus.CRITICAL)}</div>
            <div class="health-summary-label">Critical</div>
            <div class="health-summary-value">{critical}</div>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        st.markdown(f"""
        <div class="health-summary-card total">
            <div class="health-summary-icon">&#128451;</div>
            <div class="health-summary-label">Total</div>
            <div class="health-summary-value">{total}</div>
        </div>
        """, unsafe_allow_html=True)


def render_health_card(health: dict, index: int):
    """Render a single health card for an RDS instance.

    Args:
        health: Health data dict for the instance
        index: Unique index for the expander key
    """
    status = health["overall_status"]
    status_color = get_status_color(status)
    status_dim = get_status_dim_color(status)
    metrics = health.get("metrics", {})

    # Format metric values
    cpu = format_metric_value("CPUUtilization", metrics.get("CPUUtilization"))
    memory = format_metric_value("FreeableMemory", metrics.get("FreeableMemory"))
    connections = format_metric_value("DatabaseConnections", metrics.get("DatabaseConnections"))

    # Shorten region for display
    region_short = health["region"].replace("southeast", "se").replace("northeast", "ne").replace("east", "e").replace("west", "w")

    st.markdown(f"""
    <div class="health-card" style="border-left: 4px solid {status_color};">
        <div class="health-card-header">
            <div class="health-card-title">
                <span class="health-card-icon" style="background: {status_dim}; color: {status_color};">&#9632;</span>
                <span class="health-card-name">{health["db_id"]}</span>
            </div>
            <div class="health-card-meta">{health.get("engine", "")} | {region_short}</div>
        </div>
        <div class="health-status-badge" style="background: {status_dim}; color: {status_color};">
            {status.value.upper()}
        </div>
        <div class="health-metrics-row">
            <div class="health-metric">
                <div class="health-metric-label">CPU</div>
                <div class="health-metric-value">{cpu}</div>
            </div>
            <div class="health-metric">
                <div class="health-metric-label">Memory</div>
                <div class="health-metric-value">{memory}</div>
            </div>
            <div class="health-metric">
                <div class="health-metric-label">Conn</div>
                <div class="health-metric-value">{connections}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Expandable details with charts
    with st.expander(f"View Details - {health['db_id']}", expanded=False):
        render_health_charts(health["db_id"], health["region"])


def render_health_charts(db_id: str, region: str):
    """Render detailed metric charts for an RDS instance.

    Args:
        db_id: RDS instance identifier
        region: AWS region
    """
    metrics_data = fetch_health_metrics_for_charts(db_id, region, hours=1)

    if not any(metrics_data.values()):
        st.info("No metric data available for the past hour.")
        return

    # Create 2x3 grid of charts
    col1, col2 = st.columns(2)

    metric_configs = [
        ("CPUUtilization", "CPU Utilization", "%", col1),
        ("FreeableMemory", "Freeable Memory", "bytes", col2),
        ("ReadLatency", "Read Latency", "ms", col1),
        ("WriteLatency", "Write Latency", "ms", col2),
        ("DiskQueueDepth", "Disk Queue Depth", "", col1),
        ("DatabaseConnections", "Connections", "", col2),
    ]

    for metric_name, title, unit, col in metric_configs:
        data = metrics_data.get(metric_name, [])
        if not data:
            continue

        with col:
            timestamps = [d["timestamp"] for d in data]
            values = [d["value"] for d in data]

            # Convert units for display
            if metric_name == "FreeableMemory":
                values = [v / (1024 * 1024 * 1024) for v in values]  # Convert to GB
                unit = "GB"
            elif metric_name in ("ReadLatency", "WriteLatency"):
                values = [v * 1000 for v in values]  # Convert to ms

            fig = go.Figure(data=[
                go.Scatter(
                    x=timestamps,
                    y=values,
                    mode='lines',
                    fill='tozeroy',
                    line=dict(color='#4da3ff', width=2),
                    fillcolor='rgba(77, 163, 255, 0.1)',
                    hovertemplate=f'%{{x}}<br>%{{y:.2f}} {unit}<extra></extra>'
                )
            ])

            fig.update_layout(
                title=dict(text=title, font=dict(size=12, color='#8b8b9e')),
                height=150,
                margin=dict(l=0, r=0, t=30, b=20),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='#1a1a24',
                xaxis=dict(
                    showgrid=False,
                    color='#5c5c6e',
                    tickfont=dict(size=9),
                ),
                yaxis=dict(
                    showgrid=True,
                    gridcolor='#2a2a3a',
                    color='#5c5c6e',
                    tickfont=dict(size=9),
                    ticksuffix=f' {unit}' if unit else '',
                ),
            )

            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})


def render_rds_health_section(rds_data: list[dict]):
    """Render the complete RDS health monitoring section.

    Args:
        rds_data: List of RDS instance dicts from the main app
    """
    if not rds_data:
        st.info("No RDS instances found to monitor.")
        return

    # Convert to tuple for caching
    rds_tuple = tuple(
        {k: v for k, v in inst.items()}
        for inst in rds_data
    )

    # Fetch health data for all instances
    with st.spinner(""):
        health_data = fetch_all_health(rds_tuple)

    # Render summary cards
    render_summary_cards(health_data)

    st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)

    # Render health cards in a grid (2 per row)
    # Sort by status severity (critical first, then warning, then healthy)
    status_order = {
        HealthStatus.CRITICAL: 0,
        HealthStatus.WARNING: 1,
        HealthStatus.UNKNOWN: 2,
        HealthStatus.HEALTHY: 3,
    }
    health_data_sorted = sorted(health_data, key=lambda h: status_order.get(h["overall_status"], 3))

    for i in range(0, len(health_data_sorted), 2):
        cols = st.columns(2)
        for j, col in enumerate(cols):
            if i + j < len(health_data_sorted):
                with col:
                    render_health_card(health_data_sorted[i + j], i + j)


def get_health_css() -> str:
    """Get CSS styles for health monitoring components.

    Returns:
        CSS string
    """
    return """
    /* Health Summary Cards */
    .health-summary-card {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        padding: 1rem;
        text-align: center;
        transition: all 0.2s ease;
    }

    .health-summary-card:hover {
        transform: translateY(-2px);
    }

    .health-summary-card.healthy {
        border-color: rgba(0, 217, 126, 0.3);
    }

    .health-summary-card.warning {
        border-color: rgba(255, 179, 71, 0.3);
    }

    .health-summary-card.critical {
        border-color: rgba(255, 71, 87, 0.3);
    }

    .health-summary-card.total {
        border-color: rgba(77, 163, 255, 0.3);
    }

    .health-summary-icon {
        font-size: 1.25rem;
        margin-bottom: 0.25rem;
    }

    .health-summary-card.healthy .health-summary-icon { color: #00d97e; }
    .health-summary-card.warning .health-summary-icon { color: #ffb347; }
    .health-summary-card.critical .health-summary-icon { color: #ff4757; }
    .health-summary-card.total .health-summary-icon { color: #4da3ff; }

    .health-summary-label {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.65rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: var(--text-muted);
        margin-bottom: 0.25rem;
    }

    .health-summary-value {
        font-family: 'Outfit', sans-serif;
        font-size: 1.75rem;
        font-weight: 700;
        color: var(--text-primary);
    }

    /* Health Cards */
    .health-card {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        padding: 1.25rem;
        margin-bottom: 0.5rem;
        transition: all 0.2s ease;
    }

    .health-card:hover {
        background: var(--bg-card-hover);
    }

    .health-card-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 0.75rem;
    }

    .health-card-title {
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .health-card-icon {
        width: 24px;
        height: 24px;
        border-radius: 6px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.75rem;
    }

    .health-card-name {
        font-family: 'Outfit', sans-serif;
        font-weight: 600;
        font-size: 1rem;
        color: var(--text-primary);
    }

    .health-card-meta {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.7rem;
        color: var(--text-muted);
    }

    .health-status-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 6px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 0.05em;
        margin-bottom: 1rem;
    }

    .health-metrics-row {
        display: flex;
        gap: 1.5rem;
    }

    .health-metric {
        flex: 1;
    }

    .health-metric-label {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.65rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: var(--text-muted);
        margin-bottom: 0.25rem;
    }

    .health-metric-value {
        font-family: 'Outfit', sans-serif;
        font-size: 1rem;
        font-weight: 600;
        color: var(--text-primary);
    }
    """
