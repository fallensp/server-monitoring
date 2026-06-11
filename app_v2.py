"""
AWS Resource Monitoring Portal v2
A beautifully designed dashboard for monitoring AWS resources with billing metrics.
"""

import calendar
import html

import streamlit as st
import boto3
import pandas as pd
import plotly.graph_objects as go
from botocore.exceptions import BotoCoreError, ClientError
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from src.ui.rds_health_view import render_rds_health_section
from src.ui.theme import get_base_css
from src.ui import auth
from src.ui import control_view
from src.ui import nav
from src.services.billing_centers import classify_resource, get_center_label
from src.services.rds_watchdog import get_restart_countdowns, format_remaining

# Page config - must be first
st.set_page_config(
    page_title="AWS Monitor",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for modern dark theme
st.markdown(f"<style>{get_base_css()}</style>", unsafe_allow_html=True)

# Login gate — nothing below runs (or is fetched) until authenticated
# with a role that may open this page
auth.require_login(page="overview")

# Region configurations — the actual infrastructure footprint (all four
# billing centers): Singapore, Jakarta, Tokyo, Hong Kong + us-east-1 (global)
COMMON_REGIONS = [
    "ap-southeast-1", "ap-southeast-3", "ap-northeast-1",
    "ap-east-1", "us-east-1",
]

@st.cache_data(ttl=3600)
def get_all_regions():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    return sorted([r["RegionName"] for r in ec2.describe_regions()["Regions"]])

def fetch_ec2_for_region(region):
    """Fetch EC2 instances in one region. Returns (instances, error)."""
    instances = []
    try:
        # Fresh session per call: boto3's default session is not thread-safe
        ec2 = boto3.session.Session().client("ec2", region_name=region)
        paginator = ec2.get_paginator("describe_instances")
        for page in paginator.paginate():
            for res in page.get("Reservations", []):
                for inst in res.get("Instances", []):
                    tags = {tag["Key"]: tag["Value"] for tag in inst.get("Tags", [])}
                    name = tags.get("Name", "-")
                    project = tags.get("Project") or tags.get("project")

                    # Determine pricing model
                    lifecycle = inst.get("InstanceLifecycle", "")
                    if lifecycle == "spot":
                        pricing = "Spot"
                    elif lifecycle == "scheduled":
                        pricing = "Scheduled"
                    else:
                        pricing = "On-Demand"

                    instances.append({
                        "Name": name,
                        "Instance ID": inst["InstanceId"],
                        "Type": inst.get("InstanceType", "-"),
                        "Pricing": pricing,
                        "State": inst["State"]["Name"],
                        "Billing Center": get_center_label(classify_resource(region, project)),
                        "Region": region,
                        "Private IP": inst.get("PrivateIpAddress", "-"),
                        "Public IP": inst.get("PublicIpAddress", "-"),
                    })
    except (ClientError, BotoCoreError) as e:
        return instances, str(e)
    return instances, None

def fetch_rds_for_region(region):
    """Fetch RDS instances in one region. Returns (instances, error)."""
    instances = []
    try:
        rds = boto3.session.Session().client("rds", region_name=region)
        paginator = rds.get_paginator("describe_db_instances")
        for page in paginator.paginate():
            for db in page.get("DBInstances", []):
                instances.append({
                    "Identifier": db["DBInstanceIdentifier"],
                    "Engine": db.get("Engine", "-"),
                    "Version": db.get("EngineVersion", "-"),
                    "Status": db.get("DBInstanceStatus", "-"),
                    "Class": db.get("DBInstanceClass", "-"),
                    "Storage": f"{db.get('AllocatedStorage', 0)} GB",
                    "Billing Center": get_center_label(classify_resource(region, None)),
                    "Region": region,
                    "Endpoint": db.get("Endpoint", {}).get("Address", ""),
                    "Port": db.get("Endpoint", {}).get("Port", ""),
                })
    except (ClientError, BotoCoreError) as e:
        return instances, str(e)
    return instances, None

def fetch_all_parallel(fetch_func, regions):
    """Run a per-region fetch in parallel; collect items and per-region errors."""
    items, errors = [], {}
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(fetch_func, r): r for r in regions}
        for future in as_completed(futures):
            region = futures[future]
            data, error = future.result()
            items.extend(data)
            if error:
                errors[region] = error
    return {
        "items": items,
        "errors": errors,
        "fetched_at": datetime.now(timezone.utc),
    }

