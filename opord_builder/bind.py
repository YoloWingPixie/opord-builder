"""Data sources and `${var/pointer}` bindings: declare variables in `extensions.org.opord-builder.data`, substitute
them into the strings of a document before it is validated. Selectors are JSON Pointers and equality only."""

from __future__ import annotations

import copy
import csv
import glob
import json
import math
import re
from contextvars import ContextVar
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml

from opord_builder import load
from opord_builder.openaix.validate import OpenAIXError
from opord_builder.openaix.validate import pointer as ptr_of
from opord_builder.pointer import MISSING, resolve, tokens

DATA = load.NS + "data"
_VARS = f"/extensions/{DATA}/vars"
_REF = r"\$\$\{|\$\{([^}]*)\}"  # `$${` is an escape; re caches the pattern
_GLOB = r"[*?\[]"
_STACK: ContextVar[tuple[Path, ...]] = ContextVar("bind_stack", default=())
_FAILED = object()


class _Err(Exception):
    def __init__(self, pointer: str, message: str):
        super().__init__(message)
        self.pointer = pointer


def resolve_document(
    doc: Any, path: Path
) -> tuple[Any, list[OpenAIXError], dict[str, str]]:
    """Substitute the bindings of `doc` (read from `path`) and strip its data group.
    Returns (document, errors, provenance); provenance maps a pointer to the text that explains a bound value."""
    ext = doc.get("extensions") if isinstance(doc, dict) else None
    data = ext.get(DATA) if isinstance(ext, dict) else None
    if data is not None:
        errors = [
            OpenAIXError(ptr_of(("extensions", DATA, *e.absolute_path)), e.message)
            for e in load.extension_validators()[DATA].iter_errors(data)
        ]
        if errors:
            return doc, errors, {}
    ctx = _Ctx(path, (data or {}).get("vars", {}))
    token = _STACK.set((*_STACK.get(), path))
    try:
        doc = _walk(doc, (), ctx)
    finally:
        _STACK.reset(token)
    if data is not None:
        del ext[DATA]
        if not ext:
            del doc["extensions"]
    return doc, ctx.errors, ctx.prov


def annotate(errors: list[OpenAIXError], prov: dict[str, str]) -> list[OpenAIXError]:
    """Add the provenance of a bound value to the schema errors at or below its pointer."""
    out = []
    for e in errors:
        parts = e.pointer.split("/")
        prefixes = ("/".join(parts[:n]) for n in range(len(parts), 0, -1))
        note = next((prov[q] for q in prefixes if q in prov), None)
        out.append(OpenAIXError(e.pointer, f"{e.message} ({note})") if note else e)
    return out


def _Ctx(path: Path, decl: dict[str, Any]) -> SimpleNamespace:
    """Per-document state: declared vars, their values, parsed files, the var chain, errors, provenance."""
    return SimpleNamespace(
        path=path, decl=decl, errors=[], prov={}, vals={}, files={}, chain=[]
    )


# --------------------------------------------------------------------------- substitution


def _walk(node: Any, at: tuple, ctx: SimpleNamespace) -> Any:
    if isinstance(node, str):
        return _bind(node, at, ctx) if "${" in node else node
    if isinstance(node, dict):
        for k, v in node.items():
            if not (at == ("extensions",) and k == DATA):
                node[k] = _walk(v, (*at, k), ctx)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            node[i] = _walk(v, (*at, i), ctx)
    return node


def _split(s: str) -> list[str | re.Match] | None:
    """The text and `${ref}` parts of `s` (`$${` becomes a literal `${`), or None when a `${` is unterminated."""
    parts: list[str | re.Match] = []
    pos = 0
    for m in re.finditer(_REF, s):
        if "${" in s[pos : m.start()]:
            return None
        parts += [s[pos : m.start()], "${" if m.group(1) is None else m]
        pos = m.end()
    return None if "${" in s[pos:] else [*parts, s[pos:]]


def _bind(s: str, at: tuple, ctx: SimpleNamespace) -> Any:
    where = ptr_of(at)
    parts = _split(s)
    if parts is None:
        ctx.errors.append(OpenAIXError(where, f"unterminated '${{' in {s!r}"))
        return s
    refs = [p for p in parts if isinstance(p, re.Match)]
    whole = len(refs) == 1 and all(p == "" for p in parts if isinstance(p, str))
    out, ok = [], True
    for p in parts:
        if isinstance(p, str):
            out.append(p)
            continue
        try:
            value, note = _lookup(p.group(1).strip(), ctx)
        except _Err as e:
            ctx.errors.append(OpenAIXError(where, f"{p.group(0)}: {e}"))
            ok = False
            continue
        if value is _FAILED:
            ok = False
            continue
        ctx.prov[where] = f"bound from {p.group(0)}; var {note}"
        if whole:
            return copy.deepcopy(value)
        if isinstance(value, bool) or not isinstance(value, str | int | float):
            msg = f"{p.group(0)} is {_kind(value)}; only a whole-value binding takes it"
            ctx.errors.append(OpenAIXError(where, msg))
            ok = False
        else:
            out.append(repr(value) if isinstance(value, float) else str(value))
    return "".join(out) if ok else s


