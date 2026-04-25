"""Pydantic schema for a U.S. Army Operations Order (OPORD).

Structure tracks FM 6-0 (May 2022) Appendix D and ATP 5-0.2-1 (Dec 2020).
Every field except the header and the mission statement is optional so that
authors can write a sparse YAML and trust the renderer to skip empty sections.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Annotated, Literal, Optional

from pydantic import Field, model_validator

from opord_builder.schema._base import _Base
from opord_builder.schema.shared import KneeboardCard, OrdersGroup, PlanningMilestone, RehearsalPlan

if TYPE_CHECKING:
    from opord_builder.schema.annexes import AnnexTypedBody


class ClassificationLevel(str, Enum):
    """U.S. Government classification markings permitted on an OPORD banner."""

    UNCLASSIFIED = "UNCLASSIFIED"
    CUI = "CUI"
    CONFIDENTIAL = "CONFIDENTIAL"
    SECRET = "SECRET"
    TOP_SECRET = "TOP SECRET"

    @property
    def css_slug(self) -> str:
        return self.value.lower().replace(" ", "-")


class AnnexStatus(str, Enum):
    """Publication state of an annex: published in full, deliberately omitted, or a reserved 'Not Used' letter."""

    PUBLISHED = "published"
    OMITTED = "omitted"
    NOT_USED = "not_used"

    @property
    def css_slug(self) -> str:
        return self.value

    @property
    def display_label(self) -> str:
        return self.value.replace("_", " ").title()


# ---------------------------------------------------------------------------
# Canonical Army annex letters per FM 6-0 (2022) / ATP 5-0.2-1.
# Reserved letters (I, O, T, W, X, Y) are NEVER assigned — I/O to avoid
# confusion with numerals, T/W/X/Y held for future doctrinal use.
# ---------------------------------------------------------------------------
CANONICAL_ANNEXES: dict[str, str] = {
    "A": "Task Organization",
    "B": "Intelligence",
    "C": "Operations",
    "D": "Fires",
    "E": "Protection",
    "F": "Sustainment",
    "G": "Engineer",
    "H": "Signal",
    "I": "Not Used",
    "J": "Public Affairs",
    "K": "Civil Affairs Operations",
    "L": "Information Collection",
    "M": "Assessment",
    "N": "Space Operations",
    "O": "Not Used",
    "P": "Host-Nation Support",
    "Q": "Knowledge Management",
    "R": "Reports",
    "S": "Special Technical Operations",
    "T": "Not Used",
    "U": "Inspector General",
    "V": "Interagency Coordination",
    "W": "Not Used",
    "X": "Not Used",
    "Y": "Not Used",
    "Z": "Distribution",
}
RESERVED_LETTERS = {"I", "O", "T", "W", "X", "Y"}


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
class Reference(_Base):
    """A single reference entry in the OPORD header (maps, orders, SOPs, doctrine)."""

    citation: str = Field(
        description="The formal citation for the reference (e.g. map sheet name and series, higher OPORD number, SOP title)."
    )
    description: Optional[str] = Field(
        default=None,
        description="Optional human-readable clarification of what the reference is and how it applies to this order.",
    )


class Unit(_Base):
    """A unit in a task organization tree."""

    name: str = Field(
        description="Official designation of the unit (e.g. 'A Co, 1-508 PIR' or 'TF DAGGER')."
    )
    callsign: Optional[str] = Field(
        default=None,
        description="Radio callsign used for the unit in the current SOI, if different from the unit name.",
    )
    commander: Optional[str] = Field(
        default=None,
        description="Rank and last name of the unit commander (e.g. 'CPT SMITH').",
    )
    role: Optional[str] = Field(
        default=None,
        description="Tactical role within this operation (e.g. 'Main Effort', 'Reserve', 'Support by Fire').",
    )
    relationship: Optional[str] = Field(
        default=None,
        description="Command or support relationship per FM 3-0: OPCON, TACON, ADCON, assigned, attached, DS, GS, GSR, or R.",
    )
    subordinate_units: list["Unit"] = Field(
        default_factory=list,
        description="Child units in the task-organization tree, rendered recursively beneath this unit.",
    )


class Header(_Base):
    """OPORD header block: classification, issuing HQ, DTG, references, and task organization."""

    classification: ClassificationLevel = Field(
        description="Overall classification marking that appears on the top/bottom banner of every page."
    )
    classification_caveat: Optional[str] = Field(
        default=None,
        description="Dissemination caveat appended to the classification line, e.g. 'REL TO USA, FVEY' or 'NOFORN'.",
    )
    copy_number: Optional[int] = Field(
        default=None,
        description="This specific copy's number within the distribution. Required on classified orders per AR 380-5.",
    )
    number_of_copies: Optional[int] = Field(
        default=None,
        description="Total number of copies produced in this distribution (the 'of N' in 'Copy X of N').",
    )
    issuing_headquarters: str = Field(
        description="Full designation of the headquarters publishing the order (e.g. '1st Brigade Combat Team, 82nd Airborne Division')."
    )
    place_of_issue: str = Field(
        description="Location where the order is issued, typically an installation, AO name, or MGRS grid."
    )
    dtg: str = Field(
        description="Date-time group the order is signed, in military DTG format (e.g. '181200ZAPR26')."
    )
    message_reference_number: Optional[str] = Field(
        default=None,
        description="Originator-assigned message reference number used for record traffic and cross-referencing.",
    )
    operation_order_number: str = Field(
        description="OPORD number, typically fiscal year plus sequence (e.g. '26-04')."
    )
    operation_name: str = Field(
        description="Nickname or codeword for the operation in standard two-word form (e.g. 'FALCON SHIELD')."
    )
    author: Optional[str] = Field(
        default=None,
        description="Name and role of the drafting officer or staff element (e.g. 'MAJ J. Rivera, S3'). Shown on the cover as the plan author.",
    )
    logo: Optional[str] = Field(
        default=None,
        description="Path or URL to a unit crest or command logo rendered on the cover. Local paths (PNG/SVG/JPG) are resolved relative to the YAML file; absolute URLs are supported. Omit for a text-only cover.",
    )
    page_icon: Optional[str] = Field(
        default=None,
        description="Optional small icon rendered in the top-right of every PDF page header (distinct from the cover logo). Useful for a compact unit/command mark that persists on every page. Supports local paths and absolute URLs.",
    )
    watermark: Optional[str] = Field(
        default=None,
        description="Optional page watermark. Accepts either short text (e.g. 'DRAFT', 'WORKING COPY', 'FOUO') — rendered as large rotated letters — or an image URL/path (PNG/JPG/SVG) — rendered as a large rotated image overlay. Applied to every page of the HTML and PDF output.",
    )
    references: list[Reference] = Field(
        default_factory=list,
        description="Ordered list of maps, higher orders, SOPs, and doctrinal publications the order relies on.",
    )
    time_zone: str = Field(
        description="Time-zone suffix used throughout the order (e.g. 'ZULU' or 'ROMEO'); all times in the order use this zone unless noted."
    )
    task_organization: Optional[Unit] = Field(
        default=None,
        description="Root of the task-organization tree when shown in the header; alternatively refer to Annex A.",
    )
    task_organization_note: Optional[str] = Field(
        default=None,
        description="Short note used in lieu of an inline task organization, typically 'See Annex A (Task Organization).'",
    )


# ---------------------------------------------------------------------------
# Paragraph 1 — Situation
# ---------------------------------------------------------------------------
class Terrain(_Base):
    """OAKOC — the five military aspects of terrain."""

    observation_and_fields_of_fire: Optional[str] = Field(
        default=None,
        description="Observation and fields of fire: how terrain affects visibility and weapon engagement ranges (the 'O' in OAKOC).",
    )
    avenues_of_approach: Optional[str] = Field(
        default=None,
        description="Avenues of approach: air and ground routes leading to objectives or key terrain (the 'A' in OAKOC).",
    )
    key_terrain: Optional[str] = Field(
        default=None,
        description="Key (and decisive) terrain: locations whose seizure or retention affords a marked advantage to either combatant (the 'K' in OAKOC).",
    )
    obstacles: Optional[str] = Field(
        default=None,
        description="Existing and reinforcing obstacles that disrupt, turn, fix, or block movement (the 'O' in OAKOC).",
    )
    cover_and_concealment: Optional[str] = Field(
        default=None,
        description="Cover (protection from fire) and concealment (protection from observation) available in the AO (the 'C' in OAKOC).",
    )


class LightData(_Base):
    """Canonical astronomical / illumination data for a calendar day per the SWO product.

    Doctrinal set: date, BMNT, sunrise, sunset, EENT, moonrise, moonset,
    moon phase, percent illumination (FM 6-0 App D / ATP 2-01.3 Ch 3).
    """

    date: Optional[str] = Field(
        default=None,
        description="Calendar date this light data applies to (YYYY-MM-DD or DDMMMYY).",
    )
    bmnt: Optional[str] = Field(
        default=None,
        description="Beginning Morning Nautical Twilight time (HHMM local or Z).",
    )
    sunrise: Optional[str] = Field(default=None, description="Sunrise time (HHMM).")
    sunset: Optional[str] = Field(default=None, description="Sunset time (HHMM).")
    eent: Optional[str] = Field(
        default=None, description="End Evening Nautical Twilight time (HHMM)."
    )
    moonrise: Optional[str] = Field(default=None, description="Moonrise time (HHMM).")
    moonset: Optional[str] = Field(default=None, description="Moonset time (HHMM).")
    moon_phase: Optional[str] = Field(
        default=None,
        description="Moon phase (new, waxing crescent, first quarter, waxing gibbous, full, waning gibbous, last quarter, waning crescent).",
    )
    percent_illumination: Optional[float] = Field(
        default=None,
        ge=0,
        le=100,
        description="Moon illumination percent (0–100). Drives NVG/thermal planning.",
    )


class WeatherPeriodForecast(_Base):
    """One row of the operation-period weather forecast.

    Per FM 6-0 / ATP 2-01.3, multi-day or phased operations require a
    forecast covering the full operation period — typically keyed to
    phase or D+N day — not a single snapshot. Each row carries the 5
    aspects, optional structured light data, and an effects-on-operations
    'so what' line. Produced by the Staff Weather Officer (SWO) /
    G-2/S-2 weather team.
    """

    phase_or_day: str = Field(
        description="Phase label or D+N day the forecast covers (e.g. 'Phase II / D+1', 'D-Day', 'H-6 to H+12')."
    )
    period_start: Optional[str] = Field(
        default=None,
        description="Period start DTG or date (e.g. '190500ZAPR26' or '2026-04-19').",
    )
    period_end: Optional[str] = Field(
        default=None,
        description="Period end DTG or date.",
    )
    visibility: Optional[str] = Field(
        default=None, description="Visibility forecast with effects."
    )
    winds: Optional[str] = Field(default=None, description="Wind forecast with effects.")
    precipitation: Optional[str] = Field(
        default=None, description="Precipitation forecast with effects."
    )
    cloud_cover: Optional[str] = Field(
        default=None, description="Cloud cover / ceiling forecast with effects."
    )
    temperature_and_humidity: Optional[str] = Field(
        default=None,
        description="Temperature (Hi/Lo) and humidity for this period.",
    )
    light_data: Optional[LightData] = Field(
        default=None,
        description="Structured light data covering this period (if period ≤ 24 hrs) or the most operationally critical day in the window.",
    )
    effects_on_operations: Optional[str] = Field(
        default=None,
        description="The 'so what' — net effect on friendly and enemy operations and specific warfighting functions (aviation, fires, ISR, optics, mobility, CBRN).",
    )


class Weather(_Base):
    """Paragraph 1.b.(2) Weather — five military aspects, light, forecast, climate, effects.

    Per FM 6-0 (May 2022) Appendix D and ATP 2-01.3 Ch 3, the weather
    sub-paragraph must cover the five military aspects of weather
    (visibility, winds, precipitation, cloud cover, temperature/humidity),
    a light table, AND for multi-day operations a forecast keyed to
    phases or days — a single snapshot is insufficient for campaign-
    scale OPORDs. ``effects_on_operations`` captures the doctrinally
    required 'so what' analysis. ``climate_baseline`` provides the
    seasonal norm when the forecast confidence is low or the AO is
    unfamiliar. The SWO / tactical weather team produces the underlying
    Staff Weather Product; this paragraph is the executive summary
    with the tables typically living in Annex B (Intelligence).
    """

    # --- Snapshot: short ops may populate these without a per-period forecast
    visibility: Optional[str] = Field(
        default=None,
        description="Visibility conditions and effects on operations (fog, haze, obscurants, illumination limits).",
    )
    winds: Optional[str] = Field(
        default=None,
        description="Surface and aloft winds with effects on aviation, fires, smoke, and CBRN employment.",
    )
    precipitation: Optional[str] = Field(
        default=None,
        description="Expected precipitation type, intensity, and effects on mobility, optics, and soldier load.",
    )
    cloud_cover: Optional[str] = Field(
        default=None,
        description="Ceiling and cloud coverage with effects on aviation, ISR, and close air support.",
    )
    temperature_and_humidity: Optional[str] = Field(
        default=None,
        description="Temperature and humidity ranges with effects on personnel, equipment, and heat/cold casualty risk.",
    )
    light_data: Optional[str] = Field(
        default=None,
        description="Light table single-line summary: BMNT, sunrise, sunset, EENT, moon phase, illumination %. Use ``light_data_structured`` or ``forecast_by_period[].light_data`` for field-level data.",
    )
    light_data_structured: Optional[LightData] = Field(
        default=None,
        description="Structured light data for the critical day/event of the operation.",
    )

    # --- Campaign-period doctrine additions
    climate_baseline: Optional[str] = Field(
        default=None,
        description="Seasonal/regional climatology baseline for the AO (prevailing winds, precipitation norms, temperature bands). Used as the reference against which the operation-period forecast is compared; most useful for unfamiliar AOs or operations > 72 hrs.",
    )
    forecast_by_period: list[WeatherPeriodForecast] = Field(
        default_factory=list,
        description="Forecast rows keyed to phases or D+N days for the full operation period. Doctrinally expected for multi-day / phased campaigns.",
    )
    effects_on_operations: Optional[str] = Field(
        default=None,
        description="Consolidated 'so what' for the base order: how weather across the operation period affects friendly and enemy COAs and warfighting functions. Doctrinally required per ATP 2-01.3 Ch 3.",
    )
    forecast_confidence: Optional[str] = Field(
        default=None,
        description="Forecast confidence level (LOW / MODERATE / HIGH) with rationale — drives branch planning around weather-dependent assets.",
    )
    swo_product_reference: Optional[str] = Field(
        default=None,
        description="Pointer to the authoritative SWO / tactical weather team product (e.g. 'Annex B, App 1, Tab B (Weather), SWO Product 26-04-WX-015').",
    )


class AreaOfOperations(_Base):
    """Description of the assigned AO with terrain (OAKOC) and weather analysis."""

    description: Optional[str] = Field(
        default=None,
        description="Narrative description of the AO boundaries and character (rural/urban, restricted/unrestricted, etc.).",
    )
    terrain: Optional[Terrain] = Field(
        default=None,
        description="OAKOC analysis of the terrain within the AO.",
    )
    weather: Optional[Weather] = Field(
        default=None,
        description="Weather analysis and light data for the operation's duration.",
    )


class EnemyForces(_Base):
    """Paragraph 1.b — enemy situation: composition, activity, capabilities, and likely/dangerous COAs."""

    composition_disposition_strength: Optional[str] = Field(
        default=None,
        description="Enemy composition, disposition, and strength (CDS) — who, where, and how many.",
    )
    recent_activities: Optional[str] = Field(
        default=None,
        description="Summary of recent enemy activity and significant events within the AO and AOI.",
    )
    capabilities: Optional[str] = Field(
        default=None,
        description="Enemy capabilities and limitations (defend, reinforce, attack, withdraw, delay), often framed by warfighting function.",
    )
    most_likely_coa: Optional[str] = Field(
        default=None,
        description="Enemy Most Likely Course of Action (ECOA-ML) as produced by IPB step 4.",
    )
    most_dangerous_coa: Optional[str] = Field(
        default=None,
        description="Enemy Most Dangerous Course of Action (ECOA-MD) as produced by IPB step 4.",
    )


class HigherHeadquarters(_Base):
    """Mission and intent for two-up and one-up HQ."""

    two_up_designation: Optional[str] = Field(
        default=None,
        description="Designation of the headquarters two echelons up (e.g. division when this is a battalion order).",
    )
    two_up_mission: Optional[str] = Field(
        default=None,
        description="Mission statement of the two-up headquarters, quoted verbatim from its order.",
    )
    two_up_intent: Optional[str] = Field(
        default=None,
        description="Commander's intent of the two-up headquarters, quoted verbatim from its order.",
    )
    one_up_designation: Optional[str] = Field(
        default=None,
        description="Designation of the immediate higher headquarters (one echelon up).",
    )
    one_up_mission: Optional[str] = Field(
        default=None,
        description="Mission statement of the one-up headquarters, quoted verbatim from its order.",
    )
    one_up_intent: Optional[str] = Field(
        default=None,
        description="Commander's intent of the one-up headquarters, quoted verbatim from its order.",
    )


class FriendlyForces(_Base):
    """Paragraph 1.c — friendly forces: higher HQ mission/intent, adjacent units, and others that affect this operation."""

    higher_headquarters: Optional[HigherHeadquarters] = Field(
        default=None,
        description="Mission and intent of the one-up and two-up higher headquarters.",
    )
    adjacent_units: Optional[str] = Field(
        default=None,
        description="Missions and tasks of units to the left, right, front, and rear whose actions affect this operation.",
    )
    other_units: Optional[str] = Field(
        default=None,
        description="Other friendly units (supporting, coordinating, or in adjacent AOs) whose actions affect this operation.",
    )


class CivilConsiderations(_Base):
    """ASCOPE — Areas, Structures, Capabilities, Organizations, People, Events."""

    areas: Optional[str] = Field(
        default=None,
        description="ASCOPE 'A' — key civilian areas: political boundaries, districts, enclaves, and population centers that affect operations.",
    )
    structures: Optional[str] = Field(
        default=None,
        description="ASCOPE 'S' — significant structures: bridges, power plants, hospitals, religious sites, and cultural property.",
    )
    capabilities: Optional[str] = Field(
        default=None,
        description="ASCOPE 'C' — capabilities of the local populace and government to sustain itself (food, water, power, sanitation, security).",
    )
    organizations: Optional[str] = Field(
        default=None,
        description="ASCOPE 'O' — organizations present in the AO: IGOs, NGOs, religious, tribal, criminal, and political groups.",
    )
    people: Optional[str] = Field(
        default=None,
        description="ASCOPE 'P' — civilian population: demographics, attitudes, key leaders, and displaced persons.",
    )
    events: Optional[str] = Field(
        default=None,
        description="ASCOPE 'E' — routine, cyclical, and planned events (elections, religious holidays, market days, harvests) that shape operations.",
    )


class AttachmentsDetachments(_Base):
    """Units attached to or detached from the issuing HQ for this operation."""

    attachments: list[str] = Field(
        default_factory=list,
        description="Units, personnel, or capabilities attached to the issuing headquarters for this operation, with effective DTG if relevant.",
    )
    detachments: list[str] = Field(
        default_factory=list,
        description="Units normally assigned but detached from the issuing headquarters for this operation, with effective DTG if relevant.",
    )
    note: Optional[str] = Field(
        default=None,
        description="Short note used in lieu of an inline list, typically 'See Annex A (Task Organization).'",
    )


class Situation(_Base):
    """Paragraph 1 — Situation: AO, enemy, friendly, civil, attachments/detachments, and assumptions."""

    area_of_interest: Optional[str] = Field(
        default=None,
        description="Area of Interest (AOI): the area outside the AO that contains factors affecting mission accomplishment.",
    )
    area_of_operations: Optional[AreaOfOperations] = Field(
        default=None,
        description="The assigned Area of Operations with terrain (OAKOC) and weather analysis.",
    )
    enemy_forces: Optional[EnemyForces] = Field(
        default=None,
        description="Paragraph 1.b — enemy situation and courses of action from IPB.",
    )
    friendly_forces: Optional[FriendlyForces] = Field(
        default=None,
        description="Paragraph 1.c — higher, adjacent, and other friendly forces that affect this operation.",
    )
    interagency_intergovernmental_ngo: Optional[str] = Field(
        default=None,
        description="Relevant interagency, intergovernmental, and non-governmental organizations operating in or affecting the AO.",
    )
    civil_considerations: Optional[CivilConsiderations] = Field(
        default=None,
        description="ASCOPE analysis of civil considerations. Required in doctrine when civil considerations affect the operation; omit otherwise.",
    )
    attachments_and_detachments: Optional[AttachmentsDetachments] = Field(
        default=None,
        description="Units attached to or detached from the issuing HQ for this operation; typically refers to Annex A.",
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Planning assumptions used in the absence of facts; must be valid, necessary, and likely true per ADP 5-0.",
    )


# ---------------------------------------------------------------------------
# Paragraph 3 — Execution
# ---------------------------------------------------------------------------
class CommandersIntent(_Base):
    """Paragraph 3.a — Commander's Intent: purpose, key tasks, and end state per ADP 6-0."""

    purpose: Optional[str] = Field(
        default=None,
        description="The broader purpose of the operation — the 'why' beyond the mission statement's immediate purpose.",
    )
    key_tasks: list[str] = Field(
        default_factory=list,
        description="Activities the force must perform as a whole to achieve the end state; not specified tasks to subordinates.",
    )
    end_state: Optional[str] = Field(
        default=None,
        description="The desired conditions at operation's end. Per ADP 5-0, expressed in terms of friendly, enemy, terrain, and civil conditions.",
    )
    end_state_friendly: Optional[str] = Field(
        default=None,
        description="Desired condition of friendly forces at end state (the 'friendly' category per ADP 5-0).",
    )
    end_state_enemy: Optional[str] = Field(
        default=None,
        description="Desired condition of enemy forces at end state (the 'enemy' category per ADP 5-0).",
    )
    end_state_terrain: Optional[str] = Field(
        default=None,
        description="Desired condition of terrain at end state (the 'terrain' category per ADP 5-0).",
    )
    end_state_civil: Optional[str] = Field(
        default=None,
        description="Desired condition of civil considerations at end state (the 'civil' category per ADP 5-0).",
    )


