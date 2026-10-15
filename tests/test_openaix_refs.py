"""One source per fact: an openaix ref forbids the inline duplicates."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from opord_builder.renderer import load_opord
from opord_builder.schema import OPORD, OpenAIXRefs

ROOT = Path(__file__).resolve().parent.parent


def base() -> dict:
    return load_opord(ROOT / "examples" / "example_minimal.yaml").model_dump(
        mode="json", exclude_unset=True, exclude_none=True
    )


def appendix_with_table() -> dict:
    return {
        "letter": "H",
        "appendices": [
            {"number": 1, "title": "Comms", "frequency_tables": [{"title": "UHF"}]}
        ],
    }


def card(**extra) -> dict:
    return {"flight_callsign": "VIPER1", **extra}


def test_no_ref_allows_inline_everything():
    data = base()
    data["annexes"] = [appendix_with_table()]
    data["kneeboards"] = [
        card(positions=[{"number": 1, "modex": "420"}], comms={"intra": "276.5"})
    ]
    OPORD.model_validate(data)


def test_empty_openaix_block_is_not_a_ref():
    data = base()
    data["openaix"] = {}
    data["annexes"] = [appendix_with_table()]
    OPORD.model_validate(data)


def test_ref_without_inline_passes():
    data = base()
    data["openaix"] = {"ato": "ato.json", "resources": "res.json"}
    data["kneeboards"] = [card(msn_number="1234")]
    opord = OPORD.model_validate(data)
    assert opord.openaix.present() == ["ato", "resources"]


def test_all_ref_fields_optional_and_named():
    assert set(OpenAIXRefs.model_fields) == {"ato", "aco", "resources", "spins"}
    OpenAIXRefs()


def test_ref_with_inline_frequency_table_fails():
    data = base()
    data["openaix"] = {"resources": "res.json"}
    data["annexes"] = [appendix_with_table()]
    with pytest.raises(ValidationError) as exc:
        OPORD.model_validate(data)
    msg = str(exc.value)
    assert "frequency_tables" in msg and "openaix.resources" in msg


def test_ref_with_inline_kneeboard_comms_and_positions_fails():
    data = base()
    data["openaix"] = {"ato": "ato.json"}
    data["kneeboards"] = [
        card(positions=[{"number": 1, "modex": "420"}], comms={"intra": "276.5"})
    ]
    with pytest.raises(ValidationError) as exc:
        OPORD.model_validate(data)
    msg = str(exc.value)
    assert "kneeboards[0].comms" in msg
    assert "kneeboards[0].positions" in msg
    assert "openaix.ato" in msg


def test_ref_with_inline_airspace_control_fails():
    from opord_builder.schema.annexes import AirspaceControl, AnnexCData

    data = base()
    data["openaix"] = {"aco": "aco.json"}
    data["annexes"] = [
        {
            "letter": "C",
            "typed_body": AnnexCData(
                letter="C", airspace_control=AirspaceControl()
            ).model_dump(mode="json", exclude_none=True),
        }
    ]
    with pytest.raises(ValidationError) as exc:
        OPORD.model_validate(data)
    msg = str(exc.value)
    assert "airspace_control" in msg and "openaix.aco" in msg
    data.pop("openaix")
    OPORD.model_validate(data)


@pytest.mark.parametrize(
    "path",
    ["examples/example_full.yaml", "examples/example_minimal.yaml"],
)
def test_existing_examples_still_validate(path):
    load_opord(ROOT / path)
