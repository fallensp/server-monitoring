"""RDS health status calculation and formatting."""

from enum import Enum


class HealthStatus(Enum):
    """Health status levels for RDS metrics."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


# Thresholds for each metric
# Format: (warning_threshold, critical_threshold, is_upper_bound)
# is_upper_bound=True means values above threshold are bad (e.g., CPU)
# is_upper_bound=False means values below threshold are bad (e.g., FreeableMemory)
METRIC_THRESHOLDS = {
    "CPUUtilization": (70.0, 90.0, True),  # >70% warning, >90% critical
    "FreeableMemory": (0.25, 0.10, False),  # <25% warning, <10% critical (as ratio of total)
    "ReadLatency": (0.020, 0.050, True),  # >20ms warning, >50ms critical
    "WriteLatency": (0.020, 0.050, True),  # >20ms warning, >50ms critical
    "DiskQueueDepth": (10.0, 50.0, True),  # >10 warning, >50 critical
    "DatabaseConnections": (0.80, 0.95, True),  # >80% of max warning, >95% critical (as ratio)
}

# Default max connections by instance class (approximate)
DEFAULT_MAX_CONNECTIONS = {
    "db.t2.micro": 66,
    "db.t2.small": 150,
    "db.t2.medium": 312,
    "db.t2.large": 648,
    "db.t3.micro": 112,
    "db.t3.small": 225,
    "db.t3.medium": 450,
    "db.t3.large": 900,
    "db.t3.xlarge": 1800,
    "db.t3.2xlarge": 3600,
    "db.m5.large": 823,
    "db.m5.xlarge": 1646,
    "db.m5.2xlarge": 3429,
    "db.m5.4xlarge": 5000,
    "db.r5.large": 1000,
    "db.r5.xlarge": 2000,
    "db.r5.2xlarge": 4000,
}


def calculate_metric_status(
    metric_name: str,
    value: float | None,
    total_memory_bytes: float | None = None,
    max_connections: int | None = None,
) -> HealthStatus:
    """Calculate health status for a metric value.

    Args:
        metric_name: Name of the metric
        value: Current metric value
        total_memory_bytes: Total memory for the instance (for FreeableMemory)
        max_connections: Max connections for the instance (for DatabaseConnections)

    Returns:
        HealthStatus enum value
    """
    if value is None:
        return HealthStatus.UNKNOWN

    if metric_name not in METRIC_THRESHOLDS:
        return HealthStatus.UNKNOWN

    warning_threshold, critical_threshold, is_upper_bound = METRIC_THRESHOLDS[metric_name]

    # Handle special cases that need conversion
    if metric_name == "FreeableMemory":
        if total_memory_bytes is None or total_memory_bytes <= 0:
            # Estimate based on typical instance sizes (2GB as fallback)
            total_memory_bytes = 2 * 1024 * 1024 * 1024
        ratio = value / total_memory_bytes
        # For memory, we check if the FREE ratio is below threshold
        if ratio < critical_threshold:
            return HealthStatus.CRITICAL
        elif ratio < warning_threshold:
            return HealthStatus.WARNING
        return HealthStatus.HEALTHY

    if metric_name == "DatabaseConnections":
        if max_connections is None or max_connections <= 0:
            # Can't evaluate without knowing max
            return HealthStatus.HEALTHY
        ratio = value / max_connections
        # Check connection usage ratio
        if ratio >= critical_threshold:
            return HealthStatus.CRITICAL
        elif ratio >= warning_threshold:
            return HealthStatus.WARNING
        return HealthStatus.HEALTHY

    # Standard threshold comparison
    if is_upper_bound:
        if value >= critical_threshold:
            return HealthStatus.CRITICAL
        elif value >= warning_threshold:
            return HealthStatus.WARNING
    else:
        if value <= critical_threshold:
            return HealthStatus.CRITICAL
        elif value <= warning_threshold:
            return HealthStatus.WARNING

    return HealthStatus.HEALTHY


def format_metric_value(metric_name: str, value: float | None) -> str:
    """Format a metric value for human-readable display.

    Args:
        metric_name: Name of the metric
        value: Raw metric value

    Returns:
        Formatted string representation
    """
    if value is None:
        return "N/A"

    if metric_name == "CPUUtilization":
        return f"{value:.1f}%"

    if metric_name == "FreeableMemory":
        # Convert bytes to human-readable
        gb = value / (1024 * 1024 * 1024)
        if gb >= 1:
            return f"{gb:.2f} GB"
        mb = value / (1024 * 1024)
        return f"{mb:.0f} MB"

    if metric_name in ("ReadLatency", "WriteLatency"):
        # Convert seconds to milliseconds
        ms = value * 1000
        if ms < 1:
            return f"{ms:.2f} ms"
        return f"{ms:.1f} ms"

    if metric_name == "DiskQueueDepth":
        return f"{value:.1f}"

    if metric_name == "DatabaseConnections":
        return f"{int(value)}"

    return f"{value:.2f}"


def get_overall_health(metrics: dict[str, float | None], **kwargs) -> HealthStatus:
    """Calculate overall health status from all metrics.

    Args:
        metrics: Dict mapping metric name to value
        **kwargs: Additional context (total_memory_bytes, max_connections)

    Returns:
        Worst (most severe) health status from all metrics
    """
    statuses = []

    for metric_name, value in metrics.items():
        status = calculate_metric_status(
            metric_name,
            value,
            total_memory_bytes=kwargs.get("total_memory_bytes"),
            max_connections=kwargs.get("max_connections"),
        )
        statuses.append(status)

    # Return the worst status
    if HealthStatus.CRITICAL in statuses:
        return HealthStatus.CRITICAL
    if HealthStatus.WARNING in statuses:
        return HealthStatus.WARNING
    if all(s == HealthStatus.UNKNOWN for s in statuses):
        return HealthStatus.UNKNOWN
    return HealthStatus.HEALTHY


def get_status_color(status: HealthStatus) -> str:
    """Get CSS color for a health status.

    Args:
        status: HealthStatus enum value

    Returns:
        CSS color string
    """
    colors = {
        HealthStatus.HEALTHY: "#00d97e",    # Green
        HealthStatus.WARNING: "#ffb347",    # Orange/Yellow
        HealthStatus.CRITICAL: "#ff4757",   # Red
        HealthStatus.UNKNOWN: "#6c757d",    # Gray
    }
    return colors.get(status, "#6c757d")


def get_status_dim_color(status: HealthStatus) -> str:
    """Get dimmed CSS color for a health status (for backgrounds).

    Args:
        status: HealthStatus enum value

    Returns:
        CSS color string with transparency
    """
    colors = {
        HealthStatus.HEALTHY: "rgba(0, 217, 126, 0.15)",
        HealthStatus.WARNING: "rgba(255, 179, 71, 0.15)",
        HealthStatus.CRITICAL: "rgba(255, 71, 87, 0.15)",
        HealthStatus.UNKNOWN: "rgba(108, 117, 125, 0.15)",
    }
    return colors.get(status, "rgba(108, 117, 125, 0.15)")


def get_status_icon(status: HealthStatus) -> str:
    """Get icon/emoji for a health status.

    Args:
        status: HealthStatus enum value

    Returns:
        Icon string
    """
    icons = {
        HealthStatus.HEALTHY: "✓",
        HealthStatus.WARNING: "⚠",
        HealthStatus.CRITICAL: "✗",
        HealthStatus.UNKNOWN: "?",
    }
    return icons.get(status, "?")


def get_max_connections_for_class(instance_class: str) -> int | None:
    """Get the default max connections for an RDS instance class.

    Args:
        instance_class: RDS instance class (e.g., 'db.t3.micro')

    Returns:
        Max connections or None if unknown
    """
    return DEFAULT_MAX_CONNECTIONS.get(instance_class)
