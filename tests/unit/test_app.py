import json
import logging

import pytest

from app import create_app
from auth import ApiKeyError
from cloud_manager import CloudManager
from tests.unit.fakes import FakeProvider

API_KEY = 'unit-test-key-0123456789abcdef'
AUTH = {'Authorization': 'Bearer ' + API_KEY}
SENTINEL = 'S3NTINEL-pw'


@pytest.fixture
def manager():
    return CloudManager({}, providers={
        'aws': FakeProvider('aws', cost_per_instance=10.0),
        'azure': FakeProvider('azure', cost_per_instance=5.0),
    })


@pytest.fixture
def client(manager):
    app = create_app(manager, api_key=API_KEY)
    app.testing = True
    return app.test_client()


def post_query(client, query, variables=None, headers=AUTH):
    body = {'query': query}
    if variables is not None:
        body['variables'] = variables
    return client.post('/graphql', data=json.dumps(body),
                       content_type='application/json', headers=headers)


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
    monkeypatch.setenv('MC_API_KEY', API_KEY)
    app = create_app()
    response = app.test_client().get('/healthz')
    assert calls == [True]
    assert json.loads(response.get_data(as_text=True))['providers'] == ['aws']


PROVISION = 'mutation { provisionInstance(provider: "aws", name: "x1") { id } }'
DESTROY = 'mutation { destroyInstance(provider: "aws", id: "aws-1") { ok } }'
READS = ['{ providers }', '{ instances { id } }', '{ costs { total } }']


def test_create_app_refuses_to_start_without_an_api_key(monkeypatch, manager):
    monkeypatch.delenv('MC_API_KEY', raising=False)
    monkeypatch.delenv('MC_API_KEY_FILE', raising=False)
    with pytest.raises(ApiKeyError):
        create_app(manager)


def test_create_app_reads_the_key_from_the_environment(monkeypatch, manager):
    monkeypatch.setenv('MC_API_KEY', API_KEY)
    client = create_app(manager).test_client()
    assert post_query(client, '{ providers }').status_code == 200
    assert post_query(client, '{ providers }', headers={}).status_code == 401


@pytest.mark.parametrize('headers', [
    {},
    {'Authorization': 'Bearer wrong-key-0123456789abcdef'},
    {'Authorization': 'Bearer ' + API_KEY[:-1]},
    {'Authorization': 'Basic ' + API_KEY},
    {'Authorization': API_KEY},
], ids=['missing', 'wrong', 'prefix', 'basic', 'no-scheme'])
@pytest.mark.parametrize('query', [PROVISION, DESTROY] + READS)
def test_graphql_refuses_requests_without_the_right_key(client, manager,
                                                        headers, query):
    manager.provision('aws', {'name': 'keep'})
    response = post_query(client, query, headers=headers)
    assert response.status_code == 401
    assert response.headers['WWW-Authenticate'] == 'Bearer'
    payload = json.loads(response.get_data(as_text=True))
    assert payload == {'errors': [{'message': 'Unauthorized'}]}
    assert [i['name'] for i in manager.list_resources()] == ['keep']


@pytest.mark.parametrize('query', READS)
def test_get_queries_need_the_key_too(client, query):
    url = '/graphql?query=' + query
    assert client.get(url).status_code == 401
    response = client.get(url, headers=AUTH)
    assert response.status_code == 200
    assert 'data' in json.loads(response.get_data(as_text=True))


def test_mutations_work_with_the_right_key(client, manager):
    assert post_query(client, PROVISION).status_code == 200
    assert [i['name'] for i in manager.list_resources()] == ['x1']
    response = post_query(client, 'mutation { destroyInstance(provider: "aws", '
                                  'id: "aws-1") { ok } }')
    assert json.loads(response.get_data(as_text=True)) == {
        'data': {'destroyInstance': {'ok': True}}}
    assert manager.list_resources() == []


def test_cross_origin_form_post_is_refused(client, manager):
    response = client.post('/graphql', data={'query': PROVISION}, headers={
        'Origin': 'http://evil.example', 'Referer': 'http://evil.example/'})
    assert response.status_code == 401
    assert manager.list_resources() == []


@pytest.mark.parametrize('content_type', [
    'application/x-www-form-urlencoded', 'multipart/form-data',
    'text/plain', 'application/graphql',
])
def test_post_must_be_json_even_with_the_key(client, manager, content_type):
    if content_type == 'application/graphql':
        data = PROVISION
    elif content_type == 'text/plain':
        data = json.dumps({'query': PROVISION})
    else:
        data = {'query': PROVISION}
    response = client.post('/graphql', data=data, headers=AUTH,
                           content_type=content_type)
    assert response.status_code == 415
    assert manager.list_resources() == []


