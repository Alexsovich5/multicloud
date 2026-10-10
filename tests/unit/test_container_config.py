"""
Checks on the compose file, Makefile and Dockerfile that keep the stack
loopback-only and keep secrets and unauthenticated package sources out.
"""

import os
import re

import pytest
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))


def _read(*parts):
    with open(os.path.join(REPO_ROOT, *parts)) as handle:
        return handle.read()


@pytest.fixture(scope='module')
def compose():
    return yaml.safe_load(_read('docker-compose.yml'))


def _published(compose):
    for name, service in compose['services'].items():
        for port in service.get('ports') or []:
            yield name, port


def test_compose_publishes_the_api(compose):
    assert dict(_published(compose))['api']


def test_every_published_compose_port_is_loopback_only(compose):
    for name, port in _published(compose):
        if isinstance(port, dict):
            assert port.get('host_ip') == '127.0.0.1', (name, port)
        else:
            assert str(port).startswith('127.0.0.1:'), (name, port)


def test_every_makefile_port_publish_is_loopback_only():
    makefile = _read('Makefile')
    publishes = re.findall(r'(?:-p|--publish)[ =](\S+)', makefile)
    publishes = [p for p in publishes if p != 'multicloud']
    assert publishes, 'expected make run to publish a port'
    for value in publishes:
        assert value.startswith('127.0.0.1:'), value


def test_api_key_volume_is_mounted_and_no_key_is_set(compose):
    api = compose['services']['api']
    assert any(str(v).endswith(':/run/multicloud') for v in api['volumes'])
    environment = api.get('environment') or {}
    assert 'MC_API_KEY' not in environment
    for name, service in compose['services'].items():
        assert 'MC_API_KEY' not in (service.get('environment') or {}), name


def test_dockerfile_points_the_app_at_a_generated_key_file():
    dockerfile = _read('Dockerfile')
    assert 'MC_API_KEY_FILE=/run/multicloud/api_key' in dockerfile
    assert not re.search(r'MC_API_KEY\s*=', dockerfile)


UNAUTHENTICATED_APT = re.compile(
    r'--allow-unauthenticated|--force-yes|trusted=yes|AllowUnauthenticated'
    r'|--no-check-gpg|deb\s+http://|--trusted-host|index-url[\s=]+http://',
    re.I)


@pytest.mark.parametrize('path', ['Dockerfile', 'docker-compose.yml', 'Makefile'])
def test_no_unauthenticated_or_plain_http_package_sources(path):
    assert not UNAUTHENTICATED_APT.search(_read(path)), path
