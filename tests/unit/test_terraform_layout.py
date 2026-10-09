import os
import re

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
TF_DIR = os.path.join(REPO_ROOT, "terraform")

BARE_REFERENCE = re.compile(r"=\s*(aws|azurerm)_\w+\.\w+")
INTERPOLATION = re.compile(r'"\$\{[^"]*\}"')


def _tf_files():
    found = []
    for root, dirs, files in os.walk(TF_DIR):
        dirs[:] = [d for d in dirs if d != ".terraform"]
        for name in files:
            if name.endswith(".tf"):
                found.append(os.path.join(root, name))
    return sorted(found)


def _read(path):
    with open(path) as handle:
        return handle.read()


def _provider_block(text, provider):
    match = re.search(
        r'provider\s+"%s"\s*\{(.*?)\n\}' % provider, text, re.S)
    assert match, "provider %s block missing" % provider
    return match.group(1)


def test_terraform_files_exist():
    assert _tf_files(), "no .tf files under terraform/"


def test_compute_module_exists():
    assert os.path.isfile(
        os.path.join(TF_DIR, "modules", "compute", "main.tf"))


@pytest.mark.parametrize("name", ["variables.tf", "outputs.tf"])
def test_compute_module_has_inputs_and_outputs(name):
    assert os.path.isfile(os.path.join(TF_DIR, "modules", "compute", name))


def test_no_bare_resource_references_outside_interpolation():
    offenders = []
    for path in _tf_files():
        for number, line in enumerate(_read(path).splitlines(), 1):
            stripped = INTERPOLATION.sub('""', line.split("#", 1)[0])
            if BARE_REFERENCE.search(stripped):
                offenders.append("%s:%d: %s" % (
                    os.path.relpath(path, TF_DIR), number, line.strip()))
    assert offenders == []


def test_bare_reference_check_catches_012_syntax():
    line = "  location = azurerm_resource_group.main.location"
    assert BARE_REFERENCE.search(INTERPOLATION.sub('""', line))
    wrapped = '  location = "${azurerm_resource_group.main.location}"'
    assert not BARE_REFERENCE.search(INTERPOLATION.sub('""', wrapped))


@pytest.mark.parametrize("provider,version", [
    ("aws", "1.46.0"),
    ("azurerm", "1.19.0"),
])
def test_providers_are_pinned_exactly(provider, version):
    block = _provider_block(_read(os.path.join(TF_DIR, "main.tf")), provider)
    pins = re.findall(r'version\s*=\s*"=\s*(\d+\.\d+\.\d+)"', block)
    assert pins == [version]


def test_main_calls_compute_module_for_both_clouds():
    text = _read(os.path.join(TF_DIR, "main.tf"))
    for name, kind in (("aws_compute", "aws"), ("azure_compute", "azure")):
        match = re.search(r'module\s+"%s"\s*\{(.*?)\n\}' % name, text, re.S)
        assert match, "module %s missing" % name
        body = match.group(1)
        assert re.search(r'source\s*=\s*"\./modules/compute"', body)
        assert re.search(r'provider_type\s*=\s*"%s"' % kind, body)


def test_aws_module_call_has_no_azure_references():
    text = _read(os.path.join(TF_DIR, "main.tf"))
    body = re.search(
        r'module\s+"aws_compute"\s*\{(.*?)\n\}', text, re.S).group(1)
    assert re.search(r'azure_subnet_id\s*=\s*""', body)
    assert "azurerm_" not in body
