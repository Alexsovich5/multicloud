"""
Azure Cloud Provider

Virtual machines via azure-mgmt-compute, resource groups via
azure-mgmt-resource. Setting ``base_url`` in the config points both clients
at an ARM-compatible endpoint such as the fake ARM simulator; a static bearer
token is used there instead of Azure AD.

The VM create payload has no network_profile/NIC. Real ARM rejects such a VM,
so create_instance only works against the fake ARM simulator.
"""

import logging
import os

from azure.common.credentials import ServicePrincipalCredentials
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.resource import ResourceManagementClient
from msrest.authentication import BasicTokenAuthentication
from msrestazure.azure_exceptions import CloudError

from providers.base import CloudProvider, InstanceNotFound, normalize_instance

logger = logging.getLogger('azure_provider')

DEFAULT_RESOURCE_GROUP = 'demo-rg'
DEFAULT_LOCATION = 'eastus'
DEFAULT_SIZE = 'Standard_B1s'
DEFAULT_IMAGE = {
    'publisher': 'Canonical',
    'offer': 'UbuntuServer',
    'sku': '18.04-LTS',
    'version': 'latest',
}
DEFAULT_ADMIN_USERNAME = 'azureuser'
CREDENTIAL_VARS = ('AZURE_CLIENT_ID', 'AZURE_CLIENT_SECRET', 'AZURE_TENANT_ID')


def _status_code(error):
    response = getattr(error, 'response', None)
    return getattr(response, 'status_code', None)


def _error_code(error):
    """The ARM error code (e.g. ResourceGroupNotFound) of a CloudError."""
    return getattr(getattr(error, 'error', None), 'error', None)


class AzureProvider(CloudProvider):
    """Azure resource management."""

    name = 'azure'

    def __init__(self, config, price_table=None):
        config = config or {}
        self.subscription_id = config.get('subscription_id', '')
        self.resource_group = config.get('resource_group', DEFAULT_RESOURCE_GROUP)
        self.location = config.get('location', DEFAULT_LOCATION)
        self.base_url = config.get('base_url')
        self.default_size = config.get('default_size', DEFAULT_SIZE)
        self.default_image = config.get('default_image', DEFAULT_IMAGE)
        self.admin_username = config.get('admin_username', DEFAULT_ADMIN_USERNAME)
        self.price_table = price_table

        credentials = self._credentials()
        self.compute = ComputeManagementClient(
            credentials, self.subscription_id, base_url=self.base_url)
        self.resources = ResourceManagementClient(
            credentials, self.subscription_id, base_url=self.base_url)

    def _credentials(self):
        """Static token for a custom ARM endpoint, service principal otherwise."""
        if self.base_url:
            return BasicTokenAuthentication({'access_token': 'fake'})
        missing = [var for var in CREDENTIAL_VARS if not os.environ.get(var)]
        if missing:
            raise ValueError(
                'Azure credentials are not configured: set %s, or set base_url '
                'to use a local ARM endpoint' % ', '.join(missing))
        return ServicePrincipalCredentials(
            client_id=os.environ['AZURE_CLIENT_ID'],
            secret=os.environ['AZURE_CLIENT_SECRET'],
            tenant=os.environ['AZURE_TENANT_ID'],
        )

    def _normalize(self, vm):
        state = (vm.provisioning_state or '').lower()
        if state == 'succeeded':
            state = 'running'
        return normalize_instance(
            id=vm.name,
            name=vm.name,
            provider=self.name,
            type=vm.hardware_profile.vm_size if vm.hardware_profile else '',
            state=state,
            ip=None,
            region=vm.location,
        )

    def _vms(self):
        """VMs in the resource group; [] only if ARM says the group is missing.

        Any other error, including other 404s such as SubscriptionNotFound,
        is raised so a failed listing is never reported as "no VMs".
        """
        try:
            return list(self.compute.virtual_machines.list(self.resource_group))
        except CloudError as exc:
            if (_status_code(exc) == 404
                    and _error_code(exc) == 'ResourceGroupNotFound'):
                return []
            raise

    def list_instances(self):
        """List the VMs in the configured resource group."""
        return [self._normalize(vm) for vm in self._vms()]

    def create_instance(self, spec):
        """Create a VM named ``spec['name']``, creating the resource group if needed."""
        name = spec.get('name', 'multicloud')
        image = spec.get('image', self.default_image)
        if not isinstance(image, dict):
            # A plain string is taken as an image resource id.
            image = {'id': image}
        self.resources.resource_groups.create_or_update(
            self.resource_group, {'location': self.location})
        poller = self.compute.virtual_machines.create_or_update(
            self.resource_group, name, {
                'location': self.location,
                'hardware_profile': {'vm_size': spec.get('size', self.default_size)},
                'storage_profile': {'image_reference': image},
                'os_profile': {
                    'computer_name': name,
                    'admin_username': self.admin_username,
                },
            })
        return self._normalize(poller.result())

    def destroy_instance(self, instance_id):
        """Delete a VM by name; InstanceNotFound if it does not exist."""
        try:
            self.compute.virtual_machines.get(self.resource_group, instance_id)
        except CloudError as exc:
            if _status_code(exc) == 404:
                raise InstanceNotFound(instance_id)
            raise
        self.compute.virtual_machines.delete(self.resource_group, instance_id).result()
        return True

    def get_cost_estimate(self):
        """Monthly cost of the VMs and the sizes with no price.

        Without a price table every VM is unpriced.
        """
        sizes = [vm.hardware_profile.vm_size for vm in self._vms() if vm.hardware_profile]
        if self.price_table is None:
            return {'monthly': 0.0, 'unpriced': sizes}
        return {'monthly': self.price_table.monthly(self.name, sizes),
                'unpriced': self.price_table.unpriced(self.name, sizes)}

    def get_monthly_cost(self):
        """Estimated monthly cost of the VMs from the price table."""
        return self.get_cost_estimate()['monthly']
