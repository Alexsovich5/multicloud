import os

import pytest
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
MANIFEST = os.path.join(REPO_ROOT, "k8s", "deployment.yaml")


@pytest.fixture(scope="module")
def documents():
    with open(MANIFEST) as handle:
        return [doc for doc in yaml.safe_load_all(handle) if doc]


@pytest.fixture(scope="module")
def deployment(documents):
    return next(doc for doc in documents if doc["kind"] == "Deployment")


@pytest.fixture(scope="module")
def service(documents):
    return next(doc for doc in documents if doc["kind"] == "Service")


@pytest.fixture(scope="module")
def container(deployment):
    containers = deployment["spec"]["template"]["spec"]["containers"]
    assert len(containers) == 1
    return containers[0]


def test_manifest_holds_exactly_a_deployment_and_a_service(documents):
    assert sorted(doc["kind"] for doc in documents) == [
        "Deployment", "Service"]


def test_deployment_uses_apps_v1(deployment):
    assert deployment["apiVersion"] == "apps/v1"
    assert deployment["metadata"]["name"] == "multicloud-api"


def test_deployment_selector_matches_template_labels(deployment):
    selector = deployment["spec"]["selector"]["matchLabels"]
    labels = deployment["spec"]["template"]["metadata"]["labels"]
    assert selector
    for key, value in selector.items():
        assert labels.get(key) == value


def test_deployment_runs_two_replicas_of_the_api_image(deployment,
                                                       container):
    assert deployment["spec"]["replicas"] == 2
    assert container["image"] == "multicloud:dev"


def test_container_listens_on_8000(container):
    ports = [port["containerPort"] for port in container["ports"]]
    assert ports == [8000]


@pytest.mark.parametrize("probe", ["readinessProbe", "livenessProbe"])
def test_probes_check_healthz(container, probe):
    http_get = container[probe]["httpGet"]
    assert http_get["path"] == "/healthz"
    assert http_get["port"] == 8000


def test_container_sets_simulator_endpoints(container):
    names = {item["name"] for item in container["env"]}
    assert {"MC_AWS_ENDPOINT", "MC_AZURE_BASE_URL"} <= names


def test_container_declares_requests_and_limits(container):
    resources = container["resources"]
    for section in ("requests", "limits"):
        assert set(resources[section]) == {"cpu", "memory"}


def test_service_targets_the_api_port(service, deployment):
    assert service["apiVersion"] == "v1"
    assert service["spec"]["type"] == "ClusterIP"
    ports = service["spec"]["ports"]
    assert len(ports) == 1
    assert ports[0]["port"] == 80
    assert ports[0]["targetPort"] == 8000
    labels = deployment["spec"]["template"]["metadata"]["labels"]
    for key, value in service["spec"]["selector"].items():
        assert labels.get(key) == value


def test_api_key_comes_from_a_secret_not_the_manifest(container):
    env = {item["name"]: item for item in container["env"]}
    key = env["MC_API_KEY"]
    assert "value" not in key
    ref = key["valueFrom"]["secretKeyRef"]
    assert ref == {"name": "multicloud-api-key", "key": "api-key"}