@pytest.mark.parametrize('method', ['put', 'delete', 'patch'])
def test_other_methods_are_not_allowed(client, manager, method):
    response = getattr(client, method)(
        '/graphql', data=json.dumps({'query': PROVISION}), headers=AUTH,
        content_type='application/json')
    assert response.status_code == 405
    assert manager.list_resources() == []


def test_graphiql_page_is_static_and_runs_no_query(client, manager):
    calls = []
    original = manager.list_resources
    manager.list_resources = lambda *a: calls.append(a) or original(*a)
    response = client.get(
        '/graphql?query=%7B%20instances%20%7B%20id%20%7D%20%7D',
        headers={'Accept': 'text/html'})
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert 'graphiql' in text.lower()
    assert 'instances' not in text
    assert 'Authorization' in text
    assert 'sessionStorage' in text
    assert calls == []


def test_responses_forbid_framing_and_sniffing(client):
    for response in (client.get('/healthz'),
                     client.get('/graphql', headers={'Accept': 'text/html'}),
                     post_query(client, '{ providers }')):
        assert response.headers['X-Frame-Options'] == 'DENY'
        assert response.headers['X-Content-Type-Options'] == 'nosniff'


class BrokenProvider(FakeProvider):
    def list_instances(self):
        raise RuntimeError(
            'GET http://admin:%s@moto:5000/ failed in /app/src/x.py' % SENTINEL)


def test_unexpected_errors_are_masked_in_responses(caplog):
    manager = CloudManager({}, providers={'aws': BrokenProvider('aws')})
    client = create_app(manager, api_key=API_KEY).test_client()
    with caplog.at_level(logging.ERROR, logger='app'):
        response = post_query(client, '{ instances { id } }')
    text = response.get_data(as_text=True)
    assert SENTINEL not in text
    assert '/app/src' not in text
    payload = json.loads(text)
    assert payload['errors'][0]['message'] == 'Internal server error'
    assert any('RuntimeError' in r.getMessage() for r in caplog.records
               if r.name == 'app')
    assert not any(SENTINEL in r.getMessage() for r in caplog.records
                   if r.name == 'app')
    assert SENTINEL not in caplog.text
    assert '/app/src' not in caplog.text


def test_expected_errors_keep_their_message(client):
    response = post_query(client, '{ instances(provider: "gcp") { id } }')
    payload = json.loads(response.get_data(as_text=True))
    assert payload['errors'][0]['message'] == 'Unknown provider: gcp'


def test_the_key_is_never_echoed_or_logged(client, caplog):
    with caplog.at_level(logging.DEBUG):
        response = post_query(client, '{ providers }', headers={
            'Authorization': 'Bearer ' + SENTINEL + '-0123456789'})
        ok = post_query(client, '{ instances(provider: "gcp") { id } }')
    for resp in (response, ok):
        text = resp.get_data(as_text=True) + str(resp.headers)
        assert SENTINEL not in text
        assert API_KEY not in text
    assert SENTINEL not in caplog.text
    assert API_KEY not in caplog.text


class LeakyValueErrorProvider(FakeProvider):
    """An SDK ValueError (e.g. requests InvalidURL) carrying a secret URL."""

    def list_instances(self):
        raise ValueError('Invalid URL http://admin:%s@moto:5000/' % SENTINEL)


class LeakyKeyErrorProvider(FakeProvider):
    """A KeyError from inside an SDK response parser."""

    def list_instances(self):
        raise KeyError('/app/src/x.py ' + SENTINEL)


@pytest.mark.parametrize('provider_class', [LeakyValueErrorProvider,
                                            LeakyKeyErrorProvider])
def test_sdk_value_and_key_errors_are_masked_too(provider_class, caplog):
    manager = CloudManager({}, providers={'aws': provider_class('aws')})
    client = create_app(manager, api_key=API_KEY).test_client()
    with caplog.at_level(logging.DEBUG):
        response = post_query(client, '{ instances { id } }')
    text = response.get_data(as_text=True)
    assert SENTINEL not in text
    assert json.loads(text)['errors'][0]['message'] == 'Internal server error'
    assert SENTINEL not in caplog.text


def test_unknown_instance_error_names_only_the_id(client):
    response = post_query(client, 'mutation { destroyInstance(provider: "aws", '
                                  'id: "aws-9") { ok } }')
    payload = json.loads(response.get_data(as_text=True))
    assert payload['errors'][0]['message'] == 'Unknown instance: aws-9'


def test_invalid_name_error_is_returned(client):
    response = post_query(client, 'mutation { provisionInstance(provider: "aws", '
                                  'name: "../x") { id } }')
    payload = json.loads(response.get_data(as_text=True))
    assert payload['errors'][0]['message'].startswith('Invalid instance name')


def test_graphiql_page_does_not_prefill_queries_from_the_url(client):
    text = client.get('/graphql', headers={'Accept': 'text/html'}).get_data(
        as_text=True)
    assert 'location.search' not in text
    assert 'URLSearchParams' not in text
