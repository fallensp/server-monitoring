"""Cost visualization views."""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from src.services.costs import (
    get_cost_summary,
    get_monthly_cost_data,
    get_daily_cost_data,
    get_service_cost_breakdown,
)


def render_costs_view():
    """Render the costs visualization page."""
    st.title("💰 Cost Analysis")

    st.info(
        "💡 **Note:** Cost Explorer API only works in us-east-1 and costs $0.01 per API call. "
        "Cost data may have up to 24 hours delay."
    )

    try:
        # Summary metrics
        summary = get_cost_summary()

        col1, col2, col3 = st.columns(3)

        with col1:
            mtd = summary.get("mtd_cost", 0)
            st.metric("Month-to-Date Cost", f"${mtd:,.2f}")

        with col2:
            forecast = summary.get("forecast")
            if forecast:
                st.metric(
                    "30-Day Forecast",
                    f"${forecast['amount']:,.2f}",
                    help="Estimated cost for the next 30 days",
                )
            else:
                st.metric("30-Day Forecast", "N/A")

        with col3:
            top_services = summary.get("top_services", [])
            if top_services:
                top_service = top_services[0]
                st.metric(
                    "Top Service",
                    top_service["service"][:20] + "..." if len(top_service["service"]) > 20 else top_service["service"],
                    f"${top_service['cost']:,.2f}",
                )
            else:
                st.metric("Top Service", "N/A")

        st.markdown("---")

        # Tabs for different views
        tab1, tab2, tab3 = st.tabs(["Monthly Trend", "Daily Costs", "By Service"])

        with tab1:
            render_monthly_costs()

        with tab2:
            render_daily_costs()

        with tab3:
            render_service_breakdown()

    except Exception as e:
        st.error(
            "Unable to fetch cost data. Please ensure:\n"
            "- Cost Explorer is enabled in your AWS account\n"
            "- You have the required IAM permissions (ce:GetCostAndUsage, ce:GetCostForecast)\n"
            f"\nError: {str(e)}"
        )


def render_monthly_costs():
    """Render monthly cost trend chart."""
    st.subheader("Monthly Cost Trend")

    months = st.slider("Number of months", 3, 12, 6)

    data = get_monthly_cost_data(months)

    if not data:
        st.warning("No monthly cost data available")
        return

    df = pd.DataFrame(data)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["month"],
        y=df["cost"],
        marker_color="#FF9900",
        text=[f"${c:,.2f}" for c in df["cost"]],
        textposition="outside",
    ))

    fig.update_layout(
        title="Monthly AWS Costs",
        xaxis_title="Month",
        yaxis_title="Cost (USD)",
        showlegend=False,
        height=400,
    )

    st.plotly_chart(fig, use_container_width=True)

    # Summary stats
    if len(df) >= 2:
        latest = df.iloc[-1]["cost"]
        previous = df.iloc[-2]["cost"]
        change = latest - previous
        pct_change = (change / previous * 100) if previous > 0 else 0

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Latest Month", f"${latest:,.2f}")
        with col2:
            st.metric("Previous Month", f"${previous:,.2f}")
        with col3:
            st.metric(
                "Change",
                f"${change:,.2f}",
                f"{pct_change:+.1f}%",
                delta_color="inverse",
            )


def render_daily_costs():
    """Render daily cost chart."""
    st.subheader("Daily Costs")

    days = st.slider("Number of days", 7, 90, 30)

    data = get_daily_cost_data(days)

    if not data:
        st.warning("No daily cost data available")
        return

    df = pd.DataFrame(data)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["date"],
        y=df["cost"],
        mode="lines+markers",
        line=dict(color="#FF9900"),
        marker=dict(size=4),
    ))

    fig.update_layout(
        title="Daily AWS Costs",
        xaxis_title="Date",
        yaxis_title="Cost (USD)",
        showlegend=False,
        height=400,
    )

    st.plotly_chart(fig, use_container_width=True)

    # Summary stats
    avg_daily = df["cost"].mean()
    max_daily = df["cost"].max()
    min_daily = df["cost"].min()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Average Daily", f"${avg_daily:,.2f}")
    with col2:
        st.metric("Max Daily", f"${max_daily:,.2f}")
    with col3:
        st.metric("Min Daily", f"${min_daily:,.2f}")


def render_service_breakdown():
    """Render cost breakdown by service."""
    st.subheader("Cost by Service")

    days = st.slider("Analysis period (days)", 7, 90, 30, key="service_days")

    data = get_service_cost_breakdown(days)

    if not data:
        st.warning("No service cost data available")
        return

    df = pd.DataFrame(data)

    # Show top 10 services in pie chart
    top_10 = df.head(10)
    other_cost = df.iloc[10:]["cost"].sum() if len(df) > 10 else 0

    if other_cost > 0:
        top_10 = pd.concat([
            top_10,
            pd.DataFrame([{"service": "Other", "cost": other_cost}])
        ], ignore_index=True)

    fig = px.pie(
        top_10,
        values="cost",
        names="service",
        title="Cost Distribution by Service",
        color_discrete_sequence=px.colors.sequential.Oranges_r,
    )

    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(height=500)

    st.plotly_chart(fig, use_container_width=True)

    # Full table
    st.subheader("All Services")
    df["cost"] = df["cost"].apply(lambda x: f"${x:,.2f}")
    df = df.rename(columns={"service": "Service", "cost": "Cost"})
    st.dataframe(df, use_container_width=True, hide_index=True)
