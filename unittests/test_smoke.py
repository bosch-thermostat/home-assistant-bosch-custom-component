"""Packaging smoke tests.

Standard library only, so CI can run them without installing Home Assistant.
They catch the class of breakage that is invisible until a user installs the
integration: a manifest that does not parse, has lost a key HACS or Home
Assistant requires, or has drifted from the directory it lives in.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
COMPONENT = REPO / "custom_components" / "bosch"
MANIFEST = COMPONENT / "manifest.json"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_exists_and_parses() -> None:
    assert MANIFEST.is_file(), f"no manifest at {MANIFEST}"
    assert isinstance(_manifest(), dict)


@pytest.mark.parametrize(
    "key",
    ["domain", "name", "documentation", "codeowners", "requirements", "version"],
)
def test_manifest_has_required_key(key: str) -> None:
    """`version` is not optional for a custom integration; HACS needs it."""
    manifest = _manifest()
    assert key in manifest, f"manifest.json is missing {key!r}"
    assert manifest[key] not in ("", [], None), f"manifest.json has an empty {key!r}"


def test_domain_matches_directory() -> None:
    """A mismatch here makes Home Assistant refuse to load the integration."""
    assert _manifest()["domain"] == COMPONENT.name


def test_config_flow_declared_and_translations_present() -> None:
    """config_flow: true without strings.json gives an unlabelled setup dialog."""
    manifest = _manifest()
    if manifest.get("config_flow"):
        assert (COMPONENT / "strings.json").is_file() or (
            COMPONENT / "translations" / "en.json"
        ).is_file(), "config_flow is true but no strings.json or translations/en.json"


def test_every_platform_module_is_importable_source() -> None:
    """Every .py in the package parses. Cheap guard against a broken commit."""
    import ast

    for path in sorted(COMPONENT.rglob("*.py")):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