class ConceptOfOperations(_Base):
    """Paragraph 3.b — Concept of Operations: how the commander visualizes the operation unfolding."""

    overview: Optional[str] = Field(
        default=None,
        description="High-level narrative of how the operation will unfold from start to end state.",
    )
    maneuver: Optional[str] = Field(
        default=None,
        description="Overall maneuver concept tying decisive, shaping, and sustaining operations together.",
    )
    decisive_operation: Optional[str] = Field(
        default=None,
        description="The operation that directly accomplishes the mission; the main effort at the decisive point per ADP 3-0.",
    )
    shaping_operations: Optional[str] = Field(
        default=None,
        description="Operations that create and preserve conditions for success of the decisive operation.",
    )
    sustaining_operations: Optional[str] = Field(
        default=None,
        description="Operations that enable the decisive and shaping operations by generating and maintaining combat power.",
    )
    reserve: Optional[str] = Field(
        default=None,
        description="Composition, location, priorities, and planned employment of the reserve.",
    )
    fires: Optional[str] = Field(
        default=None,
        description="High-level concept of fires in support of maneuver; detailed scheme appears in scheme_of_fires and Annex D.",
    )


class CCIR(_Base):
    """Commander's Critical Information Requirements: PIR and FFIR that drive decisions."""

    pir: list[str] = Field(
        default_factory=list,
        description="Priority Intelligence Requirements — information about the enemy, terrain, weather, or civil considerations the commander needs to make a decision.",
    )
    ffir: list[str] = Field(
        default_factory=list,
        description="Friendly Force Information Requirements — information about friendly forces the commander needs to make a decision.",
    )