def _kind(v: Any) -> str:
    names = {dict: "an object", list: "a list", bool: "a bool", type(None): "null"}
    return names.get(type(v), type(v).__name__)


def _lookup(ref: str, ctx: SimpleNamespace) -> tuple[Any, str]:
    """The value of `var` or `var/pointer`, and the text that says where the var comes from."""
    name, slash, rest = ref.partition("/")
    if name not in ctx.decl:
        raise _Err(
            "", f"no var {name!r} (vars: {', '.join(sorted(ctx.decl)) or 'none'})"
        )
    value = _var(name, ctx)
    if value is _FAILED:
        return _FAILED, ""
    note, toks = _describe(name, ctx), tokens(slash + rest) if slash else []
    for i, tok in enumerate(toks):  # find the first token that does not resolve
        try:
            found = resolve(value, ptr_of(toks[: i + 1]))
        except ValueError as e:
            raise _Err("", f"{e} in var {name} ({note})") from None
        if found is MISSING:
            raise _Err("", f"no key or index {tok!r} in var {name} ({note})")
    return resolve(value, slash + rest) if slash else value, note


def _describe(name: str, ctx: SimpleNamespace) -> str:
    spec = ctx.decl[name]
    if "path" in spec:
        src = spec["path"]
    elif "from" in spec:
        src = "<- " + "; ".join(_describe(n, ctx) for n in _names(spec["from"]))
    else:
        src = "value"
    sel = [
        f"{k} {json.dumps(spec[k])}"
        for k in ("select", "where", "key", "map")
        if k in spec
    ]
    return " ".join([name, src, *sel])


def _names(v: Any) -> list[str]:
    return [v] if isinstance(v, str) else list(v)


# --------------------------------------------------------------------------- variables


def _var(name: str, ctx: SimpleNamespace) -> Any:
    if name in ctx.vals:
        return ctx.vals[name]
    at = f"{_VARS}/{name}"
    if name in ctx.chain:
        ctx.errors.append(
            OpenAIXError(
                f"{at}/from",
                f"cycle {' -> '.join([*ctx.chain[ctx.chain.index(name) :], name])}",
            )
        )
        return _FAILED
    ctx.chain.append(name)
    try:
        ctx.vals[name] = _evaluate(ctx.decl[name], at, ctx)
    except _Err as e:
        ctx.errors.append(OpenAIXError(e.pointer or at, str(e)))
        ctx.vals[name] = _FAILED
    finally:
        ctx.chain.pop()
    return ctx.vals[name]


def _evaluate(spec: dict, at: str, ctx: SimpleNamespace) -> Any:
    if "path" in spec:
        return _read_paths(spec, at, ctx)
    if "from" in spec:
        names = _names(spec["from"])
        parts = []
        for n in names:
            if n not in ctx.decl:
                raise _Err(
                    f"{at}/from", f"no var {n!r} (vars: {', '.join(sorted(ctx.decl))})"
                )
            p = _var(n, ctx)
            if p is _FAILED:
                return _FAILED  # already reported
            parts.append(p)
        v = _combine(parts, names, f"{at}/from")
    else:
        v = spec["value"]
    if "select" in spec:
        v = _pick(v, spec["select"], f"{at}/select", "the var")
    return _refine(v, spec, at)


def _refine(v: Any, spec: dict, at: str) -> Any:
    if "where" in spec:
        v = _where(v, spec["where"], f"{at}/where")
    if "key" in spec:
        v = _key(v, spec["key"], f"{at}/key")
    if "map" in spec:
        v = _map(v, spec["map"], f"{at}/map")
    return v


def _get(item: Any, pointer: str) -> Any:
    try:
        return resolve(item, pointer)
    except ValueError:  # a pointer through a scalar finds nothing
        return MISSING


def _pick(v: Any, pointer: str, at: str, label: str) -> Any:
    if (found := _get(v, pointer)) is MISSING:
        raise _Err(at, f"{pointer!r} not found in {label}")
    return found


def _items(v: Any, at: str, what: str) -> list[tuple[Any, Any]]:
    if not isinstance(v, list | dict):
        raise _Err(at, f"{what} needs a list or an object, not {_kind(v)}")
    return list(enumerate(v) if isinstance(v, list) else v.items())


def _rebuild(v: Any, pairs: list[tuple[Any, Any]]) -> Any:
    return [x for _, x in pairs] if isinstance(v, list) else dict(pairs)


def _where(v: Any, cond: dict, at: str) -> Any:
    def keep(item: Any) -> bool:  # JSON equality: True is not 1
        return all(
            (got := _get(item, p)) is not MISSING
            and isinstance(got, bool) == isinstance(want, bool)
            and got == want
            for p, want in cond.items()
        )

    return _rebuild(v, [(k, i) for k, i in _items(v, at, "where") if keep(i)])


