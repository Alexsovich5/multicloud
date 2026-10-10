import os
import re

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
README = os.path.join(REPO_ROOT, "README.md")
MANIFEST = os.path.join(REPO_ROOT, "MANIFEST")

PATH_EXTENSIONS = (
    ".py", ".md", ".txt", ".yml", ".yaml", ".tf", ".cfg", ".json",
    ".log", ".sh", ".ini",
)
PATH_NAMES = ("Makefile", "Dockerfile", "MANIFEST")


@pytest.fixture(scope="module")
def readme():
    with open(README) as handle:
        return handle.read()


@pytest.fixture(scope="module")
def manifest():
    with open(MANIFEST) as handle:
        return [line.strip() for line in handle if line.strip()]


def _looks_like_path(token):
    if re.search(r"\s", token) or "://" in token or token.startswith("/"):
        return False
    return ("/" in token or token.endswith(PATH_EXTENSIONS)
            or token in PATH_NAMES)


def _backticked(text):
    without_fences = re.sub(r"```.*?```", "", text, flags=re.S)
    return re.findall(r"`([^`\n]+)`", without_fences)


def _layout_block(text):
    match = re.search(r"^## Layout\s*\n+```[^\n]*\n(.*?)^```", text,
                      flags=re.S | re.M)
    assert match, "README has no fenced block under '## Layout'"
    return match.group(1).splitlines()


def _render_tree(paths):
    """Indented tree: each directory once as ``name/``, then its files."""
    lines, seen = [], set()
    for path in sorted(paths):
        parts = path.split("/")
        for depth in range(len(parts) - 1):
            directory = "/".join(parts[:depth + 1])
            if directory not in seen:
                seen.add(directory)
                lines.append("  " * depth + parts[depth] + "/")
        lines.append("  " * (len(parts) - 1) + parts[-1])
    return lines


def test_backticked_paths_exist(readme):
    paths = [t.rstrip("/") for t in _backticked(readme) if _looks_like_path(t)]
    assert paths, "expected the README to reference repository paths"
    missing = [p for p in paths
               if not os.path.exists(os.path.join(REPO_ROOT, p))]
    assert missing == []


def test_manifest_paths_exist(manifest):
    assert "MANIFEST" in manifest
    missing = [p for p in manifest
               if not os.path.exists(os.path.join(REPO_ROOT, p))]
    assert missing == []


def test_layout_lists_every_manifest_path(readme, manifest):
    layout = _layout_block(readme)
    expected = _render_tree(manifest)
    absent = [line for line in expected if line not in layout]
    assert absent == []
    assert layout == expected


def test_no_badges(readme):
    assert "img.shields.io" not in readme


def test_no_role_or_organisation_lines(readme):
    for line in readme.splitlines():
        plain = line.replace("**", "").replace("__", "").strip()
        plain = re.sub(r"^[-*]\s+", "", plain)
        assert not re.match(r"(Role:|Organization:|Developed during)", plain), line


def test_render_tree_lists_each_directory_once(manifest):
    assert "README.md" in manifest and "docs/SPEC.md" in manifest
    assert "config/" in _render_tree(manifest)
    assert "  multicloud.yml" in _render_tree(manifest)


def test_no_era_wording(readme):
    assert not re.search(r"\b(19|20)\d\d-era\b|\bera\b", readme, flags=re.I)


def test_no_percentage_metrics(readme):
    assert re.findall(r"\d+(\.\d+)?%", readme) == []
