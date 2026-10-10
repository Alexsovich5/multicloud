import os
import stat

import pytest

from auth import ApiKeyError, key_matches, load_api_key

KEY = 'k' * 40


def test_key_from_environment_variable():
    assert load_api_key({'MC_API_KEY': KEY}) == KEY


def test_environment_key_wins_over_key_file(tmpdir):
    path = tmpdir.join('api_key')
    path.write('f' * 40)
    environ = {'MC_API_KEY': KEY, 'MC_API_KEY_FILE': str(path)}
    assert load_api_key(environ) == KEY


def test_existing_key_file_is_read_and_stripped(tmpdir):
    path = tmpdir.join('api_key')
    path.write(KEY + '\n')
    assert load_api_key({'MC_API_KEY_FILE': str(path)}) == KEY


def test_missing_key_file_is_created_with_a_random_private_key(tmpdir):
    path = tmpdir.join('api_key')
    key = load_api_key({'MC_API_KEY_FILE': str(path)})
    assert len(key) == 64
    assert int(key, 16) >= 0
    assert path.read().strip() == key
    assert stat.S_IMODE(os.stat(str(path)).st_mode) == 0o600
    assert load_api_key({'MC_API_KEY_FILE': str(path)}) == key


def test_each_install_gets_its_own_key(tmpdir):
    first = load_api_key({'MC_API_KEY_FILE': str(tmpdir.join('a'))})
    second = load_api_key({'MC_API_KEY_FILE': str(tmpdir.join('b'))})
    assert first != second


def test_no_key_configured_is_an_error():
    with pytest.raises(ApiKeyError) as err:
        load_api_key({})
    assert 'MC_API_KEY' in str(err.value)


@pytest.mark.parametrize('value', ['', '   ', 'S3NTINEL-pw'])
def test_empty_or_short_keys_are_rejected_without_echoing_them(value):
    with pytest.raises(ApiKeyError) as err:
        load_api_key({'MC_API_KEY': value})
    assert 'S3NTINEL' not in str(err.value)


def test_short_key_file_is_rejected(tmpdir):
    path = tmpdir.join('api_key')
    path.write('S3NTINEL-pw\n')
    with pytest.raises(ApiKeyError) as err:
        load_api_key({'MC_API_KEY_FILE': str(path)})
    assert 'S3NTINEL' not in str(err.value)


@pytest.mark.parametrize('header, expected', [
    ('Bearer ' + KEY, True),
    ('Bearer ' + KEY + 'x', False),
    ('Bearer ' + KEY[:-1], False),
    ('bearer ' + KEY, False),
    ('Basic ' + KEY, False),
    (KEY, False),
    ('Bearer ', False),
    ('', False),
    (None, False),
    ('Bearer é' + KEY, False),
])
def test_key_matches_only_the_exact_bearer_key(header, expected):
    assert key_matches(KEY, header) is expected
