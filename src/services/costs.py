"""Cost analysis service."""

import streamlit as st
from src.aws.cost_explorer import (
    get_monthly_costs,
    get_daily_costs,
    get_cost_by_service,
    get_cost_forecast,
    get_mtd_cost,
)


@st.cache_data(ttl=3600)  # 1-hour cache for cost data
def get_cost_summary() -> dict:
    """Get summary of cost data.

    Returns:
        Dict with MTD cost, forecast, and top services
    """
    mtd = get_mtd_cost()
    forecast = get_cost_forecast(days=30)
    top_services = get_cost_by_service(days=30)[:5]

    return {
        "mtd_cost": mtd,
        "forecast": forecast,
        "top_services": top_services,
    }


@st.cache_data(ttl=3600)
def get_monthly_cost_data(months: int = 6) -> list[dict]:
    """Get monthly cost data with caching.

    Args:
        months: Number of months to fetch

    Returns:
        List of monthly cost data
    """
    return get_monthly_costs(months)


@st.cache_data(ttl=3600)
def get_daily_cost_data(days: int = 30) -> list[dict]:
    """Get daily cost data with caching.

    Args:
        days: Number of days to fetch

    Returns:
        List of daily cost data
    """
    return get_daily_costs(days)


@st.cache_data(ttl=3600)
def get_service_cost_breakdown(days: int = 30) -> list[dict]:
    """Get cost breakdown by service with caching.

    Args:
        days: Number of days to analyze

    Returns:
        List of service costs
    """
    return get_cost_by_service(days)
