"""
Fails if a compose file publishes a port on anything but 127.0.0.1.

Reads YAML from stdin, normally the rendered file from
``docker compose config``, and handles both the short (``"127.0.0.1:20901:8000"``)
and the long (``host_ip``/``published``) port syntax. ``make compose-check``
runs it; the unit tests run it against the repository's compose file.
"""

import sys

import yaml

LOOPBACK = '127.0.0.1'


def _is_loopback(port):
    if isinstance(port, dict):
        return port.get('host_ip') == LOOPBACK
    return str(port).startswith(LOOPBACK + ':')


def non_loopback_ports(compose):
    """(service, port) pairs published on an address other than 127.0.0.1."""
    found = []
    for name, service in sorted((compose.get('services') or {}).items()):
        for port in (service or {}).get('ports') or []:
            if not _is_loopback(port):
                found.append((name, port))
    return found


def main(stream=None):
    compose = yaml.safe_load(stream or sys.stdin) or {}
    found = non_loopback_ports(compose)
    for name, port in found:
        sys.stderr.write('%s publishes %r on every interface\n' % (name, port))
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main())
