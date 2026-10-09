import json

import pytest

from app import create_app
from cloud_manager import CloudManager
from tests.unit.fakes import FakeProvider


@pytest.fixture
def client():
    manager = CloudManager({}, providers={
        'aws': FakeProvider('aws', cost_per_instance=10.0),
        'azure': FakeProvider('azure', cost_per_instance=5.0),
    })
    app = create_app(manager)
    app.testing = True
    return app.test_client()


def post_query(client, query, variables=None):
    body = {'query': query}
    if variables is not None:
        body['variables'] = variables
    return client.post('/graphql', data=json.dumps(body),
                       content_type='application/json')


def test_post_graphql_returns_data(client):
    response = post_query(client, '{ providers }')
    assert response.status_code == 200
    payload = json.loads(response.get_data(as_text=True))
    assert payload == {'data': {'providers': ['aws', 'azure']}}


def test_post_graphql_mutation_with_variables(client):
    response = post_query(
        client,
        'mutation($p: String!) { provisionInstance(provider: $p, name: "w1") '
        '{ id provider name } }',
        variables={'p': 'azure'},
    )
    assert response.status_code == 200
    payload = json.loads(response.get_data(as_text=True))
    assert payload['data']['provisionInstance'] == {
        'id': 'azure-1', 'provider': 'azure', 'name': 'w1',
    }


def test_get_graphql_serves_graphiql_for_browsers(client):
    response = client.get('/graphql', headers={'Accept': 'text/html'})
    assert response.status_code == 200
    assert response.mimetype == 'text/html'
    assert 'graphiql' in response.get_data(as_text=True).lower()


def test_healthz_lists_providers(client):
    response = client.get('/healthz')
    assert response.status_code == 200
    assert response.mimetype == 'application/json'
    assert json.loads(response.get_data(as_text=True)) == {
        'status': 'ok', 'providers': ['aws', 'azure'],
    }


def test_malformed_query_returns_400_with_errors(client):
    response = post_query(client, '{ providers ')
    assert response.status_code == 400
    payload = json.loads(response.get_data(as_text=True))
    assert payload['errors']
    assert 'Syntax Error' in payload['errors'][0]['message']


def test_create_app_without_manager_builds_one_from_config(monkeypatch):
    built = CloudManager({}, providers={'aws': FakeProvider('aws')})
    calls = []

    def fake_build_manager():
        calls.append(True)
        return built

    monkeypatch.setattr('app.build_manager', fake_build_manager)
    app = create_app()
    response = app.test_client().get('/healthz')
    assert calls == [True]
    assert json.loads(response.get_data(as_text=True))['providers'] == ['aws']
