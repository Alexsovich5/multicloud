# multicloud — Specification

Target period: July–November 2018. Every dependency is pinned to a release on or before 2018-11-30.

## Problem

Running workloads on both AWS and Azure means two consoles, two SDKs and two sets of Terraform. This project puts one small abstraction over both clouds so a user can:

- list compute instances from both clouds in one query,
- provision and destroy an instance on either cloud through the same call,
- see an estimated monthly compute cost per cloud and in total,
- describe the same compute footprint for both clouds as Terraform 0.11 code.

The Python layer sits behind a GraphQL API (Flask + Graphene). It ships as a Docker image and comes with a Kubernetes 1.11 manifest.

Neither cloud is contacted for real. AWS EC2 is simulated with moto, and Azure Resource Manager is simulated with a small local fake. See "Simulated/mocked integrations".

## In scope

1. **Provider abstraction.** A `CloudProvider` base class with `list_instances()`, `create_instance(spec)`, `destroy_instance(id)` and `get_monthly_cost()`. `AWSProvider` and `AzureProvider` implement it and return the same instance dict shape.
2. **AWS compute via boto3.** List, launch (with a `Name` tag) and terminate EC2 instances. The endpoint is configurable, so the same code runs against moto.
3. **Azure compute via the Azure SDK.** List, create and delete VMs in a resource group, creating the group if it does not exist. This uses `azure-mgmt-compute` and `azure-mgmt-resource` with a configurable ARM `base_url`, so the same code runs against the fake ARM server.
4. **CloudManager.** Dispatches to the configured providers and merges results from all of them. Unknown provider names raise `ValueError`.
5. **Cross-cloud cost estimate.** Monthly cost per provider plus a total, computed as running instances × hourly list price (from `config/pricing.yaml`) × 730 h. This is an estimate from a static price table, not billing data.
6. **GraphQL API.** Flask 1.0 + Graphene 2 + Flask-GraphQL 2 at `/graphql`, with GraphiQL. Queries: `providers`, `instances(provider)`, `costs`. Mutations: `provisionInstance`, `destroyInstance`. There is also a plain `/healthz` endpoint.
7. **YAML configuration.** `config/multicloud.yml` says which providers are enabled, sets region/location/resource group, and gives the endpoints. Environment variables override the endpoints (`MC_AWS_ENDPOINT`, `MC_AZURE_BASE_URL`).
8. **Terraform 0.11 multi-cloud IaC.** `terraform/main.tf` calls a reusable `modules/compute` module once for AWS and once for Azure, selected with `provider_type`. Both pass `terraform validate`. The AWS side also passes a resource-targeted `terraform plan` (`-target=module.aws_compute.data.aws_availability_zones.available -target=module.aws_compute.aws_instance.this`) that reads availability zones from the moto EC2 endpoint and shows `Plan: 2 to add`. Targeting the resources rather than the whole module keeps the azurerm provider out of the graph, so no Azure credentials are needed.
9. **Local stack via docker-compose.** Three services: `api` (gunicorn + Flask), `moto` (moto EC2 server) and `fake-arm` (simulated Azure ARM). One `curl` against `/graphql` shows instances from both clouds.
10. **Kubernetes 1.11 manifest.** `k8s/deployment.yaml` holds a Deployment and a Service for the API image (apps/v1). It is checked with kubeval 0.7.3 against the v1.11.0 schemas, and with a structural unit test.

## Out of scope

| Original README item | Reason |
|---|---|
| Real AWS / Azure accounts | No cloud accounts. Both are simulated (moto, fake ARM), and the code only changes the endpoint. |
| Deploying to a running Kubernetes 1.11 cluster | A local cluster tool for this era (kind 0.1 / minikube 0.30 inside Docker) is fragile. The manifest is written and schema-validated but not deployed. |
| `terraform apply` | moto 1.3.7 does not implement `DescribeInstanceCreditSpecifications`, which aws provider 1.46.0 calls after launch (verified: apply hangs). azurerm 1.19.0 refuses to configure without Azure credentials (verified: "Azure CLI Authorization Profile was not found"), so any plan that includes an azurerm resource fails. The acceptance bar is validate for both clouds plus a resource-targeted plan for AWS. |
| Cost tracking from real billing data (Cost Explorer / Azure Consumption) | Neither simulator implements billing APIs. Costs are estimated from a static price table. |
| Cost optimization / recommendations (rightsizing, reserved-instance advice) | The simulators provide no usage metrics, so only a static estimate is provided. |
| Storage, networking and IAM management through the API | The README concept is about compute provisioning. VNet/NIC appear only as far as Terraform needs them for a VM. |
| "Single pane of glass" as a web dashboard | The unified view is the GraphQL `instances` query plus GraphiQL. No separate UI was described. |
| "50% faster provisioning", other impact metrics | These are not measurable in this repo and are dropped. |
| "Vendor flexibility / avoid lock-in" as a claim | This is delivered only as feature 1 (provider abstraction). It is not a claim. |
| Python 3.7 | Python 3.6 was the dominant production runtime in 2018 (3.7 came out in June 2018, and many libraries still lagged). The target stack for this rebuild is 3.6. |
| API authentication / multi-user access | Not described in the README. The API is meant for local use only. |