class CoordinatingInstructions(_Base):
    """Paragraph 3.d — Coordinating Instructions: items applicable to two or more units."""

    effective_time: Optional[str] = Field(
        default=None,
        description="DTG at which the order becomes effective (often 'On receipt' or a specific DTG).",
    )
    ccir: Optional[CCIR] = Field(
        default=None,
        description="Commander's Critical Information Requirements (PIR and FFIR).",
    )
    eefi: list[str] = Field(
        default_factory=list,
        description="Essential Elements of Friendly Information — information about friendly forces that must be protected from adversary collection.",
    )
    fscm: Optional[str] = Field(
        default=None,
        description="Fire Support Coordination Measures (e.g. CFL, FSCL, RFA, NFA) in effect for the operation.",
    )
    acm: Optional[str] = Field(
        default=None,
        description="Airspace Coordinating Measures (e.g. ROZ, ACA, UA) in effect for the operation.",
    )
    roe: Optional[str] = Field(
        default=None,
        description="Rules of Engagement applicable to the operation; typically references a SROE/MROE annex or card.",
    )
    risk_reduction_control_measures: Optional[str] = Field(
        default=None,
        description="Control measures used to mitigate tactical and accidental risks identified in the risk assessment per ATP 5-19.",
    )
    personnel_recovery: Optional[str] = Field(
        default=None,
        description="Personnel Recovery (PR) guidance: isolated personnel reporting, authentication, and recovery procedures.",
    )
    environmental_considerations: Optional[str] = Field(
        default=None,
        description="Environmental protection measures and constraints per AR 200-1 that apply to this operation.",
    )
    themes_and_messages: list[str] = Field(
        default_factory=list,
        description="Approved themes and messages that subordinate units reinforce through word and deed.",
    )
    cema: Optional[str] = Field(
        default=None,
        description="Cyberspace Electromagnetic Activities (CEMA) coordinating instructions per FM 3-12.",
    )
    time_line: list[PlanningMilestone] = Field(
        default_factory=list,
        description="Paragraph 3.d Time Line per FM 6-0: sequenced planning and execution milestones (recon LD, confirmation brief, rehearsal, OPORD issue, LD).",
    )
    earliest_movement_of_forces: Optional[str] = Field(
        default=None,
        description="Earliest DTG at which subordinate units may begin movement; movement may precede full OPORD issue when authorized here.",
    )
    reconnaissance_and_surveillance_instructions: Optional[str] = Field(
        default=None,
        description="Reconnaissance and surveillance guidance per FM 3-98; typically references Annex L with summary here.",
    )
    orders_group: Optional[OrdersGroup] = Field(
        default=None,
        description="Commander's orders group meeting — purpose, DTG, location, attendees, products distributed.",
    )
    rehearsal: Optional[RehearsalPlan] = Field(
        default=None,
        description="Rehearsal plan per FM 6-0 Appendix F — type, DTG, location, participants, and method notes.",
    )
    other: Optional[str] = Field(
        default=None,
        description="Any additional coordinating instructions not captured by the named subfields.",
    )


