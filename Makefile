IMAGE ?= multicloud:dev
COMPOSE ?= docker compose -p multicloud
RUN_PORT ?= 20900

.PHONY: build test run

build:
	docker build -t $(IMAGE) .

test: build
	docker run --rm $(IMAGE) sh -c "flake8 src simulators tests && python -m pytest tests/unit -q"

run: build
	docker run --rm -p $(RUN_PORT):8000 $(IMAGE) gunicorn -b 0.0.0.0:8000 "app:create_app()"
