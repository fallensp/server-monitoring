"""Sidebar navigation and region filters."""

import streamlit as st


# Default regions when AWS is not available
DEFAULT_REGIONS = [
    "us-east-1", "us-east-2", "us-west-1", "us-west-2",
    "eu-west-1", "eu-west-2", "eu-central-1",
    "ap-northeast-1", "ap-southeast-1", "ap-southeast-2",
]


def render_sidebar() -> tuple[str, tuple[str, ...]]:
    """Render the sidebar with navigation and filters.

    Returns:
        Tuple of (selected_page, selected_regions)
    """
    st.sidebar.title("🔶 AWS Monitor")
    st.sidebar.markdown("---")

    # Navigation
    st.sidebar.subheader("Navigation")
    pages = {
        "Dashboard": "📊",
        "EC2 Instances": "🖥️",
        "RDS Databases": "🗄️",
        "Metrics": "📈",
        "Costs": "💰",
        "Alerts": "🚨",
    }

    selected_page = st.sidebar.radio(
        "Select Page",
        list(pages.keys()),
        format_func=lambda x: f"{pages[x]} {x}",
        label_visibility="collapsed",
    )

    st.sidebar.markdown("---")

    # Region filter
    st.sidebar.subheader("Region Filter")

    # Use default regions (avoid blocking API call on startup)
    available_regions = DEFAULT_REGIONS

    # Default regions (common ones)
    default_regions = ["us-east-1", "us-west-2", "eu-west-1"]
    default_selection = [r for r in default_regions if r in available_regions]

    # Select all / clear buttons
    col1, col2 = st.sidebar.columns(2)
    if col1.button("Select All", use_container_width=True):
        st.session_state["selected_regions"] = available_regions
    if col2.button("Clear", use_container_width=True):
        st.session_state["selected_regions"] = []

    # Multi-select for regions
    selected_regions = st.sidebar.multiselect(
        "Regions",
        available_regions,
        default=st.session_state.get("selected_regions", default_selection),
        label_visibility="collapsed",
    )

    # Store selection in session state
    st.session_state["selected_regions"] = selected_regions

    st.sidebar.markdown("---")
    st.sidebar.caption(f"Monitoring {len(selected_regions)} region(s)")

    # Refresh button
    if st.sidebar.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    return selected_page, tuple(selected_regions)