## Architecture

```
                  +-------------------------- docker-compose ---------------------------+
 curl / GraphiQL  |                                                                      |
 ---------------> |  api (python:3.6.7-stretch, gunicorn :8000)                          |
   POST /graphql  |   app.py (Flask) -> GraphQLView(schema, root_value=CloudManager)    |
                  |      graphql_schema.py (Query / Mutation)                            |
                  |      cloud_manager.CloudManager                                      |
                  |         |-- providers.aws_provider.AWSProvider --boto3--------------+--> moto :5000   (moto_server ec2)
                  |         |-- providers.azure_provider.AzureProvider --azure-mgmt-----+--> fake-arm :5001 (simulators/fake_arm.py)
                  |         '-- pricing.PriceTable (config/pricing.yaml)                 |
                  +----------------------------------------------------------------------+

 terraform/ (hashicorp/terraform:0.11.10)
   main.tf -> module "aws_compute"   (modules/compute, provider_type="aws")   -- targeted plan (AZ lookup) --> moto :5000
           -> module "azure_compute" (modules/compute, provider_type="azure") -- validate only

 k8s/deployment.yaml -- kubeval 0.7.3 (schema v1.11.0)
```

Data flow for `provisionInstance(provider:"azure", name:"web1", size:"Standard_B2s")`:
GraphQLView → `Mutation.provision_instance` → `CloudManager.provision("azure", spec)` → `AzureProvider.create_instance` → `ResourceManagementClient.resource_groups.create_or_update` → `ComputeManagementClient.virtual_machines.create_or_update(...).result()` → fake ARM stores the VM → normalized instance dict → GraphQL `Instance`.

## Data model & interfaces

### Normalized instance (Python dict / GraphQL `Instance`)

| field | type | AWS source | Azure source |
|---|---|---|---|
| `id` | str | `InstanceId` | VM `name` |
| `name` | str | `Name` tag or `""` | VM `name` |
| `provider` | str | `"aws"` | `"azure"` |
| `type` | str | `InstanceType` | `hardware_profile.vm_size` |
| `state` | str | `state.Name` (`pending/running/...`) | `provisioning_state` lower-cased (`succeeded` is mapped to `running`) |
| `ip` | str or None | `PublicIpAddress` | `None` (no public IP modelled) |
| `region` | str | configured region | VM `location` |

### Provider interface (`src/providers/base.py`)

```python
class CloudProvider(object):
    name = None                                 # "aws" | "azure"
    def list_instances(self): ...               # -> [instance dict], terminated/deleted excluded
    def create_instance(self, spec): ...        # spec: {"name": str, "size": str?, "image": str?} -> instance dict
    def destroy_instance(self, instance_id): ...# -> True; raises KeyError if unknown
    def get_monthly_cost(self): ...             # -> float (USD, 2 dp)
```

### CloudManager (`src/cloud_manager.py`)

```python
CloudManager(config, providers=None)          # providers: optional {name: CloudProvider} for injection
.provider_names() -> [str]
.list_resources(provider=None) -> [instance]
.provision(provider, spec) -> instance        # ValueError on unknown provider / missing spec["name"]
.destroy(provider, resource_id) -> bool       # ValueError on unknown provider
.get_costs() -> {"aws": float, "azure": float, "total": float}
.currency -> str                              # PriceTable currency, "USD" when no price table is wired
build_manager(config_path=None) -> CloudManager   # reads YAML + env overrides
```

### Config (`config/multicloud.yml`)

