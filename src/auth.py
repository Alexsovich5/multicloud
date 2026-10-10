"""
Operator API key for the HTTP API.

The key comes from ``MC_API_KEY`` or from the file named by
``MC_API_KEY_FILE``. If that file does not exist yet, a random key is
written to it (mode 0600), so every install gets its own key and no key is
stored in the repository. With neither variable set the app does not start.
"""

import hmac
import os
import secrets
import tempfile

KEY_ENV = 'MC_API_KEY'
KEY_FILE_ENV = 'MC_API_KEY_FILE'
MIN_KEY_LENGTH = 16
BEARER = 'Bearer '


class ApiKeyError(RuntimeError):
    """No usable API key is configured."""


def generate_key():
    """A new random key: 32 bytes as 64 hex characters."""
    return secrets.token_hex(32)


def _create_key_file(path):
    """Write a new key to ``path`` unless the file already exists.

    The key goes to a private temp file first and is then hard-linked into
    place, so concurrent workers never read a half-written file and the
    first one to link wins.
    """
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=directory, prefix='.api_key.')
    try:
        with os.fdopen(fd, 'w') as fh:
            fh.write(generate_key() + '\n')
        os.chmod(tmp, 0o600)
        try:
            os.link(tmp, path)
        except FileExistsError:
            pass
    finally:
        os.unlink(tmp)


def _checked(key, source):
    key = (key or '').strip()
    if len(key) < MIN_KEY_LENGTH:
        raise ApiKeyError('The API key from %s is shorter than %d characters'
                          % (source, MIN_KEY_LENGTH))
    return key


def load_api_key(environ=None):
    """Return the configured key, creating the key file if needed."""
    environ = os.environ if environ is None else environ
    if environ.get(KEY_ENV, '') != '':
        return _checked(environ[KEY_ENV], KEY_ENV)
    path = environ.get(KEY_FILE_ENV)
    if path:
        if not os.path.exists(path):
            _create_key_file(path)
        with open(path) as fh:
            return _checked(fh.read(), path)
    raise ApiKeyError('No API key configured: set %s or %s'
                      % (KEY_ENV, KEY_FILE_ENV))


def key_matches(expected, authorization):
    """True if ``authorization`` is exactly ``Bearer <expected>``.

    The comparison runs in constant time over the encoded values.
    """
    if not authorization or not authorization.startswith(BEARER):
        return False
    supplied = authorization[len(BEARER):]
    return hmac.compare_digest(supplied.encode('utf-8'),
                               expected.encode('utf-8'))
