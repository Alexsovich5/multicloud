"""
Azure Cloud Provider
IT Operations Specialist - ACORIA (2018)
"""

import logging

logger = logging.getLogger('azure_provider')


class AzureProvider:
    """Azure resource management."""

    def __init__(self, config):
        self.subscription_id = config.get('subscription_id', '')
        self.resource_group = config.get('resource_group', 'acoria-rg')
        self.location = config.get('location', 'eastus')

    def list_instances(self):
        """List all Azure VMs."""
        # Azure SDK integration
        logger.info("Listing Azure VMs in %s", self.resource_group)
        return []

    def create_instance(self, spec):
        """Create an Azure VM."""
        logger.info("Creating Azure VM: %s", spec.get('name'))
        return {'id': 'azure-vm-id', 'provider': 'azure'}

    def destroy_instance(self, vm_id):
        """Delete an Azure VM."""
        logger.info("Destroying Azure VM: %s", vm_id)
        return True

    def get_monthly_cost(self):
        """Estimate monthly Azure cost."""
        return 0.0
