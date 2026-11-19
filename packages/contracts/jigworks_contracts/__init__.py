"""Frozen Jigworks contracts (T02).

Models are generated from schema/jigworks.schema.json (see scripts/generate.py).
Pydantic does not express the RunEvent kind → payload rules; use `validate()` or
`parse_event()` at every boundary (runner emit, hub ingest).
"""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from . import models
from .models import *  # noqa: F403

HUB_KEY_HEADER = "X-Jigworks-Key"
HUB_SESSION_COOKIE = "jigworks_session"
PUBLIC_ENDPOINTS = ("GET /api/health", "POST /api/session")


def _schema_text() -> str:
    packaged = resources.files(__package__) / "jigworks.schema.json"
    if packaged.is_file():  # installed wheel (force-include)
        return packaged.read_text()
    return (Path(__file__).resolve().parent.parent / "schema" / "jigworks.schema.json").read_text()


@cache
def schema() -> dict[str, Any]:
    return json.loads(_schema_text())


@cache
def _validator(def_name: str) -> Draft202012Validator:
    root = schema()
    if def_name not in root["$defs"]:
        raise KeyError(f"unknown contract definition: {def_name}")
    registry = Registry().with_resource(root["$id"], Resource.from_contents(root))
    return Draft202012Validator(
        {"$ref": f"{root['$id']}#/$defs/{def_name}"},
        registry=registry,
        format_checker=FormatChecker(),
    )


def validate(def_name: str, value: Any) -> list[str]:
    """Return a list of error messages (empty when `value` matches `$defs/<def_name>`)."""
    errors = sorted(_validator(def_name).iter_errors(value), key=lambda e: list(e.absolute_path))
    return [f"/{'/'.join(map(str, e.absolute_path))} {e.message}" for e in errors]


def assert_valid(def_name: str, value: Any) -> None:
    errors = validate(def_name, value)
    if errors:
        raise ValueError(f"invalid {def_name}: {'; '.join(errors)}")


def parse_event(value: dict[str, Any]) -> models.RunEvent:
    """Validate against the JSON Schema (incl. kind rules), then build the pydantic model."""
    assert_valid("RunEvent", value)
    return models.RunEvent.model_validate(value)
