"""Alert detection logic."""

from dataclasses import dataclass
from enum import Enum
from src.aws.cloudwatch import get_latest_cpu_utilization


class AlertSeverity(Enum):
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    resource_type: str
    resource_id: str
    resource_name: str
    region: str
    severity: AlertSeverity
    message: str


def detect_ec2_alerts(instances: list[dict], check_cpu: bool = True) -> list[Alert]:
    """Detect alerts for EC2 instances.

    Alert conditions:
    - Stopped instances (warning)
    - High CPU > 70% (warning)
    - High CPU > 90% (critical)

    Args:
        instances: List of EC2 instances
        check_cpu: Whether to check CPU metrics (can be slow)

    Returns:
        List of Alert objects
    """
    alerts = []

    for instance in instances:
        instance_id = instance.get("id", "")
        name = instance.get("name", instance_id)
        region = instance.get("region", "unknown")
        state = instance.get("state", "")

        # Check for stopped instances
        if state == "stopped":
            alerts.append(Alert(
                resource_type="EC2",
                resource_id=instance_id,
                resource_name=name,
                region=region,
                severity=AlertSeverity.WARNING,
                message="Instance is stopped",
            ))

        # Check CPU utilization for running instances
        if check_cpu and state == "running":
            cpu = get_latest_cpu_utilization(instance_id, region, "AWS/EC2")
            if cpu is not None:
                if cpu > 90:
                    alerts.append(Alert(
                        resource_type="EC2",
                        resource_id=instance_id,
                        resource_name=name,
                        region=region,
                        severity=AlertSeverity.CRITICAL,
                        message=f"High CPU utilization: {cpu:.1f}%",
                    ))
                elif cpu > 70:
                    alerts.append(Alert(
                        resource_type="EC2",
                        resource_id=instance_id,
                        resource_name=name,
                        region=region,
                        severity=AlertSeverity.WARNING,
                        message=f"Elevated CPU utilization: {cpu:.1f}%",
                    ))

    return alerts


def detect_rds_alerts(instances: list[dict]) -> list[Alert]:
    """Detect alerts for RDS instances.

    Alert conditions:
    - Non-available status (critical)

    Args:
        instances: List of RDS instances

    Returns:
        List of Alert objects
    """
    alerts = []

    for instance in instances:
        db_id = instance.get("id", "")
        region = instance.get("region", "unknown")
        status = instance.get("status", "")

        # Check for non-available status
        if status and status != "available":
            alerts.append(Alert(
                resource_type="RDS",
                resource_id=db_id,
                resource_name=db_id,
                region=region,
                severity=AlertSeverity.CRITICAL,
                message=f"Database status: {status}",
            ))

    return alerts


def get_all_alerts(
    ec2_instances: list[dict],
    rds_instances: list[dict],
    check_cpu: bool = False,
) -> list[Alert]:
    """Get all alerts for EC2 and RDS instances.

    Args:
        ec2_instances: List of EC2 instances
        rds_instances: List of RDS instances
        check_cpu: Whether to check CPU metrics

    Returns:
        List of all Alert objects, sorted by severity
    """
    alerts = []
    alerts.extend(detect_ec2_alerts(ec2_instances, check_cpu=check_cpu))
    alerts.extend(detect_rds_alerts(rds_instances))

    # Sort by severity (critical first)
    alerts.sort(key=lambda a: 0 if a.severity == AlertSeverity.CRITICAL else 1)

    return alerts


def get_alert_counts(alerts: list[Alert]) -> dict[str, int]:
    """Count alerts by severity.

    Args:
        alerts: List of alerts

    Returns:
        Dict with warning and critical counts
    """
    return {
        "warning": sum(1 for a in alerts if a.severity == AlertSeverity.WARNING),
        "critical": sum(1 for a in alerts if a.severity == AlertSeverity.CRITICAL),
        "total": len(alerts),
    }
