import pytest

from cloud_manager import CloudManager
from graphql_schema import schema
from tests.unit.fakes import FakeProvider


@pytest.fixture
def manager():
    aws = FakeProvider('aws', cost_per_instance=12.5)
    azure = FakeProvider('azure', cost_per_instance=7.25)
    mgr = CloudManager({}, providers={'aws': aws, 'azure': azure})
    mgr.provision('azure', {'name': 'z1', 'size': 'Standard_B1s'})
    return mgr


def run(manager, query, variables=None):
    return schema.execute(query, root=manager, variables=variables)


PROVISION = '''
mutation {
  provisionInstance(provider: "aws", name: "web1", size: "t2.micro") {
    id name provider type state
  }
}
'''


def test_provision_returns_instance_and_lists_it(manager):
    result = run(manager, PROVISION)
    assert result.errors is None
    assert result.data == {
        'provisionInstance': {
            'id': 'aws-1',
            'name': 'web1',
            'provider': 'aws',
            'type': 't2.micro',
            'state': 'running',
        },
    }

    listed = run(manager, '{ instances(provider: "aws") { id name } }')
    assert listed.errors is None
    assert listed.data == {'instances': [{'id': 'aws-1', 'name': 'web1'}]}


def test_provision_passes_image_to_provider(manager):
    seen = {}
    aws = manager.providers['aws']
    original = aws.create_instance

    def capture(spec):
        seen.update(spec)
        return original(spec)

    aws.create_instance = capture
    result = run(
        manager,
        'mutation { provisionInstance(provider: "aws", name: "w", image: "ami-1") { id } }',
    )
    assert result.errors is None
    assert seen == {'name': 'w', 'image': 'ami-1'}


def test_destroy_returns_ok_and_removes_instance(manager):
    result = run(
        manager,
        'mutation { destroyInstance(provider: "azure", id: "azure-1") { ok id } }',
    )
    assert result.errors is None
    assert result.data == {'destroyInstance': {'ok': True, 'id': 'azure-1'}}

    listed = run(manager, '{ instances(provider: "azure") { id } }')
    assert listed.errors is None
    assert listed.data == {'instances': []}


def test_provision_unknown_provider_is_a_graphql_error(manager):
    result = run(
        manager,
        'mutation { provisionInstance(provider: "gcp", name: "x") { id } }',
    )
    assert result.errors
    assert result.errors[0].message == 'Unknown provider: gcp'


def test_destroy_unknown_provider_is_a_graphql_error(manager):
    result = run(
        manager,
        'mutation { destroyInstance(provider: "gcp", id: "x") { ok } }',
    )
    assert result.errors
    assert result.errors[0].message == 'Unknown provider: gcp'
    assert manager.list_resources('azure')


def test_missing_name_fails_validation(manager):
    result = run(manager, 'mutation { provisionInstance(provider: "aws") { id } }')
    assert result.errors
    assert 'name' in result.errors[0].message
    assert manager.list_resources('aws') == []


def test_variables_are_passed_through(manager):
    result = run(
        manager,
        'mutation($p: String!, $n: String!) '
        '{ provisionInstance(provider: $p, name: $n) { provider name } }',
        variables={'p': 'azure', 'n': 'z2'},
    )
    assert result.errors is None
    assert result.data == {
        'provisionInstance': {'provider': 'azure', 'name': 'z2'},
    }
    names = sorted(i['name'] for i in manager.list_resources('azure'))
    assert names == ['z1', 'z2']
