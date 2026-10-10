# Multi-Cloud Management Platform

A small Python layer that puts one interface over AWS EC2 and Azure virtual machines. A GraphQL API (Flask + Graphene) lists instances from both clouds in one query, provisions and destroys an instance on either cloud through the same mutation, and returns an estimated monthly compute cost per cloud and in total. The repo also describes the same compute footprint for both clouds as Terraform 0.11 code built on one shared module, and ships a Kubernetes 1.11 manifest for the API. No real cloud is contacted: AWS is served by moto and Azure by a local fake Azure Resource Manager server.

Personal project built on the 2018-era stack (Python 3.6, Flask 1.0, Graphene 2, Terraform 0.11).

## Status

**Implemented**

- Provider abstraction: a `CloudProvider` base class with list, create, destroy and monthly-cost methods, implemented by an AWS and an Azure provider that return the same instance shape. Code: `src/providers/base.py`. Tests: `tests/unit/test_aws_provider.py`, `tests/unit/test_azure_provider.py`.
- AWS compute via boto3: list, launch with a `Name` tag and terminate EC2 instances, with a configurable endpoint. Code: `src/providers/aws_provider.py`. Tests: `tests/unit/test_aws_provider.py` (under moto's `mock_ec2`).
- Azure compute via `azure-mgmt-compute` and `azure-mgmt-resource`: list, create and delete VMs in a resource group, creating the group if missing, with a configurable ARM base URL. Code: `src/providers/azure_provider.py`. Tests: `tests/unit/test_azure_provider.py` (real SDK against the fake ARM server on a background thread).
- CloudManager: dispatches to the configured providers, merges their results and raises `ValueError` for unknown provider names. Code: `src/cloud_manager.py`. Tests: `tests/unit/test_cloud_manager.py`.
- Cost estimate: running instances × hourly list price × 730 hours per provider, plus a total. Code: `src/pricing.py`, `config/pricing.yaml`. Tests: `tests/unit/test_pricing.py`, `tests/unit/test_cloud_manager.py`.
- GraphQL API at `/graphql` with GraphiQL: queries `providers`, `instances(provider)` and `costs`, mutations `provisionInstance` and `destroyInstance`, and a `/healthz` endpoint. Code: `src/graphql_schema.py`, `src/app.py`. Tests: `tests/unit/test_graphql_queries.py`, `tests/unit/test_graphql_mutations.py`, `tests/unit/test_app.py`.
- API key authentication: every `/graphql` request (queries and mutations) needs `Authorization: Bearer <key>`, compared in constant time; a missing or wrong key gets a bare 401. The key comes from `MC_API_KEY` or is generated on first start into `MC_API_KEY_FILE` (mode 0600, never committed), and the app refuses to start without one. POST bodies must be JSON (Content-Type application/json), so a cross-site form cannot trigger a mutation. Browsers get a static GraphiQL page that asks for the key and keeps it in `sessionStorage`. Unexpected resolver errors are returned as "Internal server error" without exception text. Instance names and ids are restricted to plain identifiers before they reach a cloud API path. Code: `src/auth.py`, `src/app.py`, `src/graphiql_page.py`, `src/cloud_manager.py`. Tests: `tests/unit/test_auth.py`, `tests/unit/test_app.py`, `tests/unit/test_cloud_manager.py`, `tests/integration/test_stack.py`.
- YAML configuration with environment overrides for the endpoints (`MC_AWS_ENDPOINT`, `MC_AZURE_BASE_URL`). Code: `src/config.py`, `config/multicloud.yml`. Tests: `tests/unit/test_config.py`.
- Fake Azure Resource Manager: a Flask app implementing the resource group and VM REST calls the SDK makes, with case-insensitive paths. Code: `simulators/fake_arm.py`. Tests: `tests/unit/test_fake_arm.py`.
- Terraform 0.11: `terraform/main.tf` calls the shared `terraform/modules/compute` module once for AWS and once for Azure. Both pass `terraform validate`, and a resource-targeted AWS plan against moto shows `Plan: 2 to add`. Tests: `tests/unit/test_terraform_layout.py`, plus `make tf-validate` and `make tf-plan`.
- Local stack: `docker-compose.yml` runs the API, a moto EC2 server and the fake ARM server. Only the API port is published, and only on 127.0.0.1. Tests: `tests/integration/test_stack.py` (provision on both clouds, list, costs, destroy, requests without the key refused), `tests/unit/test_container_config.py` (loopback-only ports, no committed key).
- Kubernetes 1.11 manifest: a Deployment and a Service for the API image. Code: `k8s/deployment.yaml`. Tests: `tests/unit/test_k8s_manifest.py`, plus `make k8s-validate` (kubeval 0.7.3 against the v1.11.0 schemas).

**Not implemented / known limitations**

- The code has never been run against real AWS or Azure. AWS is simulated by moto (in-process `mock_ec2` in unit tests, `moto_server ec2` in the stack), and Azure by the local fake ARM server (`simulators/fake_arm.py`). The real-credential code paths (no endpoint override, `ServicePrincipalCredentials`) exist but are untested.
- Azure authentication is a fake bearer token when a base URL is set; no Azure AD login happens.
- The Azure VM create payload has no `network_profile`/NIC, so real ARM would reject it. It only works against the fake ARM server.
- Costs come from a static price table (`config/pricing.yaml`) with illustrative list prices. There is no cost tracking from real billing data (Cost Explorer, Azure Consumption) and no cost optimization or rightsizing advice.
- The fake ARM server models only resource groups and VMs: no NICs, disks or power state, so the Azure `ip` field is always null.
- `terraform apply` is not supported. moto does not implement a call the AWS provider makes after launch, and the azurerm provider will not configure without Azure credentials, so the AWS side stops at a resource-targeted plan and the Azure side at validate.
- The Kubernetes manifest is schema-validated but has never been deployed to a cluster.
- Compute only: no storage, networking or IAM management through the API (Terraform creates a VNet/NIC only as far as an Azure VM needs one).
- No web dashboard; the unified view is the GraphQL `instances` query and GraphiQL.
- Authentication is one shared operator key: no users, roles or per-user audit. There is no TLS; the API is published on 127.0.0.1 only and is meant for local use. `/healthz` is unauthenticated and only reports that the process is up and which providers are configured. The API keeps no state of its own, and the simulators lose theirs on restart; `make down` also removes the key volume, so the next `make up` generates a new key.
- An instance size missing from the price table is priced at 0.0 (with a log warning), so the cost total can understate the real cost without the API saying so.
- The containers run as root.
- `make tf-*`, `make k8s-validate` and the image build need network access to download providers, schemas and packages.
- pytest is held at 3.5.1, the newest release that does not depend on atomicwrites.

## Built with

- **Python 3.6.7** (`python:3.6.7-stretch`) — Flask 1.0.2, Werkzeug 0.14.1, graphene 2.1.3, graphql-core 2.1, Flask-GraphQL 2.0.0, gunicorn 19.9.0, PyYAML 3.13
- **AWS SDK** — boto3 1.9.57, botocore 1.12.57
- **Azure SDK** — azure-mgmt-compute 4.3.1, azure-mgmt-resource 2.0.0, msrestazure 0.5.1, msrest 0.6.2
- **Testing** — pytest 3.5.1, flake8 3.6.0, moto 1.3.7
- **Terraform 0.11.10** (hashicorp/terraform:0.11.10 image) — terraform-provider-aws 1.46.0, terraform-provider-azurerm 1.19.0
- **Kubernetes 1.11** manifest — checked with kubeval 0.7.3 (garethr/kubeval:0.7.3 image)
- **docker-compose** file format 3.6

Full transitive pins are in `requirements.txt` and `requirements-dev.txt`.

## Running it

Everything runs in Docker images from the project's era, so nothing needs installing locally beyond Docker.

```bash
docker compose -p multicloud up -d # start api, moto and fake-arm (API on 127.0.0.1:20901)
make smoke                         # POST a GraphQL query listing instances and costs
make api-key                       # print the API key generated for this stack
```

Every GraphQL request needs the key as `Authorization: Bearer <key>`. GraphiQL is served at http://127.0.0.1:20901/graphql and asks for the key once per browser tab. `make run` starts the API alone on 127.0.0.1:20900, without the simulators; its key is in the container (`docker exec multicloud-run cat /run/multicloud/api_key`). To use a key of your own, set `MC_API_KEY` (at least 16 characters). The Kubernetes manifest reads it from a Secret named `multicloud-api-key`, which you create yourself.

## Tests

```bash
make test                # flake8 + unit tests inside the period image
```

The unit tests cover the providers (against moto and the fake ARM server), the manager, pricing, config, the GraphQL schema, the Flask app, the Terraform layout and the Kubernetes manifest, and make no outbound calls. `make integration` brings up the compose stack and runs end-to-end GraphQL tests against it, `make tf-validate` validates the Terraform for both clouds, `make tf-plan` runs the targeted AWS plan against moto, and `make k8s-validate` checks the manifest with kubeval. None of them touch a real cloud account.

## Layout

```
.dockerignore
.gitignore
Dockerfile
MANIFEST
Makefile
README.md
  multicloud.yml
  pricing.yaml
docker-compose.yml
  IMPLEMENTATION_PLAN.md
  SPEC.md
  deployment.yaml
requirements-dev.txt
requirements.txt
setup.cfg
  __init__.py
  fake_arm.py
  app.py
  auth.py
  cloud_manager.py
  config.py
  graphiql_page.py
  graphql_schema.py
  pricing.py
    __init__.py
    aws_provider.py
    azure_provider.py
    base.py
  main.tf
      main.tf
      outputs.tf
      variables.tf
  outputs.tf
  variables.tf
  __init__.py
  conftest.py
    __init__.py
    conftest.py
    test_stack.py
    __init__.py
    fakes.py
    test_app.py
    test_auth.py
    test_aws_provider.py
    test_azure_provider.py
    test_cloud_manager.py
    test_config.py
    test_container_config.py
    test_environment.py
    test_fake_arm.py
    test_graphql_mutations.py
    test_graphql_queries.py
    test_k8s_manifest.py
    test_makefile_targets.py
    test_pricing.py
    test_readme.py
    test_terraform_layout.py
```
