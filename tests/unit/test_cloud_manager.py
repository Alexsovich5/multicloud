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


@pytest.mark.parametrize('name', [
    '../web', 'web/1', 'web\n1', 'web 1', '-web', '.web', 'w' * 65, 'web%2F1', 5,
])
def test_provision_rejects_names_unsafe_for_resource_paths(manager, name):
    with pytest.raises(ValueError):
        manager.provision('azure', {'name': name})
    assert manager.list_resources() == []


@pytest.mark.parametrize('name', ['w', 'web-1', 'Web_1.prod', 'w' * 64])
def test_provision_accepts_ordinary_names(manager, name):
    assert manager.provision('aws', {'name': name})['name'] == name


@pytest.mark.parametrize('resource_id', ['../x', 'a/b', 'a\r\nb', '', 'i' * 65])
def test_destroy_rejects_ids_unsafe_for_resource_paths(manager, resource_id):
    created = manager.provision('azure', {'name': 'z1'})
    with pytest.raises(ValueError):
        manager.destroy('azure', resource_id)
    assert [i['id'] for i in manager.list_resources()] == [created['id']]
