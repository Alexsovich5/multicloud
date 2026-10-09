# multicloud — Implementation Plan

This plan implements the design in `docs/SPEC.md`. Each task is one commit and leaves `make test` green. The acceptance commands run from the repo root on a host that has Docker and GNU make.

Conventions used throughout:
- `IMAGE ?= multicloud:dev` is built from `python:3.6.7-stretch`.
- `COMPOSE ?= docker compose -p multicloud`, so the compose network is `multicloud_default`.
- `PYTHONPATH=/app/src:/app`, so `providers`, `cloud_manager` and the rest import as top-level modules (the existing `from providers.aws_provider import ...` style stays), and `simulators` imports from the repo root.
- `AWS_ACCESS_KEY_ID=testing`, `AWS_SECRET_ACCESS_KEY=testing` and `AWS_DEFAULT_REGION=us-east-1` are set in the image, so boto3 never looks for real credentials.

---

## T1: Scaffold the Docker image, Makefile and test harness

- **Goal:** `make test` builds the period image and runs flake8 + pytest from the very first commit.
- **Files:**
  - create `Dockerfile`: `FROM python:3.6.7-stretch`, `WORKDIR /app`, copy the requirements files first, then `pip install --no-cache-dir -r requirements-dev.txt`, `COPY . /app`, set the ENV listed above, `EXPOSE 8000`.
  - create `.dockerignore` (`.git`, `.terraform`, `__pycache__`, `*.tfstate*`).
  - create `.gitignore` (`__pycache__/`, `.pytest_cache/`, `terraform/.terraform/`, `*.tfstate*`).
  - create `Makefile` with targets `build` (`docker build -t $(IMAGE) .`) and `test: build`. `test` runs `docker run --rm $(IMAGE) sh -c "flake8 src simulators tests && python -m pytest tests/unit -q"`. Because `test` depends on `build` and the code is baked in with `COPY . /app`, every `make test` runs the current working tree (Docker's layer cache keeps the rebuild fast).
  - create `setup.cfg`: a `[flake8]` section with max-line-length 100 and exclude `.terraform`, and a `[tool:pytest]` section with `testpaths = tests/unit`, so a bare `pytest` in the image never collects the compose-only integration tests.
  - modify `requirements.txt`: the 44 runtime pins from SPEC, one per line.
  - create `requirements-dev.txt`: `-r requirements.txt` plus the 28 dev pins.
  - create `src/providers/__init__.py` and `simulators/__init__.py` (both empty).
  - create `tests/__init__.py`, `tests/unit/__init__.py` and `tests/unit/test_environment.py`.
- **Tests to write first:** `test_environment.py` asserts `sys.version_info[:2] == (3, 6)` and that `flask.__version__ == "1.0.2"`, `graphene.VERSION[:3] == (2, 1, 3)`, `boto3.__version__ == "1.9.57"` and `moto.__version__ == "1.3.7"`, and that `azure.mgmt.compute` imports.
- **Acceptance:** `make test`, then check that edits are picked up: add a temporary `tests/unit/test_tmp.py` containing `def test_fail(): assert False`, confirm `make test` fails, delete the file and confirm `make test` passes again.
- **Commit:**
  ```
  Add period Docker image, Makefile and pytest harness

  Builds a python:3.6.7-stretch dev image with fully pinned
  dependencies and runs flake8 plus pytest via `make test`.
  ```

## T2: Introduce the provider base class and harden CloudManager

- **Goal:** Define a common provider interface and make `CloudManager` testable in isolation.
- **Files:**
  - create `src/providers/base.py`: a `CloudProvider` class whose four methods raise `NotImplementedError`, plus a `normalize_instance(**fields)` helper that returns the dict shape from SPEC.
  - modify `src/cloud_manager.py`:
    - add a `providers=None` injection argument to `__init__`;
    - add `provider_names()`;
    - make `_get(provider)` raise `ValueError("Unknown provider: x")`, and use it in `list_resources`, `provision` and `destroy`;
    - make `provision` require `spec["name"]`;
    - round `get_costs` values to 2 dp.
  - create `tests/unit/fakes.py`: a `FakeProvider(CloudProvider)` with an in-memory dict.
  - create `tests/unit/test_cloud_manager.py`.
- **Tests to write first:**
  - list across two fake providers, and filtered by one;
  - provision dispatches to the right provider;
  - unknown provider raises `ValueError` for list, provision and destroy;
  - a missing name raises `ValueError`;
  - `get_costs` returns per-provider values and a total equal to their rounded sum;
  - an empty config gives no providers.
- **Acceptance:** `make test`
- **Commit:**
  ```
  Add CloudProvider base class and validate CloudManager inputs

  Providers can now be injected, unknown provider names raise
  ValueError everywhere, and cost totals are rounded.
  ```

## T3: Add the static price table for cost estimates

- **Goal:** Replace the hard-coded `50.0` per instance with a reusable, config-driven price table.
- **Files:**
  - create `config/pricing.yaml` (content as in SPEC);
  - create `src/pricing.py` with `PriceTable.from_file(path)`, `.hourly(provider, size)` and `.monthly(provider, sizes)` (a list of sizes gives USD over `hours_per_month`, rounded to 2 dp). Unknown sizes return 0.0 and log a warning;
  - create `tests/unit/test_pricing.py`.
- **Tests to write first:**
  - `hourly("aws", "t2.micro") == 0.0116`;
  - `monthly("aws", ["t2.micro", "m4.large"]) == round((0.0116 + 0.10) * 730, 2)`;
  - an unknown size gives 0.0 and a caplog warning;
  - an unknown provider gives 0.0;
  - the file loads from the repo `config/` path.
- **Acceptance:** `make test`
- **Commit:**
  ```
  Add YAML price table for monthly compute cost estimates

  Costs are estimated as hourly list price times 730 hours per
  running instance; unknown sizes are priced at zero with a warning.
  ```

## T4: Make the AWS provider endpoint-configurable and test it with moto

- **Goal:** `AWSProvider` works unchanged against moto or real AWS, and has full CRUD plus cost.
- **Files:**
  - modify `src/providers/aws_provider.py`:
    - subclass `CloudProvider`, with `name = "aws"`;
    - the constructor takes `config`, `price_table=None` and `session=None`;
    - `endpoint_url = config.get("endpoint_url")` is passed to both `resource()` and `client()`;
    - `list_instances` skips the `terminated` and `shutting-down` states;
    - `create_instance` uses `spec.get("size", config default_size)` and `spec.get("image", config default_image)`, reloads the instance and returns the full normalized dict;
    - `destroy_instance` raises `KeyError` if the id is not found;
    - `get_monthly_cost` uses the price table over the types of running instances.
  - create `tests/unit/test_aws_provider.py`.
- **Tests to write first** (all under `@mock_ec2`):
  - create returns `provider == "aws"`, the Name tag, the requested type and `state in ("pending", "running")`;
  - list shows the created instance;
  - after destroy, the instance is gone from the list;
  - destroying an unknown id raises `KeyError`;
  - the cost of 2 running `t2.micro` is `round(2 * 0.0116 * 730, 2)`;
  - `endpoint_url` from config reaches the boto3 client (`provider.client.meta.endpoint_url`).
- **Acceptance:** `make test`
- **Commit:**
  ```
  Make AWS provider endpoint-configurable and cover it with moto

  Adds endpoint_url, default image/size, terminated-instance filtering
  and price-table costs; tests run against moto's in-process EC2 mock.
  ```

## T5: Add the fake Azure Resource Manager simulator

- **Goal:** A local stand-in for the ARM REST endpoints that the Azure SDK calls.
- **Files:**
  - create `simulators/fake_arm.py`:
    - `create_app()` is a Flask app holding in-memory RG and VM dicts;
    - routes as listed in SPEC, including HEAD on a resource group (204 if it exists, 404 if not), because `resource_groups.check_existence` treats any other status as an error and Flask would otherwise answer HEAD through the GET view with 200;
    - case-insensitive paths: Flask matches the URL before any `before_request` hook runs and Werkzeug rules are case-sensitive, so `create_app()` wraps `app.wsgi_app` in a WSGI middleware that copies `environ["PATH_INFO"]` to `environ["fake_arm.original_path"]` and then lower-cases `PATH_INFO`. All routes are declared in lower case. RG and VM dicts are keyed by the lower-cased name, and response bodies use the original-case name recovered from the saved path;
    - ARM-style error JSON (`{"error": {"code": "ResourceNotFound", "message": ...}}`);
    - `main()` runs on `0.0.0.0:${PORT:-5001}`.
  - create `tests/unit/test_fake_arm.py`.
- **Tests to write first** (Flask test client):
  - PUT RG gives 201, then GET gives 200; an unknown RG gives 404 with an error code;
  - PUT VM sets `properties.provisioningState == "Succeeded"` and the `id` path;
  - list returns `{"value": [...]}` filtered by RG;
  - DELETE gives 200, then GET gives 404;
  - HEAD on a resource group gives 404 before it is created and 204 after;
  - `resourcegroups` and `resourceGroups` paths both match (through the test client, so the middleware is exercised), and a VM created as `Web1` is returned with `name == "Web1"`;
  - two `create_app()` instances don't share state.
- **Acceptance:** `make test`
- **Commit:**
  ```
  Add fake Azure Resource Manager simulator for local testing

  Implements the resource group and virtual machine REST calls used
  by azure-mgmt-compute and azure-mgmt-resource, backed by memory.
  ```

## T6: Implement the Azure provider with the real Azure SDK

- **Goal:** Replace the logging stubs with real `azure-mgmt-*` calls, verified against the fake ARM.
- **Files:**
  - create `tests/conftest.py`: a `fake_arm_url` fixture that starts `simulators.fake_arm.create_app()` in a daemon thread via `werkzeug.serving.make_server("127.0.0.1", 0, app)`, yields `http://127.0.0.1:<port>`, then shuts down.
  - modify `src/providers/azure_provider.py`:
    - subclass `CloudProvider`, with `name = "azure"`;
    - `_credentials()` uses `BasicTokenAuthentication({"access_token": "fake"})` when `base_url` is set, and otherwise `ServicePrincipalCredentials` from `AZURE_CLIENT_ID/SECRET/TENANT`;
    - build `ComputeManagementClient` and `ResourceManagementClient` with `base_url`;
    - `create_instance` calls `resource_groups.create_or_update` and then `virtual_machines.create_or_update(rg, name, {location, hardware_profile: {vm_size}, storage_profile: {image_reference}, os_profile: {computer_name, admin_username}}).result()`. The payload has no `network_profile`/NIC; real ARM would reject it, and this is recorded as a known limitation in SPEC and the README;
    - `list_instances` calls `virtual_machines.list(rg)` and maps `succeeded` to `running`;
    - `destroy_instance` checks with `get` (a `CloudError` 404 becomes `KeyError`), then calls `delete(...).result()`;
    - `get_monthly_cost` uses the price table over the `vm_size` of each VM.
  - create `tests/unit/test_azure_provider.py`.
- **Tests to write first:**
  - create returns `provider == "azure"`, `type == "Standard_B2s"`, `state == "running"`, and `region == "eastus"`;
  - the RG exists in the fake after the first create;
  - list shows the VM;
  - destroy removes it;
  - destroying an unknown name raises `KeyError`;
  - the cost of one `Standard_B2s` is `round(0.0416 * 730, 2)`;
  - without `base_url` and without env credentials, the constructor raises a clear `ValueError`.
- **Acceptance:** `make test`
- **Commit:**
  ```
  Implement Azure provider with azure-mgmt-compute and resource SDKs

  Creates, lists and deletes VMs (auto-creating the resource group)
  against a configurable ARM base_url; tested against the fake ARM.
  ```

## T7: Add YAML configuration and the manager factory

- **Goal:** Build a fully wired `CloudManager` from one config file, with env overrides.
- **Files:**
  - create `config/multicloud.yml` (as in SPEC);
  - create `src/config.py` with `load_config(path=None)`. It reads the path from `MC_CONFIG` or defaults to `config/multicloud.yml`, and applies the `MC_AWS_ENDPOINT` / `MC_AZURE_BASE_URL` overrides. A provider set to `enabled: false` is removed;
  - modify `src/cloud_manager.py`: add `build_manager(config_path=None)`, which loads the config and the price table and passes the table to providers, and a `currency` property (the price table's `currency`, `"USD"` when no table is wired);
  - create `tests/unit/test_config.py`.
- **Tests to write first:**
  - the default file parses and has both providers;
  - the env var overrides endpoint_url and base_url (monkeypatch);
  - `enabled: false` drops the provider;
  - `build_manager` is tested in three steps, so no fake-ARM HTTP call runs inside an active moto mock. moto 1.3.7's `mock_ec2` starts `responses`' default mock, which patches `requests.adapters.HTTPAdapter.send` with no passthrough, and msrest sends the Azure SDK calls through `requests`. Inside `mock_ec2`, a call to `http://127.0.0.1:<port>` would therefore fail with responses' `ConnectionError: Connection refused`. The temp config omits `aws.endpoint_url` and the test clears `MC_AWS_ENDPOINT` with monkeypatch, because moto 1.3.7's in-process mock only intercepts `https?://ec2.<region>.amazonaws.com` URLs. Only `azure.base_url` points at the `fake_arm_url` fixture. The steps are:
    1. wiring, with no HTTP: `provider_names() == ["aws", "azure"]`, the providers are an `AWSProvider` and an `AzureProvider`, both hold the loaded price table, the Azure provider's `base_url` equals `fake_arm_url`, and `currency == "USD"`;
    2. `list_resources("aws")` inside a `mock_ec2` block returns a list;
    3. `list_resources("azure")` after that block has exited (outside any moto mock) returns a list from the fake ARM.
  No test loads the default `config/multicloud.yml` and then calls AWS.
- **Acceptance:** `make test`
- **Commit:**
  ```
  Load providers from YAML config with environment overrides

  Adds config/multicloud.yml and build_manager(), which wires the
  price table into each enabled provider.
  ```

## T8: Add GraphQL queries for providers, instances and costs

- **Goal:** Read side of the GraphQL API.
- **Files:**
  - create `src/graphql_schema.py` with graphene types `Instance`, `ProviderCost` and `Costs`, and a `Query` with `providers`, `instances(provider)` and `costs`. The resolvers use `root` (the `CloudManager` passed as `root_value`). `Costs.currency` resolves from `root.currency`. Export `schema = graphene.Schema(query=Query)`;
  - create `tests/unit/test_graphql_queries.py`, using `FakeProvider`s from `tests/unit/fakes.py`.
- **Tests to write first:**
  - `{ providers }` returns both names;
  - `{ instances { id provider type } }` merges both providers;
  - `instances(provider:"aws")` filters;
  - `instances(provider:"gcp")` returns `errors[0].message == "Unknown provider: gcp"`;
  - `{ costs { breakdown { provider monthly } total currency } }` matches `get_costs()`, with `currency == "USD"` (the `CloudManager.currency` default, since the fakes have no price table).
- **Acceptance:** `make test`
- **Commit:**
  ```
  Add GraphQL schema with provider, instance and cost queries

  Graphene 2 types expose the unified instance list and per-cloud
  cost breakdown from CloudManager.
  ```

## T9: Add GraphQL mutations for provisioning and destroying

- **Goal:** Write side of the GraphQL API.
- **Files:**
  - modify `src/graphql_schema.py`: add `ProvisionInstance(graphene.Mutation)` (args `provider!`, `name!`, `size`, `image`; `Output = Instance`) and `DestroyInstance(graphene.Mutation)` (args `provider!`, `id!`; `Output = DestroyResult` with fields `ok: Boolean!` and `id: String`). Add a `Mutation` type exposing them as `provisionInstance` and `destroyInstance`, and export `schema = graphene.Schema(query=Query, mutation=Mutation)`.
  - create `tests/unit/test_graphql_mutations.py`.
- **Tests to write first:**
  - provision on a fake provider returns the instance, and a following `instances` query includes it;
  - destroy returns `{ ok: true, id }`, and the instance is gone;
  - an unknown provider gives a GraphQL error;
  - a missing `name` fails schema validation;
  - variables are passed through (`$p: String!`).
- **Acceptance:** `make test`
- **Commit:**
  ```
  Add provisionInstance and destroyInstance GraphQL mutations

  Mutations dispatch through CloudManager so either cloud can be
  provisioned or torn down with the same call.
  ```

## T10: Serve the API with Flask, Flask-GraphQL and gunicorn

- **Goal:** An HTTP entry point with GraphiQL and a health check.
- **Files:**
  - create `src/app.py`:
    - `create_app(manager=None)` builds a Flask app. It registers `/graphql` via `GraphQLView.as_view("graphql", schema=schema, graphiql=True, root_value=manager or build_manager())` and `/healthz` returning JSON;
    - no module-level `app` object: gunicorn 19.9 evaluates the factory call itself (`gunicorn "app:create_app()"`), so importing `app` in tests never calls `build_manager()`;
  - modify `Makefile`: add `RUN_PORT ?= 20900` and a `run: build` target (`docker run --rm -p $(RUN_PORT):8000 $(IMAGE) gunicorn -b 0.0.0.0:8000 "app:create_app()"`). gunicorn listens on 8000 inside the container; the host side is 20900 because this build shares its Docker host with other projects and is limited to host ports 20900-20999;
  - create `tests/unit/test_app.py`.
- **Tests to write first** (test client, fake providers injected):
  - `POST /graphql` with a JSON `{ providers }` query returns 200 and data;
  - `GET /graphql` with `Accept: text/html` contains `graphiql`;
  - `GET /healthz` returns `{"status": "ok", "providers": ["aws", "azure"]}`;
  - a malformed query returns 400 with errors.
- **Acceptance:** `make test`
- **Commit:**
  ```
  Serve GraphQL API through Flask with GraphiQL and health check

  Adds an app factory usable by gunicorn and the test client.
  ```

## T11: Add the docker-compose stack and integration tests

- **Goal:** `api` + `moto` + `fake-arm` run together, and the end-to-end flow is tested over HTTP.
- **Files:**
  - create `docker-compose.yml` (version "3.6"):
    - `api`: `build: .` and `image: multicloud:dev`, command `gunicorn -b 0.0.0.0:8000 "app:create_app()"`, env `MC_AWS_ENDPOINT=http://moto:5000` and `MC_AZURE_BASE_URL=http://fake-arm:5001`, `depends_on` both, ports `20901:8000` (gunicorn stays on 8000 in the container; host port 20901 because this Docker host is shared and this project is limited to host ports 20900-20999, with 20900 taken by `make run`);
    - `moto`: `image: multicloud:dev` (no `build`), command `moto_server ec2 -H 0.0.0.0 -p 5000`;
    - `fake-arm`: `image: multicloud:dev` (no `build`), command `python -m simulators.fake_arm`, `PORT=5001`.
    One image serves all three services, as SPEC states. The default network uses the fixed subnet `172.49.0.0/24` (`networks.default.ipam`) so it does not collide with other projects on the same host.
  - create `tests/integration/__init__.py` and `tests/integration/conftest.py`. The conftest reads `API_URL` (default `http://api:8000`), `MOTO_URL` (default `http://moto:5000`) and `FAKE_ARM_URL` (default `http://fake-arm:5001`), and polls all three for up to 60 s (`/healthz` must return 200; for moto and fake-arm any HTTP response counts) before any test runs. If `API_URL` is unset outside compose, the tests are skipped.
  - create `tests/integration/test_stack.py`.
  - modify `Makefile`:
    - `up`: `$(COMPOSE) up -d --build`;
    - `down`: `$(COMPOSE) down -v`;
    - `integration: build`: `up`, then `$(COMPOSE) run --rm -e API_URL=http://api:8000 api python -m pytest tests/integration -q`, then `down`, preserving the exit code;
    - `API_PORT ?= 20901` and `smoke`: curl a `{ instances { id provider } costs { total } }` query to `localhost:$(API_PORT)/graphql`.
- **Tests to write first:**
  - provision `aws/web-aws` and `azure/web-azure` via mutations;
  - `instances` contains both providers;
  - `costs.total == sum(breakdown)` and is > 0;
  - destroy both, and `instances` no longer contains them.
- **Acceptance:** `make test && make integration`
- **Commit:**
  ```
  Add docker-compose stack with moto and fake ARM plus e2e tests

  Runs the API against simulated AWS and Azure endpoints and checks
  provision, list, cost and destroy over HTTP.
  ```

## T12: Rewrite Terraform in 0.11 syntax with a shared compute module

- **Goal:** Make the IaC valid for Terraform 0.11.10, with the missing module present.
- **Files:**
  - modify `terraform/main.tf`:
    - pin provider versions (`aws` `= 1.46.0`, `azurerm` `= 1.19.0`);
    - the aws provider block gets `access_key`/`secret_key` from variables, `skip_credentials_validation`, `skip_requesting_account_id`, `skip_metadata_api_check`, `skip_get_ec2_platforms`, `skip_region_validation`, and `endpoints { ec2 = "${var.aws_endpoint}" }`;
    - the azurerm provider gets `skip_credentials_validation = true` (it is never configured by `make tf-plan`, because that plan targets only AWS resources);
    - add `azurerm_resource_group`, `azurerm_virtual_network` and `azurerm_subnet`;
    - call `module "aws_compute"` (with `azure_subnet_id = ""` and no Azure references) and `module "azure_compute"` (with `azure_subnet_id = "${azurerm_subnet.main.id}"`);
    - replace every bare reference with `"${...}"`.
  - create `terraform/variables.tf` (`aws_endpoint` default `https://ec2.us-east-1.amazonaws.com`, `aws_access_key`/`aws_secret_key` default `testing`, `instance_count` default 2, `aws_instance_type` default `m4.large`, `azure_vm_size` default `Standard_B2s`, plus `azure_location` default `East US` and `ssh_public_key`, a placeholder key passed to the Azure module call, because `ssh_keys.key_data` is required).
  - create `terraform/outputs.tf`.
  - create `terraform/modules/compute/main.tf`, `variables.tf` and `outputs.tf`: a `data "aws_availability_zones" "available" {}` lookup, count-gated `aws_instance.this` (with `availability_zone = "${element(data.aws_availability_zones.available.names, count.index)}"`) and `azurerm_network_interface` + `azurerm_virtual_machine` (with `os_profile_linux_config` and `ssh_keys` from a variable), per SPEC.
  - modify `Makefile`: add a `tf-validate` target that runs `docker run --rm -v $(CURDIR)/terraform:/tf -w /tf hashicorp/terraform:0.11.10` with `init -backend=false -input=false`, then `validate`, then `fmt -check=true -diff=true`.
  - create `tests/unit/test_terraform_layout.py`.
- **Tests to write first:** `test_terraform_layout.py` does a regex check that no `.tf` file contains a bare `= (aws|azurerm)_\w+\.\w+` reference outside `${}`, that `modules/compute/main.tf` exists, and that both providers pin `version = "= x.y.z"`.
- **Acceptance:** `make test && make tf-validate`
- **Commit:**
  ```
  Rewrite Terraform for 0.11 with shared multi-cloud compute module

  Replaces 0.12-style references with interpolation, adds the missing
  modules/compute and pins aws 1.46.0 and azurerm 1.19.0 providers.
  ```

## T13: Plan the AWS Terraform module against moto

- **Goal:** Show that the AWS side of the IaC produces a plan that really queries the simulated EC2 endpoint.
- **Design (verified):** the plan targets resources, not the module: `-target=module.aws_compute.data.aws_availability_zones.available -target=module.aws_compute.aws_instance.this`. Targeting `module.aws_compute` as a whole also pulls in the count-0 azurerm resources, and azurerm 1.19.0 then fails to configure ("Azure CLI Authorization Profile was not found"). With the resource targets and no `-refresh=false`, Terraform 0.11.10 with aws 1.46.0 reads the zones from moto 1.3.7 (`us-east-1a`, `us-east-1b`) and prints `Plan: 2 to add`. With moto stopped, the same plan fails with `Error fetching Availability Zones`. This was checked with the Terraform 0.11.10 binary and `moto_server ec2` 1.3.7 run outside Docker.
- **Files:**
  - create `tests/unit/test_makefile_targets.py` first (see below).
  - modify `Makefile`: add a `tf-plan` target. It runs `$(COMPOSE) up -d moto`, then `docker run --rm --network multicloud_default -v $(CURDIR)/terraform:/tf -w /tf -e TF_VAR_aws_endpoint=http://moto:5000 hashicorp/terraform:0.11.10` with `init -backend=false -input=false` and `plan -input=false -target=module.aws_compute.data.aws_availability_zones.available -target=module.aws_compute.aws_instance.this`, piped to `tee terraform/plan.log`. It then checks `grep -q "Plan: 2 to add" terraform/plan.log && grep -q "us-east-1a" terraform/plan.log`, and finally runs `$(COMPOSE) stop moto`.
  - modify `.gitignore`: add `terraform/plan.log`.
- **Tests to write first:** `tests/unit/test_makefile_targets.py` parses the `Makefile` and asserts that a `tf-plan` target exists, that its recipe contains both `-target=module.aws_compute.aws_instance.this` and `-target=module.aws_compute.data.aws_availability_zones.available`, that it does not use `-refresh=false`, and that it greps for `Plan: 2 to add` and `us-east-1a`.
- **Acceptance:** `make test && make tf-plan`
- **Commit:**
  ```
  Add make tf-plan to plan the AWS compute module against moto

  Targets the AWS resources and uses the compose moto service as the
  EC2 endpoint, so the plan reads zones from moto without credentials.
  ```

## T14: Add the Kubernetes 1.11 manifest for the API

- **Goal:** Deployment and Service manifests for the API, validated against the 1.11 schemas.
- **Files:**
  - create `k8s/deployment.yaml`, a multi-doc file with:
    - a `apps/v1` Deployment `multicloud-api`: 2 replicas, image `multicloud:dev`, containerPort 8000, readiness and liveness `httpGet /healthz`, env `MC_AWS_ENDPOINT`/`MC_AZURE_BASE_URL`, and resource requests/limits;
    - a `v1` Service `multicloud-api` (ClusterIP, 80→8000).
  - modify `Makefile`: add a `k8s-validate` target (`docker run --rm -v $(CURDIR)/k8s:/k8s garethr/kubeval:0.7.3 --kubernetes-version 1.11.0 /k8s/deployment.yaml`).
  - create `tests/unit/test_k8s_manifest.py`.
- **Tests to write first:**
  - `yaml.safe_load_all` yields exactly Deployment and Service;
  - the Deployment is `apps/v1` and its selector matches the template labels;
  - the container port is 8000 and the probe path is `/healthz`;
  - the Service targetPort is 8000.
- **Acceptance:** `make test && make k8s-validate`
- **Commit:**
  ```
  Add Kubernetes 1.11 Deployment and Service for the GraphQL API

  Manifests are checked by a structural unit test and by kubeval
  against the v1.11.0 schemas.
  ```

## T15: Regenerate the README from the template with honest status

- **Goal:** A README that describes exactly what the repo does.
- **Files:**
  - modify `README.md`, filled from `tools/readme_template.md`:
    - title "Multi-Cloud Management Platform";
    - a one-paragraph description;
    - "Personal project built on the 2018-era stack (Python 3.6, Flask 1.0, Graphene 2, Terraform 0.11)";
    - an Implemented list with one bullet per in-scope SPEC feature, each mapped to code and a test;
    - a Not implemented / known limitations list covering every out-of-scope item and known limitation. It must say that AWS is simulated by moto, Azure by the local fake ARM server (`simulators/fake_arm.py`), and costs come from a static price table, and that the code has never been run against real AWS or Azure;
    - a Built with section listing the pinned versions;
    - Running it: `docker compose -p multicloud up`, then `make smoke`;
    - Tests: `make test`, plus a sentence on `make integration`, `make tf-validate`, `make tf-plan` and `make k8s-validate`;
    - a Layout tree generated on the host with `git ls-files | python3 -c 'import sys; [print("  " * (p.count("/")) + p.rsplit("/", 1)[-1]) for p in sorted(l.strip() for l in sys.stdin)]'` (paths indented by depth), pasted into a fenced block under a `## Layout` heading, and a `MANIFEST` file committed alongside it holding the raw `git ls-files` output (MANIFEST lists itself).
  - No badges, employer names, roles, dates or metrics.
- **Tests to write first:** create `tests/unit/test_readme.py`. It asserts that:
  - every backticked path anywhere in the README that looks like a file or directory (contains `/` or ends in a known extension) exists, checked with `os.path.exists` relative to the repo root (`git ls-files` is not available in the image);
  - every path in `MANIFEST` exists and appears in the Layout block, so no tracked file is left out;
  - the README contains no `img.shields.io` badges, no line starting with `Role:`, `Organization:` or `Developed during` (bold markers stripped first), and no percentage metrics (`\d+(\.\d+)?%`).
  The test uses only these generic patterns. No employer name appears in the repo; any employer denylist stays in the shared tools outside the repo.
- **Acceptance:** `make test`
- **Commit:**
  ```
  Rewrite README from template with honest status and layout

  Documents what is implemented, what is simulated (moto, fake ARM,
  static prices) and how to run and test the stack.
  ```

---

Total: 15 tasks (T1–T15). Each task depends only on the tasks before it:
- T2–T3 come before T4 and T6, which use the base class and the price table.
- T5 comes before T6, whose tests use the fake ARM.
- T7 comes before T10 and T11.
- T8 and T9 come before T10, which comes before T11.
- T11 provides the moto service that T13 uses.
