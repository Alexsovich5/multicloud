"""
AWS Cloud Provider
"""

import boto3
import logging

logger = logging.getLogger('aws_provider')


class AWSProvider:
    """AWS resource management."""

    def __init__(self, config):
        self.region = config.get('region', 'us-east-1')
        self.ec2 = boto3.resource('ec2', region_name=self.region)
        self.client = boto3.client('ec2', region_name=self.region)

    def list_instances(self):
        """List all EC2 instances."""
        instances = []
        for inst in self.ec2.instances.all():
            name = ''
            for tag in (inst.tags or []):
                if tag['Key'] == 'Name':
                    name = tag['Value']
            instances.append({
                'id': inst.id,
                'name': name,
                'provider': 'aws',
                'type': inst.instance_type,
                'state': inst.state['Name'],
                'ip': inst.public_ip_address,
                'region': self.region
            })
        return instances

    def create_instance(self, spec):
        """Launch an EC2 instance."""
        instances = self.ec2.create_instances(
            ImageId=spec.get('ami', 'ami-0c55b159cbfafe1f0'),
            InstanceType=spec.get('type', 't3.medium'),
            MinCount=1, MaxCount=1,
            TagSpecifications=[{
                'ResourceType': 'instance',
                'Tags': [{'Key': 'Name', 'Value': spec.get('name', 'multicloud')}]
            }]
        )
        return {'id': instances[0].id, 'provider': 'aws'}

    def destroy_instance(self, instance_id):
        """Terminate an EC2 instance."""
        self.client.terminate_instances(InstanceIds=[instance_id])
        return True

    def get_monthly_cost(self):
        """Estimate monthly cost (simplified)."""
        count = len(list(self.ec2.instances.filter(
            Filters=[{'Name': 'instance-state-name', 'Values': ['running']}]
        )))
        return count * 50.0  # rough estimate
