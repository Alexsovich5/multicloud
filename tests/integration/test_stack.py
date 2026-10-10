"""
End-to-end flow over HTTP: the API provisions on moto (EC2) and fake ARM
(Azure), lists and prices the instances, then destroys them.
"""

import pytest
import requests

PROVISION = '''
mutation($provider: String!, $name: String!) {
  provisionInstance(provider: $provider, name: $name) {
    id name provider state
  }
}
'''

DESTROY = '''
mutation($provider: String!, $id: String!) {
  destroyInstance(provider: $provider, id: $id) { ok id }
}
'''

INSTANCES = '{ instances { id name provider } }'

COSTS = ('{ costs { total currency complete '
         'breakdown { provider monthly unpricedSizes } } }')


@pytest.fixture(scope='module')
def created(api_url):
    """Holds the instances provisioned by the first test for the later ones."""
    return {}


def _ids(instances):
    return {(i['provider'], i['id']) for i in instances}


def test_provision_on_both_clouds(gql, created):
    for provider, name in (('aws', 'web-aws'), ('azure', 'web-azure')):
        data = gql(PROVISION, {'provider': provider, 'name': name})
        inst = data['provisionInstance']
        assert inst['provider'] == provider
        assert inst['name'] == name
        assert inst['id']
        created[provider] = inst['id']
    assert set(created) == {'aws', 'azure'}


def test_instances_lists_both_providers(gql, created):
    instances = gql(INSTANCES)['instances']
    assert {i['provider'] for i in instances} >= {'aws', 'azure'}
    ids = _ids(instances)
    for provider, inst_id in created.items():
        assert (provider, inst_id) in ids
    names = {i['name'] for i in instances}
    assert {'web-aws', 'web-azure'} <= names


def test_costs_total_is_sum_of_breakdown(gql, created):
    costs = gql(COSTS)['costs']
    breakdown = {b['provider']: b['monthly'] for b in costs['breakdown']}
    assert set(breakdown) == {'aws', 'azure'}
    assert breakdown['aws'] > 0
    assert breakdown['azure'] > 0
    assert costs['total'] == pytest.approx(sum(breakdown.values()))
    assert costs['total'] > 0
    assert costs['complete'] is True
    assert all(b['unpricedSizes'] == [] for b in costs['breakdown'])


def test_destroy_unknown_instance_names_only_the_id(api_url, api_key):
    resp = requests.post(
        api_url + '/graphql',
        json={'query': 'mutation { destroyInstance(provider: "azure", '
                       'id: "no-such-vm") { ok } }'},
        headers={'Authorization': 'Bearer ' + api_key}, timeout=30)
    assert resp.status_code == 200
    assert resp.json()['errors'][0]['message'] == 'Unknown instance: no-such-vm'


def test_destroy_removes_both(gql, created):
    assert set(created) == {'aws', 'azure'}
    for provider, inst_id in created.items():
        data = gql(DESTROY, {'provider': provider, 'id': inst_id})
        assert data['destroyInstance'] == {'ok': True, 'id': inst_id}

    ids = _ids(gql(INSTANCES)['instances'])
    for provider, inst_id in created.items():
        assert (provider, inst_id) not in ids


@pytest.mark.parametrize('headers', [
    {}, {'Authorization': 'Bearer not-the-key-0123456789abcdef'},
])
def test_api_refuses_requests_without_the_key(api_url, gql, headers):
    resp = requests.post(
        api_url + '/graphql',
        json={'query': 'mutation { provisionInstance(provider: "aws", '
                       'name: "intruder") { id } }'},
        headers=headers, timeout=30)
    assert resp.status_code == 401
    names = {i['name'] for i in gql(INSTANCES)['instances']}
    assert 'intruder' not in names