```yaml
aws:
  region: us-east-1
  endpoint_url: http://moto:5000      # MC_AWS_ENDPOINT overrides; omit for real AWS
  default_image: ami-12345678
  default_size: t2.micro
azure:
  subscription_id: 00000000-0000-0000-0000-000000000000
  resource_group: multicloud-demo-rg
  location: eastus
  base_url: http://fake-arm:5001      # MC_AZURE_BASE_URL overrides; omit for real ARM
  default_size: Standard_B1s
pricing_file: config/pricing.yaml
```

### Price table (`config/pricing.yaml`)

```yaml
hours_per_month: 730
currency: USD
aws:   {t2.micro: 0.0116, t2.medium: 0.0464, t3.medium: 0.0416, m4.large: 0.10}
azure: {Standard_B1s: 0.0104, Standard_B2s: 0.0416, Standard_D2s_v3: 0.096}
```
Values are illustrative Linux on-demand list prices. Unknown sizes are priced at 0.0 and logged as a warning.

### GraphQL schema

```graphql
type Instance { id: String!, name: String, provider: String!, type: String, state: String, ip: String, region: String }
type ProviderCost { provider: String!, monthly: Float! }
type DestroyResult { ok: Boolean!, id: String }
type Costs { breakdown: [ProviderCost!]!, total: Float!, currency: String! }
type Query {
  providers: [String!]!
  instances(provider: String): [Instance!]!
  costs: Costs!
}
type Mutation {
  provisionInstance(provider: String!, name: String!, size: String, image: String): Instance
  destroyInstance(provider: String!, id: String!): DestroyResult
}
```
An unknown provider returns a GraphQL error (`errors[0].message = "Unknown provider: gcp"`). HTTP: `POST /graphql` (JSON `{query, variables}`), `GET /graphql` (GraphiQL), `GET /healthz` → `{"status":"ok","providers":[...]}`.

### Fake ARM REST surface (`simulators/fake_arm.py`, api-version ignored)

| Method | Path | Behaviour |
|---|---|---|
| PUT | `/subscriptions/{sub}/resourcegroups/{rg}` | create/update RG → 201/200 |
| GET | `/subscriptions/{sub}/resourcegroups/{rg}` | 200 or 404 |
| GET | `/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Compute/virtualMachines` | `{"value":[...]}` |
| PUT | `.../virtualMachines/{name}` | store VM, `provisioningState: Succeeded` → 200 |
| GET | `.../virtualMachines/{name}` | 200 or 404 (ARM error body) |
| DELETE | `.../virtualMachines/{name}` | 200, or 204 if absent |

The routes match paths case-insensitively, as ARM does. Flask/Werkzeug routing is case-sensitive and runs before any `before_request` hook, so `create_app()` wraps `app.wsgi_app` in a small WSGI middleware that saves the original path in `environ["fake_arm.original_path"]` and lower-cases `environ["PATH_INFO"]` before Flask matches it. Routes are declared in lower case. RG and VM names are stored under their lower-cased key, but bodies return the original-case name taken from the saved path. `create_app()` returns a fresh in-memory store so tests are isolated.

The fake does not require a `network_profile` on VM create. Real ARM rejects a VM without a NIC, so the provider's create payload works only against the fake.

### Terraform interface (`terraform/modules/compute`)

Inputs: `provider_type` ("aws" or "azure"), `name_prefix`, `instance_count`, `instance_type`, `aws_ami`, `azure_location`, `azure_resource_group`, `azure_subnet_id` (default `""`), `ssh_public_key`. Outputs: `aws_instance_ids`, `azure_vm_ids`. The resources in each cloud are gated with `count = "${var.provider_type == "aws" ? var.instance_count : 0}"`, using 0.11 interpolation syntax throughout. A `data "aws_availability_zones" "available"` lookup sets each `aws_instance`'s `availability_zone` (`element(names, count.index)`). `module "aws_compute"` passes `azure_subnet_id = ""` and no Azure references, so a plan targeted at its AWS resources pulls in no azurerm nodes.

### Make targets

`make build`, `make test` (depends on `build`; flake8 + unit tests in the period image), `make integration` (depends on `build`; compose stack + integration tests), `make run` (gunicorn on port 8000 without the simulators), `make tf-validate`, `make tf-plan`, `make k8s-validate`, `make up`, `make down`, `make smoke`.

## Stack & pinned versions