class SubordinateTask(_Base):
    """Paragraph 3.c — tasks to a single subordinate unit, with purpose and priorities."""

    unit: str = Field(
        description="Designation of the subordinate unit receiving these tasks (e.g. 'A/1-508')."
    )
    callsign: Optional[str] = Field(
        default=None,
        description="Radio callsign used for the unit in the current SOI, if helpful to the subordinate.",
    )
    purpose: Optional[str] = Field(
        default=None,
        description="Purpose (the 'in order to') tying this unit's tasks to the higher mission and commander's intent.",
    )
    tasks: list[str] = Field(
        default_factory=list,
        description="Specified tasks assigned to this unit, each stated as who-what-when-where-why with a doctrinal tactical task verb.",
    )
    priorities: Optional[str] = Field(
        default=None,
        description="Priorities of effort and priorities of support for this unit during the operation.",
    )


class Execution(_Base):
    """Paragraph 3 — Execution: intent, concept, schemes by warfighting function, subordinate tasks, and coordinating instructions."""

    commanders_intent: Optional[CommandersIntent] = Field(
        default=None,
        description="Paragraph 3.a — Commander's Intent.",
    )
    concept_of_operations: Optional[ConceptOfOperations] = Field(
        default=None,
        description="Paragraph 3.b — Concept of Operations.",
    )
    scheme_of_movement_and_maneuver: Optional[str] = Field(
        default=None,
        description="Scheme of movement and maneuver — how forces move and maneuver to accomplish the mission.",
    )
    scheme_of_mobility_countermobility: Optional[str] = Field(
        default=None,
        description="Scheme of mobility and countermobility — breach, gap crossing, route clearance, and obstacle emplacement.",
    )
    scheme_of_battlefield_obscuration: Optional[str] = Field(
        default=None,
        description="Scheme of battlefield obscuration — employment of smoke and obscurants in support of maneuver.",
    )
    scheme_of_reconnaissance_and_security: Optional[str] = Field(
        default=None,
        description="Scheme of reconnaissance and security — R&S operations per FM 3-98 to answer PIR and protect the force.",
    )
    scheme_of_intelligence: Optional[str] = Field(
        default=None,
        description="Scheme of intelligence — intelligence support to operations; typically references Annex B.",
    )
    scheme_of_fires: Optional[str] = Field(
        default=None,
        description="Scheme of fires — lethal and nonlethal fires synchronized with maneuver; typically references Annex D.",
    )
    scheme_of_protection: Optional[str] = Field(
        default=None,
        description="Scheme of protection — protection tasks (AMD, survivability, OPSEC, PR, etc.); typically references Annex E.",
    )
    stability: Optional[str] = Field(
        default=None,
        description="Stability tasks per ADP 3-07 conducted during or after combat operations to consolidate gains.",
    )
    scheme_of_engineer_operations: Optional[str] = Field(
        default=None,
        description="Scheme of engineer operations — combat, general, and geospatial engineering; typically references Annex G.",
    )
    scheme_of_signal: Optional[str] = Field(
        default=None,
        description="Scheme of signal — communications architecture and PACE; typically references Annex H.",
    )
    scheme_of_information_collection: Optional[str] = Field(
        default=None,
        description="Scheme of information collection — tasking of collection assets to answer CCIR; typically references Annex L.",
    )
    scheme_of_sustainment: Optional[str] = Field(
        default=None,
        description="Scheme of sustainment — logistics, personnel services, and health services support; typically references Annex F.",
    )
    scheme_of_cema: Optional[str] = Field(
        default=None,
        description="Scheme of Cyberspace Electromagnetic Activities per FM 3-12; typically an appendix to Annex C.",
    )
    scheme_of_information_operations: Optional[str] = Field(
        default=None,
        description="Scheme of information operations — integration of information-related capabilities to affect adversary decision making.",
    )
    scheme_of_airspace_control: Optional[str] = Field(
        default=None,
        description="Scheme of airspace control — airspace management and deconfliction per ATP 3-52.1.",
    )
    scheme_of_military_deception: Optional[str] = Field(
        default=None,
        description="Scheme of military deception (MILDEC) per FM 3-13.4; usually published under restricted distribution.",
    )
    scheme_of_space_operations: Optional[str] = Field(
        default=None,
        description="Scheme of space operations — use of space-based capabilities; typically references Annex N.",
    )
    assessment: Optional[str] = Field(
        default=None,
        description="Assessment plan — MOEs, MOPs, and reporting requirements per ADP 5-0; typically references Annex M.",
    )
    tasks_to_subordinate_units: list[SubordinateTask] = Field(
        default_factory=list,
        description="Paragraph 3.c — specified tasks to each subordinate and supporting unit, one entry per unit.",
    )
    coordinating_instructions: Optional[CoordinatingInstructions] = Field(
        default=None,
        description="Paragraph 3.d — instructions applicable to two or more subordinate units.",
    )


