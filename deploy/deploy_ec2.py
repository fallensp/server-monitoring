"""Deploy AWS Monitor to EC2 spot instance."""

import boto3
import base64
import time
import sys

REGION = "ap-southeast-1"  # Singapore (closest to Malaysia)
INSTANCE_TYPE = "t3.small"
AMI_ID = None  # Will be fetched dynamically (Amazon Linux 2023)

# User data script to set up the application
USER_DATA = """#!/bin/bash
set -ex

# Update system
dnf update -y
dnf install -y python3.11 python3.11-pip git

# Create app directory
mkdir -p /opt/aws-monitor
cd /opt/aws-monitor

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install streamlit boto3 pandas plotly

# Create the application files
cat > app.py << 'APPEOF'
"""

# Read the app files
import os
app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def read_file(path):
    with open(path, 'r') as f:
        return f.read()

def get_latest_ami(ec2_client):
    """Get latest Amazon Linux 2023 AMI."""
    response = ec2_client.describe_images(
        Owners=['amazon'],
        Filters=[
            {'Name': 'name', 'Values': ['al2023-ami-2023*-x86_64']},
            {'Name': 'state', 'Values': ['available']},
            {'Name': 'architecture', 'Values': ['x86_64']},
        ]
    )
    images = sorted(response['Images'], key=lambda x: x['CreationDate'], reverse=True)
    return images[0]['ImageId'] if images else None


def create_security_group(ec2_client):
    """Create security group for the app."""
    sg_name = "aws-monitor-sg"

    # Check if exists
    try:
        response = ec2_client.describe_security_groups(GroupNames=[sg_name])
        sg_id = response['SecurityGroups'][0]['GroupId']
        print(f"Using existing security group: {sg_id}")
        return sg_id
    except ec2_client.exceptions.ClientError:
        pass

    # Create new security group
    response = ec2_client.create_security_group(
        GroupName=sg_name,
        Description="Security group for AWS Monitor Streamlit app"
    )
    sg_id = response['GroupId']

    # Add inbound rules
    ec2_client.authorize_security_group_ingress(
        GroupId=sg_id,
        IpPermissions=[
            {
                'IpProtocol': 'tcp',
                'FromPort': 8501,
                'ToPort': 8501,
                'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'Streamlit'}]
            },
            {
                'IpProtocol': 'tcp',
                'FromPort': 22,
                'ToPort': 22,
                'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'SSH'}]
            }
        ]
    )
    print(f"Created security group: {sg_id}")
    return sg_id


def create_iam_role(iam_client):
    """Create IAM role for EC2 instance."""
    role_name = "aws-monitor-ec2-role"
    instance_profile_name = "aws-monitor-instance-profile"

    # Check if role exists
    try:
        iam_client.get_role(RoleName=role_name)
        print(f"Using existing IAM role: {role_name}")
    except iam_client.exceptions.NoSuchEntityException:
        # Create role
        assume_role_policy = '''{
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": "ec2.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }]
        }'''

        iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=assume_role_policy,
            Description="Role for AWS Monitor EC2 instance"
        )

        # Attach policies for read-only access
        policies = [
            "arn:aws:iam::aws:policy/AmazonEC2ReadOnlyAccess",
            "arn:aws:iam::aws:policy/AmazonRDSReadOnlyAccess",
            "arn:aws:iam::aws:policy/CloudWatchReadOnlyAccess",
            "arn:aws:iam::aws:policy/AWSBillingReadOnlyAccess",
        ]
        for policy in policies:
            try:
                iam_client.attach_role_policy(RoleName=role_name, PolicyArn=policy)
            except Exception as e:
                print(f"Warning: Could not attach {policy}: {e}")

        print(f"Created IAM role: {role_name}")

    # Check if instance profile exists
    try:
        iam_client.get_instance_profile(InstanceProfileName=instance_profile_name)
        print(f"Using existing instance profile: {instance_profile_name}")
    except iam_client.exceptions.NoSuchEntityException:
        # Create instance profile
        iam_client.create_instance_profile(InstanceProfileName=instance_profile_name)
        iam_client.add_role_to_instance_profile(
            InstanceProfileName=instance_profile_name,
            RoleName=role_name
        )
        print(f"Created instance profile: {instance_profile_name}")
        # Wait for it to be available
        time.sleep(10)

    return instance_profile_name