| Component | Version | Released | Why it was the popular choice then |
|---|---|---|---|
| Python | 3.6.7 | 2018-10-20 | The default production Python 3 in 2018. Most wheels (cryptography, cffi) were built for it. |
| Flask | 1.0.2 | 2018-05-02 | The first 1.0 line, and the default microframework for small Python APIs. |
| Werkzeug | 0.14.1 | 2017-12-31 | Flask 1.0's WSGI layer at the time. |
| graphene | 2.1.3 | 2018-07-19 | The standard Python GraphQL server library. |
| graphql-core | 2.1 | 2018-07-19 | Graphene 2's engine. |
| Flask-GraphQL | 2.0.0 | 2018-07-19 | The official graphene/Flask view with GraphiQL. |
| boto3 | 1.9.57 | 2018-11-30 | The AWS SDK for Python (botocore 1.12.57). |
| azure-mgmt-compute | 4.3.1 | 2018-10-16 | The Azure SDK management plane for VMs (api 2018-06-01). |
| azure-mgmt-resource | 2.0.0 | 2018-07-20 | The Azure SDK for resource groups. |
| msrestazure / msrest | 0.5.1 / 0.6.2 | 2018-11-01 / 2018-11-20 | The Azure SDK runtime, including LRO polling. |
| PyYAML | 3.13 | 2018-07-05 | The YAML library for config (3.13 was the Python 3.7-compatible fix release). |
| gunicorn | 19.9.0 | 2018-07-03 | The default WSGI server for Flask in containers. |
| moto (server) | 1.3.7 | 2018-11-04 | The de-facto AWS mock, used both in-process (`mock_ec2`) and as `moto_server ec2`. |
| pytest | 3.5.1 | 2018-04-24 | The dominant Python test runner. See the note below on why this is not 3.10/4.0. |
| flake8 | 3.6.0 | 2018-10-24 | The standard linter. |
| Terraform | 0.11.10 | 2018-10-23 | The current stable line before the 0.12 HCL2 rewrite (0.12 shipped in May 2019). |
| terraform-provider-aws | 1.46.0 | 2018-11-20 | A 1.x release from the period, verified against moto 1.3.7 (validate and targeted plan). |
| terraform-provider-azurerm | 1.19.0 | 2018-11-15 | The current azurerm release in the period. |
| Kubernetes API target | 1.11 | 2018-06-27 | The current stable Kubernetes in the period (per the README). |
| kubeval | 0.7.3 | 2018-08-21 | The common manifest schema validator in 2018. |
| docker-compose file format | 3.6 | Compose 1.22, 2018-07 | The current v3 format in the period. |

Full transitive pins, all checked with `tools/check_period.py` (0 problems, every package released ≤ 2018-11-30):

`requirements.txt` (runtime, 44):
```
adal==1.2.0 aniso8601==3.0.2 asn1crypto==0.24.0 azure-common==1.1.16 azure-mgmt-compute==4.3.1
azure-mgmt-nspkg==3.0.2 azure-mgmt-resource==2.0.0 azure-nspkg==3.0.2 boto3==1.9.57 botocore==1.12.57
certifi==2018.11.29 cffi==1.11.5 chardet==3.0.4 click==7.0 cryptography==2.4.2 docutils==0.14
flask==1.0.2 flask-graphql==2.0.0 graphene==2.1.3 graphql-core==2.1 graphql-relay==0.4.5
graphql-server-core==1.1.1 gunicorn==19.9.0 idna==2.7 isodate==0.6.0 itsdangerous==1.1.0 jinja2==2.10
jmespath==0.9.3 markupsafe==1.1.0 msrest==0.6.2 msrestazure==0.5.1 oauthlib==2.1.0 promise==2.2.1
pycparser==2.19 pyjwt==1.6.4 python-dateutil==2.7.5 pyyaml==3.13 requests==2.20.1
requests-oauthlib==1.0.0 rx==1.6.1 s3transfer==0.1.13 six==1.11.0 urllib3==1.24.1 werkzeug==0.14.1
```
`requirements-dev.txt` (`-r requirements.txt` plus 28):
```
attrs==18.2.0 aws-xray-sdk==0.95 boto==2.49.0 docker==3.6.0 docker-pycreds==0.4.0 ecdsa==0.13
flake8==3.6.0 future==0.17.1 jsondiff==1.1.1 jsonpickle==1.0 mccabe==0.6.1 mock==2.0.0
more-itertools==4.3.0 moto==1.3.7 pbr==5.1.1 pluggy==0.6.0 py==1.7.0 pyaml==18.11.0
pycodestyle==2.4.0 pycryptodome==3.7.2 pyflakes==2.0.0 pytest==3.5.1 python-jose==2.0.2
pytz==2018.7 responses==0.10.4 websocket-client==0.54.0 wrapt==1.10.11 xmltodict==0.11.0
```
Both files hold one pin per line. They are shown wrapped here only to save space.

