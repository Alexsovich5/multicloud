import os

import boto3
import pytest
from moto import mock_ec2

from pricing import PriceTable
from providers.aws_provider import AWSProvider
from providers.base import CloudProvider, INSTANCE_FIELDS, InstanceNotFound

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PRICING_FILE = os.path.join(REPO_ROOT, 'config', 'pricing.yaml')

CONFIG = {
    'region': 'us-east-1',
    'default_image': 'ami-12345678',
    'default_size': 't2.micro',
}


@pytest.fixture
def provider():
    with mock_ec2():
        yield AWSProvider(dict(CONFIG), price_table=PriceTable.from_file(PRICING_FILE))


def test_is_a_cloud_provider(provider):
    assert isinstance(provider, CloudProvider)
    assert provider.name == 'aws'


def test_create_returns_normalized_instance(provider):
    inst = provider.create_instance({'name': 'web-1', 'size': 't2.medium'})
    assert set(inst) == set(INSTANCE_FIELDS)
    assert inst['provider'] == 'aws'
    assert inst['name'] == 'web-1'
    assert inst['type'] == 't2.medium'
    assert inst['state'] in ('pending', 'running')
    assert inst['region'] == 'us-east-1'
    assert inst['id'].startswith('i-')


def test_create_uses_configured_defaults(provider):
    inst = provider.create_instance({'name': 'plain'})
    assert inst['type'] == 't2.micro'
    described = provider.client.describe_instances(InstanceIds=[inst['id']])
    assert described['Reservations'][0]['Instances'][0]['ImageId'] == 'ami-12345678'


def test_list_shows_created_instance(provider):
    created = provider.create_instance({'name': 'web-1'})
    listed = provider.list_instances()
    assert [i['id'] for i in listed] == [created['id']]
    assert listed[0]['name'] == 'web-1'
    assert listed[0]['provider'] == 'aws'


def test_destroyed_instance_is_gone_from_list(provider):
    keep = provider.create_instance({'name': 'keep'})
    drop = provider.create_instance({'name': 'drop'})
    assert provider.destroy_instance(drop['id']) is True
    assert [i['id'] for i in provider.list_instances()] == [keep['id']]


def test_destroy_unknown_id_raises_key_error(provider):
    with pytest.raises(KeyError):
        provider.destroy_instance('i-0123456789abcdef0')


def test_cost_of_running_instances(provider):
    provider.create_instance({'name': 'a', 'size': 't2.micro'})
    provider.create_instance({'name': 'b', 'size': 't2.micro'})
    assert provider.get_monthly_cost() == round(2 * 0.0116 * 730, 2)


def test_cost_ignores_stopped_and_terminated(provider):
    running = provider.create_instance({'name': 'run', 'size': 'm4.large'})
    stopped = provider.create_instance({'name': 'stop', 'size': 'm4.large'})
    gone = provider.create_instance({'name': 'gone', 'size': 'm4.large'})
    provider.client.stop_instances(InstanceIds=[stopped['id']])
    provider.destroy_instance(gone['id'])
    assert running['id']
    assert provider.get_monthly_cost() == round(0.10 * 730, 2)


def test_cost_without_price_table_is_zero():
    with mock_ec2():
        provider = AWSProvider(dict(CONFIG))
        provider.create_instance({'name': 'a'})
        assert provider.get_monthly_cost() == 0.0


def test_endpoint_url_reaches_boto3_client():
    config = dict(CONFIG, endpoint_url='http://moto:5000')
    provider = AWSProvider(config)
    assert provider.client.meta.endpoint_url == 'http://moto:5000'
    assert provider.ec2.meta.client.meta.endpoint_url == 'http://moto:5000'


def test_injected_session_is_used():
    session = boto3.session.Session(region_name='eu-west-1')
    provider = AWSProvider({'region': 'eu-west-1'}, session=session)
    assert provider.client.meta.region_name == 'eu-west-1'
    assert provider.region == 'eu-west-1'


def test_cost_estimate_reports_unpriced_sizes(provider):
    provider.create_instance({'name': 'a', 'size': 't2.micro'})
    provider.create_instance({'name': 'b', 'size': 'x9.huge'})
    assert provider.get_cost_estimate() == {
        'monthly': round(0.0116 * 730, 2), 'unpriced': ['x9.huge']}


def test_cost_estimate_without_price_table_marks_everything_unpriced():
    with mock_ec2():
        provider = AWSProvider(dict(CONFIG))
        provider.create_instance({'name': 'a'})
        assert provider.get_cost_estimate() == {
            'monthly': 0.0, 'unpriced': ['t2.micro']}


def test_destroy_unknown_id_raises_instance_not_found(provider):
    with pytest.raises(InstanceNotFound) as err:
        provider.destroy_instance('i-0123456789abcdef0')
    assert str(err.value) == 'Unknown instance: i-0123456789abcdef0'