def generate_user_data():
    """Generate the user data script with embedded application code."""

    app_code = read_file(os.path.join(app_dir, 'app.py'))

    # Read all source files
    src_files = {}
    for root, dirs, files in os.walk(os.path.join(app_dir, 'src')):
        for file in files:
            if file.endswith('.py'):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, app_dir)
                src_files[rel_path] = read_file(full_path)

    script = """#!/bin/bash
set -ex
exec > /var/log/user-data.log 2>&1

# Update system
dnf update -y
dnf install -y python3.11 python3.11-pip

# Create app directory
mkdir -p /opt/aws-monitor/src/aws
mkdir -p /opt/aws-monitor/src/services
mkdir -p /opt/aws-monitor/src/ui
mkdir -p /opt/aws-monitor/.streamlit
cd /opt/aws-monitor

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install streamlit boto3 pandas plotly

# Create streamlit config
cat > .streamlit/config.toml << 'STCONFIG'
[theme]
primaryColor = "#FF9900"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F5F5F5"
textColor = "#232F3E"
font = "sans serif"

[server]
headless = true
address = "0.0.0.0"
port = 8501
STCONFIG

"""

    # Add app.py
    script += f"""
# Create app.py
cat > app.py << 'APPFILE'
{app_code}
APPFILE

"""

    # Add all source files
    for rel_path, content in src_files.items():
        # Escape single quotes in content for heredoc
        escaped_content = content.replace("'", "'\"'\"'")
        script += f"""
# Create {rel_path}
mkdir -p $(dirname {rel_path})
cat > {rel_path} << 'SRCFILE_{rel_path.replace('/', '_').replace('.', '_')}'
{content}
SRCFILE_{rel_path.replace('/', '_').replace('.', '_')}

"""

    # Add systemd service and start
    script += """
# Create systemd service
cat > /etc/systemd/system/aws-monitor.service << 'SVCFILE'
[Unit]
Description=AWS Monitor Streamlit App
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/aws-monitor
ExecStart=/opt/aws-monitor/venv/bin/streamlit run app.py --server.address 0.0.0.0 --server.port 8501
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCFILE

# Start the service
systemctl daemon-reload
systemctl enable aws-monitor
systemctl start aws-monitor

echo "Deployment complete!"
"""

    return script


def launch_spot_instance(ec2_client, sg_id, instance_profile, ami_id):
    """Launch a spot instance."""

    user_data = generate_user_data()

    response = ec2_client.run_instances(
        ImageId=ami_id,
        InstanceType=INSTANCE_TYPE,
        MinCount=1,
        MaxCount=1,
        SecurityGroupIds=[sg_id],
        IamInstanceProfile={'Name': instance_profile},
        UserData=user_data,
        InstanceMarketOptions={
            'MarketType': 'spot',
            'SpotOptions': {
                'SpotInstanceType': 'one-time',
                'InstanceInterruptionBehavior': 'terminate'
            }
        },
        TagSpecifications=[{
            'ResourceType': 'instance',
            'Tags': [
                {'Key': 'Name', 'Value': 'aws-monitor'},
                {'Key': 'Project', 'Value': 'aws-monitor'}
            ]
        }]
    )

    instance_id = response['Instances'][0]['InstanceId']
    print(f"Launched spot instance: {instance_id}")
    return instance_id


def wait_for_instance(ec2_client, instance_id):
    """Wait for instance to be running and get public IP."""
    print("Waiting for instance to start...")

    waiter = ec2_client.get_waiter('instance_running')
    waiter.wait(InstanceIds=[instance_id])

    response = ec2_client.describe_instances(InstanceIds=[instance_id])
    instance = response['Reservations'][0]['Instances'][0]
    public_ip = instance.get('PublicIpAddress')

    print(f"Instance is running!")
    print(f"Public IP: {public_ip}")

    return public_ip


def main():
    print(f"Deploying AWS Monitor to {REGION}...")

    ec2 = boto3.client('ec2', region_name=REGION)
    iam = boto3.client('iam', region_name=REGION)

    # Get AMI
    ami_id = get_latest_ami(ec2)
    if not ami_id:
        print("ERROR: Could not find Amazon Linux 2023 AMI")
        sys.exit(1)
    print(f"Using AMI: {ami_id}")

    # Create security group
    sg_id = create_security_group(ec2)

    # Create IAM role
    instance_profile = create_iam_role(iam)

    # Launch instance
    instance_id = launch_spot_instance(ec2, sg_id, instance_profile, ami_id)

    # Wait and get IP
    public_ip = wait_for_instance(ec2, instance_id)

    print("\n" + "="*50)
    print("DEPLOYMENT COMPLETE!")
    print("="*50)
    print(f"\nInstance ID: {instance_id}")
    print(f"Public IP: {public_ip}")
    print(f"\nThe app will be available at:")
    print(f"  http://{public_ip}:8501")
    print(f"\nNote: It may take 2-3 minutes for the app to fully start.")
    print("You can check the setup progress by SSHing into the instance and running:")
    print("  tail -f /var/log/user-data.log")


if __name__ == "__main__":
    main()
