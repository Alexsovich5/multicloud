"""
Common interface implemented by every cloud provider.
"""

INSTANCE_FIELDS = ('id', 'name', 'provider', 'type', 'state', 'ip', 'region')


class RequestError(ValueError):
    """The caller asked for something invalid; the message is safe to return."""


class InstanceNotFound(KeyError):
    """No instance with this id exists; the message names only the id."""

    def __init__(self, instance_id):
        super(InstanceNotFound, self).__init__(instance_id)
        self.instance_id = instance_id

    def __str__(self):
        return 'Unknown instance: %s' % self.instance_id


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

    def get_cost_estimate(self):
        """Return ``{'monthly': float, 'unpriced': [size, ...]}``.

        ``unpriced`` lists the sizes of counted instances that have no list
        price, so a caller can tell a complete estimate from an understated
        one. Providers that price every instance can keep this default.
        """
        return {'monthly': float(self.get_monthly_cost()), 'unpriced': []}
