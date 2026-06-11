"""C5 stack monitor UI components (pages/1_C5_Monitor.py)."""

import html

import streamlit as st
import plotly.graph_objects as go

from src.aws.cloudwatch import get_metric_data_bundle
from src.services import c5_monitor
from src.services.rds_health import (
    HealthStatus,
    get_status_color,
    get_status_dim_color,
)

# Chart palette (matches the dashboard theme)
BLUE = "#4da3ff"
ORANGE = "#ff6b2c"
GREEN = "#00d97e"
RED = "#ff4757"
AMBER = "#ffb347"
PURPLE = "#a855f7"
MUTED = "#5c5c6e"
CHART_BG = "#1a1a24"
GRID = "#2a2a3a"

_latest = c5_monitor.latest


# ---------------------------------------------------------------------------
# Cached data fetchers
# ---------------------------------------------------------------------------

@st.cache_data(ttl=120)
def fetch_inventory() -> dict:
    """Discover c5 EC2/RDS resources and attached EBS volumes.

    Raises on AWS errors. st.cache_data does not memoize exceptions, so a
    transient failure is retried on the next rerun instead of pinning an
    error page for the whole TTL — the page catches and renders it.
    """
    ec2 = c5_monitor.discover_ec2()
    rds = c5_monitor.discover_rds()
    volumes = {inst["id"]: c5_monitor.get_attached_volumes(inst["id"])
               for inst in ec2}
    return {"ec2": ec2, "rds": rds, "volumes": volumes}


@st.cache_data(ttl=120)
def fetch_metrics(
    ec2_key: tuple,
    vol_key: tuple,
    rds_key: tuple,
    hours: int,
) -> dict:
    """One batched GetMetricData call for every c5 metric series.

    Args:
        ec2_key: tuple of (instance_id, instance_type)
        vol_key: tuple of volume ids
        rds_key: tuple of (db_id, instance_class)
        hours: lookback window
    """
    ec2_period, rds_period = c5_monitor.periods_for_range(hours)
    queries = []
    for instance_id, instance_type in ec2_key:
        queries += c5_monitor.ec2_metric_queries(instance_id, instance_type, ec2_period)
    for volume_id in vol_key:
        queries += c5_monitor.volume_metric_queries(volume_id, ec2_period)
    for db_id, instance_class in rds_key:
        queries += c5_monitor.rds_metric_queries(db_id, instance_class, rds_period)
    if not queries:
        return {}
    return get_metric_data_bundle(c5_monitor.C5_REGION, queries, hours=hours)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _human_rate(value: float | None) -> str:
    """Format a bytes/second rate."""
    if value is None:
        return "N/A"
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if abs(value) < 1024 or unit == "GB/s":
            return f"{value:.1f} {unit}" if unit != "B/s" else f"{value:.0f} {unit}"
        value /= 1024
    return f"{value:.1f} GB/s"


def _human_bytes(value: float | None) -> str:
    if value is None:
        return "N/A"
    gb = value / (1024 ** 3)
    if gb >= 1:
        return f"{gb:.2f} GB"
    return f"{value / (1024 ** 2):.0f} MB"


def _fmt_pct(value: float | None, decimals: int = 1) -> str:
    return "N/A" if value is None else f"{value:.{decimals}f}%"


def _series_stats(series: list[dict]) -> tuple[float | None, float | None]:
    """(average, max) over a series."""
    if not series:
        return None, None
    values = [d["value"] for d in series]
    return sum(values) / len(values), max(values)


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

