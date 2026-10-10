IMAGE ?= multicloud:dev
COMPOSE ?= docker compose -p multicloud
RUN_PORT ?= 20900
API_PORT ?= 20901
TERRAFORM ?= docker run --rm -v $(CURDIR)/terraform:/tf -w /tf hashicorp/terraform:0.11.10
KUBEVAL ?= docker run --rm -v $(CURDIR)/k8s:/k8s garethr/kubeval:0.7.3
TF_MOTO ?= docker run --rm --network multicloud_default -v $(CURDIR)/terraform:/tf -w /tf -e TF_VAR_aws_endpoint=http://moto:5000 hashicorp/terraform:0.11.10

.PHONY: build test run up down integration smoke api-key compose-check tf-validate tf-plan k8s-validate

build:
	docker build -t $(IMAGE) .

test: build
	docker run --rm $(IMAGE) sh -c "flake8 src simulators scripts tests && python -m pytest tests/unit -q"

run: build
	docker run --rm --name multicloud-run -p 127.0.0.1:$(RUN_PORT):8000 $(IMAGE) \
	  gunicorn -b 0.0.0.0:8000 "app:create_app()"

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down -v

integration: build
	$(MAKE) up
	$(COMPOSE) run --rm -e API_URL=http://api:8000 api python -m pytest tests/integration -q; \
	status=$$?; $(MAKE) down; exit $$status

# The key is piped to curl on stdin so it never shows up in a process list.
smoke:
	$(COMPOSE) exec -T api sh -c 'printf "Authorization: Bearer %s\n" "$$(cat $$MC_API_KEY_FILE)"' | \
	curl -sf -H @- -H 'Content-Type: application/json' \
	  -d '{"query": "{ instances { id provider } costs { total } }"}' \
	  http://127.0.0.1:$(API_PORT)/graphql

api-key:
	@$(COMPOSE) exec -T api cat /run/multicloud/api_key

# Renders the compose file and fails if any port is published beyond 127.0.0.1.
compose-check: build
	$(COMPOSE) config | docker run --rm -i $(IMAGE) python scripts/check_published_ports.py

tf-validate:
	$(TERRAFORM) init -backend=false -input=false
	$(TERRAFORM) validate
	$(TERRAFORM) fmt -check=true -diff=true

tf-plan:
	$(COMPOSE) up -d moto
	rm -f terraform/plan.log; \
	$(TF_MOTO) init -backend=false -input=false && \
	$(TF_MOTO) plan -input=false -no-color \
	  -target=module.aws_compute.data.aws_availability_zones.available \
	  -target=module.aws_compute.aws_instance.this | tee terraform/plan.log; \
	grep -q "Plan: 2 to add" terraform/plan.log && grep -q "us-east-1a" terraform/plan.log; \
	status=$$?; $(COMPOSE) stop moto; exit $$status

k8s-validate:
	$(KUBEVAL) --kubernetes-version 1.11.0 /k8s/deployment.yaml
