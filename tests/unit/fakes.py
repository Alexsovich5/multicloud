"""In-memory provider used to exercise CloudManager without any cloud SDK."""

from providers.base import CloudProvider, InstanceNotFound, normalize_instance


class FakeProvider(CloudProvider):
    """Keeps instances in a dict and charges a flat amount per instance.

    Instances whose size is in ``unpriced_sizes`` are charged nothing and
    reported as unpriced by ``get_cost_estimate``.
    """

    def __init__(self, name, cost_per_instance=0.0, unpriced_sizes=()):
        self.name = name
        self.cost_per_instance = cost_per_instance
        self.unpriced_sizes = set(unpriced_sizes)
        self.instances = {}

    def list_instances(self):
        return [dict(inst) for inst in self.instances.values()]

    def create_instance(self, spec):
        instance = normalize_instance(
            id='%s-%d' % (self.name, len(self.instances) + 1),
            name=spec['name'],
            provider=self.name,
            type=spec.get('size', 'small'),
            state='running',
            region='local',
        )
        self.instances[instance['id']] = instance
        return dict(instance)

    def destroy_instance(self, instance_id):
        if instance_id not in self.instances:
            raise InstanceNotFound(instance_id)
        del self.instances[instance_id]
        return True

    def _sizes(self):
        return [inst['type'] for inst in self.instances.values()]

    def get_monthly_cost(self):
        priced = [s for s in self._sizes() if s not in self.unpriced_sizes]
        return len(priced) * self.cost_per_instance

    def get_cost_estimate(self):
        return {
            'monthly': self.get_monthly_cost(),
            'unpriced': [s for s in self._sizes() if s in self.unpriced_sizes],
        }
