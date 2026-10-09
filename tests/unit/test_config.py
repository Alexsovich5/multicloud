import os

import pytest
from moto import mock_ec2

from cloud_manager import build_manager
from config import load_config
from pricing import PriceTable
from providers.aws_provider import AWSProvider
from providers.azure_provider import AzureProvider

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_CONFIG = os.path.join(REPO_ROOT, 'config', 'multicloud.yml')
PRICING_FILE = os.path.join(REPO_ROOT, 'config', 'pricing.yaml')


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ('MC_CONFIG', 'MC_AWS_ENDPOINT', 'MC_AZURE_BASE_URL'):
        monkeypatch.delenv(var, raising=False)


def write_config(tmpdir, text):
    path = tmpdir.join('multicloud.yml')
    path.write(text)
    return str(path)


def test_default_file_has_both_providers():
    config = load_config(DEFAULT_CONFIG)

    assert config['aws']['region'] == 'us-east-1'
    assert config['aws']['endpoint_url'] == 'http://moto:5000'
    assert config['azure']['resource_group'] == 'multicloud-demo-rg'
    assert config['azure']['base_url'] == 'http://fake-arm:5001'
    assert config['pricing_file'] == 'config/pricing.yaml'


def test_path_comes_from_mc_config(monkeypatch, tmpdir):
    path = write_config(tmpdir, 'aws:\n  region: eu-west-1\n')
    monkeypatch.setenv('MC_CONFIG', path)

    config = load_config()

    assert config['aws']['region'] == 'eu-west-1'
    assert 'azure' not in config


def test_env_overrides_endpoints(monkeypatch):
    monkeypatch.setenv('MC_AWS_ENDPOINT', 'http://localhost:20950')
    monkeypatch.setenv('MC_AZURE_BASE_URL', 'http://localhost:20951')

    config = load_config(DEFAULT_CONFIG)

    assert config['aws']['endpoint_url'] == 'http://localhost:20950'
    assert config['azure']['base_url'] == 'http://localhost:20951'


def test_disabled_provider_is_dropped(tmpdir):
    path = write_config(tmpdir, (
        'aws:\n  enabled: false\n  region: us-east-1\n'
        'azure:\n  enabled: true\n  location: eastus\n'))

    config = load_config(path)

    assert 'aws' not in config
    assert config['azure']['location'] == 'eastus'
    assert 'enabled' not in config['azure']


@pytest.fixture
def manager(tmpdir, fake_arm_url):
    path = write_config(tmpdir, (
        'aws:\n  region: us-east-1\n'
        'azure:\n'
        '  subscription_id: 00000000-0000-0000-0000-000000000000\n'
        '  resource_group: config-test-rg\n'
        '  location: eastus\n'
        '  base_url: %s\n'
        'pricing_file: %s\n') % (fake_arm_url, PRICING_FILE))
    return build_manager(path)


def test_build_manager_wires_providers(manager, fake_arm_url):
    assert manager.provider_names() == ['aws', 'azure']
    aws = manager.providers['aws']
    azure = manager.providers['azure']
    assert isinstance(aws, AWSProvider)
    assert isinstance(azure, AzureProvider)
    assert isinstance(aws.price_table, PriceTable)
    assert aws.price_table is azure.price_table
    assert aws.price_table.prices['azure']['Standard_B2s'] == 0.0416
    assert azure.base_url == fake_arm_url
    assert manager.currency == 'USD'


def test_build_manager_lists_aws_and_azure(manager):
    with mock_ec2():
        aws_instances = manager.list_resources('aws')
    assert aws_instances == []

    manager.provision('azure', {'name': 'vm1', 'size': 'Standard_B2s'})
    azure_instances = manager.list_resources('azure')
    assert [i['name'] for i in azure_instances] == ['vm1']


def test_currency_defaults_to_usd_without_price_table():
    from cloud_manager import CloudManager
    assert CloudManager({}, providers={}).currency == 'USD'


def test_currency_comes_from_price_table():
    from cloud_manager import CloudManager
    table = PriceTable({}, currency='EUR')
    assert CloudManager({}, providers={}, price_table=table).currency == 'EUR'
