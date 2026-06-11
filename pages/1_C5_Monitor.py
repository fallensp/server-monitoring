"""C5 stack monitor — vital stats, EBS usage & pressure, and load for the
c5 resources (Project=titantech) in Singapore: c5-winlose-job EC2 and
c5-sqlserver RDS, discovered live by name prefix."""

import streamlit as st

# Page config - must be the first Streamlit call
st.set_page_config(
    page_title="C5 Monitor",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

from datetime import datetime, timezone

from src.ui.theme import get_base_css
from src.ui import auth
from src.ui import c5_view
from src.ui import nav
from src.services import c5_monitor

st.markdown(f"<style>{get_base_css()}</style>", unsafe_allow_html=True)

# Login gate — nothing below runs (or is fetched) until authenticated
# with a role that may open this page
auth.require_login(page="c5")

TIME_RANGES = {
    "1 hour": 1,
    "6 hours": 6,
    "24 hours": 24,
    "3 days": 72,
    "7 days": 168,
}

# Sidebar
with st.sidebar:
    st.markdown("""
    <div style="padding: 1rem 0;">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 1.5rem;">
            <div style="width: 40px; height: 40px; background: linear-gradient(135deg, #ff6b2c, #ff8551); border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 1.25rem;">⚡</div>
            <div>
                <div style="font-family: 'Outfit', sans-serif; font-weight: 700; font-size: 1.25rem; color: #fff;">AWS Monitor</div>
                <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; color: #5c5c6e; text-transform: uppercase; letter-spacing: 0.1em;">C5 Stack Monitor</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    auth.render_logout()

    st.markdown("---")

    nav.render_nav(auth.allowed_pages())

    st.markdown("---")

    st.markdown("##### Time Range")
    range_label = st.radio(
        "Time range",
        list(TIME_RANGES),
        index=2,
        label_visibility="collapsed",
    )
    hours = TIME_RANGES[range_label]

    st.markdown("---")

    if st.button("🔄 Refresh metrics", width="stretch",
                 help="Re-discover c5 resources and re-fetch CloudWatch metrics."):
        c5_view.fetch_inventory.clear()
        c5_view.fetch_metrics.clear()
        st.rerun()

# Header
st.markdown(f"""
<div class="dashboard-header">
    <div>
        <h1>🎯 C5 Stack Monitor</h1>
        <div class="subtitle">Vitals, EBS usage &amp; pressure, and load ·
        {c5_monitor.C5_REGION} · resources named {c5_monitor.C5_NAME_PREFIX}*</div>
    </div>
</div>
""", unsafe_allow_html=True)

# Discover resources. Errors are caught HERE, not inside the cached
# fetcher — st.cache_data would pin a cached error dict for the whole TTL,
# whereas a raised exception is never cached and retries on the next rerun.
try:
    with st.spinner(""):
        inventory = c5_view.fetch_inventory()
except Exception as e:
    st.error(f"⚠️ Failed to discover c5 resources in {c5_monitor.C5_REGION}: {e}")
    st.stop()

ec2_list = inventory["ec2"]
rds_list = inventory["rds"]
volumes_map = inventory["volumes"]

if not ec2_list and not rds_list:
    st.warning(f"No resources named `{c5_monitor.C5_NAME_PREFIX}*` found in "
               f"{c5_monitor.C5_REGION}.")
    st.stop()

# One batched CloudWatch call for every series on the page
ec2_key = tuple((i["id"], i["type"]) for i in ec2_list)
vol_key = tuple(v["id"] for vols in volumes_map.values() for v in vols)
rds_key = tuple((d["id"], d["instance_class"]) for d in rds_list)

# A metrics failure must NOT render as "all healthy": GetMetricData is
# all-or-nothing, so a swallowed error would blank every series and the
# alert strip would show green. Surface it and stop instead.
try:
    with st.spinner(""):
        series = c5_view.fetch_metrics(ec2_key, vol_key, rds_key, hours)
except Exception as e:
    st.error(f"⚠️ CloudWatch metrics fetch failed — health state is UNKNOWN, "
             f"not healthy: {e}")
    st.stop()

# Data freshness — most recent datapoint across all series
all_timestamps = [pt["timestamp"] for s in series.values() for pt in s[-1:]]
if all_timestamps:
    newest = max(all_timestamps)
    age_min = int((datetime.now(timezone.utc) - newest).total_seconds() // 60)
    st.markdown(f"""
    <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; color: #5c5c6e; margin-bottom: 0.75rem;">
        Window: {range_label} · latest datapoint {age_min} min ago · {newest.strftime("%H:%M UTC")}
    </div>
    """, unsafe_allow_html=True)

# Alert strip — every threshold breach across the stack, worst first.
# Offline resources are excluded: their "latest" datapoints are from
# before shutdown (e.g. a CPU spike during the stop) and would render
# stale values as current breaches.
alerts = []
for inst in ec2_list:
    if inst["state"] == "running":
        alerts += c5_monitor.collect_alerts(series, inst, None, volumes_map.get(inst["id"], []))
for db in rds_list:
    if db["status"] == "available":
        alerts += c5_monitor.collect_alerts(series, None, db, [])
alerts.sort(key=lambda a: 0 if a["status"].value == "critical" else 1)
offline = ([i["name"] for i in ec2_list if i["state"] != "running"]
           + [d["id"] for d in rds_list if d["status"] != "available"])
c5_view.render_alert_strip(alerts, offline)

# EC2 sections
for inst in ec2_list:
    c5_view.render_ec2_section(inst, volumes_map.get(inst["id"], []), series)

if not ec2_list:
    st.info("No c5 EC2 instances found.")

# RDS sections
for db in rds_list:
    c5_view.render_rds_section(db, series)

if not rds_list:
    st.info("No c5 RDS instances found.")

# Footer
st.markdown("""
<div style="margin-top: 3rem; padding-top: 1.5rem; border-top: 1px solid var(--border-color); text-align: center;">
    <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; color: #5c5c6e;">
        AWS Monitor · C5 Stack · CloudWatch metrics via GetMetricData
    </div>
</div>
""", unsafe_allow_html=True)
