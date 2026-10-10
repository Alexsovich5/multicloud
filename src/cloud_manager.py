"""
Multi-Cloud Manager

Unified interface for managing resources across AWS and Azure.
"""

import logging
import re

from config import load_config, resolve_path
from pricing import DEFAULT_CURRENCY, PriceTable
from providers.aws_provider import AWSProvider
from providers.azure_provider import AzureProvider
from providers.base import RequestError

logger = logging.getLogger('cloud_manager')

# Instance names and ids end up in cloud API URL paths (ARM puts the VM name
# in the path), so only plain identifiers are accepted.
IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z')


def check_identifier(value, what):
    """Raise RequestError unless ``value`` is a plain resource identifier."""
    if not isinstance(value, str) or not IDENTIFIER.match(value):
        raise RequestError('Invalid %s: use 1-64 letters, digits, ".", "_" or "-", '
                           'starting with a letter or digit' % what)
    return value


class CloudManager:
    """Orchestrates multi-cloud operations."""

    def __init__(self, config, providers=None, price_table=None):
        self.price_table = price_table
        if providers is not None:
            self.providers = dict(providers)
            return
        config = config or {}
        self.providers = {}
        if 'aws' in config:
            self.providers['aws'] = AWSProvider(config['aws'], price_table=price_table)
        if 'azure' in config:
            self.providers['azure'] = AzureProvider(config['azure'], price_table=price_table)

    @property
    def currency(self):
        """Currency of the cost estimates."""
        if self.price_table is None:
            return DEFAULT_CURRENCY
        return self.price_table.currency

    def provider_names(self):
        """Names of the configured providers."""
        return list(self.providers)

    def _get(self, provider):
        if provider not in self.providers:
            raise RequestError(f"Unknown provider: {provider}")
        return self.providers[provider]

    def list_resources(self, provider=None):
        """List all resources across clouds."""
        resources = []
        targets = [self._get(provider)] if provider else self.providers.values()
        for p in targets:
            resources.extend(p.list_instances())
        return resources

    def provision(self, provider, spec):
        """Provision resources on a specific cloud."""
        target = self._get(provider)
        if not spec.get('name'):
            raise RequestError("spec['name'] is required")
        check_identifier(spec['name'], 'instance name')
        return target.create_instance(spec)

    def get_cost_report(self):
        """Per-provider monthly cost, the total, and whether it is complete.

        ``complete`` is False when any counted instance has no list price,
        so the total understates the real cost.
        """
        providers = []
        for name, provider in self.providers.items():
            estimate = provider.get_cost_estimate()
            providers.append({
                'provider': name,
                'monthly': round(float(estimate['monthly']), 2),
                'unpriced': list(estimate['unpriced']),
            })
        return {
            'providers': providers,
            'total': round(sum(p['monthly'] for p in providers), 2),
            'complete': not any(p['unpriced'] for p in providers),
        }

    def get_costs(self):
        """Aggregate costs across all providers."""
        report = self.get_cost_report()
        costs = dict((p['provider'], p['monthly']) for p in report['providers'])
        costs['total'] = report['total']
        return costs

    def destroy(self, provider, resource_id):
        """Destroy a resource on a specific cloud."""
        target = self._get(provider)
        check_identifier(resource_id, 'instance id')
        return target.destroy_instance(resource_id)


def build_manager(config_path=None):
    """Build a CloudManager from the YAML config and its price table."""
    config = load_config(config_path)
    price_table = None
    if config.get('pricing_file'):
        price_table = PriceTable.from_file(resolve_path(config['pricing_file']))
    return CloudManager(config, price_table=price_table)
