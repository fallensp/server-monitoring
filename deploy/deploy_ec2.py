"""Deploy AWS Monitor to EC2 with Auto Scaling Group for resilience."""

import boto3
import time
import sys
import json

REGION = "ap-southeast-1"
INSTANCE_TYPE = "t3.small"
GITHUB_REPO = "https://github.com/fallensp/server-monitoring.git"
EIP_ALLOCATION_ID = "eipalloc-073453656b3e5755f"  # Fixed Elastic IP


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


def get_default_vpc_subnets(ec2_client):
    """Get subnets from the default VPC."""
    response = ec2_client.describe_vpcs(Filters=[{'Name': 'isDefault', 'Values': ['true']}])
    if not response['Vpcs']:
        print("ERROR: No default VPC found")
        sys.exit(1)
    vpc_id = response['Vpcs'][0]['VpcId']

    response = ec2_client.describe_subnets(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
    subnet_ids = [s['SubnetId'] for s in response['Subnets']]
    return subnet_ids


def create_security_group(ec2_client):
    """Create security group for the app."""
    sg_name = "aws-monitor-sg"

    try:
        response = ec2_client.describe_security_groups(GroupNames=[sg_name])
        sg_id = response['SecurityGroups'][0]['GroupId']
        print(f"Using existing security group: {sg_id}")
        return sg_id
    except ec2_client.exceptions.ClientError:
        pass

    response = ec2_client.create_security_group(
        GroupName=sg_name,
        Description="Security group for AWS Monitor Streamlit app"
    )
    sg_id = response['GroupId']

    ec2_client.authorize_security_group_ingress(
        GroupId=sg_id,
        IpPermissions=[
            {'IpProtocol': 'tcp', 'FromPort': 80, 'ToPort': 80,
             'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'HTTP'}]},
            {'IpProtocol': 'tcp', 'FromPort': 443, 'ToPort': 443,
             'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'HTTPS'}]},
            {'IpProtocol': 'tcp', 'FromPort': 22, 'ToPort': 22,
             'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'SSH'}]},
            {'IpProtocol': 'tcp', 'FromPort': 8501, 'ToPort': 8501,
             'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'Streamlit'}]},
        ]
    )
    print(f"Created security group: {sg_id}")
    return sg_id


def create_iam_role(iam_client):
    """Create IAM role for EC2 instance with EIP association permission."""
    role_name = "aws-monitor-ec2-role"
    instance_profile_name = "aws-monitor-instance-profile"

    try:
        iam_client.get_role(RoleName=role_name)
        print(f"Using existing IAM role: {role_name}")
    except iam_client.exceptions.NoSuchEntityException:
        assume_role_policy = json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": "ec2.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }]
        })

        iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=assume_role_policy,
            Description="Role for AWS Monitor EC2 instance"
        )
        print(f"Created IAM role: {role_name}")

    # Attach required policies
    policies = [
        "arn:aws:iam::aws:policy/AmazonEC2ReadOnlyAccess",
        "arn:aws:iam::aws:policy/AmazonRDSReadOnlyAccess",
        "arn:aws:iam::aws:policy/CloudWatchReadOnlyAccess",
        "arn:aws:iam::aws:policy/AWSBillingReadOnlyAccess",
        "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
    ]
    for policy in policies:
        try:
            iam_client.attach_role_policy(RoleName=role_name, PolicyArn=policy)
        except Exception:
            pass

    # Add inline policy for EIP association
    eip_policy = json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": [
                "ec2:AssociateAddress",
                "ec2:DescribeAddresses"
            ],
            "Resource": "*"
        }]
    })
    try:
        iam_client.put_role_policy(
            RoleName=role_name,
            PolicyName="eip-association",
            PolicyDocument=eip_policy
        )
    except Exception:
        pass

    try:
        iam_client.get_instance_profile(InstanceProfileName=instance_profile_name)
        print(f"Using existing instance profile: {instance_profile_name}")
    except iam_client.exceptions.NoSuchEntityException:
        iam_client.create_instance_profile(InstanceProfileName=instance_profile_name)
        iam_client.add_role_to_instance_profile(
            InstanceProfileName=instance_profile_name,
            RoleName=role_name
        )
        print(f"Created instance profile: {instance_profile_name}")
        time.sleep(10)

    return instance_profile_name