# ---------------------------------------------------------------------------
# Paragraph 4 — Sustainment
# ---------------------------------------------------------------------------
class Logistics(_Base):
    """Paragraph 4.a — Logistics: the ten logistics functions per ADP 4-0."""

    sustainment_overlay: Optional[str] = Field(
        default=None,
        description="Reference to the sustainment overlay/graphic depicting LRPs, MSRs/ASRs, and sustainment nodes.",
    )
    maintenance: Optional[str] = Field(
        default=None,
        description="Maintenance concept: priorities of maintenance, evacuation, and recovery per ATP 4-33.",
    )
    transportation: Optional[str] = Field(
        default=None,
        description="Transportation concept: MSRs/ASRs, movement control, and mode selection.",
    )
    supply: Optional[str] = Field(
        default=None,
        description="Supply concept by class (I–X), including CL V basic loads and CL III(B) planning figures.",
    )
    field_services: Optional[str] = Field(
        default=None,
        description="Field services: shower/laundry, food service, mortuary affairs, aerial delivery, billeting, and water purification.",
    )
    distribution: Optional[str] = Field(
        default=None,
        description="Distribution concept: throughput, LRPs, convoy operations, and distribution priorities.",
    )
    contract_support: Optional[str] = Field(
        default=None,
        description="Operational contract support (OCS) per ATP 4-10: contracted capabilities supporting the operation.",
    )
    general_engineering_support: Optional[str] = Field(
        default=None,
        description="General engineering support to sustainment: base camp construction, horizontal/vertical construction, and real estate.",
    )


class PersonnelServices(_Base):
    """Paragraph 4.b — Personnel Services: HR, finance, legal, religious, and band support."""

    human_resources_support: Optional[str] = Field(
        default=None,
        description="Human resources support per FM 1-0: PAT, postal, casualty, personnel accountability, and strength reporting.",
    )
    financial_management: Optional[str] = Field(
        default=None,
        description="Financial management support per FM 1-06: funding, disbursing, and resource management.",
    )
    legal_support: Optional[str] = Field(
        default=None,
        description="Legal support per FM 1-04: LOAC/ROE advice, claims, military justice, and detainee operations.",
    )
    religious_support: Optional[str] = Field(
        default=None,
        description="Religious support per FM 1-05: unit ministry team coverage, worship, counseling, and memorial services.",
    )
    band_support: Optional[str] = Field(
        default=None,
        description="Army band support to ceremonies, morale, and community relations activities.",
    )


class HealthServices(_Base):
    """Army Health System (AHS) support."""

    medical_command_and_control: Optional[str] = Field(
        default=None,
        description="Medical command and control: medical chain of command, MEDCOM relationships, and supporting medical HQ.",
    )
    medical_treatment: Optional[str] = Field(
        default=None,
        description="Medical treatment: Role 1–4 care locations, BAS and FSMT positioning, and surgical capability.",
    )
    medical_evacuation: Optional[str] = Field(
        default=None,
        description="Medical evacuation (MEDEVAC/CASEVAC) plan: MEDEVAC requests, AXPs, dust-off, and ground ambulance routes.",
    )
    dental_services: Optional[str] = Field(
        default=None,
        description="Dental services: emergency dental care and dental readiness during the operation.",
    )
    preventive_medicine: Optional[str] = Field(
        default=None,
        description="Preventive medicine: DNBI mitigation, field sanitation, vector control, and water/food surveillance.",
    )
    combat_operational_stress_control: Optional[str] = Field(
        default=None,
        description="Combat and operational stress control (COSC) per ATP 4-02.8: prevention, triage, and restoration.",
    )
    veterinary_services: Optional[str] = Field(
        default=None,
        description="Veterinary services: MWD care and food safety/defense inspections.",
    )
    medical_logistics: Optional[str] = Field(
        default=None,
        description="Medical logistics (MEDLOG) per ATP 4-02.1: CL VIII resupply, blood products, and medical equipment maintenance.",
    )
    medical_laboratory_services: Optional[str] = Field(
        default=None,
        description="Medical laboratory services supporting diagnostics, health surveillance, and CBRN health threats.",
    )
    area_medical_support: Optional[str] = Field(
        default=None,
        description="Area medical support: which medical units provide coverage to units without organic medical capability.",
    )


