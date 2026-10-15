"""The OPORD <-> OpenAIX field mapping, written once and used by both directions.

`encode(dump, ctx)` moves every field that has a typed OpenAIX home out of the model dump and into `ctx.doc` /
`ctx.resources`; whatever is left of the dump, and every typed field that does not read back exactly, goes into
`ctx.stash` (the `org.opord-builder.authoring` extension, keyed by dotted model path). `decode(doc, resources,
ctx)` rebuilds the model dict from the typed fields and then lays the stash over it, so
model -> OpenAIX -> model is exact.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from opord_builder.openaix import _measures as m
from opord_builder.openaix import _targeting as tg
from opord_builder.openaix import convert as c
from opord_builder.openaix._engine import (
    AUTHORING_NS,
    MISSING,
    PRINT_NS,
    Ctx,
    flatten,
    get_path,
    group_stash,
    pop_path,
    ptr_get,
    ptr_set,
    set_path,
    sorted_paths,
    ungroup_stash,
)
from opord_builder.openaix.registry import schemas

PRINT_PTR = f"/extensions/{PRINT_NS}"
Conv = Callable[[Any, Ctx], Any]


def schema_version() -> str:
    return schemas()["opord"]["properties"]["schema_version"]["const"]


# --------------------------------------------------------------------------- value conversions


def ident(v: Any, ctx: Ctx) -> Any:
    return v


def text(v: Any, ctx: Ctx) -> str:
    if not isinstance(v, str) or not v.strip():
        raise c.ConvertError("text", f"empty or non-text value {v!r}")
    return v


def to_dtg_rfc(v: Any, ctx: Ctx) -> str:
    return c.dtg_to_rfc3339(v)


def from_rfc_dtg(v: Any, ctx: Ctx) -> str:
    return c.rfc3339_to_dtg(v, warnings=ctx.warnings)


def to_zone(v: Any, ctx: Ctx) -> str:
    if v.upper() == "ZULU":
        return "Z"
    if len(v) == 1 and v.isalpha() and v.upper() != "J":
        return v.upper()
    raise c.ConvertError("time_zone", f"not a time-zone letter or ZULU: {v!r}")


def from_zone(v: Any, ctx: Ctx) -> str:
    return "ZULU" if v == "Z" else v


def to_classification(v: Any, ctx: Ctx) -> str:
    return c.map_enum("classification", v)


def from_classification(v: Any, ctx: Ctx) -> str:
    return c.unmap_enum("classification", v)


def to_revision(v: Any, ctx: Ctx) -> str:
    return text(v, ctx)


def from_revision(v: Any, ctx: Ctx) -> Any:
    return None if v == "1" else v


def positive_int(v: Any, ctx: Ctx) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise c.ConvertError("int", f"not an integer: {v!r}")
    return v


# --------------------------------------------------------------------------- codecs


@dataclass
class Leaf:
    """One authoring field <-> one OpenAIX pointer, with a conversion and its inverse."""

    src: str
    dst: str
    fwd: Conv = text
    rev: Conv = ident
    when: str | None = None  # src path that must be present for this leaf to be typed

    def enc(self, d: dict, ctx: Ctx) -> None:
        if self.when and get_path(d, self.when) is MISSING:
            return
        v = get_path(d, self.src)
        if v is MISSING:
            return
        try:
            typed = self.fwd(v, ctx)
        except c.ConvertError as exc:
            ctx.warn(f"{self.src}: kept in authoring overlay ({exc})")
            return
        pop_path(d, self.src)
        ptr_set(ctx.doc, self.dst, typed)
        try:
            back = self.rev(typed, ctx)
        except c.ConvertError:
            back = MISSING
        if back != v:
            ctx.stash[self.src] = v

    def dec(self, doc: dict, d: dict, ctx: Ctx) -> None:
        typed = ptr_get(doc, self.dst)
        if typed is MISSING:
            return
        try:
            v = self.rev(typed, ctx)
        except c.ConvertError as exc:
            ctx.warn(f"{self.dst}: ignored ({exc})")
            return
        if v is not None:
            set_path(d, self.src, v)


@dataclass
class StrList:
    """list[str] <-> list of objects with an id and one text field."""

    src: str
    dst: str
    key: str
    prefix: str
    extra: Callable[[int], dict] | None = None

    def enc(self, d: dict, ctx: Ctx) -> None:
        v = get_path(d, self.src)
        if v is MISSING or not isinstance(v, list) or not v:
            return
        try:
            items = []
            for i, s in enumerate(v, 1):
                item = {"id": f"{self.prefix}-{i}", self.key: text(s, ctx)}
                if self.extra:
                    item.update(self.extra(i))
                items.append(item)
        except c.ConvertError:
            return
        pop_path(d, self.src)
        ptr_set(ctx.doc, self.dst, items)

    def dec(self, doc: dict, d: dict, ctx: Ctx) -> None:
        items = ptr_get(doc, self.dst)
        if items is MISSING or not isinstance(items, list):
            return
        set_path(d, self.src, [it[self.key] for it in items if self.key in it])


@dataclass
class OneItem:
    """One authoring string <-> a one-element list of objects (ROE, other coordinating instructions)."""

    src: str
    dst: str
    key: str
    item_id: str

    def enc(self, d: dict, ctx: Ctx) -> None:
        v = get_path(d, self.src)
        if v is MISSING:
            return
        try:
            body = text(v, ctx)
        except c.ConvertError:
            return
        pop_path(d, self.src)
        ptr_set(ctx.doc, self.dst, [{"id": self.item_id, self.key: body}])

    def dec(self, doc: dict, d: dict, ctx: Ctx) -> None:
        items = ptr_get(doc, self.dst)
        if items is MISSING or not isinstance(items, list):
            return
        bodies = [it[self.key] for it in items if self.key in it]
        if bodies:
            set_path(d, self.src, "\n\n".join(bodies))


class References:
    """header.references <-> references[] (DocumentRef: id, title)."""

    def enc(self, d: dict, ctx: Ctx) -> None:
        refs = get_path(d, "header.references")
        if refs is MISSING or not refs:
            return
        taken: set[str] = set()
        out = []
        try:
            for r in refs:
                out.append(
                    {
                        "id": c.slug(r["citation"][:48], taken, "references"),
                        "title": text(r["citation"], ctx),
                    }
                )
        except c.ConvertError:
            return
        ctx.typed_lists.add("header.references")
        for r in refs:
            r.pop("citation")
        ctx.doc["references"] = out

    def dec(self, doc: dict, d: dict, ctx: Ctx) -> None:
        refs = ptr_get(doc, "/references")
        if refs is MISSING:
            return
        set_path(
            d,
            "header.references",
            [{"citation": r.get("title") or r["id"]} for r in refs],
        )


REL_CASE = {k.upper(): k for k in c.ENUMS["command_relationship"]}


class TaskOrg:
    """header.task_organization (a Unit tree) <-> task_organization{id: Unit} with `parent`, and the
    relationship of each unit <-> annexes.A.relationships (CommandRelationship)."""

    def enc(self, d: dict, ctx: Ctx) -> None:
        root = get_path(d, "header.task_organization")
        if root is MISSING:
            return
        work = copy.deepcopy(root)
        taken: set[str] = set()
        units: dict[str, Any] = {}
        rels: list[dict] = []
        stash: dict[str, Any] = {}
        lists: set[str] = set()
        names: dict[str, str] = {}

        def walk(node: dict, path: str, parent: str | None) -> None:
            ident_ = c.slug(node["name"], taken, "task_organization")
            u: dict[str, Any] = {"name": text(node.pop("name"), ctx)}
            for k, dst in (
                ("callsign", "callsign"),
                ("commander", "commander"),
                ("role", "unit_type"),
            ):
                if k in node:
                    u[dst] = text(node.pop(k), ctx)
            if parent:
                u["parent"] = parent
            units[ident_] = u
            names.setdefault(u["name"], ident_)
            rel = node.get("relationship")
            if rel is not None and parent:
                key = REL_CASE.get(rel.upper())
                if key:
                    rels.append(
                        {
                            "unit": ident_,
                            "relationship": c.map_enum("command_relationship", key),
                            "to": parent,
                        }
                    )
                    node.pop("relationship")
                    if key != rel:
                        stash[f"{path}.relationship"] = rel
            lists.add(f"{path}.subordinate_units")
            for i, sub in enumerate(node.get("subordinate_units", [])):
                walk(sub, f"{path}.subordinate_units.{i}", ident_)

        try:
            walk(work, "header.task_organization", None)
        except c.ConvertError as exc:
            ctx.warn(f"header.task_organization: kept in authoring overlay ({exc})")
            return
        set_path(d, "header.task_organization", work)
        ctx.typed_lists |= lists
        ctx.stash.update(stash)
        ctx.doc["task_organization"] = units
        ctx.scratch["unit_ids"] = names
        ctx.scratch["relationships"] = rels

    def dec(self, doc: dict, d: dict, ctx: Ctx) -> None:
        units = doc.get("task_organization")
        if not units:
            return
        rels = {
            r["unit"]: r
            for r in (ptr_get(doc, "/annexes/A/relationships", []) or [])
            if "unit" in r
        }
        children: dict[str | None, list[str]] = {}
        for uid, u in units.items():
            children.setdefault(u.get("parent"), []).append(uid)
        roots = children.get(None, [])
        if not roots:
            return
        if len(roots) > 1:
            ctx.warn(
                f"task_organization has {len(roots)} roots; only '{roots[0]}' is imported to header.task_organization"
            )

        def build(uid: str) -> dict:
            u = units[uid]
            node: dict[str, Any] = {"name": u["name"]}
            if "callsign" in u:
                node["callsign"] = u["callsign"]
            if "commander" in u:
                node["commander"] = u["commander"]
            if "unit_type" in u:
                node["role"] = u["unit_type"]
            r = rels.get(uid)
            if r:
                try:
                    node["relationship"] = c.unmap_enum(
                        "command_relationship", r["relationship"]
                    )
                except c.ConvertError:
                    pass
            subs = [build(k) for k in children.get(uid, [])]
            if subs:
                node["subordinate_units"] = subs
            return node

        set_path(d, "header.task_organization", build(roots[0]))
        ctx.scratch["unit_names"] = {uid: u["name"] for uid, u in units.items()}


class TasksToUnits:
    """execution.tasks_to_subordinate_units <-> execution.tasks_to_subordinate_units{unit, tasks[{id, task}]}.
    Typed only when every unit name is a task-organization unit."""

    SRC = "execution.tasks_to_subordinate_units"
    DST = "/execution/tasks_to_subordinate_units"

    def enc(self, d: dict, ctx: Ctx) -> None:
        items = get_path(d, self.SRC)
        ids = ctx.scratch.get("unit_ids")
        if items is MISSING or not items or not ids:
            return
        if any(i.get("unit") not in ids or not i.get("tasks") for i in items):
            ctx.warn(
                f"{self.SRC}: a unit is not in the task organization; kept in authoring overlay"
            )
            return
        out = []
        for n, i in enumerate(items, 1):
            out.append(
                {
                    "unit": ids[i["unit"]],
                    "tasks": [
                        {"id": f"t{n}-{k}", "task": text(t, ctx)}
                        for k, t in enumerate(i["tasks"], 1)
                    ],
                }
            )
        ctx.typed_lists.add(self.SRC)
        for i in items:
            i.pop("unit")
            i.pop("tasks")
        ptr_set(ctx.doc, self.DST, out)

    def dec(self, doc: dict, d: dict, ctx: Ctx) -> None:
        items = ptr_get(doc, self.DST)
        names = ctx.scratch.get("unit_names", {})
        if items is MISSING:
            return
        out = []
        for i in items:
            out.append(
                {
                    "unit": names.get(i["unit"], i["unit"]),
                    "tasks": [t["task"] for t in i["tasks"]],
                }
            )
        set_path(d, self.SRC, out)


class HigherHQ:
    """friendly_forces.higher_headquarters one-up / two-up <-> higher_one_level / higher_two_levels."""

    def enc(self, d: dict, ctx: Ctx) -> None:
        base = "situation.friendly_forces.higher_headquarters"
        for pre, dst in (
            ("one_up", "higher_one_level"),
            ("two_up", "higher_two_levels"),
        ):
            name = get_path(d, f"{base}.{pre}_designation")
            if name is MISSING or not isinstance(name, str) or not name.strip():
                continue
            out = {"name": name}
            pop_path(d, f"{base}.{pre}_designation")
            for src, key in (("mission", "mission"), ("intent", "commanders_intent")):
                v = get_path(d, f"{base}.{pre}_{src}")
                if isinstance(v, str) and v.strip():
                    out[key] = v
                    pop_path(d, f"{base}.{pre}_{src}")
            ptr_set(ctx.doc, f"/situation/friendly_forces/{dst}", out)

    def dec(self, doc: dict, d: dict, ctx: Ctx) -> None:
        base = "situation.friendly_forces.higher_headquarters"
        for pre, src in (
            ("one_up", "higher_one_level"),
            ("two_up", "higher_two_levels"),
        ):
            node = ptr_get(doc, f"/situation/friendly_forces/{src}")
            if node is MISSING:
                continue
            set_path(d, f"{base}.{pre}_designation", node["name"])
            if "mission" in node:
                set_path(d, f"{base}.{pre}_mission", node["mission"])
            if "commanders_intent" in node:
                set_path(d, f"{base}.{pre}_intent", node["commanders_intent"])


class EnemyCOAs:
    """enemy_forces.most_likely_coa / most_dangerous_coa <-> courses_of_action."""

    KINDS = (
        ("most_likely_coa", "most_likely", "coa-most-likely"),
        ("most_dangerous_coa", "most_dangerous", "coa-most-dangerous"),
    )

    def enc(self, d: dict, ctx: Ctx) -> None:
        out = []
        for src, kind, ident_ in self.KINDS:
            v = get_path(d, f"situation.enemy_forces.{src}")
            if v is not MISSING and isinstance(v, str) and v.strip():
                out.append({"id": ident_, "kind": kind, "summary": v})
                pop_path(d, f"situation.enemy_forces.{src}")
        if out:
            ptr_set(ctx.doc, "/situation/enemy_forces/courses_of_action", out)

    def dec(self, doc: dict, d: dict, ctx: Ctx) -> None:
        for coa in ptr_get(doc, "/situation/enemy_forces/courses_of_action", []) or []:
            for src, kind, _ in self.KINDS:
                if coa.get("kind") == kind and "summary" in coa:
                    set_path(d, f"situation.enemy_forces.{src}", coa["summary"])


class Authentication:
    """authentication + acknowledgement."""

    def enc(self, d: dict, ctx: Ctx) -> None:
        auth = get_path(d, "authentication")
        if auth is MISSING:
            return
        if "acknowledge" in auth:
            ack = auth.pop("acknowledge")
            ptr_set(ctx.doc, "/acknowledgement/acknowledge", bool(ack))
        name = auth.get("commander_last_name")
        if name:
            out = {"commander_name": name}
            auth.pop("commander_last_name")
            for src, dst in (
                ("commander_rank", "commander_rank"),
                ("authenticating_officer_name", "authenticator_name"),
                ("authenticating_officer_position", "authenticator_position"),
            ):
                if auth.get(src):
                    out[dst] = auth.pop(src)
            ctx.doc["authentication"] = out

    def dec(self, doc: dict, d: dict, ctx: Ctx) -> None:
        ack = ptr_get(doc, "/acknowledgement")
        if ack is not MISSING:
            set_path(d, "authentication.acknowledge", bool(ack.get("acknowledge")))
        a = ptr_get(doc, "/authentication")
        if a is MISSING:
            return
        for src, dst in (
            ("commander_name", "commander_last_name"),
            ("commander_rank", "commander_rank"),
            ("authenticator_name", "authenticating_officer_name"),
            ("authenticator_position", "authenticating_officer_position"),
        ):
            if src in a:
                set_path(d, f"authentication.{dst}", a[src])


# --------------------------------------------------------------------------- annexes, measures, channels

CANONICAL_LETTERS = set("ABCDEFGHJKLMNPQRSUVWZ")


class Annexes:
    """annexes: list[Annex] <-> annexes{letter}. Also owns the print extension's annex_status, the measures of
    Annexes C and D (resources.control_measures) and the frequency tables (resources.channels)."""

    def enc(self, d: dict, ctx: Ctx) -> None:
        annexes = get_path(d, "annexes")
        rels = ctx.scratch.get("relationships")
        ordered = (
            annexes is not MISSING
            and annexes
            and [a["letter"] for a in annexes] == sorted(a["letter"] for a in annexes)
            and len({a["letter"] for a in annexes}) == len(annexes)
        )
        if not ordered:
            if annexes:
                ctx.warn(
                    "annexes are not in A-Z order; kept whole in the authoring overlay"
                )
            if rels:
                ctx.doc.setdefault("annexes", {})["A"] = {"relationships": rels}
            ptr_set(ctx.doc, f"{PRINT_PTR}/annex_status", {})
            return
        ctx.typed_lists.add("annexes")
        status: dict[str, str] = {}
        out: dict[str, Any] = ctx.doc.setdefault("annexes", {})
        ids = ctx.scratch.setdefault("measure_ids", set())
        cm = ctx.resources.setdefault("control_measures", {})
        for i, a in enumerate(annexes):
            path = f"annexes.{i}"
            letter = a.pop("letter")
            entry: dict[str, Any] = {}
            st = a.pop("status", None)
            status[letter] = st or "published"
            title = a.pop("title", None)
            if title is not None and title != self._canonical(letter):
                ctx.stash[f"{path}.title"] = title
            body = a.get("body")
            if body and letter in CANONICAL_LETTERS:
                entry["summary"] = a.pop("body")
            tb = a.get("typed_body")
            if tb and letter == "C":
                self._enc_c(tb, f"{path}.typed_body", entry, ids, cm, ctx)
            if tb and letter == "D":
                self._enc_d(tb, f"{path}.typed_body", entry, ids, cm, ctx)
            self._enc_tables(a, path, ctx)
            if letter == "A" and ctx.scratch.get("relationships"):
                entry["relationships"] = ctx.scratch["relationships"]
            if entry and letter in CANONICAL_LETTERS:
                out[letter] = entry
        if "A" not in out and ctx.scratch.get("relationships"):
            out["A"] = {"relationships": ctx.scratch["relationships"]}
        if not out:
            del ctx.doc["annexes"]
        ptr_set(ctx.doc, f"{PRINT_PTR}/annex_status", status)
        if not cm:
            ctx.resources.pop("control_measures")

    @staticmethod
    def _canonical(letter: str) -> str:
        from opord_builder.schema.core import CANONICAL_ANNEXES

        return CANONICAL_ANNEXES.get(letter, "")

    # ---- measures
    def _items(
        self,
        tb: dict,
        field: str,
        kind: str,
        path: str,
        ids: set[str],
        cm: dict,
        ctx: Ctx,
    ) -> list[str]:
        items = get_path(tb, field)
        if items is MISSING or not items:
            return []
        ctx.typed_lists.add(f"{path}.{field}")
        out = []
        for i, item in enumerate(items):
            ident_ = c.slug(
                item.get("name") or item.get("callsign") or f"{kind}-{i}", ids, kind
            )
            doc, consumed = m.encode_item(
                kind, item, ident_, ctx, f"{path}.{field}.{i}"
            )
            _, back = m.decode_item(doc)
            for f, orig in consumed.items():
                if back.get(f, MISSING) != orig:
                    ctx.stash[f"{path}.{field}.{i}.{f}"] = orig
            cm[ident_] = doc
            out.append(ident_)
        return out

    def _enc_c(
        self, tb: dict, path: str, entry: dict, ids: set, cm: dict, ctx: Ctx
    ) -> None:
        overlay = self._items(
            tb, "control_measures", "control_measure", path, ids, cm, ctx
        )
        if overlay:
            entry["operation_overlay"] = overlay
        ac = tb.get("airspace_control")
        if ac:
            airspace: list[str] = []
            for field, kind in (
                ("geo_refs", "geo_ref"),
                ("airspace_zones", "zone"),
                ("cap_tracks", "cap"),
                ("aar_tracks", "aar"),
                ("ingress_corridors", "mrr"),
            ):
                airspace += self._items(
                    ac, field, kind, f"{path}.airspace_control", ids, cm, ctx
                )
            if airspace:
                entry["airspace"] = {"measures": airspace}

    def _enc_d(
        self, tb: dict, path: str, entry: dict, ids: set, cm: dict, ctx: Ctx
    ) -> None:
        fscm = self._items(
            tb, "fire_support_coordination_measures", "fscm", path, ids, cm, ctx
        )
        if fscm:
            entry["fire_support_coordination_measures"] = fscm
        self._enc_targeting(tb, path, entry, ctx)

    @staticmethod
    def _stash_diff(consumed: dict, back: dict, path: str, ctx: Ctx) -> None:
        for f, orig in consumed.items():
            if back.get(f, MISSING) != orig:
                ctx.stash[f"{path}.{f}"] = orig

    def _enc_targeting(self, tb: dict, path: str, entry: dict, ctx: Ctx) -> None:
        # JPITL -> jiptl document
        jp = tg.present(tb, "jpitl")
        built = [tg.jpitl_target(i) for i in jp]
        if jp and all(built):
            ctx.typed_lists.add(f"{path}.jpitl")
            targets = []
            for n, (item, (target, consumed)) in enumerate(zip(jp, built, strict=True)):
                self._stash_diff(
                    consumed, tg.jpitl_item(target), f"{path}.jpitl.{n}", ctx
                )
                for k in consumed:
                    item.pop(k)
                targets.append(target)
            ctx.scratch["jiptl"] = targets
        # TST -> targeting appendix
        targeting: dict[str, Any] = {}
        tsts = tg.present(tb, "time_sensitive_targets")
        taken: set[str] = set()
        ttaken = ctx.scratch.setdefault("target_ids", set())
        built_t = [tg.tst_entry(i, taken, ttaken) for i in tsts]
        if tsts and all(built_t):
            ctx.typed_lists.add(f"{path}.time_sensitive_targets")
            res_targets = ctx.resources.setdefault("targets", {})
            out = []
            for n, (item, (e, target, tid, consumed)) in enumerate(
                zip(tsts, built_t, strict=True)
            ):
                res_targets[tid] = target
                back = tg.tst_item(e, {tid: target})
                self._stash_diff(
                    consumed, back, f"{path}.time_sensitive_targets.{n}", ctx
                )
                for k in consumed:
                    item.pop(k)
                out.append(e)
            targeting["time_sensitive_targets"] = out
        # HPT + attack guidance -> high_payoff_targets
        hvts, agm = (
            tg.present(tb, "high_payoff_target_list"),
            tg.present(tb, "attack_guidance_matrix"),
        )
        built_h = tg.hpt_entries(hvts, agm, set(), ttaken)
        if built_h:
            hp, hp_targets = built_h
            ctx.resources.setdefault("targets", {}).update(hp_targets)
            ctx.typed_lists |= {
                f"{path}.high_payoff_target_list",
                f"{path}.attack_guidance_matrix",
            }
            bh, ba = tg.hpt_items(hp, hp_targets)
            for n, (h, a) in enumerate(zip(hvts, agm, strict=True)):
                self._stash_diff(
                    {k: h[k] for k in ("priority_rank", "target_description")},
                    bh[n],
                    f"{path}.high_payoff_target_list.{n}",
                    ctx,
                )
                self._stash_diff(
                    {"effect": a["effect"], "when": a["when"]},
                    ba[n],
                    f"{path}.attack_guidance_matrix.{n}",
                    ctx,
                )
                h.pop("priority_rank")
                h.pop("target_description")
                a.pop("effect")
                a.pop("when")
            targeting["high_payoff_targets"] = hp
        if targeting:
            entry["targeting"] = targeting

    # ---- frequency tables
    def _enc_tables(self, a: dict, path: str, ctx: Ctx) -> None:
        channels = ctx.resources.setdefault("channels", {})
        taken = ctx.scratch.setdefault("channel_ids", set())
        for ai, app in enumerate(a.get("appendices") or []):
            for ti, table in enumerate(app.get("frequency_tables") or []):
                rows = table.get("channels") or []
                base = f"{path}.appendices.{ai}.frequency_tables.{ti}.channels"
                for ri, row in enumerate(rows):
                    try:
                        freq = c.parse_frequency(
                            row["frequency"], f"{base}.{ri}.frequency"
                        )
                        if "modulation" not in freq:
                            raise c.ConvertError(
                                f"{base}.{ri}.frequency", "no modulation"
                            )
                        cid = c.slug(row["name"], taken, "channel")
                    except (c.ConvertError, KeyError):
                        continue
                    ch = {"name": row["name"], "frequency": freq}
                    if row.get("purpose"):
                        ch["usage"] = row["purpose"]
                    channels[cid] = ch
                    ctx.stash[f"{base}.{ri}.@channel"] = cid
                    back = self._channel_row(ch)
                    for f in ("name", "frequency", "purpose"):
                        if f in row and back.get(f) != row[f]:
                            ctx.stash[f"{base}.{ri}.{f}"] = row[f]
                        row.pop(f, None)
        if not channels:
            ctx.resources.pop("channels")

    @staticmethod
    def _channel_row(ch: dict) -> dict:
        row = {"name": ch["name"], "frequency": c.format_frequency(ch["frequency"])}
        if ch.get("usage"):
            row["purpose"] = ch["usage"]
        return row

    # ---- decoding
    def dec(self, doc: dict, d: dict, ctx: Ctx, resources: dict | None = None) -> None:
        status = ptr_get(doc, f"{PRINT_PTR}/annex_status")
        entries = doc.get("annexes") or {}
        letters = sorted(entries) if status is MISSING else sorted(status)
        letters = [x for x in letters if x in CANONICAL_ANNEXES_ALL]
        if not letters:
            return
        cm = (resources or {}).get("control_measures", {}) or {}
        from opord_builder.schema.core import RESERVED_LETTERS

        out = []
        for letter in letters:
            e = entries.get(letter, {})
            if letter in RESERVED_LETTERS and e:
                ctx.warn(
                    f"annex {letter} has content, but the authoring model reserves that letter; not imported"
                )
                continue
            i = len(out)
            a: dict[str, Any] = {"letter": letter}
            if e.get("summary"):
                a["body"] = e["summary"]
            tb: dict[str, Any] = {}
            if letter == "C":
                tb = self._dec_c(e, cm, f"annexes.{i}.typed_body", ctx)
            if letter == "D":
                tb = self._dec_d(e, cm, f"annexes.{i}.typed_body", ctx, resources)
            if tb:
                tb["letter"] = letter
                a["typed_body"] = tb
            out.append(a)
        d["annexes"] = out

    def _dec_items(
        self, ids: list[str], cm: dict, want: str, list_path: str, ctx: Ctx
    ) -> list[dict]:
        """Items of kind `want` among measure `ids`. An item the authoring model cannot hold (a required field
        the measure does not give, an unknown type) is skipped with a warning."""
        model = m.KIND_MODELS[want]
        stash = ctx.scratch.get("stash", {})
        out: list[dict] = []
        for ident_ in ids:
            doc = cm.get(ident_)
            if not doc:
                ctx.warn(
                    f"measure '{ident_}' is not in the resources document; skipped"
                )
                continue
            kind, item = m.decode_item(doc)
            if kind != want:
                continue
            probe = copy.deepcopy(item)
            prefix = f"{list_path}.{len(out)}."
            for key in sorted_paths(k for k in stash if k.startswith(prefix)):
                set_path(probe, key[len(prefix) :], stash[key])
            try:
                model.model_validate(probe)
            except ValidationError as exc:
                ctx.warn(
                    f"measure '{ident_}' is not imported: {exc.errors()[0]['loc']} {exc.errors()[0]['msg']}"
                )
                continue
            out.append(item)
        ctx.scratch.setdefault("measure_lists", {})[list_path] = len(out)
        return out

    def _dec_c(self, e: dict, cm: dict, path: str, ctx: Ctx) -> dict:
        tb: dict[str, Any] = {}
        cms = self._dec_items(
            e.get("operation_overlay", []),
            cm,
            "control_measure",
            f"{path}.control_measures",
            ctx,
        )
        if cms:
            tb["control_measures"] = cms
        ids = ptr_get(e, "/airspace/measures", []) or []
        ac: dict[str, Any] = {}
        for kind, field in (
            ("geo_ref", "geo_refs"),
            ("zone", "airspace_zones"),
            ("cap", "cap_tracks"),
            ("aar", "aar_tracks"),
            ("mrr", "ingress_corridors"),
        ):
            items = self._dec_items(
                ids, cm, kind, f"{path}.airspace_control.{field}", ctx
            )
            if items:
                ac[field] = items
        if ac:
            tb["airspace_control"] = ac
        return tb

    def _dec_d(
        self, e: dict, cm: dict, path: str, ctx: Ctx, res: dict | None = None
    ) -> dict:
        items = self._dec_items(
            e.get("fire_support_coordination_measures", []),
            cm,
            "fscm",
            f"{path}.fire_support_coordination_measures",
            ctx,
        )
        tb: dict[str, Any] = (
            {"fire_support_coordination_measures": items} if items else {}
        )
        from opord_builder.schema import shared
        from opord_builder.schema.annexes import AttackGuidanceEntry

        lp = f"{path}.jpitl"
        jp = [
            self._keep(shared.JPITLEntry, tg.jpitl_item(t), lp, i, ctx)
            for i, t in enumerate(ctx.scratch.get("jiptl_in", []))
        ]
        jp = [x for x in jp if x is not None]
        ctx.scratch.setdefault("measure_lists", {})[lp] = len(jp)
        if jp:
            tb["jpitl"] = jp
        targeting = e.get("targeting") or {}
        targets = (res or {}).get("targets", {})
        lp = f"{path}.time_sensitive_targets"
        ts = [
            self._keep(shared.TSTEntry, tg.tst_item(t, targets), lp, i, ctx)
            for i, t in enumerate(targeting.get("time_sensitive_targets", []))
        ]
        ts = [x for x in ts if x is not None]
        ctx.scratch.setdefault("measure_lists", {})[lp] = len(ts)
        if ts:
            tb["time_sensitive_targets"] = ts
        hp = targeting.get("high_payoff_targets", [])
        lh, la = f"{path}.high_payoff_target_list", f"{path}.attack_guidance_matrix"
        hv, ag = tg.hpt_items(hp, targets) if hp else ([], [])
        ok = [
            self._keep(shared.HVT, h, lh, i, ctx, quiet=True) is not None
            and self._keep(AttackGuidanceEntry, a, la, i, ctx, quiet=True) is not None
            for i, (h, a) in enumerate(zip(hv, ag, strict=True))
        ]
        if hp and all(ok):
            tb["high_payoff_target_list"], tb["attack_guidance_matrix"] = hv, ag
        elif hp:
            for lpath in (lh, la):
                ctx.scratch.setdefault("measure_lists", {})[lpath] = 0
            ctx.warn(
                "high_payoff_targets are not imported: the authoring model needs more fields than the entries give"
            )
        return tb

    def _keep(
        self,
        model: Any,
        item: dict,
        list_path: str,
        index: int,
        ctx: Ctx,
        quiet: bool = False,
    ) -> dict | None:
        """`item` if the model accepts it once its authoring-overlay entries are laid over it, else None."""
        stash = ctx.scratch.get("stash", {})
        probe = copy.deepcopy(item)
        prefix = f"{list_path}.{index}."
        for key in sorted_paths(k for k in stash if k.startswith(prefix)):
            set_path(probe, key[len(prefix) :], stash[key])
        try:
            model.model_validate(probe)
        except ValidationError as exc:
            if not quiet:
                ctx.warn(
                    f"{list_path}.{index} is not imported: {exc.errors()[0]['loc']} {exc.errors()[0]['msg']}"
                )
            return None
        return item


CANONICAL_ANNEXES_ALL = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")


# --------------------------------------------------------------------------- the table

PRINT_LEAVES = (
    "logo",
    "page_icon",
    "watermark",
    "message_reference_number",
    "classification_caveat",
    "place_of_issue",
)


def _leaves() -> list[Any]:
    h = "header."
    cc = "execution.coordinating_instructions"
    out: list[Any] = [
        Leaf(
            h + "classification",
            "/meta/classification",
            to_classification,
            from_classification,
        ),
        Leaf(h + "issuing_headquarters", "/issuing_headquarters"),
        Leaf(h + "dtg", "/date_time", to_dtg_rfc, from_rfc_dtg),
        Leaf(h + "operation_order_number", "/order_number"),
        Leaf(h + "operation_name", "/operation_name"),
        Leaf(h + "author", "/meta/author"),
        Leaf(h + "revision", "/meta/revision", to_revision, from_revision),
        Leaf(h + "time_zone", "/time_zone", to_zone, from_zone),
        Leaf(h + "copy_number", f"{PRINT_PTR}/copy_number", positive_int),
        Leaf(h + "number_of_copies", f"{PRINT_PTR}/number_of_copies", positive_int),
    ]
    out += [Leaf(h + k, f"{PRINT_PTR}/{k}") for k in PRINT_LEAVES]
    out += [
        References(),
        TaskOrg(),
        Leaf("mission", "/mission/statement"),
        Leaf(
            "situation.area_of_operations.description",
            "/situation/area_of_operations/summary",
        ),
        Leaf(
            "situation.enemy_forces.composition_disposition_strength",
            "/situation/enemy_forces/summary",
        ),
        HigherHQ(),
        EnemyCOAs(),
        StrList("situation.assumptions", "/situation/assumptions", "assumption", "as"),
        Leaf(
            "execution.commanders_intent.purpose",
            "/execution/commanders_intent/purpose",
        ),
        StrList(
            "execution.commanders_intent.key_tasks",
            "/execution/commanders_intent/key_tasks",
            "task",
            "kt",
        ),
        Leaf(
            "execution.commanders_intent.end_state",
            "/execution/commanders_intent/end_state/summary",
        ),
        Leaf(
            "execution.concept_of_operations.overview",
            "/execution/concept_of_operations/summary",
        ),
    ]
    for src, dst in (
        ("scheme_of_movement_and_maneuver", "maneuver"),
        ("scheme_of_fires", "fires"),
        ("scheme_of_intelligence", "intelligence"),
        ("scheme_of_protection", "protection"),
        ("scheme_of_engineer_operations", "engineering"),
        ("scheme_of_information_collection", "information_collection"),
        ("scheme_of_airspace_control", "airspace_control"),
    ):
        out.append(Leaf(f"execution.{src}", f"/execution/schemes/{dst}/summary"))
    out += [
        Leaf(
            f"{cc}.effective_time",
            "/execution/coordinating_instructions/effective_time",
            to_dtg_rfc,
            from_rfc_dtg,
        ),
        StrList(
            f"{cc}.ccir.pir",
            "/execution/coordinating_instructions/ccir/priority_intelligence_requirements",
            "question",
            "pir",
        ),
        StrList(
            f"{cc}.ccir.ffir",
            "/execution/coordinating_instructions/ccir/friendly_force_information_requirements",
            "question",
            "ffir",
        ),
        StrList(
            f"{cc}.eefi", "/execution/coordinating_instructions/eefi", "item", "eefi"
        ),
        OneItem(
            f"{cc}.roe",
            "/execution/coordinating_instructions/rules_of_engagement",
            "rule",
            "roe-1",
        ),
        OneItem(
            f"{cc}.other",
            "/execution/coordinating_instructions/other",
            "instruction",
            "ci-1",
        ),
        TasksToUnits(),
        Leaf(
            "command_and_signal.signal.methods_of_communication_by_echelon",
            "/command_and_signal/signal/summary",
        ),
        Annexes(),
        Authentication(),
    ]
    return out


# --------------------------------------------------------------------------- entry points


def new_doc(d: dict) -> dict[str, Any]:
    return {
        "$schema": schemas()["opord"]["$id"],
        "kind": "opord",
        "schema_version": schema_version(),
    }


def encode(dump: dict, ctx: Ctx) -> None:
    """Fill ctx.doc / ctx.resources / ctx.stash from a model dump. Consumes `dump`."""
    ctx.doc = new_doc(dump)
    for codec in _leaves():
        codec.enc(dump, ctx)
    for k, v in flatten(dump, ctx.typed_lists).items():
        ctx.stash.setdefault(k, v)
    doc = ctx.doc
    # derived document identity
    number = ptr_get(doc, "/order_number")
    oid = c.slug(f"opord {number}") if number is not MISSING else "opord"
    meta = doc.setdefault("meta", {})
    meta.setdefault("id", oid)
    meta.setdefault("revision", "1")
    if ptr_get(doc, "/operation_name") is not MISSING:
        meta.setdefault("operation", doc["operation_name"])
    if "date_time" in doc:
        meta.setdefault("issued_at", doc["date_time"])
    if "issuing_headquarters" in doc:
        meta.setdefault("issuing_unit", doc["issuing_headquarters"])
    doc["meta"] = dict(sorted(meta.items()))
    if ctx.resources:
        ctx.resources.setdefault("channels", {})
        if not ctx.resources["channels"]:
            del ctx.resources["channels"]
        doc["resources_ref"] = {"id": f"{oid}-resources", "revision": meta["revision"]}
        if ctx.resources.get("channels"):
            ptr_set(
                doc,
                "/command_and_signal/signal/channels",
                list(ctx.resources["channels"]),
            )
    if ctx.stash:
        ptr_set(doc, f"/extensions/{AUTHORING_NS}", group_stash(ctx.stash))


def decode(
    doc: dict, resources: dict | None, ctx: Ctx, jiptl: dict | None = None
) -> dict[str, Any]:
    """Model dict (unvalidated) from an OpenAIX OPORD and its optional resources document."""
    d: dict[str, Any] = {}
    stash, _ = ungroup_stash(ptr_get(doc, f"/extensions/{AUTHORING_NS}", {}) or {})
    ctx.scratch["stash"] = stash
    ctx.scratch["jiptl_in"] = (jiptl or {}).get("targets", [])
    res = (resources or {}).get("resources", {}) if resources else {}
    for codec in _leaves():
        if isinstance(codec, Annexes):
            codec.dec(doc, d, ctx, res)
        else:
            codec.dec(doc, d, ctx)
    lists: dict[str, int] = ctx.scratch.get("measure_lists", {})
    dropped = 0
    for key in sorted_paths(stash):
        if _orphan(key, lists):
            dropped += 1
            continue
        set_path(d, key, stash[key])
    if dropped:
        ctx.warn(
            f"{dropped} authoring entries dropped: their measure or target is not in the supplied documents"
        )
    _resolve_channels(d, res)
    return d


def _orphan(key: str, lists: dict[str, int]) -> bool:
    """True for an authoring entry of a measure item that was not imported (no resources document, or the
    measure was skipped)."""
    for prefix, count in lists.items():
        if key.startswith(prefix + "."):
            index = key[len(prefix) + 1 :].split(".", 1)[0]
            if index.isdigit() and int(index) >= count:
                return True
    return False


def _resolve_channels(d: Any, res: dict) -> None:
    """Replace `@channel` markers with the channel row from resources."""
    channels = res.get("channels", {})
    if isinstance(d, dict):
        marker = d.pop("@channel", None)
        if marker is not None:
            ch = channels.get(marker)
            if ch is not None:
                row = Annexes._channel_row(ch)
                for k, v in row.items():
                    d.setdefault(k, v)
        for v in d.values():
            _resolve_channels(v, res)
    elif isinstance(d, list):
        for v in d:
            _resolve_channels(v, res)