def generate_user_data():
    """Generate the user data script with EIP auto-association."""
    script = f"""#!/bin/bash
set -ex
exec > /var/log/user-data.log 2>&1

# Get instance metadata
TOKEN=$(curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
INSTANCE_ID=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-id)
REGION=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)

# Associate Elastic IP
aws ec2 associate-address --instance-id $INSTANCE_ID --allocation-id {EIP_ALLOCATION_ID} --region $REGION --allow-reassociation || echo "EIP association failed, continuing..."

# Update system
dnf update -y
dnf install -y python3.11 python3.11-pip git nginx

# Clone repository
cd /opt
rm -rf aws-monitor
git clone {GITHUB_REPO} aws-monitor
cd /opt/aws-monitor

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install streamlit boto3 pandas plotly

# Create streamlit service
cat > /etc/systemd/system/aws-monitor.service << 'SVCFILE'
[Unit]
Description=AWS Monitor Streamlit App
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/aws-monitor
ExecStart=/opt/aws-monitor/venv/bin/streamlit run app_v2.py --server.address 127.0.0.1 --server.port 8501
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCFILE

# Configure nginx as reverse proxy
cat > /etc/nginx/conf.d/aws-monitor.conf << 'NGINXCONF'
server {{
    listen 80;
    server_name _;

    location / {{
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }}

    location /_stcore/stream {{
        proxy_pass http://127.0.0.1:8501/_stcore/stream;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }}
}}
NGINXCONF

rm -f /etc/nginx/conf.d/default.conf

# Start services
systemctl daemon-reload
systemctl enable aws-monitor nginx
systemctl start aws-monitor
systemctl start nginx

echo "Deployment complete!"
"""
    return script


def create_launch_template(ec2_client, sg_id, instance_profile, ami_id):
    """Create or update launch template."""
    template_name = "aws-monitor-template"
    user_data = generate_user_data()

    import base64
    user_data_b64 = base64.b64encode(user_data.encode()).decode()

    launch_template_data = {
        'ImageId': ami_id,
        'InstanceType': INSTANCE_TYPE,
        'SecurityGroupIds': [sg_id],
        'IamInstanceProfile': {'Name': instance_profile},
        'UserData': user_data_b64,
        'TagSpecifications': [{
            'ResourceType': 'instance',
            'Tags': [
                {'Key': 'Name', 'Value': 'aws-monitor'},
                {'Key': 'Project', 'Value': 'aws-monitor'}
            ]
        }],
    }

    try:
        # Try to create new version of existing template
        response = ec2_client.create_launch_template_version(
            LaunchTemplateName=template_name,
            LaunchTemplateData=launch_template_data,
            SourceVersion='$Latest'
        )
        version = response['LaunchTemplateVersion']['VersionNumber']

        # Set as default version
        ec2_client.modify_launch_template(
            LaunchTemplateName=template_name,
            DefaultVersion=str(version)
        )
        print(f"Updated launch template: {template_name} (version {version})")

    except ec2_client.exceptions.ClientError as e:
        if 'InvalidLaunchTemplateName.NotFoundException' in str(e):
            response = ec2_client.create_launch_template(
                LaunchTemplateName=template_name,
                LaunchTemplateData=launch_template_data
            )
            print(f"Created launch template: {template_name}")
        else:
            raise

    return template_name


