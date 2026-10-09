"""
GraphQL schema for the multi-cloud API.

Resolvers read from the CloudManager passed in as the query root value.
"""

import graphene


class Instance(graphene.ObjectType):
    """A compute instance in the normalized shape shared by every cloud."""

    id = graphene.String(required=True)
    name = graphene.String()
    provider = graphene.String(required=True)
    type = graphene.String()
    state = graphene.String()
    ip = graphene.String()
    region = graphene.String()

    @staticmethod
    def from_dict(data):
        return Instance(
            id=data.get('id'),
            name=data.get('name'),
            provider=data.get('provider'),
            type=data.get('type'),
            state=data.get('state'),
            ip=data.get('ip'),
            region=data.get('region'),
        )


class ProviderCost(graphene.ObjectType):
    """Estimated monthly cost for one provider."""

    provider = graphene.String(required=True)
    monthly = graphene.Float(required=True)


class Costs(graphene.ObjectType):
    """Per-provider cost breakdown and the total across providers."""

    breakdown = graphene.List(graphene.NonNull(ProviderCost), required=True)
    total = graphene.Float(required=True)
    currency = graphene.String(required=True)


class Query(graphene.ObjectType):
    providers = graphene.List(graphene.NonNull(graphene.String), required=True)
    instances = graphene.List(
        graphene.NonNull(Instance),
        required=True,
        provider=graphene.String(),
    )
    costs = graphene.Field(Costs, required=True)

    def resolve_providers(root, info):
        return root.provider_names()

    def resolve_instances(root, info, provider=None):
        return [Instance.from_dict(i) for i in root.list_resources(provider)]

    def resolve_costs(root, info):
        costs = root.get_costs()
        breakdown = [
            ProviderCost(provider=name, monthly=costs[name])
            for name in root.provider_names()
        ]
        return Costs(
            breakdown=breakdown,
            total=costs['total'],
            currency=root.currency,
        )


class ProvisionInstance(graphene.Mutation):
    """Create an instance on the named provider."""

    class Arguments:
        provider = graphene.String(required=True)
        name = graphene.String(required=True)
        size = graphene.String()
        image = graphene.String()

    Output = Instance

    def mutate(root, info, provider, name, size=None, image=None):
        spec = {'name': name}
        if size is not None:
            spec['size'] = size
        if image is not None:
            spec['image'] = image
        return Instance.from_dict(root.provision(provider, spec))


class DestroyResult(graphene.ObjectType):
    """Outcome of a destroyInstance mutation."""

    ok = graphene.Boolean(required=True)
    id = graphene.String()


class DestroyInstance(graphene.Mutation):
    """Remove an instance from the named provider."""

    class Arguments:
        provider = graphene.String(required=True)
        id = graphene.String(required=True)

    Output = DestroyResult

    def mutate(root, info, provider, id):
        ok = root.destroy(provider, id)
        return DestroyResult(ok=bool(ok), id=id)


class Mutation(graphene.ObjectType):
    provision_instance = ProvisionInstance.Field()
    destroy_instance = DestroyInstance.Field()


schema = graphene.Schema(query=Query, mutation=Mutation)
