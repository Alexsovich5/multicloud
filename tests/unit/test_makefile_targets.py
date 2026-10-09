import os
import re

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
MAKEFILE = os.path.join(REPO_ROOT, "Makefile")


def _targets():
    """Map each Makefile target to its recipe text (tab-indented lines)."""
    with open(MAKEFILE) as handle:
        lines = handle.read().splitlines()
    variables = {}
    targets = {}
    current = None
    for line in lines:
        assign = re.match(r"^([A-Z_]+)\s*\??=\s*(.*)$", line)
        if assign:
            variables[assign.group(1)] = assign.group(2)
            current = None
            continue
        header = re.match(r"^([A-Za-z0-9_.-]+)\s*:(?!=)", line)
        if header and not line.startswith("\t"):
            current = header.group(1)
            targets[current] = []
            continue
        if current and line.startswith("\t"):
            targets[current].append(line.strip())
        elif current and line.strip() == "":
            continue
        else:
            current = None

    def expand(text):
        for _ in range(5):
            text = re.sub(
                r"\$\(([A-Z_]+)\)",
                lambda m: variables.get(m.group(1), m.group(0)),
                text)
        return text

    return {name: expand("\n".join(body)) for name, body in targets.items()}


@pytest.fixture(scope="module")
def tf_plan():
    targets = _targets()
    assert "tf-plan" in targets, "Makefile has no tf-plan target"
    return targets["tf-plan"]


def test_tf_plan_targets_the_aws_instances(tf_plan):
    assert "-target=module.aws_compute.aws_instance.this" in tf_plan


def test_tf_plan_targets_the_availability_zone_lookup(tf_plan):
    assert ("-target=module.aws_compute.data.aws_availability_zones"
            ".available") in tf_plan


def test_tf_plan_does_not_skip_refresh(tf_plan):
    assert "-refresh=false" not in tf_plan


def test_tf_plan_points_terraform_at_moto(tf_plan):
    assert "TF_VAR_aws_endpoint=http://moto:5000" in tf_plan
    assert "--network multicloud_default" in tf_plan


def test_tf_plan_checks_the_plan_output(tf_plan):
    assert 'grep -q "Plan: 2 to add"' in tf_plan
    assert 'grep -q "us-east-1a"' in tf_plan