def create_auto_scaling_group(asg_client, template_name, subnet_ids):
    """Create or update Auto Scaling Group with spot instances."""
    asg_name = "aws-monitor-asg"

    # Check if ASG exists
    response = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])

    mixed_instances_policy = {
        'LaunchTemplate': {
            'LaunchTemplateSpecification': {
                'LaunchTemplateName': template_name,
                'Version': '$Latest'
            },
        },
        'InstancesDistribution': {
            'OnDemandBaseCapacity': 0,
            'OnDemandPercentageAboveBaseCapacity': 0,  # 100% spot
            'SpotAllocationStrategy': 'price-capacity-optimized',
        }
    }

    if response['AutoScalingGroups']:
        # Update existing ASG
        asg_client.update_auto_scaling_group(
            AutoScalingGroupName=asg_name,
            MixedInstancesPolicy=mixed_instances_policy,
            MinSize=1,
            MaxSize=1,
            DesiredCapacity=1,
            VPCZoneIdentifier=','.join(subnet_ids),
        )
        print(f"Updated Auto Scaling Group: {asg_name}")

        # Force instance refresh to apply new launch template
        try:
            asg_client.start_instance_refresh(
                AutoScalingGroupName=asg_name,
                Strategy='Rolling',
                Preferences={
                    'MinHealthyPercentage': 0,
                    'InstanceWarmup': 120
                }
            )
            print("Started instance refresh...")
        except Exception as e:
            if 'InstanceRefreshInProgress' not in str(e):
                print(f"Note: {e}")
    else:
        # Create new ASG
        asg_client.create_auto_scaling_group(
            AutoScalingGroupName=asg_name,
            MixedInstancesPolicy=mixed_instances_policy,
            MinSize=1,
            MaxSize=1,
            DesiredCapacity=1,
            VPCZoneIdentifier=','.join(subnet_ids),
            Tags=[
                {'Key': 'Name', 'Value': 'aws-monitor', 'PropagateAtLaunch': True},
                {'Key': 'Project', 'Value': 'aws-monitor', 'PropagateAtLaunch': True},
            ],
            HealthCheckType='EC2',
            HealthCheckGracePeriod=300,
        )
        print(f"Created Auto Scaling Group: {asg_name}")

    return asg_name


def wait_for_instance(asg_client, ec2_client, asg_name):
    """Wait for ASG instance to be running."""
    print("Waiting for instance to start...")

    for _ in range(30):  # Wait up to 5 minutes
        response = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
        instances = response['AutoScalingGroups'][0].get('Instances', [])

        for inst in instances:
            if inst['LifecycleState'] == 'InService':
                instance_id = inst['InstanceId']

                # Get public IP
                ec2_response = ec2_client.describe_instances(InstanceIds=[instance_id])
                public_ip = ec2_response['Reservations'][0]['Instances'][0].get('PublicIpAddress')

                return instance_id, public_ip

        time.sleep(10)

    return None, None


def main():
    print(f"Deploying AWS Monitor to {REGION} with Auto Scaling...")

    ec2 = boto3.client('ec2', region_name=REGION)
    iam = boto3.client('iam', region_name=REGION)
    asg = boto3.client('autoscaling', region_name=REGION)

    # Get AMI
    ami_id = get_latest_ami(ec2)
    if not ami_id:
        print("ERROR: Could not find Amazon Linux 2023 AMI")
        sys.exit(1)
    print(f"Using AMI: {ami_id}")

    # Get subnets
    subnet_ids = get_default_vpc_subnets(ec2)
    print(f"Using subnets: {subnet_ids}")

    # Create security group
    sg_id = create_security_group(ec2)

    # Create IAM role
    instance_profile = create_iam_role(iam)

    # Create launch template
    template_name = create_launch_template(ec2, sg_id, instance_profile, ami_id)

    # Create/update ASG
    asg_name = create_auto_scaling_group(asg, template_name, subnet_ids)

    # Wait for instance
    instance_id, public_ip = wait_for_instance(asg, ec2, asg_name)

    print("\n" + "="*50)
    print("DEPLOYMENT COMPLETE!")
    print("="*50)
    print(f"\nAuto Scaling Group: {asg_name}")
    print(f"Instance ID: {instance_id}")
    print(f"Elastic IP: 54.151.150.4")
    print(f"\nThe app will be available at:")
    print(f"  http://54.151.150.4")
    print(f"  http://monitoring.thedaydreamer.ai")
    print(f"\nNote: It may take 2-3 minutes for the app to fully start.")
    print("\nThe ASG will automatically launch a new instance if the spot")
    print("instance is terminated, and it will bind to the same Elastic IP.")


if __name__ == "__main__":
    main()
