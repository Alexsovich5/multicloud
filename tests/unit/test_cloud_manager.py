import pytest

from cloud_manager import CloudManager
from providers.base import CloudProvider, normalize_instance
from tests.unit.fakes import FakeProvider


@pytest.fixture
def manager():
    aws = FakeProvider('aws', cost_per_instance=10.004)
    azure = FakeProvider('azure', cost_per_instance=20.333)
    return CloudManager({}, providers={'aws': aws, 'azure': azure})


def test_list_resources_merges_all_providers(manager):
    manager.provision('aws', {'name': 'a1'})
    manager.provision('azure', {'name': 'z1'})
    manager.provision('azure', {'name': 'z2'})

    names = sorted(i['name'] for i in manager.list_resources())
    assert names == ['a1', 'z1', 'z2']


def test_list_resources_filtered_by_provider(manager):
    manager.provision('aws', {'name': 'a1'})
    manager.provision('azure', {'name': 'z1'})

    result = manager.list_resources('azure')
    assert [i['name'] for i in result] == ['z1']
    assert all(i['provider'] == 'azure' for i in result)


def test_provision_dispatches_to_named_provider(manager):
    created = manager.provision('azure', {'name': 'web1', 'size': 'Standard_B2s'})

    assert created['provider'] == 'azure'
    assert created['type'] == 'Standard_B2s'
    assert manager.providers['azure'].instances
    assert manager.providers['aws'].instances == {}


def test_destroy_dispatches_to_named_provider(manager):
    created = manager.provision('aws', {'name': 'a1'})

    assert manager.destroy('aws', created['id']) is True
    assert manager.list_resources('aws') == []


@pytest.mark.parametrize('call', [
    lambda m: m.list_resources('gcp'),
    lambda m: m.provision('gcp', {'name': 'x'}),
    lambda m: m.destroy('gcp', 'i-1'),
])
def test_unknown_provider_raises_value_error(manager, call):
    with pytest.raises(ValueError) as exc:
        call(manager)
    assert str(exc.value) == 'Unknown provider: gcp'


@pytest.mark.parametrize('spec', [{}, {'name': ''}, {'size': 't2.micro'}])
def test_provision_requires_name(manager, spec):
    with pytest.raises(ValueError):
        manager.provision('aws', spec)
    assert manager.list_resources() == []


def test_get_costs_per_provider_and_rounded_total(manager):
    manager.provision('aws', {'name': 'a1'})
    manager.provision('azure', {'name': 'z1'})
    manager.provision('azure', {'name': 'z2'})

    costs = manager.get_costs()
    assert costs['aws'] == 10.0
    assert costs['azure'] == 40.67
    assert costs['total'] == round(costs['aws'] + costs['azure'], 2) == 50.67


def test_provider_names(manager):
    assert sorted(manager.provider_names()) == ['aws', 'azure']


def test_empty_config_gives_no_providers():
    manager = CloudManager({})
    assert manager.provider_names() == []
    assert manager.list_resources() == []
    assert manager.get_costs() == {'total': 0.0}


def test_base_provider_methods_are_abstract():
    provider = CloudProvider()
    with pytest.raises(NotImplementedError):
        provider.list_instances()
    with pytest.raises(NotImplementedError):
        provider.create_instance({'name': 'x'})
    with pytest.raises(NotImplementedError):
        provider.destroy_instance('x')
    with pytest.raises(NotImplementedError):
        provider.get_monthly_cost()


def test_normalize_instance_shape():
    inst = normalize_instance(id='i-1', provider='aws', type='t2.micro',
                              state='running', region='us-east-1')
    assert inst == {
        'id': 'i-1', 'name': '', 'provider': 'aws', 'type': 't2.micro',
        'state': 'running', 'ip': None, 'region': 'us-east-1',
    }


def test_normalize_instance_rejects_unknown_field():
    with pytest.raises(TypeError):
        normalize_instance(id='i-1', provider='aws', type='t2.micro',
                           state='running', region='us-east-1', zone='a')