class Sustainment(_Base):
    """Paragraph 4 — Sustainment: logistics, personnel services, and health services support."""

    logistics: Optional[Logistics] = Field(
        default=None,
        description="Paragraph 4.a — Logistics.",
    )
    personnel_services: Optional[PersonnelServices] = Field(
        default=None,
        description="Paragraph 4.b — Personnel Services Support.",
    )
    health_services: Optional[HealthServices] = Field(
        default=None,
        description="Paragraph 4.c — Army Health System Support.",
    )


# ---------------------------------------------------------------------------
# Paragraph 5 — Command and Signal
# ---------------------------------------------------------------------------
class Command(_Base):
    """Paragraph 5.a — Command: location of commander, succession, and command posts."""

    location_of_commander: Optional[str] = Field(
        default=None,
        description="Location of the commander by phase (e.g. 'With main effort during actions on the objective').",
    )
    succession_of_command: list[str] = Field(
        default_factory=list,
        description="Ordered list of officers who assume command if the commander becomes a casualty.",
    )
    command_posts: Optional[str] = Field(
        default=None,
        description="Locations and displacement plan for main, tactical, and rear command posts.",
    )


class Control(_Base):
    """Paragraph 5.b — Control: command and support relationships and liaison requirements."""

    command_and_support_relationships: Optional[str] = Field(
        default=None,
        description="Command (OPCON/TACON/assigned/attached) and support (DS/GS/GSR/R) relationships per FM 3-0.",
    )
    liaison_requirements: Optional[str] = Field(
        default=None,
        description="Liaison officer (LNO) requirements: who sends LNOs to whom, when, and with what capabilities.",
    )


class Signal(_Base):
    """Paragraph 5.c — Signal: SOI, comms methods, recognition/identification, and CEMA."""

    soi_edition: Optional[str] = Field(
        default=None,
        description="Signal Operating Instructions (SOI) edition in effect for the operation.",
    )
    methods_of_communication_by_echelon: Optional[str] = Field(
        default=None,
        description="Communications methods by echelon and their PACE plan (primary/alternate/contingency/emergency).",
    )
    recognition_and_identification: Optional[str] = Field(
        default=None,
        description="Recognition and identification signals: near/far recognition, challenge/password, running password, and IFF.",
    )
    cema: Optional[str] = Field(
        default=None,
        description="CEMA considerations affecting signal: EW posture, spectrum management, and cyberspace defense.",
    )


class CommandAndSignal(_Base):
    """Paragraph 5 — Command and Signal."""

    command: Optional[Command] = Field(
        default=None,
        description="Paragraph 5.a — Command.",
    )
    control: Optional[Control] = Field(
        default=None,
        description="Paragraph 5.b — Control.",
    )
    signal: Optional[Signal] = Field(
        default=None,
        description="Paragraph 5.c — Signal.",
    )


# ---------------------------------------------------------------------------
# Annex-supporting structures (call signs, frequency plans)
# ---------------------------------------------------------------------------
class CallSignEntry(_Base):
    """A single unit-to-callsign mapping in a signal roster."""

    unit: str = Field(
        description="Unit or element designation (e.g. '2-14 IN', 'VFA-81', 'CJTF-LR Commander')."
    )
    callsign: str = Field(
        description="One or more tactical callsigns for this unit, comma-separated if multiple (e.g. 'HAVOC' or 'SUNDIAL, SOL, INFERNO, LINER')."
    )


class CallSignGroup(_Base):
    """A categorized group of unit-to-callsign assignments, typically one group per echelon or component."""

    category: str = Field(
        description="Category heading for the group (e.g. 'U.S. Army – 3/10 BCT (10th Mountain Division)', 'Naval Air Wing (CVW-1)', 'Command and Control (C2)')."
    )
    entries: list[CallSignEntry] = Field(
        default_factory=list,
        description="Ordered list of unit-callsign pairs belonging to this category.",
    )


class FrequencyChannel(_Base):
    """A single channel row in a radio ladder or frequency plan."""

    name: str = Field(
        description="Channel name or net callsign (e.g. 'CASINO', 'CCA TWR', 'BN CMD')."
    )
    channel: str = Field(
        description="Radio preset channel number (e.g. '01', '14', or 'HF-A')."
    )
    frequency: str = Field(
        description="Frequency assignment including band (e.g. '241.000 MHz', 'HOPSET 07')."
    )
    purpose: str = Field(
        description="What the channel is used for and which unit or function owns it."
    )


class FrequencyTable(_Base):
    """A radio ladder or frequency plan for a specific platform, site, or band."""

    title: str = Field(
        description="Primary title of the table (e.g. 'UHF (Uniform) Radio', 'Naval Aviation Radio Ladder', 'Battalion Internal Nets')."
    )
    sub_title: Optional[str] = Field(
        default=None,
        description="Optional scope qualifier (e.g. 'Muwwafaq Salti AB (OJMS)', 'Incirlik AB (LTAG)', 'SINCGARS hopsets').",
    )
    channels: list[FrequencyChannel] = Field(
        default_factory=list,
        description="Ordered list of channels in the ladder.",
    )


# ---------------------------------------------------------------------------
# Annexes
# ---------------------------------------------------------------------------
class Appendix(_Base):
    """A numbered appendix beneath an annex."""

    number: int = Field(
        description="Appendix number within the parent annex (1, 2, 3, ...)."
    )
    title: str = Field(
        description="Appendix title (e.g. 'Intelligence Estimate', 'Target List Worksheet')."
    )
    body: Optional[str] = Field(
        default=None,
        description="Appendix content. If omitted the appendix is listed in the annex's contents without an inline body.",
    )
    distribution_list: list[str] = Field(
        default_factory=list,
        description="Per-appendix distribution list (recipient organizations), used when this appendix carries a narrower audience than the parent annex.",
    )
    frequency_tables: list[FrequencyTable] = Field(
        default_factory=list,
        description="Radio ladders / frequency plans carried in this appendix. Most commonly used under Annex H, Appendix 1 (Communications Plan).",
    )


