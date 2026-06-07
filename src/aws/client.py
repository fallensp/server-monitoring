"""boto3 client factory with retry configuration."""

import boto3
from botocore.config import Config
from botocore.exceptions import NoCredentialsError, ClientError

# Standard retry config with exponential backoff
RETRY_CONFIG = Config(
    retries={
        "max_attempts": 3,
        "mode": "standard",
    },
    connect_timeout=5,
    read_timeout=10,
)


def get_client(service: str, region: str = "us-east-1"):
    """Create a boto3 client with standard retry configuration.

    Args:
        service: AWS service name (e.g., 'ec2', 'rds', 'cloudwatch')
        region: AWS region name

    Returns:
        boto3 client for the specified service
    """
    # A fresh Session per client: boto3's default session is not thread-safe,
    # and these clients are created from ThreadPoolExecutor workers.
    session = boto3.session.Session()
    return session.client(service, region_name=region, config=RETRY_CONFIG)


def get_available_regions() -> list[str]:
    """Get list of all available AWS regions for EC2.

    Returns:
        List of region names
    """
    ec2 = get_client("ec2", "us-east-1")
    response = ec2.describe_regions(AllRegions=False)
    return [region["RegionName"] for region in response["Regions"]]