def _key(v: Any, pointer: str, at: str) -> dict:
    if not isinstance(v, list):
        raise _Err(at, f"key needs a list, not {_kind(v)}")
    out: dict[str, Any] = {}
    for n, item in enumerate(v):
        if (k := _get(item, pointer)) is MISSING:
            raise _Err(at, f"item {n} has no {pointer!r}")
        if str(k) in out:
            raise _Err(at, f"duplicate key {str(k)!r} (item {n})")
        out[str(k)] = item
    return out


def _map(v: Any, spec: str | dict, at: str) -> Any:
    def one(item: Any, label: Any, p: str) -> Any:
        if (got := _get(item, p)) is MISSING:
            raise _Err(at, f"{p!r} not found in item {label}")
        return got

    def project(item: Any, label: Any) -> Any:
        if isinstance(spec, str):
            return one(item, label, spec)
        return {f: one(item, label, p) for f, p in spec.items()}

    return _rebuild(v, [(k, project(i, k)) for k, i in _items(v, at, "map")])


def _combine(parts: list[Any], labels: list[str], at: str) -> Any:
    """Several values as one: lists concatenate, objects merge (a duplicate key is an error)."""
    if len(parts) == 1:
        return parts[0]
    if all(isinstance(p, list) for p in parts):
        return [x for p in parts for x in p]
    if not all(isinstance(p, dict) for p in parts):
        kinds = ", ".join(
            f"{lb} is {_kind(p)}" for lb, p in zip(labels, parts, strict=True)
        )
        raise _Err(at, f"cannot combine: {kinds} (all lists or all objects are needed)")
    out: dict[str, Any] = {}
    owner: dict[str, str] = {}
    for lb, p in zip(labels, parts, strict=True):
        for k, x in p.items():
            if k in out:
                raise _Err(at, f"key {k!r} is in both {owner[k]} and {lb}")
            out[k], owner[k] = x, lb
    return out


# --------------------------------------------------------------------------- files


def _read_paths(spec: dict, at: str, ctx: SimpleNamespace) -> Any:
    raw, base = spec["path"], ctx.path.parent
    if m := re.search(_GLOB, raw):
        pattern = raw if Path(raw).is_absolute() else f"{glob.escape(str(base))}/{raw}"
        found = (Path(f) for f in glob.glob(pattern, recursive=True))
        files = sorted({f.resolve() for f in found if f.is_file()})
        if not files:
            raise _Err(f"{at}/path", f"no file matches {raw!r} (in {base})")
        head = raw[: m.start()]  # the directory to watch for new matches
        load.note(base / head if head.endswith("/") else (base / head).parent)
    else:
        files = [(base / raw).resolve()]
    parts = []
    for f in files:
        v = _file(f, spec, f"{at}/path", ctx, raw)
        if "select" in spec:
            v = _pick(v, spec["select"], f"{at}/select", str(f))
        parts.append(v)
    return _refine(_combine(parts, [f.name for f in files], f"{at}/path"), spec, at)


def _file(f: Path, spec: dict, at: str, ctx: SimpleNamespace, raw: str) -> Any:
    fmt = spec.get("format") or {".json": "json", ".csv": "csv"}.get(
        f.suffix.lower(), "yaml"
    )
    memo = (f, fmt, spec.get("validate"))
    if memo not in ctx.files:
        try:
            if spec.get("validate") == "openaix":
                if f in _STACK.get():
                    raise _Err(at, f"cycle {' -> '.join(map(str, (*_STACK.get(), f)))}")
                v = load.load_document(f)
            elif fmt == "yaml":
                v = load.read(f)
            else:
                load.note(f)
                v = (
                    _csv(f)
                    if fmt == "csv"
                    else json.loads(f.read_text(encoding="utf-8"))
                )
            _check_json(v)
        except OSError as e:
            raise _Err(at, f"cannot read {raw} ({f}): {e.strerror or e}") from None
        except (ValueError, yaml.YAMLError, load.DocumentError) as e:
            raise _Err(at, f"{raw} ({f}): {e}") from None
        ctx.files[memo] = v
    return ctx.files[memo]


def _csv(f: Path) -> list[dict[str, str]]:
    with f.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        head = reader.fieldnames or []
        if not head or len(set(head)) != len(head):
            raise ValueError("a CSV file needs a header row without duplicate names")
        return [dict(r) for r in reader]


def _check_json(v: Any, at: str = "") -> None:
    if isinstance(v, dict | list):
        for k, x in v.items() if isinstance(v, dict) else enumerate(v):
            if isinstance(v, dict) and not isinstance(k, str):
                raise ValueError(f"{at or '/'}: key {k!r} is not text")  # noqa: TRY004
            _check_json(x, f"{at}/{k}")
    elif not (v is None or isinstance(v, str | int | bool)) and not (
        isinstance(v, float) and math.isfinite(v)
    ):
        raise ValueError(f"{at or '/'}: {v!r} is not a JSON value")