class Annex(_Base):
    """An OPORD annex identified by a canonical A–Z letter per FM 6-0 / ATP 5-0.2-1."""

    letter: Annotated[str, Field(
        min_length=1,
        max_length=1,
        pattern=r"^[A-Z]$",
        description="Single uppercase letter A–Z identifying the annex; reserved letters (I, O, T, W, X, Y) are only valid with status 'not_used'.",
    )]
    title: Optional[str] = Field(
        default=None,
        description="Annex title; if omitted, the validator fills in the canonical title from FM 6-0 (e.g. 'Task Organization' for Annex A).",
    )
    status: AnnexStatus = Field(
        default=AnnexStatus.PUBLISHED,
        description=(
            "Computed automatically from content and letter. Derived as: "
            "'not_used' for reserved letters (I, O, T, W, X, Y); "
            "'published' when the annex has body/appendices/distribution list/callsigns; "
            "'omitted' when the annex is listed but carries no content. "
            "Setting this field manually is allowed but usually unnecessary."
        ),
    )
    body: Optional[str] = Field(
        default=None,
        description="Annex content. Omit when the annex is published separately or when status is 'omitted'/'not_used'.",
    )
    appendices: list[Appendix] = Field(
        default_factory=list,
        description="Ordered list of appendices beneath this annex.",
    )
    distribution_list: list[str] = Field(
        default_factory=list,
        description="Per-annex distribution list (recipient organizations). Overrides or supplements the order-level distribution when this annex has a narrower audience (e.g. Annex H restricted to comms-cleared units).",
    )
    call_sign_groups: list[CallSignGroup] = Field(
        default_factory=list,
        description="Structured callsign roster grouped by category (component, echelon, or functional area). Typically populated under Annex H (Signal) and referenced by subordinate annexes.",
    )
    typed_body: Optional["AnnexTypedBody"] = Field(
        default=None,
        description="Optional structured-content layer with annex-specific doctrinal fields. Discriminated by annex letter; reserved letters (I, O, T, W, X, Y) must leave this None.",
    )

    @model_validator(mode="after")
    def _resolve_status_and_title(self) -> "Annex":
        # _Base sets str_strip_whitespace=True, so self.body is already stripped.
        has_any_content = (
            bool(self.body)
            or bool(self.appendices)
            or bool(self.distribution_list)
            or bool(self.call_sign_groups)
            or self.typed_body is not None
        )
        if self.letter in RESERVED_LETTERS:
            # Reserved letters are always NOT_USED and may carry no content.
            if has_any_content:
                raise ValueError(
                    f"Annex letter '{self.letter}' is reserved (I, O, T, W, X, Y) and "
                    f"cannot carry content; remove the body/appendices or pick a valid letter."
                )
            self.status = AnnexStatus.NOT_USED
            if not self.title:
                self.title = "Not Used"
            return self
        # If a typed_body is provided, its discriminator letter must match the annex letter.
        if self.typed_body is not None and getattr(self.typed_body, "letter", None) != self.letter:
            raise ValueError(
                f"typed_body.letter ({getattr(self.typed_body, 'letter', None)!r}) "
                f"does not match annex letter ({self.letter!r})."
            )
        # Non-reserved letters: status is derived from content.
        self.status = AnnexStatus.PUBLISHED if has_any_content else AnnexStatus.OMITTED
        if not self.title:
            self.title = CANONICAL_ANNEXES.get(self.letter, "")
        return self

    @property
    def is_published(self) -> bool:
        return self.status == AnnexStatus.PUBLISHED


# ---------------------------------------------------------------------------
# Authentication / footer
# ---------------------------------------------------------------------------
class Authentication(_Base):
    """OPORD authentication block: acknowledgement, signature, authenticator, and distribution."""

    acknowledge: bool = Field(
        default=True,
        description="Whether subordinates must acknowledge receipt of the order; defaults to True per FM 6-0.",
    )
    commander_last_name: Optional[str] = Field(
        default=None,
        description="Last name of the signing commander as it appears in the signature block.",
    )
    commander_rank: Optional[str] = Field(
        default=None,
        description="Rank of the signing commander (e.g. 'LTC', 'COL').",
    )
    authenticating_officer_name: Optional[str] = Field(
        default=None,
        description="Name of the officer authenticating the order (typically the XO or S-3) when the commander does not sign personally.",
    )
    authenticating_officer_position: Optional[str] = Field(
        default=None,
        description="Duty position of the authenticating officer (e.g. 'S-3', 'Executive Officer').",
    )
    distribution: Optional[str] = Field(
        default=None,
        description="Distribution statement or reference to the distribution annex (typically Annex Z).",
    )


# ---------------------------------------------------------------------------
# Top-level OPORD
# ---------------------------------------------------------------------------
class OPORD(_Base):
    """U.S. Army Operations Order (OPORD). Full 5-paragraph format per FM 6-0 (May 2022) Appendix D / ATP 5-0.2-1."""

    header: Header = Field(
        description="OPORD header block with classification, issuing HQ, DTG, references, and task organization."
    )
    situation: Optional[Situation] = Field(
        default=None,
        description="Paragraph 1 — Situation.",
    )
    mission: str = Field(
        description="Paragraph 2 — Mission statement: a single sentence answering who, what (task), when, where, and why (purpose)."
    )
    execution: Optional[Execution] = Field(
        default=None,
        description="Paragraph 3 — Execution.",
    )
    sustainment: Optional[Sustainment] = Field(
        default=None,
        description="Paragraph 4 — Sustainment.",
    )
    command_and_signal: Optional[CommandAndSignal] = Field(
        default=None,
        description="Paragraph 5 — Command and Signal.",
    )
    annexes: list[Annex] = Field(
        default_factory=list,
        description="Ordered list of annexes attached to this order; gaps are filled canonically by annex_directory().",
    )
    authentication: Optional[Authentication] = Field(
        default=None,
        description="Authentication block including acknowledgement flag, signature, and distribution.",
    )
    kneeboards: list["KneeboardCard"] = Field(
        default_factory=list,
        description="Kneeboard cards for DCS World or print export. Each card renders as a 768×1024 PNG.",
    )

    def annex_directory(self) -> list[Annex]:
        """Return the full A–Z directory, filling gaps with canonical
        not-used or omitted entries so the renderer can display the
        complete list without the author having to spell out reserved
        letters."""
        provided = {a.letter: a for a in self.annexes}
        out: list[Annex] = []
        for letter, canonical_title in CANONICAL_ANNEXES.items():
            if letter in provided:
                out.append(provided[letter])
            elif letter in RESERVED_LETTERS:
                out.append(Annex(letter=letter, title="Not Used", status=AnnexStatus.NOT_USED))
            else:
                out.append(Annex(letter=letter, title=canonical_title, status=AnnexStatus.OMITTED))
        return out


Unit.model_rebuild()


