"""
AWS Resource Monitoring Portal

A Streamlit-based dashboard for monitoring AWS resources (EC2, RDS)
across multiple regions with health metrics, alerts, and cost tracking.
"""

import streamlit as st

st.set_page_config(
    page_title="AWS Monitor",
    page_icon="🔶",
    layout="wide",
    initial_sidebar_state="expanded",
)

from src.ui.sidebar import render_sidebar
from src.ui.dashboard import render_dashboard
from src.ui.inventory_view import render_ec2_inventory, render_rds_inventory
from src.ui.metrics_view import render_metrics_view
from src.ui.costs_view import render_costs_view
from src.ui.alerts_view import render_alerts_view
from src.services.inventory import get_all_ec2_instances, get_all_rds_instances


# Demo data for when AWS credentials are not available
DEMO_EC2 = [
    {"id": "i-demo001", "name": "web-server-1", "type": "t3.medium", "state": "running", "region": "us-east-1", "private_ip": "10.0.1.10", "public_ip": "54.123.45.67"},
    {"id": "i-demo002", "name": "web-server-2", "type": "t3.medium", "state": "running", "region": "us-east-1", "private_ip": "10.0.1.11", "public_ip": "54.123.45.68"},
    {"id": "i-demo003", "name": "api-server", "type": "t3.large", "state": "running", "region": "us-west-2", "private_ip": "10.0.2.10", "public_ip": ""},
    {"id": "i-demo004", "name": "batch-processor", "type": "c5.xlarge", "state": "stopped", "region": "us-west-2", "private_ip": "10.0.2.20", "public_ip": ""},
    {"id": "i-demo005", "name": "dev-server", "type": "t3.small", "state": "running", "region": "eu-west-1", "private_ip": "10.0.3.10", "public_ip": "52.18.100.50"},
]

DEMO_RDS = [
    {"id": "prod-db", "engine": "mysql", "engine_version": "8.0.35", "status": "available", "instance_class": "db.r5.large", "storage_gb": 100, "multi_az": True, "region": "us-east-1", "endpoint": "prod-db.cluster.us-east-1.rds.amazonaws.com", "port": 3306},
    {"id": "analytics-db", "engine": "postgres", "engine_version": "15.4", "status": "available", "instance_class": "db.r5.xlarge", "storage_gb": 500, "multi_az": True, "region": "us-east-1", "endpoint": "analytics-db.cluster.us-east-1.rds.amazonaws.com", "port": 5432},
    {"id": "dev-db", "engine": "mysql", "engine_version": "8.0.35", "status": "available", "instance_class": "db.t3.medium", "storage_gb": 20, "multi_az": False, "region": "eu-west-1", "endpoint": "dev-db.eu-west-1.rds.amazonaws.com", "port": 3306},
]


@st.cache_data(ttl=60)
def check_aws_credentials() -> bool:
    """Check if AWS credentials are available."""
    import os
    # Quick check: look for credentials file or env vars
    has_env = os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY")
    has_file = os.path.exists(os.path.expanduser("~/.aws/credentials"))

    if not has_env and not has_file:
        return False

    # Verify credentials work
    try:
        import boto3
        from botocore.config import Config
        config = Config(connect_timeout=3, read_timeout=3)
        sts = boto3.client("sts", region_name="us-east-1", config=config)
        sts.get_caller_identity()
        return True
    except Exception:
        return False


def main():
    """Main application entry point."""
    # Render sidebar and get navigation state
    selected_page, selected_regions = render_sidebar()

    # Check if regions are selected
    if not selected_regions:
        st.warning("Please select at least one region from the sidebar to view resources.")
        return

    # Check for demo mode
    demo_mode = not check_aws_credentials()

    if demo_mode:
        st.warning("⚠️ **Demo Mode**: AWS credentials not found. Showing sample data. Configure AWS credentials to see real resources.")
        ec2_instances = [i for i in DEMO_EC2 if i["region"] in selected_regions]
        rds_instances = [i for i in DEMO_RDS if i["region"] in selected_regions]
    else:
        # Fetch inventory data (cached)
        try:
            with st.spinner("Loading EC2 instances..."):
                ec2_instances = get_all_ec2_instances(selected_regions)
        except Exception as e:
            st.error(f"Failed to fetch EC2 instances: {e}")
            ec2_instances = []

        try:
            with st.spinner("Loading RDS instances..."):
                rds_instances = get_all_rds_instances(selected_regions)
        except Exception as e:
            st.error(f"Failed to fetch RDS instances: {e}")
            rds_instances = []

    # Route to selected page
    if selected_page == "Dashboard":
        render_dashboard(ec2_instances, rds_instances, selected_regions)

    elif selected_page == "EC2 Instances":
        render_ec2_inventory(ec2_instances)

    elif selected_page == "RDS Databases":
        render_rds_inventory(rds_instances)

    elif selected_page == "Metrics":
        if demo_mode:
            st.title("📈 CloudWatch Metrics")
            st.info("Metrics are not available in demo mode. Configure AWS credentials to view real metrics.")
        else:
            render_metrics_view(ec2_instances, rds_instances)

    elif selected_page == "Costs":
        if demo_mode:
            st.title("💰 Cost Analysis")
            st.info("Cost data is not available in demo mode. Configure AWS credentials to view real costs.")
        else:
            render_costs_view()

    elif selected_page == "Alerts":
        render_alerts_view(ec2_instances, rds_instances)


if __name__ == "__main__":
    main()
