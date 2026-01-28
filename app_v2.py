"""
AWS Resource Monitoring Portal v2
A beautifully designed dashboard for monitoring AWS resources with billing metrics.
"""

import streamlit as st
import boto3
import pandas as pd
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

from src.ui.rds_health_view import render_rds_health_section, get_health_css

# Page config - must be first
st.set_page_config(
    page_title="AWS Monitor",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for modern dark theme
st.markdown("""
<style>
    /* Import fonts */
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Outfit:wght@300;400;500;600;700&display=swap');

    /* Root variables */
    :root {
        --bg-primary: #0a0a0f;
        --bg-secondary: #12121a;
        --bg-card: #1a1a24;
        --bg-card-hover: #22222e;
        --accent-orange: #ff6b2c;
        --accent-orange-dim: rgba(255, 107, 44, 0.15);
        --accent-green: #00d97e;
        --accent-green-dim: rgba(0, 217, 126, 0.15);
        --accent-red: #ff4757;
        --accent-red-dim: rgba(255, 71, 87, 0.15);
        --accent-blue: #4da3ff;
        --accent-blue-dim: rgba(77, 163, 255, 0.15);
        --accent-purple: #a855f7;
        --text-primary: #ffffff;
        --text-secondary: #8b8b9e;
        --text-muted: #5c5c6e;
        --border-color: #2a2a3a;
    }

    /* Global styles */
    .stApp {
        background: var(--bg-primary);
        font-family: 'Outfit', sans-serif;
    }

    /* Hide default streamlit elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stDeployButton {display: none;}

    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: var(--bg-secondary);
        border-right: 1px solid var(--border-color);
    }

    [data-testid="stSidebar"] .stMarkdown {
        color: var(--text-secondary);
    }

    /* Main content area */
    .main .block-container {
        padding: 2rem 3rem;
        max-width: 100%;
    }

    /* Custom header */
    .dashboard-header {
        display: flex;
        align-items: center;
        gap: 16px;
        margin-bottom: 2rem;
        padding-bottom: 1.5rem;
        border-bottom: 1px solid var(--border-color);
    }

    .dashboard-header h1 {
        font-family: 'Outfit', sans-serif;
        font-weight: 700;
        font-size: 2rem;
        color: var(--text-primary);
        margin: 0;
        letter-spacing: -0.02em;
    }

    .dashboard-header .subtitle {
        color: var(--text-muted);
        font-size: 0.875rem;
        font-weight: 400;
    }

    /* Metric cards */
    .metric-card {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 16px;
        padding: 1.5rem;
        transition: all 0.2s ease;
    }

    .metric-card:hover {
        background: var(--bg-card-hover);
        border-color: var(--accent-orange);
        transform: translateY(-2px);
    }

    .metric-card .label {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.7rem;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: var(--text-muted);
        margin-bottom: 0.5rem;
    }

    .metric-card .value {
        font-family: 'Outfit', sans-serif;
        font-size: 2.25rem;
        font-weight: 700;
        color: var(--text-primary);
        line-height: 1;
        margin-bottom: 0.25rem;
    }

    .metric-card .delta {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.75rem;
        font-weight: 500;
    }

    .metric-card .delta.positive { color: var(--accent-green); }
    .metric-card .delta.negative { color: var(--accent-red); }
    .metric-card .delta.neutral { color: var(--text-muted); }

    /* Icon badges */
    .icon-badge {
        width: 40px;
        height: 40px;
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.25rem;
        margin-bottom: 1rem;
    }

    .icon-badge.orange { background: var(--accent-orange-dim); }
    .icon-badge.green { background: var(--accent-green-dim); }
    .icon-badge.red { background: var(--accent-red-dim); }
    .icon-badge.blue { background: var(--accent-blue-dim); }

    /* Section headers */
    .section-header {
        display: flex;
        align-items: center;
        gap: 12px;
        margin: 2rem 0 1rem 0;
    }

    .section-header h2 {
        font-family: 'Outfit', sans-serif;
        font-weight: 600;
        font-size: 1.25rem;
        color: var(--text-primary);
        margin: 0;
    }

    .section-header .count {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.75rem;
        color: var(--text-muted);
        background: var(--bg-card);
        padding: 4px 10px;
        border-radius: 20px;
        border: 1px solid var(--border-color);
    }

    /* Data tables */
    .stDataFrame {
        border-radius: 12px;
        overflow: hidden;
    }

    [data-testid="stDataFrame"] > div {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 12px;
    }

    /* Status badges */
    .status-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 12px;
        border-radius: 20px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.7rem;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    .status-badge.running {
        background: var(--accent-green-dim);
        color: var(--accent-green);
    }

    .status-badge.stopped {
        background: var(--accent-red-dim);
        color: var(--accent-red);
    }

    .status-badge.available {
        background: var(--accent-green-dim);
        color: var(--accent-green);
    }

    /* Billing card */
    .billing-card {
        background: linear-gradient(135deg, #1a1a24 0%, #12121a 100%);
        border: 1px solid var(--border-color);
        border-radius: 20px;
        padding: 2rem;
        position: relative;
        overflow: hidden;
    }

    .billing-card::before {
        content: '';
        position: absolute;
        top: 0;
        right: 0;
        width: 200px;
        height: 200px;
        background: radial-gradient(circle, var(--accent-orange-dim) 0%, transparent 70%);
        pointer-events: none;
    }

    .billing-card .amount {
        font-family: 'Outfit', sans-serif;
        font-size: 3rem;
        font-weight: 700;
        color: var(--text-primary);
        line-height: 1;
    }

    .billing-card .currency {
        font-size: 1.5rem;
        color: var(--accent-orange);
        margin-right: 4px;
    }

    /* Streamlit overrides */
    .stSelectbox > div > div {
        background: var(--bg-card);
        border-color: var(--border-color);
    }

    .stMultiSelect > div > div {
        background: var(--bg-card);
        border-color: var(--border-color);
    }

    .stButton > button {
        background: var(--accent-orange);
        color: white;
        border: none;
        border-radius: 8px;
        font-family: 'Outfit', sans-serif;
        font-weight: 500;
        padding: 0.5rem 1.5rem;
        transition: all 0.2s ease;
    }

    .stButton > button:hover {
        background: #ff8551;
        transform: translateY(-1px);
    }

    .stSpinner > div {
        border-color: var(--accent-orange);
    }

    /* Radio buttons */
    .stRadio > div {
        gap: 0.5rem;
    }

    .stRadio label {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 8px;
        padding: 0.5rem 1rem;
        transition: all 0.2s ease;
    }

    .stRadio label:hover {
        border-color: var(--accent-orange);
    }

    /* Warning/Info boxes */
    .stAlert {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 12px;
    }

    /* Divider */
    hr {
        border-color: var(--border-color);
        margin: 2rem 0;
    }

    /* Scrollbar */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }

    ::-webkit-scrollbar-track {
        background: var(--bg-secondary);
    }

    ::-webkit-scrollbar-thumb {
        background: var(--border-color);
        border-radius: 4px;
    }

    ::-webkit-scrollbar-thumb:hover {
        background: var(--text-muted);
    }

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
</style>
""", unsafe_allow_html=True)

# Region configurations
COMMON_REGIONS = [
    "ap-southeast-1", "ap-southeast-3", "ap-northeast-1",
    "ap-northeast-2", "ap-south-1", "us-east-1",
    "us-west-2", "eu-west-1", "eu-central-1",
]

@st.cache_data(ttl=3600)
def get_all_regions():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    return sorted([r["RegionName"] for r in ec2.describe_regions()["Regions"]])

def fetch_ec2_for_region(region):
    instances = []
    try:
        ec2 = boto3.client("ec2", region_name=region)
        response = ec2.describe_instances()
        for res in response.get("Reservations", []):
            for inst in res.get("Instances", []):
                name = next((tag["Value"] for tag in inst.get("Tags", []) if tag["Key"] == "Name"), "-")

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
                    "Region": region,
                    "Private IP": inst.get("PrivateIpAddress", "-"),
                    "Public IP": inst.get("PublicIpAddress", "-"),
                })
    except:
        pass
    return instances

