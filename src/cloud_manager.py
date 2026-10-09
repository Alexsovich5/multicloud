"""
Multi-Cloud Manager

Unified interface for managing resources across AWS and Azure.
"""

import logging
from providers.aws_provider import AWSProvider
from providers.azure_provider import AzureProvider

logger = logging.getLogger('cloud_manager')


class CloudManager:
    """Orchestrates multi-cloud operations."""

    def __init__(self, config, providers=None):
        if providers is not None:
            self.providers = dict(providers)
            return
        config = config or {}
        self.providers = {}
        if 'aws' in config:
            self.providers['aws'] = AWSProvider(config['aws'])
        if 'azure' in config:
            self.providers['azure'] = AzureProvider(config['azure'])

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