@st.cache_data(ttl=300)
def get_ec2_data(regions_key):
    return fetch_all_parallel(fetch_ec2_for_region, list(regions_key))

@st.cache_data(ttl=300)
def get_rds_data(regions_key):
    return fetch_all_parallel(fetch_rds_for_region, list(regions_key))

@st.cache_data(ttl=900)
def get_rds_restart_countdowns(rds_key):
    """Cached auto-restart countdowns for stopped RDS instances.

    Args:
        rds_key: Tuple of (identifier, region, status) tuples (hashable cache key)
    """
    instances = [
        {"Identifier": db_id, "Region": region, "Status": status}
        for (db_id, region, status) in rds_key
    ]
    return get_restart_countdowns(instances)

@st.cache_data(ttl=300)
def get_billing_data():
    """Fetch billing data from Cost Explorer."""
    try:
        ce = boto3.client("ce", region_name="us-east-1")

        # Get current month dates. End is exclusive, so use tomorrow: this
        # includes today's partial spend and avoids Start == End on the 1st
        # of the month (which Cost Explorer rejects).
        today = datetime.now(timezone.utc).date()
        first_of_month = today.replace(day=1)
        mtd_end = today + timedelta(days=1)

        # MTD Cost
        mtd_response = ce.get_cost_and_usage(
            TimePeriod={
                "Start": first_of_month.strftime("%Y-%m-%d"),
                "End": mtd_end.strftime("%Y-%m-%d"),
            },
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
        )
        mtd_cost = float(mtd_response["ResultsByTime"][0]["Total"]["UnblendedCost"]["Amount"]) if mtd_response["ResultsByTime"] else 0

        # Last month cost for comparison
        last_month_end = first_of_month - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)

        last_month_response = ce.get_cost_and_usage(
            TimePeriod={
                "Start": last_month_start.strftime("%Y-%m-%d"),
                "End": (last_month_end + timedelta(days=1)).strftime("%Y-%m-%d"),
            },
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
        )
        last_month_cost = float(last_month_response["ResultsByTime"][0]["Total"]["UnblendedCost"]["Amount"]) if last_month_response["ResultsByTime"] else 0

        # Forecast
        forecast_estimated = False
        if mtd_end.month != today.month:
            # Last day of the month: MTD already covers the whole month and
            # a forecast call would have Start == End (ValidationException)
            forecast = mtd_cost
        else:
            try:
                forecast_response = ce.get_cost_forecast(
                    TimePeriod={
                        "Start": mtd_end.strftime("%Y-%m-%d"),
                        "End": (today.replace(day=1) + timedelta(days=32)).replace(day=1).strftime("%Y-%m-%d"),
                    },
                    Metric="UNBLENDED_COST",
                    Granularity="MONTHLY",
                )
                # Forecast covers the remaining days only — add MTD for month total
                forecast = mtd_cost + float(forecast_response["Total"]["Amount"])
            except (ClientError, BotoCoreError, KeyError, ValueError):
                # Linear extrapolation when the forecast API has no data/permission
                days_in_month = calendar.monthrange(today.year, today.month)[1]
                forecast = (mtd_cost / today.day) * days_in_month if today.day > 0 else mtd_cost
                forecast_estimated = True

        # Cost by service (top 5)
        service_response = ce.get_cost_and_usage(
            TimePeriod={
                "Start": first_of_month.strftime("%Y-%m-%d"),
                "End": today.strftime("%Y-%m-%d"),
            },
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )

        services = []
        if service_response["ResultsByTime"]:
            for group in service_response["ResultsByTime"][0].get("Groups", []):
                services.append({
                    "service": group["Keys"][0],
                    "cost": float(group["Metrics"]["UnblendedCost"]["Amount"]),
                })
        services.sort(key=lambda x: x["cost"], reverse=True)

        # Cost by region
        region_response = ce.get_cost_and_usage(
            TimePeriod={
                "Start": first_of_month.strftime("%Y-%m-%d"),
                "End": today.strftime("%Y-%m-%d"),
            },
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "REGION"}],
        )

        regions_cost = []
        if region_response["ResultsByTime"]:
            for group in region_response["ResultsByTime"][0].get("Groups", []):
                region_name = group["Keys"][0]
                cost = float(group["Metrics"]["UnblendedCost"]["Amount"])
                if cost > 0.01:  # Filter out negligible costs
                    regions_cost.append({
                        "region": region_name if region_name else "Global",
                        "cost": cost,
                    })
        regions_cost.sort(key=lambda x: x["cost"], reverse=True)

        # RDS costs breakdown
        rds_response = ce.get_cost_and_usage(
            TimePeriod={
                "Start": first_of_month.strftime("%Y-%m-%d"),
                "End": today.strftime("%Y-%m-%d"),
            },
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            Filter={
                "Dimensions": {
                    "Key": "SERVICE",
                    "Values": ["Amazon Relational Database Service"]
                }
            },
            GroupBy=[{"Type": "DIMENSION", "Key": "USAGE_TYPE"}],
        )

        rds_costs = []
        rds_total = 0
        if rds_response["ResultsByTime"]:
            for group in rds_response["ResultsByTime"][0].get("Groups", []):
                usage_type = group["Keys"][0]
                cost = float(group["Metrics"]["UnblendedCost"]["Amount"])
                if cost > 0.01:
                    rds_costs.append({
                        "usage_type": usage_type,
                        "cost": cost,
                    })
                    rds_total += cost
        rds_costs.sort(key=lambda x: x["cost"], reverse=True)

        # RDS daily trend (last 14 days)
        rds_daily_response = ce.get_cost_and_usage(
            TimePeriod={
                "Start": (today - timedelta(days=14)).strftime("%Y-%m-%d"),
                "End": today.strftime("%Y-%m-%d"),
            },
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
            Filter={
                "Dimensions": {
                    "Key": "SERVICE",
                    "Values": ["Amazon Relational Database Service"]
                }
            },
        )

        rds_daily = []
        if rds_daily_response["ResultsByTime"]:
            for day in rds_daily_response["ResultsByTime"]:
                rds_daily.append({
                    "date": day["TimePeriod"]["Start"],
                    "cost": float(day["Total"]["UnblendedCost"]["Amount"]),
                })

        return {
            "mtd_cost": mtd_cost,
            "last_month_cost": last_month_cost,
            "forecast": forecast,
            "forecast_estimated": forecast_estimated,
            "top_services": services[:5],
            "regions_cost": regions_cost,
            "rds_costs": rds_costs[:10],
            "rds_total": rds_total,
            "rds_daily": rds_daily,
            "available": True,
        }
    except Exception as e:
        return {
            "mtd_cost": 0,
            "last_month_cost": 0,
            "forecast": 0,
            "forecast_estimated": True,
            "top_services": [],
            "regions_cost": [],
            "rds_costs": [],
            "rds_total": 0,
            "rds_daily": [],
            "available": False,
            "error": str(e),
        }

