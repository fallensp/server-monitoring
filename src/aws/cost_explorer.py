"""Cost Explorer API for cost tracking.

Note: Cost Explorer API only works in us-east-1 and costs $0.01 per API call.
"""

from datetime import datetime, timedelta
from src.aws.client import get_client


def get_monthly_costs(months: int = 6) -> list[dict]:
    """Get monthly costs for the past N months.

    Args:
        months: Number of months to fetch

    Returns:
        List of dicts with month and cost
    """
    ce = get_client("ce", "us-east-1")

    end_date = datetime.utcnow().replace(day=1)
    start_date = (end_date - timedelta(days=months * 31)).replace(day=1)

    try:
        response = ce.get_cost_and_usage(
            TimePeriod={
                "Start": start_date.strftime("%Y-%m-%d"),
                "End": end_date.strftime("%Y-%m-%d"),
            },
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
        )

        costs = []
        for result in response.get("ResultsByTime", []):
            period_start = result["TimePeriod"]["Start"]
            amount = float(result["Total"]["UnblendedCost"]["Amount"])
            costs.append({
                "month": period_start[:7],  # YYYY-MM format
                "cost": round(amount, 2),
            })

        return costs
    except Exception as e:
        return []


def get_daily_costs(days: int = 30) -> list[dict]:
    """Get daily costs for the past N days.

    Args:
        days: Number of days to fetch

    Returns:
        List of dicts with date and cost
    """
    ce = get_client("ce", "us-east-1")

    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=days)

    try:
        response = ce.get_cost_and_usage(
            TimePeriod={
                "Start": start_date.strftime("%Y-%m-%d"),
                "End": end_date.strftime("%Y-%m-%d"),
            },
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
        )

        costs = []
        for result in response.get("ResultsByTime", []):
            date = result["TimePeriod"]["Start"]
            amount = float(result["Total"]["UnblendedCost"]["Amount"])
            costs.append({
                "date": date,
                "cost": round(amount, 2),
            })

        return costs
    except Exception as e:
        return []


def get_cost_by_service(days: int = 30) -> list[dict]:
    """Get costs grouped by AWS service.

    Args:
        days: Number of days to analyze

    Returns:
        List of dicts with service and cost, sorted by cost descending
    """
    ce = get_client("ce", "us-east-1")

    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=days)

    try:
        response = ce.get_cost_and_usage(
            TimePeriod={
                "Start": start_date.strftime("%Y-%m-%d"),
                "End": end_date.strftime("%Y-%m-%d"),
            },
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )

        service_costs = {}
        for result in response.get("ResultsByTime", []):
            for group in result.get("Groups", []):
                service = group["Keys"][0]
                amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                service_costs[service] = service_costs.get(service, 0) + amount

        costs = [
            {"service": service, "cost": round(cost, 2)}
            for service, cost in service_costs.items()
        ]
        costs.sort(key=lambda x: x["cost"], reverse=True)

        return costs
    except Exception as e:
        return []


def get_cost_forecast(days: int = 30) -> dict | None:
    """Get cost forecast for the next N days.

    Args:
        days: Number of days to forecast

    Returns:
        Dict with forecast amount and confidence interval, or None
    """
    ce = get_client("ce", "us-east-1")

    start_date = datetime.utcnow().date() + timedelta(days=1)
    end_date = start_date + timedelta(days=days)

    try:
        response = ce.get_cost_forecast(
            TimePeriod={
                "Start": start_date.strftime("%Y-%m-%d"),
                "End": end_date.strftime("%Y-%m-%d"),
            },
            Metric="UNBLENDED_COST",
            Granularity="MONTHLY",
        )

        total = response.get("Total", {})
        return {
            "amount": round(float(total.get("Amount", 0)), 2),
            "unit": total.get("Unit", "USD"),
        }
    except Exception as e:
        return None


def get_mtd_cost() -> float:
    """Get month-to-date cost.

    Returns:
        Current month's cost so far
    """
    ce = get_client("ce", "us-east-1")

    today = datetime.utcnow().date()
    start_date = today.replace(day=1)

    try:
        response = ce.get_cost_and_usage(
            TimePeriod={
                "Start": start_date.strftime("%Y-%m-%d"),
                "End": today.strftime("%Y-%m-%d"),
            },
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
        )

        total = 0.0
        for result in response.get("ResultsByTime", []):
            amount = float(result["Total"]["UnblendedCost"]["Amount"])
            total += amount

        return round(total, 2)
    except Exception as e:
        return 0.0
