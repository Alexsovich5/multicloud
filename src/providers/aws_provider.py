"""
AWS Cloud Provider

EC2 instances via boto3. Setting ``endpoint_url`` in the config points the
same code at an EC2-compatible endpoint such as moto.
"""

import logging

import boto3
from botocore.exceptions import ClientError

from providers.base import CloudProvider, InstanceNotFound, normalize_instance

logger = logging.getLogger('aws_provider')

DEFAULT_REGION = 'us-east-1'
DEFAULT_IMAGE = 'ami-12345678'
DEFAULT_SIZE = 't2.micro'
HIDDEN_STATES = ('terminated', 'shutting-down')


class AWSProvider(CloudProvider):
    """AWS resource management."""

    name = 'aws'

    def __init__(self, config, price_table=None, session=None):
        config = config or {}
        self.region = config.get('region', DEFAULT_REGION)
        self.endpoint_url = config.get('endpoint_url')
        self.default_image = config.get('default_image', DEFAULT_IMAGE)
        self.default_size = config.get('default_size', DEFAULT_SIZE)
        self.price_table = price_table
        if session is None:
            session = boto3.session.Session(region_name=self.region)
        self.session = session
        self.ec2 = session.resource('ec2', region_name=self.region,
                                    endpoint_url=self.endpoint_url)
        self.client = session.client('ec2', region_name=self.region,
                                     endpoint_url=self.endpoint_url)

    def _normalize(self, inst):
        name = ''
        for tag in (inst.tags or []):
            if tag['Key'] == 'Name':
                name = tag['Value']
        return normalize_instance(
            id=inst.id,
            name=name,
            provider=self.name,
            type=inst.instance_type,
            state=inst.state['Name'],
            ip=inst.public_ip_address,
            region=self.region,
        )

    def list_instances(self):
        """List EC2 instances that are not terminated or shutting down."""
        return [self._normalize(inst) for inst in self.ec2.instances.all()
                if inst.state['Name'] not in HIDDEN_STATES]

    def create_instance(self, spec):
        """Launch one EC2 instance tagged with ``spec['name']``."""
        instances = self.ec2.create_instances(
            ImageId=spec.get('image', self.default_image),
            InstanceType=spec.get('size', self.default_size),
            MinCount=1, MaxCount=1,
            TagSpecifications=[{
                'ResourceType': 'instance',
                'Tags': [{'Key': 'Name', 'Value': spec.get('name', 'multicloud')}]
            }]
        )
        inst = instances[0]
        inst.reload()
        return self._normalize(inst)

    def destroy_instance(self, instance_id):
        """Terminate an EC2 instance; InstanceNotFound if it does not exist."""
        try:
            found = self.client.describe_instances(InstanceIds=[instance_id])
        except ClientError as exc:
            code = exc.response.get('Error', {}).get('Code', '')
            if code.startswith('InvalidInstanceID'):
                raise InstanceNotFound(instance_id)
            raise
        if not any(r.get('Instances') for r in found.get('Reservations', [])):
            raise InstanceNotFound(instance_id)
        self.client.terminate_instances(InstanceIds=[instance_id])
        return True

    def get_cost_estimate(self):
        """Monthly cost of running instances and the sizes with no price.

        Without a price table every running instance is unpriced.
        """
        sizes = [inst.instance_type for inst in self.ec2.instances.filter(
            Filters=[{'Name': 'instance-state-name', 'Values': ['running']}]
        )]
        if self.price_table is None:
            return {'monthly': 0.0, 'unpriced': sizes}
        return {'monthly': self.price_table.monthly(self.name, sizes),
                'unpriced': self.price_table.unpriced(self.name, sizes)}

    def get_monthly_cost(self):
        """Estimated monthly cost of running instances from the price table."""
        return self.get_cost_estimate()['monthly']