**Why pytest 3.5.1.** atomicwrites (required by pytest 3.6 to 4.0) was re-uploaded to PyPI on 2022-07-09, so every version reports a 2022 upload date and fails the period check. 3.5.1 is the newest pytest without that dependency.

Resolution was done with `uv pip compile --exclude-newer 2018-12-01` (Python 3.7 marker set, since uv refuses 3.6). An in-process smoke test with these pins ran boto3+moto `mock_ec2`, graphene, and the azure-mgmt clients against a prototype fake ARM server, and all passed.

## Docker images

| Image | Use | Tag check |
|---|---|---|
| `python:3.6.7-stretch` | App/dev/test image. It is the full image because gcc is needed to build PyYAML 3.13 and wrapt 1.10.11 from sdist. | Docker Hub API 200 |
| `python:3.6.7-slim-stretch` | Not used for building. It was verified as an option for a slimmer runtime stage if wanted later. | 200 |
| `hashicorp/terraform:0.11.10` | `make tf-validate`, `make tf-plan` | 200 (Hub marks the tag "inactive", but it can still be pulled) |
| `garethr/kubeval:0.7.3` | `make k8s-validate` | 200 (pushed 2018-08-21) |

moto and fake-arm run from the same `multicloud:dev` image (built from `python:3.6.7-stretch`), so no extra images are needed. In `docker-compose.yml` only `api` has `build: .`, and all three services set `image: multicloud:dev`.

## Simulated/mocked integrations