def _chart_layout(title: str, unit: str = "", height: int = 170) -> dict:
    return dict(
        title=dict(text=title, font=dict(size=12, color="#8b8b9e")),
        height=height,
        margin=dict(l=0, r=0, t=30, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor=CHART_BG,
        showlegend=True,
        legend=dict(
            orientation="h", y=1.15, x=1, xanchor="right",
            font=dict(size=9, color=MUTED), bgcolor="rgba(0,0,0,0)",
        ),
        xaxis=dict(showgrid=False, color=MUTED, tickfont=dict(size=9)),
        yaxis=dict(
            showgrid=True, gridcolor=GRID, color=MUTED,
            tickfont=dict(size=9), ticksuffix=f" {unit}" if unit else "",
            rangemode="tozero",
        ),
    )


def _ts_chart(key: str, title: str, traces: list[dict], unit: str = "",
              height: int = 170) -> None:
    """Render a small time-series chart.

    Args:
        traces: list of {"name", "color", "series", optional "scale"}
            where series is [{"timestamp", "value"}, ...]
    """
    populated = [t for t in traces if t["series"]]
    if not populated:
        st.caption(f"{title}: no data in this window")
        return

    fig = go.Figure()
    for i, t in enumerate(populated):
        scale = t.get("scale", 1.0)
        fig.add_trace(go.Scatter(
            x=[d["timestamp"] for d in t["series"]],
            y=[d["value"] * scale for d in t["series"]],
            mode="lines",
            name=t["name"],
            line=dict(color=t["color"], width=2),
            fill="tozeroy" if i == 0 else None,
            fillcolor=f"rgba({int(t['color'][1:3], 16)}, {int(t['color'][3:5], 16)}, {int(t['color'][5:7], 16)}, 0.1)" if i == 0 else None,
            hovertemplate=f"%{{x}}<br>%{{y:.2f}} {unit}<extra>{t['name']}</extra>",
        ))
    fig.update_layout(**_chart_layout(title, unit, height))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=key)


def _gauge(key: str, title: str, value: float | None, *, invert: bool = False,
           suffix: str = "%", height: int = 150) -> None:
    """Render a 0-100 gauge. invert=True means lower values are bad."""
    if value is None:
        st.markdown(f"""
        <div class="metric-card" style="text-align:center; padding: 1rem;">
            <div class="label">{html.escape(title)}</div>
            <div class="value" style="font-size:1.5rem; color: #5c5c6e;">N/A</div>
        </div>
        """, unsafe_allow_html=True)
        return

    if invert:
        steps = [
            dict(range=[0, 20], color="rgba(255, 71, 87, 0.25)"),
            dict(range=[20, 50], color="rgba(255, 179, 71, 0.25)"),
            dict(range=[50, 100], color="rgba(0, 217, 126, 0.18)"),
        ]
        bar_color = RED if value <= 20 else AMBER if value <= 50 else GREEN
    else:
        steps = [
            dict(range=[0, 70], color="rgba(0, 217, 126, 0.18)"),
            dict(range=[70, 90], color="rgba(255, 179, 71, 0.25)"),
            dict(range=[90, 100], color="rgba(255, 71, 87, 0.25)"),
        ]
        bar_color = RED if value >= 90 else AMBER if value >= 70 else GREEN

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=min(max(value, 0), 100),
        number=dict(suffix=suffix, font=dict(size=22, color="#ffffff")),
        title=dict(text=title, font=dict(size=11, color="#8b8b9e")),
        gauge=dict(
            axis=dict(range=[0, 100], tickfont=dict(size=8, color=MUTED)),
            bar=dict(color=bar_color, thickness=0.3),
            bgcolor=CHART_BG,
            borderwidth=0,
            steps=steps,
        ),
    ))
    fig.update_layout(
        height=height,
        margin=dict(l=15, r=15, t=30, b=5),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=key)


def _metric_card(label: str, value: str, sub: str, icon: str,
                 badge: str = "blue", sub_class: str = "neutral") -> str:
    return f"""
    <div class="metric-card">
        <div class="icon-badge {badge}">{icon}</div>
        <div class="label">{html.escape(label)}</div>
        <div class="value" style="font-size: 1.6rem;">{html.escape(value)}</div>
        <div class="delta {sub_class}">{html.escape(sub)}</div>
    </div>
    """


def _resource_header(title: str, icon: str, state: str, state_ok: bool,
                     meta: str) -> None:
    badge_class = "running" if state_ok else "stopped"
    st.markdown(f"""
    <div class="section-header" style="justify-content: space-between;">
        <div style="display: flex; align-items: center; gap: 12px;">
            <h2>{icon} {html.escape(title)}</h2>
            <span class="status-badge {badge_class}">{html.escape(state)}</span>
        </div>
        <span class="count">{html.escape(meta)}</span>
    </div>
    """, unsafe_allow_html=True)