def fetch_rds_for_region(region):
    instances = []
    try:
        rds = boto3.client("rds", region_name=region)
        response = rds.describe_db_instances()
        for db in response.get("DBInstances", []):
            instances.append({
                "Identifier": db["DBInstanceIdentifier"],
                "Engine": db.get("Engine", "-"),
                "Version": db.get("EngineVersion", "-"),
                "Status": db.get("DBInstanceStatus", "-"),
                "Class": db.get("DBInstanceClass", "-"),
                "Storage": f"{db.get('AllocatedStorage', 0)} GB",
                "Region": region,
            })
    except:
        pass
    return instances

def fetch_all_parallel(fetch_func, regions):
    all_data = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(fetch_func, r): r for r in regions}
        for future in as_completed(futures):
            all_data.extend(future.result())
    return all_data

@st.cache_data(ttl=300)
def get_ec2_data(regions_key):
    return fetch_all_parallel(fetch_ec2_for_region, list(regions_key))

@st.cache_data(ttl=300)
def get_rds_data(regions_key):
    return fetch_all_parallel(fetch_rds_for_region, list(regions_key))

@st.cache_data(ttl=3600)
def get_billing_data():
    """Fetch billing data from Cost Explorer."""
    try:
        ce = boto3.client("ce", region_name="us-east-1")

        # Get current month dates
        today = datetime.utcnow().date()
        first_of_month = today.replace(day=1)

        # MTD Cost
        mtd_response = ce.get_cost_and_usage(
            TimePeriod={
                "Start": first_of_month.strftime("%Y-%m-%d"),
                "End": today.strftime("%Y-%m-%d"),
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
        try:
            forecast_response = ce.get_cost_forecast(
                TimePeriod={
                    "Start": today.strftime("%Y-%m-%d"),
                    "End": (today.replace(day=1) + timedelta(days=32)).replace(day=1).strftime("%Y-%m-%d"),
                },
                Metric="UNBLENDED_COST",
                Granularity="MONTHLY",
            )
            forecast = float(forecast_response["Total"]["Amount"])
        except:
            forecast = mtd_cost * 1.1  # Estimate if forecast fails

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

    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.markdown("---")

    st.markdown(f"""
    <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; color: #5c5c6e;">
        Last updated<br/>
        <span style="color: #8b8b9e;">{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</span>
    </div>
    """, unsafe_allow_html=True)

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

# Load data
cache_key = tuple(sorted(selected_regions))

with st.spinner(""):
    ec2_data = get_ec2_data(cache_key)
    rds_data = get_rds_data(cache_key)
    billing = get_billing_data()

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
    stopped = len([i for i in ec2_data if i["State"] == "stopped"])
    alert_color = "negative" if stopped > 0 else "positive"
    st.markdown(f"""
    <div class="metric-card">
        <div class="icon-badge red">⚠️</div>
        <div class="label">Alerts</div>
        <div class="value">{stopped}</div>
        <div class="delta {alert_color}">● {stopped} stopped instances</div>
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
        change = billing["mtd_cost"] - (billing["last_month_cost"] * (datetime.now().day / 30))
        change_pct = (change / billing["last_month_cost"] * 100) if billing["last_month_cost"] > 0 else 0
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
        st.markdown(f"""
        <div class="metric-card">
            <div class="label">Forecast</div>
            <div class="value" style="font-size: 1.5rem;">${billing["forecast"]:,.0f}</div>
            <div class="delta neutral">● end of month</div>
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
    st.info("💡 Billing data requires Cost Explorer API access. Enable it in your AWS account to see cost metrics.")

# EC2 Section
st.markdown(f"""
<div class="section-header">
    <h2>🖥️ EC2 Instances</h2>
    <span class="count">{len(ec2_data)} total</span>
</div>
""", unsafe_allow_html=True)

if ec2_data:
    df_ec2 = pd.DataFrame(ec2_data)

    col1, col2 = st.columns(2)
    with col1:
        region_filter = st.multiselect("Filter by Region", sorted(df_ec2["Region"].unique()), key="ec2_region", placeholder="All regions")
    with col2:
        state_filter = st.multiselect("Filter by State", sorted(df_ec2["State"].unique()), key="ec2_state", placeholder="All states")

    if region_filter:
        df_ec2 = df_ec2[df_ec2["Region"].isin(region_filter)]
    if state_filter:
        df_ec2 = df_ec2[df_ec2["State"].isin(state_filter)]

    st.dataframe(
        df_ec2,
        use_container_width=True,
        hide_index=True,
        column_config={
            "State": st.column_config.TextColumn("State", help="Instance state"),
            "Instance ID": st.column_config.TextColumn("Instance ID", width="medium"),
        }
    )
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
    df_rds = pd.DataFrame(rds_data)

    col1, col2 = st.columns(2)
    with col1:
        region_filter = st.multiselect("Filter by Region", sorted(df_rds["Region"].unique()), key="rds_region", placeholder="All regions")
    with col2:
        engine_filter = st.multiselect("Filter by Engine", sorted(df_rds["Engine"].unique()), key="rds_engine", placeholder="All engines")

    if region_filter:
        df_rds = df_rds[df_rds["Region"].isin(region_filter)]
    if engine_filter:
        df_rds = df_rds[df_rds["Engine"].isin(engine_filter)]

    st.dataframe(
        df_rds,
        use_container_width=True,
        hide_index=True,
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

            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

            # Show average daily cost
            avg_daily = sum(d["cost"] for d in billing["rds_daily"]) / len(billing["rds_daily"]) if billing["rds_daily"] else 0
            st.markdown(f"""
            <div style="text-align: center;">
                <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; color: #5c5c6e;">Avg Daily</div>
                <div style="font-family: 'Outfit', sans-serif; font-weight: 600; color: #4da3ff; font-size: 1.1rem;">${avg_daily:,.2f}</div>
            </div>
            """, unsafe_allow_html=True)

# Footer
st.markdown("""
<div style="margin-top: 3rem; padding-top: 1.5rem; border-top: 1px solid var(--border-color); text-align: center;">
    <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; color: #5c5c6e;">
        AWS Monitor • Built with Streamlit & boto3
    </div>
</div>
""", unsafe_allow_html=True)
