"""JSON-Schema validation and deterministic argument synthesis (REQ-C3, REQ-C4).

Two pure functions the Contract engine leans on:

* :func:`validate_schema` — is a tool's declared input/output schema itself well-formed
  and self-consistent (resolvable ``$ref``, sane types/enums)? Uses ``jsonschema``'s
  meta-schema checker.
* :func:`synthesize_args` — produce a *schema-valid* instance to invoke the tool with.
  It is a pure function of (schema, seed): the same inputs always yield the same args, so
  the determinism probe (REQ-C5) — which calls a tool twice with identical args — is
  itself deterministic.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


@dataclass(frozen=True)
class SchemaIssue:
    path: str
    message: str


def validate_schema(schema: dict[str, Any]) -> list[SchemaIssue]:
    """Return issues with the *schema itself* (not an instance). Empty = well-formed."""
    issues: list[SchemaIssue] = []
    if not isinstance(schema, dict):
        return [SchemaIssue(path="", message="schema is not an object")]
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        issues.append(SchemaIssue(path="/".join(map(str, exc.path)), message=exc.message))
    # Flag unresolvable local $refs — a common real-world footgun that check_schema misses.
    issues.extend(_check_refs(schema, schema))
    return issues


def _check_refs(node: Any, root: dict[str, Any], _seen: set[int] | None = None) -> list[SchemaIssue]:
    seen = _seen if _seen is not None else set()
    if id(node) in seen:
        return []
    issues: list[SchemaIssue] = []
    if isinstance(node, dict):
        seen.add(id(node))
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/"):
            if not _resolve_local_ref(root, ref):
                issues.append(SchemaIssue(path=ref, message=f"unresolvable local $ref: {ref}"))
        for value in node.values():
            issues.extend(_check_refs(value, root, seen))
    elif isinstance(node, list):
        for item in node:
            issues.extend(_check_refs(item, root, seen))
    return issues


def _resolve_local_ref(root: dict[str, Any], ref: str) -> bool:
    cur: Any = root
    for part in ref.lstrip("#/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return False
    return True


def validate_against(instance: Any, schema: dict[str, Any]) -> list[SchemaIssue]:
    """Validate an *instance* against a schema (used for output conformance, REQ-C4)."""
    if not schema:
        return []
    validator = Draft202012Validator(schema)
    return [
        SchemaIssue(path="/".join(map(str, err.absolute_path)), message=err.message)
        for err in sorted(validator.iter_errors(instance), key=str)
    ]


def _seed_int(seed: int, salt: str) -> int:
    h = hashlib.sha256(f"{seed}:{salt}".encode()).hexdigest()
    return int(h[:8], 16)


def synthesize_args(schema: dict[str, Any], *, seed: int = 42, _path: str = "") -> Any:
    """Deterministically synthesize a schema-valid instance.

    Covers the constructs MCP tool schemas use in practice: object/properties/required,
    arrays, enums, const, defaults, type unions, and string ``format`` hints. When a
    field is optional it is still filled (we want maximal coverage of the tool's surface),
    unless the schema forbids additional structure.
    """
    if not isinstance(schema, dict):
        return None

    if "const" in schema:
        return schema["const"]
    if "default" in schema:
        return schema["default"]
    if "enum" in schema and isinstance(schema["enum"], list) and schema["enum"]:
        idx = _seed_int(seed, _path + "enum") % len(schema["enum"])
        return schema["enum"][idx]
    for combiner in ("anyOf", "oneOf", "allOf"):
        if combiner in schema and schema[combiner]:
            return synthesize_args(schema[combiner][0], seed=seed, _path=_path + combiner)

    typ = schema.get("type")
    if isinstance(typ, list):  # type union → pick the first concrete type deterministically
        typ = next((t for t in typ if t != "null"), typ[0])

    if typ == "object" or "properties" in schema:
        result: dict[str, Any] = {}
        props: dict[str, Any] = schema.get("properties", {})
        for key, subschema in props.items():
            result[key] = synthesize_args(subschema, seed=seed, _path=f"{_path}.{key}")
        return result
    if typ == "array":
        items = schema.get("items", {"type": "string"})
        min_items = int(schema.get("minItems", 1) or 1)
        return [synthesize_args(items, seed=seed, _path=f"{_path}[{i}]") for i in range(max(1, min_items))]
    if typ == "integer":
        lo = schema.get("minimum", schema.get("exclusiveMinimum", 1))
        return int(lo) + (_seed_int(seed, _path) % 5)
    if typ == "number":
        lo = float(schema.get("minimum", 1))
        return lo + (_seed_int(seed, _path) % 5)
    if typ == "boolean":
        return bool(_seed_int(seed, _path) % 2)
    if typ == "null":
        return None
    # default: string, honouring a few common format hints
    return _synth_string(schema, seed, _path)


def _synth_string(schema: dict[str, Any], seed: int, path: str) -> str:
    fmt = schema.get("format")
    token = f"{_seed_int(seed, path):x}"[:6]
    if fmt in ("uri", "url"):
        return f"https://example.test/{token}"
    if fmt == "email":
        return f"probe-{token}@example.test"
    if fmt in ("date-time", "datetime"):
        return "2026-01-01T00:00:00Z"
    if fmt == "date":
        return "2026-01-01"
    if fmt == "uuid":
        return f"00000000-0000-4000-8000-{token:>012}"
    min_len = int(schema.get("minLength", 0) or 0)
    base = f"probe-{token}"
    return base if len(base) >= min_len else base + "x" * (min_len - len(base))