def render_alert_strip(alerts: list[dict], offline: list[str] | None = None) -> None:
    """Threshold breaches across the whole stack, worst first.

    Args:
        alerts: output of c5_monitor.collect_alerts for online resources
        offline: names of stopped resources excluded from evaluation —
            shown explicitly so "no alerts" can't be read as "all healthy"
    """
    offline_html = ""
    if offline:
        names = ", ".join(html.escape(n) for n in offline)
        offline_html = (
            '<div style="display: flex; align-items: center; gap: 10px; background: rgba(108, 117, 125, 0.08); '
            'border: 1px solid rgba(108, 117, 125, 0.3); border-radius: 12px; padding: 0.6rem 1.25rem; margin-bottom: 1rem;">'
            '<span style="color: #6c757d;">⏸</span>'
            '<span style="font-family: \'JetBrains Mono\', monospace; font-size: 0.72rem; color: #6c757d;">'
            f'Offline, not evaluated: {names}</span></div>'
        )

    if not alerts:
        scope = "monitored" if not offline else "online"
        st.markdown(f"""
        <div style="display: flex; align-items: center; gap: 10px; background: rgba(0, 217, 126, 0.08);
             border: 1px solid rgba(0, 217, 126, 0.3); border-radius: 12px; padding: 0.75rem 1.25rem; margin-bottom: 1rem;">
            <span style="color: #00d97e;">✓</span>
            <span style="font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: #00d97e;">
                All {scope} metrics within thresholds</span>
        </div>
        {offline_html}
        """, unsafe_allow_html=True)
        return

    items = []
    for a in alerts:
        color = get_status_color(a["status"])
        dim = get_status_dim_color(a["status"])
        items.append(
            f'<div style="display: flex; align-items: center; gap: 10px; background: {dim}; '
            f'border-left: 3px solid {color}; border-radius: 8px; padding: 0.5rem 1rem; margin-bottom: 6px;">'
            f'<span style="color: {color}; font-size: 0.8rem;">{"✗" if a["status"] == HealthStatus.CRITICAL else "⚠"}</span>'
            f'<span style="font-family: \'JetBrains Mono\', monospace; font-size: 0.75rem; color: {color};">'
            f'<strong>{html.escape(a["resource"])}</strong> — {html.escape(a["message"])}</span></div>'
        )
    st.markdown("".join(items) + offline_html, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def render_ec2_section(inst: dict, volumes: list[dict],
                       series: dict[str, list[dict]]) -> None:
    p = f"ec2:{inst['id']}"        # series key prefix (see c5_monitor)
    kp = f"c5_{inst['id']}"        # widget key prefix — unique per instance
    running = inst["state"] == "running"
    meta = f"{inst['type']} · {inst['az']} · {inst['private_ip']}"
    _resource_header(inst["name"], "🖥️", inst["state"], running, meta)

    if not running:
        st.info(f"⏸️ Instance is {inst['state']} — no telemetry is being published. "
                "Charts below show the last data before it went offline.")

    cpu = series.get(f"{p}:cpu", [])
    cpu_max = series.get(f"{p}:cpu_max", [])
    cpu_avg_w, _ = _series_stats(cpu)
    _, cpu_peak_w = _series_stats(cpu_max)

    status_now = _latest(series.get(f"{p}:status_failed", []))
    if status_now is None:
        status_txt, status_sub, status_cls = "N/A", "no recent data", "neutral"
    elif status_now > 0:
        sys_fail = (_latest(series.get(f"{p}:status_failed_system", [])) or 0) > 0
        status_txt = "FAIL"
        status_sub = "system check" if sys_fail else "instance check"
        status_cls = "negative"
    else:
        status_txt, status_sub, status_cls = "PASS", "2/2 checks", "positive"

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(_metric_card(
            "CPU Now", _fmt_pct(_latest(cpu)),
            f"avg {_fmt_pct(cpu_avg_w, 0)} · peak {_fmt_pct(cpu_peak_w, 0)}",
            "🔥", "orange",
        ), unsafe_allow_html=True)
    with col2:
        st.markdown(_metric_card(
            "Network In", _human_rate(_latest(series.get(f"{p}:net_in", []))),
            "● latest rate", "📥", "blue",
        ), unsafe_allow_html=True)
    with col3:
        st.markdown(_metric_card(
            "Network Out", _human_rate(_latest(series.get(f"{p}:net_out", []))),
            "● latest rate", "📤", "blue",
        ), unsafe_allow_html=True)
    with col4:
        st.markdown(_metric_card(
            "Status Checks", status_txt, f"● {status_sub}", "🩺", "green",
            sub_class=status_cls,
        ), unsafe_allow_html=True)

    st.markdown("<div style='height: 0.75rem;'></div>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        _ts_chart(f"{kp}_cpu", "CPU Utilization (load)", [
            {"name": "avg", "color": ORANGE, "series": cpu},
            {"name": "max", "color": RED, "series": cpu_max},
        ], unit="%")
    with col2:
        _ts_chart(f"{kp}_net", "Network Throughput", [
            {"name": "in", "color": BLUE, "series": series.get(f"{p}:net_in", []),
             "scale": 1 / (1024 ** 2)},
            {"name": "out", "color": PURPLE, "series": series.get(f"{p}:net_out", []),
             "scale": 1 / (1024 ** 2)},
        ], unit="MB/s")

    st.caption("OS memory isn't published by EC2 without the CloudWatch agent — "
               "CPU, network, disk, and status checks are shown from hypervisor metrics.")

    # --- EBS usage & pressure -------------------------------------------
    st.markdown("""
    <div class="section-header" style="margin-top: 1rem;">
        <h2 style="font-size: 1rem;">💾 EBS Usage & Pressure</h2>
    </div>
    """, unsafe_allow_html=True)

    gauge_cols = st.columns(4)
    with gauge_cols[0]:
        _gauge(f"{kp}_io_bal", "EBS IO Balance",
               _latest(series.get(f"{p}:ebs_io_balance", [])), invert=True)
    with gauge_cols[1]:
        _gauge(f"{kp}_byte_bal", "EBS Byte Balance",
               _latest(series.get(f"{p}:ebs_byte_balance", [])), invert=True)
    with gauge_cols[2]:
        burst_vol = next((v for v in volumes
                          if series.get(f"vol:{v['id']}:burst")), None)
        if burst_vol:
            _gauge(f"c5_vol_burst_{burst_vol['id']}",
                   f"Vol Burst ({burst_vol['device']})",
                   _latest(series.get(f"vol:{burst_vol['id']}:burst", [])),
                   invert=True)
        else:
            _gauge(f"{kp}_vol_burst_none", "Vol Burst Balance", None)
    with gauge_cols[3]:
        credits = _latest(series.get(f"{p}:cpu_credits", []))
        max_credits = c5_monitor.max_cpu_credits(inst.get("type", ""))
        if credits is not None and max_credits:
            _gauge(f"{kp}_credits", "CPU Credits",
                   credits / max_credits * 100, invert=True)
        else:
            queue_vals = [_latest(series.get(f"vol:{v['id']}:queue", []))
                          for v in volumes]
            queue_vals = [q for q in queue_vals if q is not None]
            queue_now = max(queue_vals) if queue_vals else None
            st.markdown(_metric_card(
                "Vol Queue Depth",
                "N/A" if queue_now is None else f"{queue_now:.2f}",
                "● warn ≥ 5", "⏳", "red",
                sub_class="negative" if (queue_now or 0) >= 5 else "neutral",
            ), unsafe_allow_html=True)

    st.caption("Balance gauges are burst buckets — 100% is a full bucket; "
               "sustained low % means the workload is pressing against the "
               "instance/volume baseline and will be throttled at 0%.")

    col1, col2 = st.columns(2)
    with col1:
        _ts_chart(f"{kp}_ebs_iops", "EBS IOPS", [
            {"name": "read", "color": GREEN, "series": series.get(f"{p}:ebs_read_ops", [])},
            {"name": "write", "color": ORANGE, "series": series.get(f"{p}:ebs_write_ops", [])},
        ], unit="ops/s")
    with col2:
        _ts_chart(f"{kp}_ebs_tput", "EBS Throughput", [
            {"name": "read", "color": GREEN, "series": series.get(f"{p}:ebs_read_bytes", []),
             "scale": 1 / (1024 ** 2)},
            {"name": "write", "color": ORANGE, "series": series.get(f"{p}:ebs_write_bytes", []),
             "scale": 1 / (1024 ** 2)},
        ], unit="MB/s")

    col1, col2 = st.columns(2)
    with col1:
        _ts_chart(f"{kp}_ebs_balance", "EBS Burst Balances", [
            {"name": "IO balance", "color": BLUE,
             "series": series.get(f"{p}:ebs_io_balance", [])},
            {"name": "byte balance", "color": PURPLE,
             "series": series.get(f"{p}:ebs_byte_balance", [])},
        ], unit="%")
    with col2:
        _ts_chart(f"{kp}_vol_queue", "Volume Queue Length", [
            {"name": f"{v['device']}", "color": [BLUE, ORANGE, GREEN, PURPLE][i % 4],
             "series": series.get(f"vol:{v['id']}:queue", [])}
            for i, v in enumerate(volumes)
        ])

    if volumes:
        chips = []
        for v in volumes:
            perf = f"{v['iops']} IOPS" if v.get("iops") else ""
            if v.get("throughput"):
                perf += f" · {v['throughput']} MB/s"
            chips.append(
                f'<div style="display: inline-flex; align-items: center; gap: 8px; background: #1a1a24; '
                f'border: 1px solid #2a2a3a; border-radius: 20px; padding: 4px 14px; margin: 0 8px 8px 0; '
                f'font-family: \'JetBrains Mono\', monospace; font-size: 0.7rem; color: #8b8b9e;">'
                f'💾 {html.escape(v["id"])} · {html.escape(v["device"])} · '
                f'{html.escape(v["type"])} {v["size_gb"]} GB'
                f'{" · " + html.escape(perf) if perf else ""}</div>'
            )
        st.markdown("".join(chips), unsafe_allow_html=True)


