import os

import pytest
import requests

from pricing import PriceTable
from providers.azure_provider import AzureProvider
from providers.base import CloudProvider, INSTANCE_FIELDS

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PRICING_FILE = os.path.join(REPO_ROOT, 'config', 'pricing.yaml')

SUBSCRIPTION = '00000000-0000-0000-0000-000000000000'
RESOURCE_GROUP = 'multicloud-test-rg'
CREDENTIAL_VARS = ('AZURE_CLIENT_ID', 'AZURE_CLIENT_SECRET', 'AZURE_TENANT_ID')


def make_config(base_url=None):
    config = {
        'subscription_id': SUBSCRIPTION,
        'resource_group': RESOURCE_GROUP,
        'location': 'eastus',
        'default_size': 'Standard_B1s',
    }
    if base_url:
        config['base_url'] = base_url
    return config


@pytest.fixture
def provider(fake_arm_url):
    return AzureProvider(make_config(fake_arm_url),
                         price_table=PriceTable.from_file(PRICING_FILE))


def rg_status(base_url):
    url = '%s/subscriptions/%s/resourcegroups/%s' % (base_url, SUBSCRIPTION, RESOURCE_GROUP)
    return requests.get(url).status_code


def test_is_a_cloud_provider(provider):
    assert isinstance(provider, CloudProvider)
    assert provider.name == 'azure'


def test_create_returns_normalized_instance(provider):
    inst = provider.create_instance({'name': 'web1', 'size': 'Standard_B2s'})
    assert set(inst) == set(INSTANCE_FIELDS)
    assert inst['provider'] == 'azure'
    assert inst['id'] == 'web1'
    assert inst['name'] == 'web1'
    assert inst['type'] == 'Standard_B2s'
    assert inst['state'] == 'running'
    assert inst['region'] == 'eastus'
    assert inst['ip'] is None


def test_create_uses_default_size(provider):
    inst = provider.create_instance({'name': 'plain'})
    assert inst['type'] == 'Standard_B1s'


def test_first_create_makes_resource_group(provider, fake_arm_url):
    assert rg_status(fake_arm_url) == 404
    provider.create_instance({'name': 'web1'})
    assert rg_status(fake_arm_url) == 200


def test_list_shows_created_vm(provider):
    assert provider.list_instances() == []
    created = provider.create_instance({'name': 'web1', 'size': 'Standard_B2s'})
    assert provider.list_instances() == [created]


def test_list_without_resource_group_is_empty(provider):
    assert provider.list_instances() == []


def test_destroy_removes_vm(provider):
    provider.create_instance({'name': 'keep'})
    provider.create_instance({'name': 'drop'})
    assert provider.destroy_instance('drop') is True
    assert [i['id'] for i in provider.list_instances()] == ['keep']


def test_destroy_unknown_name_raises_key_error(provider):
    provider.create_instance({'name': 'web1'})
    with pytest.raises(KeyError):
        provider.destroy_instance('missing')


def test_cost_of_one_b2s(provider):
    provider.create_instance({'name': 'web1', 'size': 'Standard_B2s'})
    assert provider.get_monthly_cost() == round(0.0416 * 730, 2)


def test_cost_without_price_table_is_zero(fake_arm_url):
    provider = AzureProvider(make_config(fake_arm_url))
    provider.create_instance({'name': 'web1', 'size': 'Standard_B2s'})
    assert provider.get_monthly_cost() == 0.0


def test_missing_credentials_raise_value_error(monkeypatch):
    for var in CREDENTIAL_VARS:
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ValueError) as exc:
        AzureProvider(make_config())
    message = str(exc.value)
    for var in CREDENTIAL_VARS:
        assert var in message
