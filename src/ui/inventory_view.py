"""Inventory views for EC2 and RDS tables."""

import streamlit as st
import pandas as pd


def render_ec2_inventory(instances: list[dict]):
    """Render EC2 instances table.

    Args:
        instances: List of EC2 instance dicts
    """
    st.title("🖥️ EC2 Instances")

    if not instances:
        st.info("No EC2 instances found in selected regions")
        return

    st.markdown(f"**{len(instances)}** instances found")

    # Filters
    col1, col2, col3 = st.columns(3)

    with col1:
        states = sorted(set(i.get("state", "") for i in instances))
        selected_state = st.selectbox("Filter by State", ["All"] + states)

    with col2:
        types = sorted(set(i.get("type", "") for i in instances))
        selected_type = st.selectbox("Filter by Type", ["All"] + types)

    with col3:
        regions = sorted(set(i.get("region", "") for i in instances))
        selected_region = st.selectbox("Filter by Region", ["All"] + regions)

    # Apply filters
    filtered = instances
    if selected_state != "All":
        filtered = [i for i in filtered if i.get("state") == selected_state]
    if selected_type != "All":
        filtered = [i for i in filtered if i.get("type") == selected_type]
    if selected_region != "All":
        filtered = [i for i in filtered if i.get("region") == selected_region]

    # Create DataFrame
    df = pd.DataFrame(filtered)

    if df.empty:
        st.warning("No instances match the selected filters")
        return

    # Select and order columns
    columns = ["name", "id", "type", "state", "region", "private_ip", "public_ip"]
    columns = [c for c in columns if c in df.columns]
    df = df[columns]

    # Style the state column
    def style_state(val):
        if val == "running":
            return "background-color: #d4edda"
        elif val == "stopped":
            return "background-color: #f8d7da"
        return ""

    styled_df = df.style.applymap(style_state, subset=["state"] if "state" in df.columns else [])

    st.dataframe(
        styled_df,
        use_container_width=True,
        hide_index=True,
    )

    # Summary stats
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        running = len([i for i in filtered if i.get("state") == "running"])
        st.metric("Running", running)
    with col2:
        stopped = len([i for i in filtered if i.get("state") == "stopped"])
        st.metric("Stopped", stopped)
    with col3:
        st.metric("Total", len(filtered))


def render_rds_inventory(instances: list[dict]):
    """Render RDS instances table.

    Args:
        instances: List of RDS instance dicts
    """
    st.title("🗄️ RDS Databases")

    if not instances:
        st.info("No RDS instances found in selected regions")
        return

    st.markdown(f"**{len(instances)}** databases found")

    # Filters
    col1, col2, col3 = st.columns(3)

    with col1:
        engines = sorted(set(i.get("engine", "") for i in instances))
        selected_engine = st.selectbox("Filter by Engine", ["All"] + engines)

    with col2:
        statuses = sorted(set(i.get("status", "") for i in instances))
        selected_status = st.selectbox("Filter by Status", ["All"] + statuses)

    with col3:
        regions = sorted(set(i.get("region", "") for i in instances))
        selected_region = st.selectbox("Filter by Region", ["All"] + regions)

    # Apply filters
    filtered = instances
    if selected_engine != "All":
        filtered = [i for i in filtered if i.get("engine") == selected_engine]
    if selected_status != "All":
        filtered = [i for i in filtered if i.get("status") == selected_status]
    if selected_region != "All":
        filtered = [i for i in filtered if i.get("region") == selected_region]

    # Create DataFrame
    df = pd.DataFrame(filtered)

    if df.empty:
        st.warning("No databases match the selected filters")
        return

    # Select and order columns
    columns = ["id", "engine", "engine_version", "status", "instance_class", "storage_gb", "multi_az", "region"]
    columns = [c for c in columns if c in df.columns]
    df = df[columns]

    # Rename columns for display
    df = df.rename(columns={
        "id": "Identifier",
        "engine": "Engine",
        "engine_version": "Version",
        "status": "Status",
        "instance_class": "Class",
        "storage_gb": "Storage (GB)",
        "multi_az": "Multi-AZ",
        "region": "Region",
    })

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
    )

    # Summary stats
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        available = len([i for i in filtered if i.get("status") == "available"])
        st.metric("Available", available)
    with col2:
        multi_az = len([i for i in filtered if i.get("multi_az")])
        st.metric("Multi-AZ", multi_az)
    with col3:
        total_storage = sum(i.get("storage_gb", 0) for i in filtered)
        st.metric("Total Storage", f"{total_storage} GB")
    with col4:
        st.metric("Total", len(filtered))
