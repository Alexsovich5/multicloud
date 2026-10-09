"""
Loads the multicloud YAML configuration.

The file path comes from the ``path`` argument, then ``MC_CONFIG``, then
``config/multicloud.yml`` in the project root. ``MC_AWS_ENDPOINT`` and
``MC_AZURE_BASE_URL`` override the provider endpoints, and a provider with
``enabled: false`` is left out.
"""

import os

import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_PATH = os.path.join(PROJECT_ROOT, 'config', 'multicloud.yml')
PROVIDERS = ('aws', 'azure')

# provider -> (config key, environment variable that overrides it)
ENDPOINT_OVERRIDES = {
    'aws': ('endpoint_url', 'MC_AWS_ENDPOINT'),
    'azure': ('base_url', 'MC_AZURE_BASE_URL'),
}


def resolve_path(path):
    """Absolute form of ``path``; relative paths are taken from the project root."""
    if os.path.isabs(path):
        return path
    return os.path.join(PROJECT_ROOT, path)


def load_config(path=None):
    """Read the config file and return it as a dict with overrides applied."""
    path = path or os.environ.get('MC_CONFIG') or DEFAULT_CONFIG_PATH
    with open(path) as fh:
        config = yaml.safe_load(fh) or {}
    if not isinstance(config, dict):
        raise ValueError('%s must contain a mapping' % path)

    for provider in PROVIDERS:
        if provider not in config:
            continue
        section = dict(config[provider] or {})
        if not section.pop('enabled', True):
            del config[provider]
            continue
        key, env_var = ENDPOINT_OVERRIDES[provider]
        if os.environ.get(env_var):
            section[key] = os.environ[env_var]
        config[provider] = section
    return config