def render_rds_section(inst: dict, series: dict[str, list[dict]]) -> None:
    p = f"rds:{inst['id']}"        # series key prefix (see c5_monitor)
    kp = f"c5_{inst['id']}"        # widget key prefix — unique per database
    available = inst["status"] == "available"
    meta = (f"{inst['engine']} {inst['engine_version']} · {inst['instance_class']} · "
            f"{inst['storage_gb']} GB {inst['storage_type']}")
    _resource_header(inst["id"], "🗄️", inst["status"], available, meta)

    if not available:
        st.info(f"⏸️ Database is {inst['status']} — no telemetry is being published. "
                "Charts below show the last data before it went offline.")

    cpu = series.get(f"{p}:cpu", [])
    cpu_max = series.get(f"{p}:cpu_max", [])
    cpu_avg_w, _ = _series_stats(cpu)
    _, cpu_peak_w = _series_stats(cpu_max)

    storage_gb = inst.get("storage_gb") or 0
    free = _latest(series.get(f"{p}:free_storage", []))
    free_pct = (free / (storage_gb * 1024 ** 3) * 100) if (free is not None and storage_gb) else None

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(_metric_card(
            "CPU Now", _fmt_pct(_latest(cpu)),
            f"avg {_fmt_pct(cpu_avg_w, 0)} · peak {_fmt_pct(cpu_peak_w, 0)}",
            "🔥", "orange",
        ), unsafe_allow_html=True)
    with col2:
        st.markdown(_metric_card(
            "Freeable Memory", _human_bytes(_latest(series.get(f"{p}:freeable_memory", []))),
            "● of 2 GB (db.t3.small)" if inst["instance_class"] == "db.t3.small" else "● available RAM",
            "🧠", "blue",
        ), unsafe_allow_html=True)
    with col3:
        st.markdown(_metric_card(
            "Free Storage", _human_bytes(free),
            f"● {free_pct:.0f}% of {storage_gb} GB" if free_pct is not None else "● allocated " + str(storage_gb) + " GB",
            "💽", "green",
            sub_class="negative" if (free_pct is not None and free_pct < 20) else "neutral",
        ), unsafe_allow_html=True)
    with col4:
        conn = _latest(series.get(f"{p}:connections", []))
        st.markdown(_metric_card(
            "Connections", "N/A" if conn is None else f"{conn:.0f}",
            "● active sessions", "🔌", "red",
        ), unsafe_allow_html=True)

    st.markdown("<div style='height: 0.75rem;'></div>", unsafe_allow_html=True)

    # Pressure gauges: CPU credits (t-class) + storage burst bucket
    gauge_cols = st.columns(4)
    with gauge_cols[0]:
        _gauge(f"{kp}_cpu_g", "CPU Load", _latest(cpu))
    with gauge_cols[1]:
        _gauge(f"{kp}_burst", "Storage Burst",
               _latest(series.get(f"{p}:burst_balance", [])), invert=True)
    with gauge_cols[2]:
        credits = _latest(series.get(f"{p}:cpu_credits", []))
        max_credits = c5_monitor.max_cpu_credits(inst.get("instance_class", ""))
        if credits is not None and max_credits:
            _gauge(f"{kp}_credits", "CPU Credits", credits / max_credits * 100,
                   invert=True)
        else:
            _gauge(f"{kp}_credits_na", "CPU Credits", None)
    with gauge_cols[3]:
        queue = _latest(series.get(f"{p}:disk_queue", []))
        st.markdown(_metric_card(
            "Disk Queue", "N/A" if queue is None else f"{queue:.2f}",
            "● warn ≥ 10", "⏳", "red",
            sub_class="negative" if (queue or 0) >= 10 else "neutral",
        ), unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        _ts_chart(f"{kp}_cpu", "CPU Utilization (load)", [
            {"name": "avg", "color": ORANGE, "series": cpu},
            {"name": "max", "color": RED, "series": cpu_max},
        ], unit="%")
    with col2:
        _ts_chart(f"{kp}_conn", "Database Connections", [
            {"name": "connections", "color": BLUE,
             "series": series.get(f"{p}:connections", [])},
        ])

    col1, col2 = st.columns(2)
    with col1:
        _ts_chart(f"{kp}_iops", "Disk IOPS", [
            {"name": "read", "color": GREEN, "series": series.get(f"{p}:read_iops", [])},
            {"name": "write", "color": ORANGE, "series": series.get(f"{p}:write_iops", [])},
        ], unit="ops/s")
    with col2:
        _ts_chart(f"{kp}_tput", "Disk Throughput", [
            {"name": "read", "color": GREEN, "series": series.get(f"{p}:read_throughput", []),
             "scale": 1 / (1024 ** 2)},
            {"name": "write", "color": ORANGE, "series": series.get(f"{p}:write_throughput", []),
             "scale": 1 / (1024 ** 2)},
        ], unit="MB/s")

    col1, col2 = st.columns(2)
    with col1:
        _ts_chart(f"{kp}_latency", "Disk Latency", [
            {"name": "read", "color": GREEN, "series": series.get(f"{p}:read_latency", []),
             "scale": 1000},
            {"name": "write", "color": ORANGE, "series": series.get(f"{p}:write_latency", []),
             "scale": 1000},
        ], unit="ms")
    with col2:
        _ts_chart(f"{kp}_queue_mem", "Disk Queue & Memory", [
            {"name": "queue depth", "color": RED,
             "series": series.get(f"{p}:disk_queue", [])},
            {"name": "free mem (GB)", "color": BLUE,
             "series": series.get(f"{p}:freeable_memory", []),
             "scale": 1 / (1024 ** 3)},
        ])
