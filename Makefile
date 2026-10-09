IMAGE ?= multicloud:dev
COMPOSE ?= docker compose -p multicloud
RUN_PORT ?= 20900
API_PORT ?= 20901

.PHONY: build test run up down integration smoke

build:
	docker build -t $(IMAGE) .

test: build
	docker run --rm $(IMAGE) sh -c "flake8 src simulators tests && python -m pytest tests/unit -q"

run: build
	docker run --rm -p $(RUN_PORT):8000 $(IMAGE) gunicorn -b 0.0.0.0:8000 "app:create_app()"

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down -v

integration: build
	$(MAKE) up
	$(COMPOSE) run --rm -e API_URL=http://api:8000 api python -m pytest tests/integration -q; \
	status=$$?; $(MAKE) down; exit $$status

smoke:
	curl -sf -H 'Content-Type: application/json' \
	  -d '{"query": "{ instances { id provider } costs { total } }"}' \
	  http://localhost:$(API_PORT)/graphql