| Real system | Replacement | Where |
|---|---|---|
| AWS EC2 API | **moto 1.3.7**: `@mock_ec2` in unit tests, and `moto_server ec2` as the `moto` compose service for the stack, integration tests and `terraform plan` (the plan's `aws_availability_zones` lookup is answered by moto) | `tests/unit/test_aws_provider.py`, `docker-compose.yml` |
| Azure Resource Manager (Compute + Resources) | **fake ARM**: a Flask app written for this repo (`simulators/fake_arm.py`) that implements the REST subset above. The real `azure-mgmt-*` SDK talks to it over HTTP. | `simulators/`, `fake-arm` compose service, in-thread server fixture in `tests/conftest.py` |
| Azure AD authentication | `msrest.authentication.BasicTokenAuthentication({"access_token": "fake"})` when `base_url` is set. A `ServicePrincipalCredentials` code path exists but is untested, and the VM create payload has no NIC, so it would not work against real ARM as written. | `providers/azure_provider.py` |
| AWS credentials | Dummy `AWS_ACCESS_KEY_ID/SECRET=testing` env vars | Dockerfile / compose |
| Cloud billing | Static price table `config/pricing.yaml` | `src/pricing.py` |
| Kubernetes cluster | kubeval schema validation only | `make k8s-validate` |

The final README must state that AWS runs against moto, Azure runs against a local fake ARM server, costs are estimates from a static table, and the code has never been run against real cloud accounts.

## Existing code inventory

| File | Decision | Reason |
|---|---|---|
| `README.md` | refactor | Regenerated in the final task from `tools/readme_template.md`, with honest status and a Layout from `git ls-files`. |
| `requirements.txt` | refactor | Replace the 7 loose top-level pins (and the stale "Python 3.7" header) with the 44 full transitive period pins. Dev tools go to `requirements-dev.txt`. |
| `src/cloud_manager.py` | refactor | The dispatch and aggregation design is good and kept. Changes: add provider injection, validate unknown providers in `list_resources`/`destroy`, round totals, add `provider_names()` and a `build_manager()` factory. The f-strings are valid on 3.6. |
| `src/providers/aws_provider.py` | refactor | The boto3 logic is sound and kept. Changes: `endpoint_url` and session injection, use the base class, skip terminated instances, `destroy` returns after terminate, cost from the price table instead of a hard-coded `50.0`, configurable default AMI/size, and return a full normalized dict from `create_instance`. |
| `src/providers/azure_provider.py` | refactor | Keep the class and config keys, and replace the logging-only stubs with real `azure-mgmt-compute`/`azure-mgmt-resource` calls. |
| `terraform/main.tf` | refactor | Uses 0.12-style bare references (`azurerm_resource_group.main.location`), which are invalid in 0.11. It references a missing `./modules/compute` and has an empty `network_interface_ids`. Rewrite in 0.11 interpolation syntax, move the VM into the module, and pin provider versions. |

No files are deleted. The README also listed `src/graphql_schema.py`, `terraform/modules/compute/main.tf`, `docker-compose.yml` and `k8s/deployment.yaml`, which were never committed. The plan creates them.

## Test strategy

- **Unit (`tests/unit`, run by `make test` in `multicloud:dev`; the tests make no outbound calls):**
  - `CloudManager` with fake in-memory providers: dispatch, aggregation, unknown-provider errors, cost totals.
  - `PriceTable`: known and unknown sizes, 730 h math, rounding.
  - `AWSProvider` under `moto.mock_ec2`: create with tag, list, terminate excluded from list, cost of running instances only.
  - Fake ARM app via the Flask test client: RG and VM CRUD, 404 bodies, case-insensitive paths.
  - `AzureProvider` with the real SDK against fake ARM served from a background werkzeug thread (`tests/conftest.py` fixture on an ephemeral port): RG auto-create, create/list/delete, cost.
  - Config loader: YAML parsing, env overrides, disabled providers. `build_manager` wiring is asserted without HTTP; `list_resources("aws")` runs under `mock_ec2` and `list_resources("azure")` runs outside it.
  - Rule: fake-ARM HTTP calls never run inside an active moto in-process mock (`mock_ec2`). moto 1.3.7 activates `responses`' default mock, which intercepts every `requests` call, including msrest's calls to the fake ARM thread, and registers no passthrough, so those calls fail with `ConnectionError`. Tests that need both clouds split the AWS and Azure calls, as in the config test above.
  - GraphQL schema via `schema.execute(..., root=manager)`: every query and mutation, plus error propagation.
  - Flask app via the test client: `POST /graphql`, `GET /healthz`, GraphiQL HTML on `GET /graphql` with `Accept: text/html`.
  - Kubernetes manifest structure (PyYAML): kinds, apps/v1, image name, port 8000, readiness probe on `/healthz`.
  - `flake8 src simulators tests` runs as part of `make test`.
- **Integration (`tests/integration`, `make integration`):** `docker compose up -d` brings up api, moto and fake-arm. The integration conftest waits until `http://api:8000/healthz`, `http://moto:5000` and `http://fake-arm:5001` all answer. pytest runs in a container on the compose network and makes HTTP calls to `http://api:8000/graphql`: provision on both clouds, list across both, costs total equals the sum, destroy, and the instance is gone.
- **IaC:** `make tf-validate` runs `terraform init -backend=false` and `validate` in `hashicorp/terraform:0.11.10`. `make tf-plan` runs `plan -target=module.aws_compute.data.aws_availability_zones.available -target=module.aws_compute.aws_instance.this` against the moto compose service. The output must show `Plan: 2 to add` and the moto-supplied zone `us-east-1a`. Without moto the plan fails at the zone lookup, so the check really exercises the simulator. `make k8s-validate` runs kubeval 0.7.3 with `--kubernetes-version 1.11.0`.

## Known limitations that will remain

- No real cloud has ever been contacted. The real-credential code paths (no `endpoint_url`/`base_url`, `ServicePrincipalCredentials`) exist but are untested.
- The Azure VM create payload omits `network_profile`/NIC and would be rejected by real ARM. It only works against the fake ARM.
- Costs are estimates from a static price table, not billing data.
- `terraform apply` is not supported against the simulators. The AWS side only reaches a resource-targeted `plan`, and the Azure side only reaches `validate`. An untargeted plan fails because azurerm needs credentials.
- The fake ARM server implements only the resource group and VM endpoints the SDK calls here. It does not model NICs, disks or power state, so Azure `ip` is always null.
- `terraform init`, `make tf-*` and `make k8s-validate` need network access to download providers and schemas. The unit tests make no outbound calls, but building the image (which `make test` does first) needs PyPI access.
- The Kubernetes manifest is schema-validated but has never been deployed to a cluster.
- The API has no authentication and keeps no state of its own. State lives in the simulators and is lost when they restart.
- pytest is held at 3.5.1 because atomicwrites, which later pytests need, carries a 2022 re-upload date on PyPI and fails the period check.
