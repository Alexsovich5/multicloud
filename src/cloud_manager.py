"""
Multi-Cloud Manager
IT Operations Specialist - ACORIA (2018)

Unified interface for managing resources across AWS and Azure.
"""

import logging
from providers.aws_provider import AWSProvider
from providers.azure_provider import AzureProvider

logger = logging.getLogger('cloud_manager')


class CloudManager:
    """Orchestrates multi-cloud operations."""

    def __init__(self, config):
        self.providers = {}
        if 'aws' in config:
            self.providers['aws'] = AWSProvider(config['aws'])
        if 'azure' in config:
            self.providers['azure'] = AzureProvider(config['azure'])

    def list_resources(self, provider=None):
        """List all resources across clouds."""
        resources = []
        targets = [self.providers[provider]] if provider else self.providers.values()
        for p in targets:
            resources.extend(p.list_instances())
        return resources

    def provision(self, provider, spec):
        """Provision resources on a specific cloud."""
        if provider not in self.providers:
            raise ValueError(f"Unknown provider: {provider}")
        return self.providers[provider].create_instance(spec)

    def get_costs(self):
        """Aggregate costs across all providers."""
        costs = {}
        for name, provider in self.providers.items():
            costs[name] = provider.get_monthly_cost()
        costs['total'] = sum(costs.values())
        return costs

    def destroy(self, provider, resource_id):
        """Destroy a resource on a specific cloud."""
        return self.providers[provider].destroy_instance(resource_id)
