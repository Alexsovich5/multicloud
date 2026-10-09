"""
Multi-Cloud Manager

Unified interface for managing resources across AWS and Azure.
"""

import logging

from config import load_config, resolve_path
from pricing import DEFAULT_CURRENCY, PriceTable
from providers.aws_provider import AWSProvider
from providers.azure_provider import AzureProvider

logger = logging.getLogger('cloud_manager')


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
            raise ValueError(f"Unknown provider: {provider}")
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
            raise ValueError("spec['name'] is required")
        return target.create_instance(spec)

    def get_costs(self):
        """Aggregate costs across all providers."""
        costs = {}
        for name, provider in self.providers.items():
            costs[name] = round(float(provider.get_monthly_cost()), 2)
        costs['total'] = round(sum(costs.values()), 2)
        return costs

    def destroy(self, provider, resource_id):
        """Destroy a resource on a specific cloud."""
        return self._get(provider).destroy_instance(resource_id)


def build_manager(config_path=None):
    """Build a CloudManager from the YAML config and its price table."""
    config = load_config(config_path)
    price_table = None
    if config.get('pricing_file'):
        price_table = PriceTable.from_file(resolve_path(config['pricing_file']))
    return CloudManager(config, price_table=price_table)