# Sidebar
with st.sidebar:
    st.markdown("""
    <div style="padding: 1rem 0;">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 1.5rem;">
            <div style="width: 40px; height: 40px; background: linear-gradient(135deg, #ff6b2c, #ff8551); border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 1.25rem;">⚡</div>
            <div>
                <div style="font-family: 'Outfit', sans-serif; font-weight: 700; font-size: 1.25rem; color: #fff;">AWS Monitor</div>
                <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; color: #5c5c6e; text-transform: uppercase; letter-spacing: 0.1em;">Resource Dashboard</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Logout first: it must render before the Operate toggle so it can
    # safely disarm ops controls on logout
    auth.render_logout()

    st.markdown("---")

    nav.render_nav(auth.allowed_pages())

    st.markdown("---")

    all_regions = get_all_regions()

    st.markdown("##### Region Selection")
    mode = st.radio(
        "Mode",
        ["Common Regions", "All Regions", "Custom"],
        index=0,
        label_visibility="collapsed",
    )

    if mode == "Common Regions":
        selected_regions = COMMON_REGIONS
    elif mode == "All Regions":
        selected_regions = all_regions
    else:
        selected_regions = st.multiselect(
            "Select regions",
            all_regions,
            default=["ap-southeast-1", "ap-southeast-3", "ap-northeast-1"],
            label_visibility="collapsed",
        )

    st.markdown(f"""
    <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: #5c5c6e; margin-top: 0.5rem;">
        {len(selected_regions)} region(s) selected
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    st.markdown("##### Server Control")
    ops_armed = control_view.render_mode_toggle()

    st.markdown("---")

    if st.button("🔄 Refresh inventory", width="stretch",
                 help="Re-fetch EC2/RDS state. Billing cache is kept (Cost Explorer charges per call)."):
        get_ec2_data.clear()
        get_rds_data.clear()
        st.rerun()

    if st.button("💵 Refresh billing", width="stretch",
                 help="Re-query Cost Explorer (~$0.07 in API charges; data lags up to 24h)."):
        get_billing_data.clear()
        st.rerun()

# Main content
st.markdown("""
<div class="dashboard-header">
    <div>
        <h1>Resource Overview</h1>
        <div class="subtitle">Real-time AWS infrastructure monitoring</div>
    </div>
</div>
""", unsafe_allow_html=True)

if not selected_regions:
    st.warning("Please select at least one region to monitor.")
    st.stop()

# Operate-mode banner
if ops_armed:
    control_view.render_armed_banner()

# Live transition tracker for in-flight start/stop/reboot actions
control_view.render_pending_ops(get_ec2_data.clear, get_rds_data.clear)

# Load data
cache_key = tuple(sorted(selected_regions))

with st.spinner(""):
    ec2_payload = get_ec2_data(cache_key)
    rds_payload = get_rds_data(cache_key)
    billing = get_billing_data()

ec2_data = ec2_payload["items"]
rds_data = rds_payload["items"]

# Surface per-region fetch failures — a silent failure would make resources
# vanish, which on an ops dashboard reads as "terminated"
fetch_errors = {**ec2_payload["errors"], **rds_payload["errors"]}
if fetch_errors:
    failed = ", ".join(f"`{r}`" for r in sorted(fetch_errors))
    with st.container():
        st.warning(f"⚠️ Fetch failed for some regions — resources there may be missing or incomplete: {failed}")
        with st.expander("Error details"):
            for r, err in sorted(fetch_errors.items()):
                st.code(f"{r}: {err}", language="text")

# Data freshness (cached up to 5 min — show actual fetch time, not render time)
data_age_s = int((datetime.now(timezone.utc) - ec2_payload["fetched_at"]).total_seconds())
st.markdown(f"""
<div style="font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; color: #5c5c6e; margin-bottom: 0.75rem;">
    Inventory fetched {data_age_s}s ago · {ec2_payload["fetched_at"].strftime("%H:%M:%S")} UTC
</div>
""", unsafe_allow_html=True)

# Metrics row
col1, col2, col3, col4 = st.columns(4)

with col1:
    running = len([i for i in ec2_data if i["State"] == "running"])
    st.markdown(f"""
    <div class="metric-card">
        <div class="icon-badge orange">🖥️</div>
        <div class="label">EC2 Instances</div>
        <div class="value">{len(ec2_data)}</div>
        <div class="delta positive">● {running} running</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    available_rds = len([i for i in rds_data if i["Status"] == "available"])
    st.markdown(f"""
    <div class="metric-card">
        <div class="icon-badge blue">🗄️</div>
        <div class="label">RDS Databases</div>
        <div class="value">{len(rds_data)}</div>
        <div class="delta positive">● {available_rds} available</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="icon-badge green">🌍</div>
        <div class="label">Regions</div>
        <div class="value">{len(selected_regions)}</div>
        <div class="delta neutral">● monitoring</div>
    </div>
    """, unsafe_allow_html=True)

with col4:
    stopped_ec2 = len([i for i in ec2_data if i["State"] == "stopped"])
    rds_attention = len([i for i in rds_data if i["Status"] != "available"])
    attention = stopped_ec2 + rds_attention
    alert_color = "negative" if attention > 0 else "positive"
    st.markdown(f"""
    <div class="metric-card">
        <div class="icon-badge red">⚠️</div>
        <div class="label">Needs Attention</div>
        <div class="value">{attention}</div>
        <div class="delta {alert_color}">● {stopped_ec2} EC2 stopped · {rds_attention} RDS offline</div>
    </div>
    """, unsafe_allow_html=True)

# Billing section
st.markdown("""
<div class="section-header">
    <h2>💰 Billing Overview</h2>
</div>
""", unsafe_allow_html=True)

if billing["available"]:
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        # Compare MTD against last month's spend prorated to the same day
        # count, using the actual length of last month (not a flat 30)
        today_utc = datetime.now(timezone.utc).date()
        last_month_anchor = today_utc.replace(day=1) - timedelta(days=1)
        days_in_last_month = calendar.monthrange(last_month_anchor.year, last_month_anchor.month)[1]
        pace = billing["last_month_cost"] * (today_utc.day / days_in_last_month)
        change = billing["mtd_cost"] - pace
        change_pct = (change / pace * 100) if pace > 0 else 0
        change_class = "negative" if change > 0 else "positive"

        st.markdown(f"""
        <div class="billing-card">
            <div class="label" style="color: #5c5c6e; margin-bottom: 0.5rem;">Month-to-Date Cost</div>
            <div class="amount"><span class="currency">$</span>{billing["mtd_cost"]:,.2f}</div>
            <div style="margin-top: 1rem; font-family: 'JetBrains Mono', monospace; font-size: 0.75rem;">
                <span class="delta {change_class}">{'+' if change > 0 else ''}{change_pct:.1f}% vs last month pace</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        forecast_note = "● end of month (est.)" if billing.get("forecast_estimated") else "● end of month"
        st.markdown(f"""
        <div class="metric-card">
            <div class="label">Forecast</div>
            <div class="value" style="font-size: 1.5rem;">${billing["forecast"]:,.0f}</div>
            <div class="delta neutral">{forecast_note}</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="label">Last Month</div>
            <div class="value" style="font-size: 1.5rem;">${billing["last_month_cost"]:,.0f}</div>
            <div class="delta neutral">● total</div>
        </div>
        """, unsafe_allow_html=True)

    # Top services
    if billing["top_services"]:
        st.markdown("""
        <div style="margin-top: 1rem; font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: #5c5c6e; text-transform: uppercase; letter-spacing: 0.1em;">Top Services</div>
        """, unsafe_allow_html=True)

        cols = st.columns(len(billing["top_services"]))
        for i, svc in enumerate(billing["top_services"]):
            with cols[i]:
                short_name = svc["service"].replace("Amazon ", "").replace("AWS ", "")[:15]
                st.markdown(f"""
                <div style="background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 8px; padding: 0.75rem; text-align: center;">
                    <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; color: #5c5c6e; margin-bottom: 0.25rem;">{short_name}</div>
                    <div style="font-family: 'Outfit', sans-serif; font-weight: 600; color: #fff;">${svc["cost"]:,.2f}</div>
                </div>
                """, unsafe_allow_html=True)

    # Cost by region
    if billing.get("regions_cost"):
        st.markdown("""
        <div style="margin-top: 1.5rem; font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: #5c5c6e; text-transform: uppercase; letter-spacing: 0.1em;">Cost by Region</div>
        """, unsafe_allow_html=True)

        # Calculate max cost for percentage bar
        max_cost = max(r["cost"] for r in billing["regions_cost"]) if billing["regions_cost"] else 1

        # Display regions as individual rows
        for r in billing["regions_cost"]:
            pct = (r["cost"] / max_cost) * 100 if max_cost > 0 else 0
            region_display = r["region"] if r["region"] != "global" else "Global (No Region)"
            st.markdown(f"""
            <div style="display: flex; align-items: center; gap: 12px; padding: 0.6rem 0; border-bottom: 1px solid #2a2a3a;">
                <div style="width: 140px; font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: #8b8b9e;">{region_display}</div>
                <div style="flex: 1; height: 8px; background: #12121a; border-radius: 4px; overflow: hidden;">
                    <div style="width: {pct:.1f}%; height: 100%; background: linear-gradient(90deg, #ff6b2c, #ff8551); border-radius: 4px;"></div>
                </div>
                <div style="width: 80px; text-align: right; font-family: 'Outfit', sans-serif; font-weight: 600; color: #fff;">${r["cost"]:,.2f}</div>
            </div>
            """, unsafe_allow_html=True)
else:
    error_msg = billing.get("error", "Unknown error")
    if "AccessDenied" in error_msg or "not authorized" in error_msg.lower():
        st.warning(f"⚠️ IAM permission error: The EC2 instance role needs `ce:GetCostAndUsage` permission. Error: {error_msg}")
    elif error_msg:
        st.info(f"💡 Billing data unavailable: {error_msg}")
    else:
        st.info("💡 Billing data requires Cost Explorer API access. Enable it in your AWS account to see cost metrics.")

# EC2 Section
st.markdown(f"""
<div class="section-header">
    <h2>🖥️ EC2 Instances</h2>
    <span class="count">{len(ec2_data)} total</span>
</div>
""", unsafe_allow_html=True)

if ec2_data:
    # Deterministic order: rows come back in region-completion order, which
    # varies per fetch — a persisted positional selection must stay stable
    df_ec2 = pd.DataFrame(ec2_data).sort_values(
        ["Region", "Name", "Instance ID"]).reset_index(drop=True)
    df_ec2["StateRaw"] = df_ec2["State"]
    state_emoji = {"running": "🟢", "stopped": "🔴", "terminated": "⚫"}
    df_ec2["State"] = df_ec2["StateRaw"].map(lambda s: f"{state_emoji.get(s, '🟡')} {s}")

    col1, col2, col3 = st.columns(3)
    with col1:
        region_filter = st.multiselect("Filter by Region", sorted(df_ec2["Region"].unique()), key="ec2_region", placeholder="All regions")
    with col2:
        state_filter = st.multiselect("Filter by State", sorted(df_ec2["StateRaw"].unique()), key="ec2_state", placeholder="All states")
    with col3:
        bc_filter = st.multiselect("Filter by Billing Center", sorted(df_ec2["Billing Center"].unique()), key="ec2_bc", placeholder="All centers")

    if region_filter:
        df_ec2 = df_ec2[df_ec2["Region"].isin(region_filter)]
    if state_filter:
        df_ec2 = df_ec2[df_ec2["StateRaw"].isin(state_filter)]
    if bc_filter:
        df_ec2 = df_ec2[df_ec2["Billing Center"].isin(bc_filter)]

    ec2_event = st.dataframe(
        df_ec2,
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="ec2_table",
        column_config={
            "State": st.column_config.TextColumn("State", help="Instance state"),
            "Instance ID": st.column_config.TextColumn("Instance ID", width="medium"),
            "StateRaw": None,  # hidden — used by the action bar
        }
    )

    # Server control: action bar for the selected row (bounds-checked —
    # a persisted selection can outlive a shrinking filter result)
    selected_rows = ec2_event.selection.rows
    if selected_rows and selected_rows[0] < len(df_ec2):
        control_view.render_ec2_action_bar(df_ec2.iloc[selected_rows[0]].to_dict(), ops_armed)
    else:
        st.caption("Select a row to start / stop / reboot / connect.")
else:
    st.info("No EC2 instances found in the selected regions.")

# RDS Section
st.markdown(f"""
<div class="section-header">
    <h2>🗄️ RDS Databases</h2>
    <span class="count">{len(rds_data)} total</span>
</div>
""", unsafe_allow_html=True)

if rds_data:
    df_rds = pd.DataFrame(rds_data).sort_values(
        ["Region", "Identifier"]).reset_index(drop=True)
    df_rds["StatusRaw"] = df_rds["Status"]
    status_emoji = {"available": "🟢", "stopped": "🔴"}
    df_rds["Status"] = df_rds["StatusRaw"].map(lambda s: f"{status_emoji.get(s, '🟡')} {s}")

    col1, col2 = st.columns(2)
    with col1:
        region_filter = st.multiselect("Filter by Region", sorted(df_rds["Region"].unique()), key="rds_region", placeholder="All regions")
    with col2:
        engine_filter = st.multiselect("Filter by Engine", sorted(df_rds["Engine"].unique()), key="rds_engine", placeholder="All engines")

    if region_filter:
        df_rds = df_rds[df_rds["Region"].isin(region_filter)]
    if engine_filter:
        df_rds = df_rds[df_rds["Engine"].isin(engine_filter)]

    rds_event = st.dataframe(
        df_rds,
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="rds_table",
        column_config={
            "StatusRaw": None,  # hidden — used by the action bar
            "Endpoint": None,   # hidden — shown in the Connect popover
            "Port": None,
        },
    )

    # Server control: action bar for the selected row (bounds-checked)
    selected_rds = rds_event.selection.rows
    if selected_rds and selected_rds[0] < len(df_rds):
        control_view.render_rds_action_bar(df_rds.iloc[selected_rds[0]].to_dict(), ops_armed)
    else:
        st.caption("Select a row to start / stop / reboot or view the endpoint.")

    # 7-day auto-restart watchdog: AWS silently restarts stopped RDS
    # instances after 7 days and they resume billing
    countdowns = get_rds_restart_countdowns(tuple(
        (i["Identifier"], i["Region"], i["Status"]) for i in rds_data
    ))
    # Recompute remaining at render time — the cached value can be 15 min stale
    now_utc = datetime.now(timezone.utc)
    for c in countdowns:
        c["remaining"] = (c["restart_eta"] - now_utc) if c["restart_eta"] else None
    if countdowns:
        urgent = [c for c in countdowns if c["remaining"] is not None and c["remaining"].total_seconds() < 48 * 3600]
        if urgent:
            names = ", ".join(f"**{c['db_id']}**" for c in urgent)
            st.error(f"⏰ {names}: AWS will auto-restart within 48h — compute billing resumes unless stopped again.", icon="🚨")
        chips = []
        for c in countdowns:
            secs = c["remaining"].total_seconds() if c["remaining"] is not None else None
            color = "#ff4757" if secs is not None and secs < 48 * 3600 else "#ffb347"
            eta_txt = c["restart_eta"].strftime("%b %d %H:%M UTC") if c["restart_eta"] else "unknown"
            chips.append(
                f'<div style="display: inline-flex; align-items: center; gap: 8px; background: {color}1f; '
                f'border: 1px solid {color}66; border-radius: 20px; padding: 4px 14px; margin: 0 8px 8px 0; '
                f'font-family: \'JetBrains Mono\', monospace; font-size: 0.72rem; color: {color};">'
                f'⏰ {html.escape(c["db_id"])} auto-restarts in {format_remaining(c["remaining"])} · {eta_txt}</div>'
            )
        st.markdown(
            '<div style="margin-top: 0.25rem;">'
            '<span style="font-family: \'JetBrains Mono\', monospace; font-size: 0.65rem; color: #5c5c6e; '
            'text-transform: uppercase; letter-spacing: 0.1em;">Stopped RDS — AWS auto-restart watchdog</span><br/>'
            + "".join(chips) + "</div>",
            unsafe_allow_html=True,
        )
else:
    st.info("No RDS instances found in the selected regions.")

# RDS Health Monitoring Section
st.markdown("""
<div class="section-header">
    <h2>💚 Database Health</h2>
    <span class="count">Real-time</span>
</div>
""", unsafe_allow_html=True)

if rds_data:
    render_rds_health_section(rds_data)
else:
    st.info("No RDS instances found to monitor health.")

# RDS Cost Drill-down Section
if billing["available"] and billing.get("rds_costs"):
    st.markdown(f"""
    <div class="section-header">
        <h2>💵 RDS Cost Breakdown</h2>
        <span class="count">${billing.get('rds_total', 0):,.2f} MTD</span>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([2, 1])

    with col1:
        # RDS cost by usage type
        st.markdown("""
        <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: #5c5c6e; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 0.5rem;">Cost by Usage Type</div>
        """, unsafe_allow_html=True)

        max_rds_cost = max(r["cost"] for r in billing["rds_costs"]) if billing["rds_costs"] else 1

        for r in billing["rds_costs"]:
            pct = (r["cost"] / max_rds_cost) * 100 if max_rds_cost > 0 else 0
            # Parse usage type to make it more readable
            usage_display = r["usage_type"].split(":")[-1] if ":" in r["usage_type"] else r["usage_type"]
            usage_display = usage_display[:40] + "..." if len(usage_display) > 40 else usage_display

            st.markdown(f"""
            <div style="display: flex; align-items: center; gap: 12px; padding: 0.5rem 0; border-bottom: 1px solid #2a2a3a;">
                <div style="width: 200px; font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: #8b8b9e; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="{r['usage_type']}">{usage_display}</div>
                <div style="flex: 1; height: 6px; background: #12121a; border-radius: 3px; overflow: hidden;">
                    <div style="width: {pct:.1f}%; height: 100%; background: linear-gradient(90deg, #4da3ff, #7bb8ff); border-radius: 3px;"></div>
                </div>
                <div style="width: 70px; text-align: right; font-family: 'Outfit', sans-serif; font-weight: 600; color: #fff; font-size: 0.85rem;">${r["cost"]:,.2f}</div>
            </div>
            """, unsafe_allow_html=True)

    with col2:
        # RDS daily trend chart
        if billing.get("rds_daily"):
            st.markdown("""
            <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: #5c5c6e; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 0.5rem;">Daily Trend (14 days)</div>
            """, unsafe_allow_html=True)

            # Create Plotly bar chart
            dates = [d["date"][5:] for d in billing["rds_daily"]]  # MM-DD format
            costs = [d["cost"] for d in billing["rds_daily"]]

            fig = go.Figure(data=[
                go.Bar(
                    x=dates,
                    y=costs,
                    marker=dict(
                        color=costs,
                        colorscale=[[0, '#2d7dd2'], [1, '#4da3ff']],
                    ),
                    hovertemplate='%{x}<br>$%{y:.2f}<extra></extra>'
                )
            ])

            fig.update_layout(
                height=150,
                margin=dict(l=0, r=0, t=10, b=20),
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
                    tickprefix='$',
                ),
                bargap=0.3,
            )

            st.plotly_chart(fig, width="stretch", config={'displayModeBar': False})

            # Show average daily cost
            avg_daily = sum(d["cost"] for d in billing["rds_daily"]) / len(billing["rds_daily"]) if billing["rds_daily"] else 0
            st.markdown(f"""
            <div style="text-align: center;">
                <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; color: #5c5c6e;">Avg Daily</div>
                <div style="font-family: 'Outfit', sans-serif; font-weight: 600; color: #4da3ff; font-size: 1.1rem;">${avg_daily:,.2f}</div>
            </div>
            """, unsafe_allow_html=True)

# Audit trail of control actions taken from this dashboard
st.markdown("""
<div class="section-header">
    <h2>🧾 Audit</h2>
</div>
""", unsafe_allow_html=True)
control_view.render_audit_log()

# Footer
st.markdown("""
<div style="margin-top: 3rem; padding-top: 1.5rem; border-top: 1px solid var(--border-color); text-align: center;">
    <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; color: #5c5c6e;">
        AWS Monitor • Built with Streamlit & boto3
    </div>
</div>
""", unsafe_allow_html=True)