# ---------------------------------------------------------------------------
# FRAGO — Fragmentary Order
# ---------------------------------------------------------------------------
class FRAGO(_Base):
    """A Fragmentary Order (FRAGO) modifying a previously issued OPORD.

    A FRAGO is a sparse delta: only paragraphs that have actually changed are
    populated. Everything else is implicitly "No change from base order" and
    the renderer emits that stub automatically. Annexes listed here REPLACE
    the corresponding annex in the base order; annexes not listed are
    inherited unchanged.

    ``base_order`` is a filesystem path (relative to this FRAGO YAML) pointing
    at the parent OPORD this FRAGO modifies — the renderer loads both and
    produces a single FRAGO document that reads as a delta against the base."""

    kind: Literal["frago"] = Field(
        default="frago",
        description="Document-kind discriminator. Must be 'frago' for the loader to route this file as a FRAGO rather than an OPORD.",
    )
    frago_number: str = Field(
        description="Sequence number of this FRAGO within the base OPORD (e.g. '01', '02'). Increments per published FRAGO."
    )
    base_order: str = Field(
        description="Relative filesystem path (from this FRAGO YAML) to the base OPORD file this FRAGO modifies."
    )
    previous_fragos: list[str] = Field(
        default_factory=list,
        description="References to prior FRAGOs in sequence (e.g. 'FRAGO 01, 181800ZAPR26') so readers can reconstruct the modification chain."
    )
    classification: Optional[ClassificationLevel] = Field(
        default=None,
        description="Overall classification marking for this FRAGO. Omit to inherit from the base OPORD; override only when the FRAGO itself has a different classification than its base.",
    )
    classification_caveat: Optional[str] = Field(
        default=None,
        description="Dissemination caveat appended to the classification line. Omit to inherit from base."
    )
    issuing_headquarters: Optional[str] = Field(
        default=None,
        description="HQ publishing this FRAGO. Omit to inherit from the base OPORD."
    )
    place_of_issue: Optional[str] = Field(
        default=None,
        description="Location where the FRAGO is issued. Omit to inherit from the base OPORD."
    )
    dtg: str = Field(
        description="DTG the FRAGO is signed (DDHHMMZMONYY). Required — FRAGO always has its own issue DTG distinct from the base."
    )
    time_zone: Optional[str] = Field(
        default=None,
        description="Time-zone suffix used throughout the FRAGO. Omit to inherit from the base OPORD."
    )
    copy_number: Optional[int] = Field(default=None)
    number_of_copies: Optional[int] = Field(default=None)
    author: Optional[str] = Field(
        default=None,
        description="Drafting officer or staff section."
    )
    situation: Optional[Situation] = Field(
        default=None,
        description="Paragraph 1 — Situation changes. Populate only fields that changed from the base order."
    )
    mission: Optional[str] = Field(
        default=None,
        description="Paragraph 2 — New mission statement if the mission changed. Omit for no change."
    )
    execution: Optional[Execution] = Field(
        default=None,
        description="Paragraph 3 — Execution changes. Populate only fields that changed."
    )
    sustainment: Optional[Sustainment] = Field(
        default=None,
        description="Paragraph 4 — Sustainment changes."
    )
    command_and_signal: Optional[CommandAndSignal] = Field(
        default=None,
        description="Paragraph 5 — Command and Signal changes."
    )
    annexes: list[Annex] = Field(
        default_factory=list,
        description="Annex modifications — each entry REPLACES the corresponding annex in the base order. Annexes not listed here are inherited unchanged."
    )
    authentication: Optional[Authentication] = Field(
        default=None,
        description="Authentication block. If omitted, the base order's authentication carries forward."
    )
    kneeboards: list["KneeboardCard"] = Field(
        default_factory=list,
        description="Kneeboard cards specific to this FRAGO. Rendered as 768×1024 PNG for DCS World or print.",
    )

    @property
    def sequence_number(self) -> str:
        return self.frago_number


# ---------------------------------------------------------------------------
# WARNO — Warning Order
# ---------------------------------------------------------------------------
class WARNO(_Base):
    """A Warning Order (WARNO) issued to trigger parallel planning before the
    full OPORD is available per FM 6-0 (May 2022) / ATP 5-0.2-1.

    A WARNO is preliminary: sections not yet decided are marked "To be
    published" (TBP) and the renderer emits that stub automatically — in
    contrast to a FRAGO, where unset sections mean "No change from base".

    ``base_order`` is OPTIONAL. When present (higher HQ's order already
    exists) the WARNO inherits header fields and exposes the base model +
    variables for interpolation, exactly like a FRAGO. When absent, the
    WARNO stands alone and must supply its own header fields."""

    kind: Literal["warno"] = Field(
        default="warno",
        description="Document-kind discriminator. Must be 'warno' for the loader to route this file as a WARNO rather than an OPORD/FRAGO.",
    )
    warno_number: str = Field(
        description="Sequence number of this WARNO within the planning effort (e.g. '01', '02'). Increments per published WARNO."
    )
    base_order: Optional[str] = Field(
        default=None,
        description="Optional relative filesystem path (from this WARNO YAML) to a higher-HQ OPORD whose context and variables should pull through. Omit for a standalone WARNO issued before any base order exists.",
    )
    previous_warnos: list[str] = Field(
        default_factory=list,
        description="References to prior WARNOs in sequence (e.g. 'WARNO 01, 171200ZAPR26') so readers can reconstruct the planning chain."
    )
    classification: Optional[ClassificationLevel] = Field(
        default=None,
        description="Overall classification marking for this WARNO. Required when standalone; omit to inherit from the base OPORD when ``base_order`` is set.",
    )
    classification_caveat: Optional[str] = Field(
        default=None,
        description="Dissemination caveat appended to the classification line. Omit to inherit from base when available."
    )
    issuing_headquarters: Optional[str] = Field(
        default=None,
        description="HQ publishing this WARNO. Required when standalone; omit to inherit from the base OPORD."
    )
    place_of_issue: Optional[str] = Field(
        default=None,
        description="Location where the WARNO is issued. Required when standalone; omit to inherit from the base OPORD."
    )
    dtg: str = Field(
        description="DTG the WARNO is signed (DDHHMMZMONYY). Required — a WARNO always has its own issue DTG."
    )
    time_zone: Optional[str] = Field(
        default=None,
        description="Time-zone suffix used throughout the WARNO. Required when standalone; omit to inherit from the base OPORD."
    )
    copy_number: Optional[int] = Field(default=None)
    number_of_copies: Optional[int] = Field(default=None)
    author: Optional[str] = Field(
        default=None,
        description="Drafting officer or staff section."
    )
    operation_name: Optional[str] = Field(
        default=None,
        description="Nickname or codeword for the operation. Required when standalone; omit to inherit from the base OPORD."
    )
    operation_order_number: Optional[str] = Field(
        default=None,
        description="Associated OPORD number (typically fiscal year + sequence). Omit to inherit from the base OPORD when set."
    )
    logo: Optional[str] = Field(
        default=None,
        description="Path or URL to a unit crest for the WARNO cover. Omit to inherit from the base OPORD when set."
    )
    page_icon: Optional[str] = Field(
        default=None,
        description="Path or URL to a small page-header icon. Omit to inherit from the base OPORD when set."
    )
    watermark: Optional[str] = Field(
        default=None,
        description="Optional page watermark (text or image). Omit to inherit from the base OPORD when set."
    )
    situation: Optional[Situation] = Field(
        default=None,
        description="Paragraph 1 — Abbreviated situation as currently understood. Omit to render 'To be published' stub."
    )
    mission: Optional[str] = Field(
        default=None,
        description="Paragraph 2 — Provisional mission statement if known. Omit to render 'To be published' stub."
    )
    execution: Optional[Execution] = Field(
        default=None,
        description="Paragraph 3 — Execution intent, concept, and subordinate tasks known at WARNO time. Populate only what has been decided."
    )
    sustainment: Optional[Sustainment] = Field(
        default=None,
        description="Paragraph 4 — Sustainment guidance. Omit to render 'To be published' stub."
    )
    command_and_signal: Optional[CommandAndSignal] = Field(
        default=None,
        description="Paragraph 5 — Command and Signal. Omit to render 'To be published' stub."
    )
    annexes: list[Annex] = Field(
        default_factory=list,
        description="Annexes published with this WARNO (typically just Annex A Task Organization if known). Most WARNOs leave this empty."
    )
    authentication: Optional[Authentication] = Field(
        default=None,
        description="Authentication block. If omitted and a base order is referenced, the base's authentication carries forward; otherwise this field is required for a formally authenticated WARNO."
    )
    kneeboards: list["KneeboardCard"] = Field(
        default_factory=list,
        description="Kneeboard cards for DCS World or print export. Each card renders as a 768×1024 PNG.",
    )

    @property
    def sequence_number(self) -> str:
        return self.warno_number
