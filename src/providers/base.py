"""
Common interface implemented by every cloud provider.
"""

INSTANCE_FIELDS = ('id', 'name', 'provider', 'type', 'state', 'ip', 'region')


def normalize_instance(**fields):
    """Return an instance dict with exactly the normalized keys.

    ``name`` defaults to an empty string and ``ip`` to None; every other
    field is required. Unknown fields raise TypeError.
    """
    unknown = set(fields) - set(INSTANCE_FIELDS)
    if unknown:
        raise TypeError('Unknown instance fields: %s' % ', '.join(sorted(unknown)))
    instance = {'name': '', 'ip': None}
    instance.update(fields)
    missing = [f for f in INSTANCE_FIELDS if f not in instance]
    if missing:
        raise TypeError('Missing instance fields: %s' % ', '.join(missing))
    return dict((f, instance[f]) for f in INSTANCE_FIELDS)


class CloudProvider(object):
    """Base class for cloud providers."""

    name = None

    def list_instances(self):
        """Return a list of normalized instance dicts."""
        raise NotImplementedError

    def create_instance(self, spec):
        """Create an instance from ``spec`` and return its normalized dict."""
        raise NotImplementedError

    def destroy_instance(self, instance_id):
        """Destroy an instance and return True."""
        raise NotImplementedError

    def get_monthly_cost(self):
        """Return the estimated monthly cost as a float."""
        raise NotImplementedError
