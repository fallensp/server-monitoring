"""EC2 and RDS control actions (start/stop/reboot).

All functions return an ActionResult so the UI can show success/failure
without crashing the dashboard on AWS errors.
"""

from dataclasses import dataclass

from botocore.exceptions import BotoCoreError, ClientError

from src.aws.client import get_client


@dataclass
class ActionResult:
    success: bool
    message: str
    new_state: str = ""


def _error_message(e: Exception) -> str:
    """Extract a readable message from a boto3 exception."""
    if isinstance(e, ClientError):
        err = e.response.get("Error", {})
        code = err.get("Code", "Error")
        msg = err.get("Message", str(e))
        return f"{code}: {msg}"
    return str(e)


# ---------------------------------------------------------------------------
# EC2 actions
# ---------------------------------------------------------------------------

def start_ec2_instance(instance_id: str, region: str) -> ActionResult:
    """Start a stopped EC2 instance."""
    try:
        ec2 = get_client("ec2", region)
        resp = ec2.start_instances(InstanceIds=[instance_id])
        state = resp["StartingInstances"][0]["CurrentState"]["Name"]
        return ActionResult(True, f"Start requested for {instance_id}", state)
    except (ClientError, BotoCoreError) as e:
        return ActionResult(False, _error_message(e))


def stop_ec2_instance(instance_id: str, region: str) -> ActionResult:
    """Stop a running EC2 instance."""
    try:
        ec2 = get_client("ec2", region)
        resp = ec2.stop_instances(InstanceIds=[instance_id])
        state = resp["StoppingInstances"][0]["CurrentState"]["Name"]
        return ActionResult(True, f"Stop requested for {instance_id}", state)
    except (ClientError, BotoCoreError) as e:
        return ActionResult(False, _error_message(e))


def reboot_ec2_instance(instance_id: str, region: str) -> ActionResult:
    """Reboot a running EC2 instance."""
    try:
        ec2 = get_client("ec2", region)
        ec2.reboot_instances(InstanceIds=[instance_id])
        # RebootInstances returns no state; it is a soft reboot request
        return ActionResult(True, f"Reboot requested for {instance_id}", "rebooting")
    except (ClientError, BotoCoreError) as e:
        return ActionResult(False, _error_message(e))


def get_ec2_state(instance_id: str, region: str) -> str:
    """Get the current state of an EC2 instance (for post-action polling)."""
    try:
        ec2 = get_client("ec2", region)
        resp = ec2.describe_instances(InstanceIds=[instance_id])
        return resp["Reservations"][0]["Instances"][0]["State"]["Name"]
    except (ClientError, BotoCoreError, IndexError, KeyError):
        return "unknown"


# ---------------------------------------------------------------------------
# RDS actions
# ---------------------------------------------------------------------------

def start_rds_instance(db_id: str, region: str) -> ActionResult:
    """Start a stopped RDS instance."""
    try:
        rds = get_client("rds", region)
        resp = rds.start_db_instance(DBInstanceIdentifier=db_id)
        status = resp["DBInstance"]["DBInstanceStatus"]
        return ActionResult(True, f"Start requested for {db_id}", status)
    except (ClientError, BotoCoreError) as e:
        return ActionResult(False, _error_message(e))


def stop_rds_instance(db_id: str, region: str) -> ActionResult:
    """Stop an available RDS instance.

    Note: AWS automatically restarts stopped RDS instances after 7 days.
    """
    try:
        rds = get_client("rds", region)
        resp = rds.stop_db_instance(DBInstanceIdentifier=db_id)
        status = resp["DBInstance"]["DBInstanceStatus"]
        return ActionResult(True, f"Stop requested for {db_id}", status)
    except (ClientError, BotoCoreError) as e:
        return ActionResult(False, _error_message(e))


def reboot_rds_instance(db_id: str, region: str) -> ActionResult:
    """Reboot an available RDS instance."""
    try:
        rds = get_client("rds", region)
        resp = rds.reboot_db_instance(DBInstanceIdentifier=db_id)
        status = resp["DBInstance"]["DBInstanceStatus"]
        return ActionResult(True, f"Reboot requested for {db_id}", status)
    except (ClientError, BotoCoreError) as e:
        return ActionResult(False, _error_message(e))


def get_rds_status(db_id: str, region: str) -> str:
    """Get the current status of an RDS instance (for post-action polling)."""
    try:
        rds = get_client("rds", region)
        resp = rds.describe_db_instances(DBInstanceIdentifier=db_id)
        return resp["DBInstances"][0]["DBInstanceStatus"]
    except (ClientError, BotoCoreError, IndexError, KeyError):
        return "unknown"
