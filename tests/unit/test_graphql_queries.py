import pytest

from cloud_manager import CloudManager
from graphql_schema import schema
from tests.unit.fakes import FakeProvider


@pytest.fixture
def manager():
    aws = FakeProvider('aws', cost_per_instance=12.5)
    azure = FakeProvider('azure', cost_per_instance=7.25)
    mgr = CloudManager({}, providers={'aws': aws, 'azure': azure})
    mgr.provision('aws', {'name': 'a1', 'size': 't2.micro'})
    mgr.provision('azure', {'name': 'z1', 'size': 'Standard_B1s'})
    mgr.provision('azure', {'name': 'z2', 'size': 'Standard_B2s'})
    return mgr


def run(manager, query, variables=None):
    return schema.execute(query, root=manager, variables=variables)


def test_providers_returns_both_names(manager):
    result = run(manager, '{ providers }')
    assert result.errors is None
    assert result.data == {'providers': ['aws', 'azure']}


def test_instances_merges_both_providers(manager):
    result = run(manager, '{ instances { id provider type } }')
    assert result.errors is None
    rows = sorted((i['id'], i['provider'], i['type'])
                  for i in result.data['instances'])
    assert rows == [
        ('aws-1', 'aws', 't2.micro'),
        ('azure-1', 'azure', 'Standard_B1s'),
        ('azure-2', 'azure', 'Standard_B2s'),
    ]


def test_instances_filtered_by_provider(manager):
    result = run(manager, '{ instances(provider: "aws") { id name provider } }')
    assert result.errors is None
    assert result.data == {
        'instances': [{'id': 'aws-1', 'name': 'a1', 'provider': 'aws'}],
    }


def test_instances_filter_accepts_variables(manager):
    result = run(
        manager,
        'query($p: String) { instances(provider: $p) { name } }',
        variables={'p': 'azure'},
    )
    assert result.errors is None
    assert sorted(i['name'] for i in result.data['instances']) == ['z1', 'z2']


def test_instances_unknown_provider_is_a_graphql_error(manager):
    result = run(manager, '{ instances(provider: "gcp") { id } }')
    assert result.errors
    assert result.errors[0].message == 'Unknown provider: gcp'


def test_costs_match_cloud_manager(manager):
    result = run(
        manager, '{ costs { breakdown { provider monthly } total currency } }')
    assert result.errors is None

    expected = manager.get_costs()
    costs = result.data['costs']
    assert costs['breakdown'] == [
        {'provider': 'aws', 'monthly': expected['aws']},
        {'provider': 'azure', 'monthly': expected['azure']},
    ]
    assert costs['total'] == expected['total'] == 27.0
    assert costs['currency'] == 'USD'


def test_costs_report_completeness(manager):
    result = run(manager, '{ costs { complete breakdown { provider unpricedSizes } } }')
    assert result.errors is None
    assert result.data['costs'] == {
        'complete': True,
        'breakdown': [{'provider': 'aws', 'unpricedSizes': []},
                      {'provider': 'azure', 'unpricedSizes': []}],
    }


def test_costs_flag_unpriced_sizes():
    aws = FakeProvider('aws', cost_per_instance=12.5, unpriced_sizes=['x9.huge'])
    mgr = CloudManager({}, providers={'aws': aws})
    mgr.provision('aws', {'name': 'a1', 'size': 'x9.huge'})
    result = run(mgr, '{ costs { total complete breakdown { provider monthly '
                      'unpricedSizes } } }')
    assert result.errors is None
    assert result.data['costs'] == {
        'total': 0.0, 'complete': False,
        'breakdown': [{'provider': 'aws', 'monthly': 0.0,
                       'unpricedSizes': ['x9.huge']}],
    }
