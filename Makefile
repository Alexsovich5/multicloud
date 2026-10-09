IMAGE ?= multicloud:dev
COMPOSE ?= docker compose -p multicloud

.PHONY: build test

build:
	docker build -t $(IMAGE) .

test: build
	docker run --rm $(IMAGE) sh -c "flake8 src simulators tests && python -m pytest tests/unit -q"
