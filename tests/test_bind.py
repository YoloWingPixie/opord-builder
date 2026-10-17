"""Data sources and `${var/pointer}` bindings."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest
import yaml

from opord_builder import bind, pointer
from opord_builder.load import (
    DocumentError,
    check_extensions,
    load_document,
    read,
    track,
    validate_document,
)

FIX = Path(__file__).resolve().parent / "fixtures" / "bindings"
DATA = "org.opord-builder.data"
USN = "orbats/players-a.yaml"


@pytest.fixture
def work(tmp_path):
    shutil.copytree(FIX, tmp_path / "w")
    return tmp_path / "w"


def run(work, variables, **body):
    """Resolve a plain dict with `variables` declared, as if read from work/doc.yaml."""
    doc = {"extensions": {DATA: {"vars": variables}}, **body}
    return bind.resolve_document(doc, work / "doc.yaml")


def ok(work, variables, **body):
    doc, errors, _ = run(work, variables, **body)
    assert not errors
    return doc


def err(work, variables, **body):
    _, errors, _ = run(work, variables, **body)
    return [str(e) for e in errors]


def write_order(work, mutate):
    doc = read(work / "order.yaml")
    mutate(doc)
    path = work / "o.yaml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- sources


def test_fixture_order_resolves_and_validates():
    doc = load_document(FIX / "order.yaml")
    assert doc["operation_name"] == "ATOMIC THUNDER"
    assert doc["meta"]["issuing_unit"] == "Headquarters, ATOMIC THUNDER Group"
    assert doc["task_organization"]["cvw-8"]["name"] == "Carrier Air Wing Eight"
    assert doc["mission"]["statement"] == (
        "ATOMIC THUNDER flies 6 sorties with Texaco 1 on 251.0. Cost ${not} a ref."
    )


def test_stripped_document_has_no_group_and_no_binding():
    doc = load_document(FIX / "order.yaml")
    assert DATA not in doc["extensions"]
    assert "${" not in json.dumps(doc).replace("${not}", "")  # only the escape survives
    d = ok(FIX, {"a": {"value": 1}})
    assert "extensions" not in d


def test_sources_yaml_json_csv_value(work):
    d = ok(
        work,
        {
            "y": {"path": USN, "select": "/units/0/slug"},
            "j": {"path": "data.json", "select": "/callsign"},
            "c": {"path": "tankers.csv", "select": "/1/name"},
            "v": {"value": {"k": [1, 2]}},
            "f": {"path": "data.json", "format": "json", "select": "/count"},
        },
        a="${y}",
        b="${j}",
        c="${c}",
        d="${v}",
        e="${f}",
    )
    assert [d[k] for k in "abcde"] == ["cvw-8", "IRON", "Shell 2", {"k": [1, 2]}, 6]


def test_csv_cells_are_strings_with_bom_stripped(work):
    d = ok(work, {"t": {"path": "tankers.csv"}}, x="${t}")
    assert d["x"] == [
        {"name": "Texaco 1", "freq": "251.0"},
        {"name": "Shell 2", "freq": "252.5"},
    ]


def test_csv_duplicate_header_is_an_error(work):
    (work / "bad.csv").write_text("a,a\n1,2\n", encoding="utf-8")
    [e] = err(work, {"t": {"path": "bad.csv"}}, x="${t}")
    assert e.startswith(f"/extensions/{DATA}/vars/t/path:") and "bad.csv" in e


def test_from_single_and_list_merge_and_concat(work):
    v = {
        "a": {"value": {"x": 1}},
        "b": {"value": {"y": 2}},
        "l1": {"value": [1]},
        "l2": {"value": [2, 3]},
        "one": {"from": "a"},
        "m": {"from": ["a", "b"]},
        "l": {"from": ["l1", "l2"]},
    }
    d = ok(work, v, one="${one}", m="${m}", l="${l}")
    assert (d["one"], d["m"], d["l"]) == ({"x": 1}, {"x": 1, "y": 2}, [1, 2, 3])


def test_from_duplicate_key_and_mixed_are_errors(work):
    v = {"a": {"value": {"x": 1}}, "b": {"value": {"x": 2}}, "c": {"value": [1]}}
    v["d"] = {"from": ["a", "b"]}
    v["e"] = {"from": ["a", "c"]}
    [dup] = err(work, v, x="${d}")
    assert "key 'x' is in both a and b" in dup and "vars/d/from" in dup
    [mixed] = err(work, v, x="${e}")
    assert "cannot combine" in mixed and "a is an object" in mixed


# --------------------------------------------------------------------------- globs


def test_glob_is_sorted_selected_per_file_and_combined(work):
    spec = {"path": "orbats/players-*.yaml", "select": "/units", "key": "/slug"}
    d = ok(work, {"p": spec}, x="${p}")
    assert list(d["x"]) == ["cvw-8", "vfa-81", "vf-11", "aw13-93rd"]  # a, then b
    lst = ok(
        work, {"p": {"path": "orbats/players-*.yaml", "select": "/units"}}, x="${p}"
    )
    assert [u["slug"] for u in lst["x"]] == ["cvw-8", "vfa-81", "vf-11", "aw13-93rd"]


def test_glob_no_match_names_the_pattern(work):
    [e] = err(work, {"p": {"path": "orbats/nothing-*.yaml"}}, x="${p}")
    assert "'orbats/nothing-*.yaml'" in e and "vars/p/path" in e


def test_glob_duplicate_key_across_files(work):
    spec = {"path": "orbats/*.yaml", "select": "/units", "key": "/slug"}
    [e] = err(work, {"p": spec}, x="${p}")
    assert "duplicate key 'vfa-81'" in e


def test_glob_mixed_list_and_map_is_an_error(work):
    (work / "orbats" / "map.yaml").write_text("units: {a: 1}\n", encoding="utf-8")
    spec = {"path": "orbats/*.yaml", "select": "/units"}
    [e] = err(work, {"p": spec}, x="${p}")
    assert "cannot combine" in e


def test_glob_tracks_files_and_parent_directory(work):
    with track() as deps:
        ok(work, {"p": {"path": "orbats/players-*.yaml", "select": "/units"}}, x="${p}")
    assert {
        work / "orbats",
        work / "orbats/players-a.yaml",
        work / "orbats/players-b.yaml",
    } <= deps


def test_path_without_glob_characters_is_one_file(work):
    d = ok(work, {"p": {"path": USN, "select": "/schemaId"}}, x="${p}")
    assert d["x"] == "fixture"


# --------------------------------------------------------------------------- selectors


def units(work, **sel):
    return {"u": {"path": USN, "select": "/units", **sel}}


def test_select_where_key_map(work):
    d = ok(work, units(work, where={"/parent": "cvw-8"}), x="${u}")
    assert [u["slug"] for u in d["x"]] == ["vfa-81"]
    d = ok(work, units(work, key="/slug", map="/short"), x="${u}")
    assert d["x"] == {"cvw-8": "CVW-8", "vfa-81": "VFA-81"}
    d = ok(
        work, units(work, key="/slug", map={"n": "/name", "s": "/strength"}), x="${u}"
    )
    assert d["x"]["vfa-81"] == {"n": "VFA-81 Sunliners", "s": 12}


def test_where_is_an_and_and_json_equality(work):
    d = ok(work, units(work, where={"/parent": "cvw-8", "/strength": 12}), x="${u}")
    assert len(d["x"]) == 1
    d = ok(
        work, {"v": {"value": [{"a": 1}, {"a": True}], "where": {"/a": True}}}, x="${v}"
    )
    assert d["x"] == [{"a": True}]  # True is not 1


def test_where_on_a_map_keeps_entries_in_order(work):
    v = {
        "m": {
            "value": {"b": {"k": 1}, "a": {"k": 1}, "c": {"k": 2}},
            "where": {"/k": 1},
        }
    }
    assert list(ok(work, v, x="${m}")["x"]) == ["b", "a"]


def test_selectors_apply_in_fixed_order(work):
    # select, then where (needs the list), then key, then map (needs the keyed map's values)
    spec = {
        "map": "/name",
        "key": "/slug",
        "where": {"/parent": "cvw-8"},
        "select": "/units",
    }
    d = ok(work, {"u": {"path": USN, **spec}}, x="${u}")
    assert d["x"] == {"vfa-81": "VFA-81 Sunliners"}


def test_selector_errors(work):
    [e] = err(work, units(work, select="/unitz"), x="${u}")
    assert "vars/u/select" in e and "'/unitz' not found" in e and "players-a.yaml" in e
    [e] = err(work, units(work, key="/nope"), x="${u}")
    assert "vars/u/key" in e and "item 0 has no '/nope'" in e
    [e] = err(work, {"d": {"value": [{"k": 1}, {"k": 1}], "key": "/k"}}, x="${d}")
    assert "vars/d/key" in e and "duplicate key '1'" in e
    [e] = err(work, units(work, map="/nope"), x="${u}")
    assert "vars/u/map" in e and "item 0" in e
    [e] = err(work, {"u": {"path": USN, "key": "/slug"}}, x="${u}")
    assert "key needs a list" in e


# --------------------------------------------------------------------------- bindings


def test_whole_value_binding_keeps_type(work):
    d = ok(
        work,
        {"i": {"path": "data.json"}},
        n="${i/count}",
        f="${i/ratio}",
        b="${i/flag}",
        z="${i/nothing}",
        o="${ i/nested }",
        li="${i/nested/list}",
        rows=[{"c": "${i/nested/list/1}"}],
    )
    assert (d["n"], d["f"], d["b"], d["z"]) == (6, 2.5, True, None)
    assert d["o"]["list"] == [1, 2] and d["li"] == [1, 2] and d["rows"] == [{"c": 2}]


def test_whole_value_binding_is_a_copy(work):
    d = ok(work, {"v": {"value": {"k": [1]}}}, a="${v}", b="${v}")
    d["a"]["k"].append(2)
    assert d["b"] == {"k": [1]}


def test_interpolation_int_float_and_pointer_escapes(work):
    d = ok(
        work,
        {"i": {"path": "data.json"}},
        s="n=${i/count} r=${i/ratio} ${i/nested/a~1b} ${i/nested/t~0x}",
    )
    assert d["s"] == "n=6 r=2.5 slash tilde"


def test_interpolation_rejects_bool_null_object_list(work):
    for ref, word in (
        ("flag", "a bool"),
        ("nothing", "null"),
        ("nested", "an object"),
        ("nested/list", "a list"),
    ):
        [e] = err(work, {"i": {"path": "data.json"}}, s=f"x ${{i/{ref}}}")
        assert word in e and e.startswith("/s:")


def test_escape_gives_literal(work):
    d = ok(work, {"a": {"value": 1}}, s="$${a} and ${a}", t="$${")
    assert d == {"s": "${a} and 1", "t": "${"}


def test_keys_and_data_are_never_interpolated(work):
    (work / "lit.yaml").write_text("x: ${nope}\n", encoding="utf-8")
    d = ok(work, {"l": {"path": "lit.yaml"}}, **{"${a}": "k", "v": "${l/x}"})
    assert d == {"${a}": "k", "v": "${nope}"}


def test_nested_var_error_messages(work):
    v = {"p": {"path": USN, "select": "/units", "key": "/slug"}}
    [e] = err(work, v, mission={"x": "${p/vfa-82/name}"})
    assert e.startswith(
        "/mission/x: ${p/vfa-82/name}: no key or index 'vfa-82' in var p ("
    )
    assert "players-a.yaml" in e and "select" in e
    [e] = err(work, v, mission="${typo}")
    assert e == "/mission: ${typo}: no var 'typo' (vars: p)"
    [e] = err(work, v, s="${p/vfa-81/name/x}")
    assert "cannot descend into str" in e
    [e] = err(work, v, s="a ${p")
    assert e.startswith("/s: unterminated")
    d, errors, _ = run(work, v, s="${p/vfa-81}")
    assert not errors and isinstance(d["s"], dict)
    [e] = err(work, v, s="x ${p/vfa-81}")
    assert "an object; only a whole-value binding takes it" in e


def test_missing_source_file_error(work):
    [e] = err(work, {"p": {"path": "gone.yaml"}}, x="${p}")
    assert e.startswith(f"/extensions/{DATA}/vars/p/path: cannot read gone.yaml (")
    assert "No such file" in e


def test_code_like_refs_are_just_undefined(work):
    [e] = err(work, {"a": {"value": "s"}}, x="${__class__}")
    assert "no var '__class__'" in e
    [e] = err(work, {"a": {"value": "s"}}, y="${a/b}")
    assert "cannot descend into str" in e


def test_data_structure_errors_stop_before_resolution(work):
    [e] = err(work, {"x": {"path": "a", "value": 1}}, s="${x}")
    assert e.startswith(f"/extensions/{DATA}/vars/x:")
    errors = err(work, {"x": {"pathh": "a"}}, s="${nope}")
    assert errors and all(f"/extensions/{DATA}/vars/x" in e for e in errors)


def test_cycle_in_vars(work):
    v = {"a": {"from": "b"}, "b": {"from": "a"}}
    [e] = err(work, v, s="${a}")
    assert f"/extensions/{DATA}/vars/" in e and "cycle a -> b -> a" in e


def test_cycle_across_files_with_validate_openaix(work):
    for me, other in (("a", "b"), ("b", "a")):
        doc = read(work / "order.yaml")
        doc["extensions"][DATA]["vars"] = {
            "o": {"path": f"{other}.yaml", "validate": "openaix"}
        }
        doc["operation_name"] = "${o/operation_name}"
        (work / f"{me}.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(DocumentError) as exc:
        load_document(work / "a.yaml")
    assert "cycle" in str(exc.value)


def test_validate_openaix_loads_bindings_recursively(work):
    doc = read(work / "order.yaml")
    doc["extensions"][DATA]["vars"] = {
        "o": {"path": "order.yaml", "validate": "openaix"}
    }
    doc["mission"] = {"statement": "m"}
    doc["meta"]["issuing_unit"] = doc["meta"]["operation"] = "u"
    doc["execution"] = {"commanders_intent": {"purpose": "p"}}
    doc["task_organization"] = {}
    doc["operation_name"] = "${o/task_organization/vfa-81/name}"
    path = work / "outer.yaml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    assert load_document(path)["operation_name"] == "VFA-81 Sunliners"


def test_provenance_on_a_schema_error_at_a_bound_field(work):
    path = write_order(
        work, lambda d: d.__setitem__("order_number", "${players/vfa-81/strength}")
    )
    with pytest.raises(DocumentError) as exc:
        load_document(path)
    [e] = [e for e in exc.value.errors if e.pointer == "/order_number"]
    assert "(bound from ${players/vfa-81/strength}; var players " in e.message
    assert "players-*.yaml" in e.message and 'select "/units"' in e.message


def test_provenance_applies_below_a_bound_object(work):
    path = write_order(
        work,
        lambda d: d["task_organization"].__setitem__("vfa-81", "${players/vfa-81}"),
    )
    with pytest.raises(DocumentError) as exc:
        load_document(path)
    assert any(
        e.pointer.startswith("/task_organization/vfa-81")
        and "bound from ${players/vfa-81}" in e.message
        for e in exc.value.errors
    )


def test_resolution_is_deterministic():
    a, b = load_document(FIX / "order.yaml"), load_document(FIX / "order.yaml")
    assert a == b and json.dumps(a) == json.dumps(b)


def test_document_without_bindings_is_untouched(work):
    doc = read(work / "order.yaml")
    plain = {"a": "x", "b": ["y", {"c": "z"}]}
    d, errors, prov = bind.resolve_document(copy.deepcopy(plain), work / "x.yaml")
    assert (d, errors, prov) == (plain, [], {})
    assert doc


# --------------------------------------------------------------------------- tracking and reuse


def test_track_collects_sources_includes_and_resources(work):
    (work / "frag.yaml").write_text("name: ${op}\n", encoding="utf-8")
    with track() as deps:
        load_document(FIX / "order.yaml")
        read(FIX / "order.yaml")
    assert {
        FIX / "data.json",
        FIX / "tankers.csv",
        FIX / "order.yaml",
        FIX / "orbats",
    } <= deps
    inc = work / "inc.yaml"
    inc.write_text("a: !include frag.yaml\n", encoding="utf-8")
    with track() as deps:
        read(inc)
    assert {inc, work / "frag.yaml"} <= deps
    with track() as outer:
        pass
    assert outer == set()


def test_track_collects_resources_path():
    from opord_builder.order import load_order

    ex = Path(__file__).resolve().parent.parent / "examples"
    with track() as deps:
        load_order(ex / "example_with_sources.yaml")
    assert ex / "resources" / "example_with_sources.yaml" in deps


def test_spins_sidecar_with_bindings_is_resolved(work):
    from opord_builder.schema.spins import SpinsOpenAIXRefs
    from opord_builder.spins_openaix import OpenAIXSources

    sources = OpenAIXSources(SpinsOpenAIXRefs(opord="order.yaml"), work)
    [(_, doc)] = sources.documents("opord")
    assert doc["task_organization"]["vfa-81"]["name"] == "VFA-81 Sunliners"


def test_data_group_validates_as_an_extension():
    doc = read(FIX / "order.yaml")
    assert not [e for e in check_extensions(doc) if DATA in e.pointer]
    doc["extensions"][DATA]["vars"]["bad"] = {"path": ""}
    assert any("vars/bad" in e.pointer for e in validate_document(copy.deepcopy(doc)))


def test_pointer_module():
    assert pointer.tokens("/a~1b/c~0d") == ["a/b", "c~d"]
    assert pointer.escape("a/b~") == "a~1b~0"
    assert pointer.resolve({"a": [1, {"b": 2}]}, "/a/1/b") == 2
    assert pointer.resolve({"a": []}, "/a/0") is pointer.MISSING
    assert pointer.at({"a": [1]}, "/a/0") == 1 and pointer.at({}, "/x") is None
    with pytest.raises(ValueError, match="not a JSON Pointer"):
        pointer.tokens("a")


# --------------------------------------------------------------------------- CLI


def cli(*args):
    from typer.testing import CliRunner

    from opord_builder.cli import app

    return CliRunner().invoke(app, [str(a) for a in args])


def test_validate_openaix_resolves_bindings_and_fails_on_a_missing_source(work):
    r = cli("validate-openaix", work / "order.yaml")
    assert r.exit_code == 0 and r.output.strip().endswith("order.yaml: ok")
    (work / "tankers.csv").unlink()
    r = cli("validate-openaix", work / "order.yaml")
    assert r.exit_code == 1
    assert "vars/tankers/path: cannot read tankers.csv" in r.output


def test_resolve_writes_the_plain_document(work, tmp_path):
    out = tmp_path / "plain.json"
    r = cli("resolve", work / "order.yaml", "-o", out)
    assert r.exit_code == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc == load_document(work / "order.yaml")
    assert list(doc) == list(load_document(work / "order.yaml"))  # key order kept
    assert not validate_document(doc)
    yml = tmp_path / "plain.yaml"
    assert cli("resolve", work / "order.yaml", "-o", yml).exit_code == 0
    assert yaml.safe_load(yml.read_text(encoding="utf-8")) == doc
    assert json.loads(cli("resolve", work / "order.yaml").output) == doc


def test_resolve_reports_errors(work):
    (work / "data.json").unlink()
    r = cli("resolve", work / "order.yaml")
    assert r.exit_code == 1 and "vars/info/path" in r.output


# --------------------------------------------------------------------------- editor schema


def _bundle_errors(doc, **kw):
    from jsonschema import Draft202012Validator

    from opord_builder.docs import bundled
    from opord_builder.openaix.validate import FORMAT_CHECKER

    v = Draft202012Validator(bundled("opord", **kw), format_checker=FORMAT_CHECKER)
    return list(v.iter_errors(doc))


def test_bundled_schema_accepts_a_binding_in_an_integer_field_but_not_a_wrong_literal():
    doc = read(Path(__file__).resolve().parent.parent / "examples/example_minimal.yaml")
    doc["extensions"]["org.opord-builder.print"]["copy_number"] = 3
    assert not _bundle_errors(doc)
    doc["extensions"]["org.opord-builder.print"]["copy_number"] = "${copies}"
    assert not _bundle_errors(doc)
    assert _bundle_errors(doc, strict=True)  # a resolved document has no bindings
    doc["extensions"]["org.opord-builder.print"]["copy_number"] = "three"
    assert _bundle_errors(doc)


def test_bundled_schema_checks_the_data_group():
    doc = read(FIX / "order.yaml")
    assert not _bundle_errors(doc)
    doc["extensions"][DATA]["vars"]["bad"] = {"pathh": "x"}
    assert _bundle_errors(doc)


def test_resolve_output_validates_under_the_strict_schema(work, tmp_path):
    out = tmp_path / "plain.json"
    assert cli("resolve", work / "order.yaml", "-o", out).exit_code == 0
    assert not _bundle_errors(json.loads(out.read_text(encoding="utf-8")), strict=True)
    strict = json.loads(cli("schema", "--strict").output)
    assert "Binding" not in strict["$defs"]
    assert "Binding" in json.loads(cli("schema").output)["$defs"]


# --------------------------------------------------------------------------- example goldens

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "bindings"


def test_bindings_example_matches_its_goldens():
    from opord_builder.order import load_order
    from opord_builder.render import render_markdown

    md = render_markdown(load_order(EXAMPLE / "order.yaml"))
    assert md == (EXAMPLE / "order.md").read_text(encoding="utf-8")
    resolved = json.dumps(
        load_document(EXAMPLE / "order.yaml"), indent=2, ensure_ascii=False
    )
    assert resolved + "\n" == (EXAMPLE / "order.resolved.json").read_text(
        encoding="utf-8"
    )
