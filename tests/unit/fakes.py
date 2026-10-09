"""In-memory provider used to exercise CloudManager without any cloud SDK."""

from providers.base import CloudProvider, normalize_instance


class FakeProvider(CloudProvider):
    """Keeps instances in a dict and charges a flat amount per instance."""

    def __init__(self, name, cost_per_instance=0.0):
        self.name = name
        self.cost_per_instance = cost_per_instance
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
        del self.instances[instance_id]
        return True

    def get_monthly_cost(self):
        return len(self.instances) * self.cost_per_instance
