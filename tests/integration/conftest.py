"""
Fixtures for the integration tests that run against the compose stack.

The tests need ``API_URL``; ``make integration`` sets it when it runs pytest
inside the compose network. Without it every test here is skipped. Before
the first test runs, the API, moto and fake ARM are polled for up to
``WAIT_SECONDS``: the API must answer ``/healthz`` with 200, and moto and
fake ARM only have to give any HTTP response. The API key is read the same
way the API reads it (``MC_API_KEY`` or the shared ``MC_API_KEY_FILE``).
"""

import os
import time

import pytest
import requests

from auth import load_api_key

WAIT_SECONDS = 60
POLL_INTERVAL = 1


def _answers(url, need_ok):
    try:
        resp = requests.get(url, timeout=2)
    except requests.RequestException:
        return False
    return resp.status_code == 200 if need_ok else True


def wait_for(url, need_ok=False, timeout=WAIT_SECONDS):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _answers(url, need_ok):
            return
        time.sleep(POLL_INTERVAL)
    raise RuntimeError('%s did not answer within %d s' % (url, timeout))


@pytest.fixture(scope='session')
def api_url():
    url = os.environ.get('API_URL')
    if not url:
        pytest.skip('API_URL is not set; run these tests with make integration')
    return url.rstrip('/')


@pytest.fixture(scope='session', autouse=True)
def stack_ready(api_url):
    moto_url = os.environ.get('MOTO_URL', 'http://moto:5000')
    fake_arm_url = os.environ.get('FAKE_ARM_URL', 'http://fake-arm:5001')
    wait_for(moto_url)
    wait_for(fake_arm_url)
    wait_for(api_url + '/healthz', need_ok=True)


@pytest.fixture(scope='session')
def api_key(stack_ready):
    return load_api_key()


@pytest.fixture
def gql(api_url, api_key):
    """POST a GraphQL query to the API and return its ``data``."""

    def run(query, variables=None):
        resp = requests.post(
            api_url + '/graphql',
            json={'query': query, 'variables': variables or {}},
            headers={'Authorization': 'Bearer ' + api_key},
            timeout=30,
        )
        body = resp.json()
        assert resp.status_code == 200, body
        assert not body.get('errors'), body['errors']
        return body['data']

    return run
