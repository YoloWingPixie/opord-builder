"""Per-annex typed-body models.

Each ``Annex{Letter}Data`` model carries the doctrine-true structured fields
for one OPORD annex (A, B, C, D, E, F, G, H, J, K, L, M, N, P, Q, R, S, U, V, Z).
The discriminated union :data:`AnnexTypedBody` is attached to
:class:`opord_builder.schema.core.Annex` via the optional ``typed_body`` field,
so authors can layer doctrine-true structured content alongside the existing
free-text ``body`` / ``appendices`` without breaking older YAML.

Scope: these models capture the HIGHEST-VALUE structured fields per the research
inventory (see ``/tmp/opord-research/INDEX.md``). Full per-appendix coverage
remains the province of the free-text ``body`` and ``appendices`` fields on
:class:`Annex`.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Union

from pydantic import ConfigDict, Field

from opord_builder.schema._base import _Base
from opord_builder.schema.core import Unit
from opord_builder.schema.shared import (
    ACM,
    ASRoute,
    AirspaceControl,
    AmbulanceExchangePoint,
    BattleRhythmEvent,
    CDEGuidance,
    ControlMeasure,
    DTGString,
    DecisionPoint,
    EnemyCOA,
    FSCM,
    HVT,
    JPITLEntry,
    LogisticsSchedule,
    MGRSGrid,
    MSRoute,
    NamedAreaOfInterest,
    NineLineCAS,
    PIR,
    ReportDefinition,
    RoleOfCare,
    TSTEntry,
)


def _annex_config(letter: str, title: str) -> ConfigDict:
    """Build a per-annex ConfigDict with human-readable JSON-Schema title + metadata."""
    return ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        title=f"Annex {letter} — {title}",
        json_schema_extra={"annex_letter": letter, "doctrinal_title": title},
    )


def _letter_field(letter: str) -> Any:
    """Factory for the per-annex `letter` discriminator Field. The `Literal[...]`
    annotation must still be declared per-class (Pydantic discriminated unions
    don't resolve through inheritance) — this just collapses the boilerplate."""
    return Field(description=f"Discriminator — always '{letter}' for Annex {letter}.")


# ---------------------------------------------------------------------------
# Annex A — Task Organization
# ---------------------------------------------------------------------------
class StrengthRollup(_Base):
    """Unit strength rollup snapshot tied to an as-of DTG."""

    assigned: int = Field(
        description="Assigned strength (personnel authorized on the MTOE/TDA)."
    )
    attached_in: int = Field(
        description="Personnel attached IN from other organizations for this operation."
    )
    detached_out: int = Field(
        description="Personnel detached OUT to other organizations for this operation."
    )
    effective: int = Field(
        description="Effective strength available for this operation (= assigned + attached_in − detached_out − losses)."
    )
    effective_as_of: DTGString = Field(
        description="As-of DTG for the effective-strength figure."
    )


class CrossAttachment(_Base):
    """A single cross-attachment or detachment entry used in Annex A."""

    unit: str = Field(
        description="Designation of the attaching/detaching unit (e.g. 'B/2-14 IN')."
    )
    relationship: Literal[
        "OPCON",
        "TACON",
        "ADCON",
        "assigned",
        "attached",
        "DS",
        "GS",
        "GSR",
        "R",
    ] = Field(
        description="Command or support relationship per FM 3-0."
    )
    direction: Literal["attached_in", "detached_out"] = Field(
        description="Whether the unit is flowing IN to this HQ or OUT to another HQ."
    )
    parent_or_gaining_unit: str = Field(
        description="Parent unit (for attachments IN) or gaining unit (for detachments OUT)."
    )
    effective_dtg: Optional[DTGString] = Field(
        default=None,
        description="DTG the relationship becomes effective; omit if effective on receipt."
    )
    termination_dtg: Optional[DTGString] = Field(
        default=None,
        description="DTG the relationship terminates; omit for duration of operation."
    )


class AnnexAData(_Base):
    """Structured body for Annex A (Task Organization)."""

    model_config = _annex_config("A", "Task Organization")

    letter: Literal["A"] = _letter_field("A")
    task_organization_list: list[Unit] = Field(
        default_factory=list,
        description="Ordered task-organization tree(s). Each root Unit expands recursively through subordinate_units."
    )
    cross_attachments: list[CrossAttachment] = Field(
        default_factory=list,
        description="Explicit cross-attachment and detachment entries with relationship and effective DTG."
    )
    strength_rollup: Optional[StrengthRollup] = Field(
        default=None,
        description="Unit strength rollup snapshot (assigned/attached/detached/effective with as-of DTG)."
    )


# ---------------------------------------------------------------------------
# Annex B — Intelligence
# ---------------------------------------------------------------------------
class AnnexBData(_Base):
    """Structured body for Annex B (Intelligence)."""

    model_config = _annex_config("B", "Intelligence")

    letter: Literal["B"] = _letter_field("B")
    priority_intelligence_requirements: list[PIR] = Field(
        default_factory=list,
        description="Commander-approved PIR list with NAI coverage, LTIOV, and indicators."
    )
    high_value_target_list: list[HVT] = Field(
        default_factory=list,
        description="High-Value Target List (HVTL); entries with hpt_nomination=True are also on the HPTL."
    )
    enemy_courses_of_action: list[EnemyCOA] = Field(
        default_factory=list,
        description="Enemy COAs from IPB step 4 (MLCOA, MDCOA, and additional analytic COAs)."
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Intelligence planning assumptions (valid, necessary, likely true) per ADP 5-0."
    )


# ---------------------------------------------------------------------------
# Annex C — Operations
# ---------------------------------------------------------------------------
class OperationPhase(_Base):
    """A single phase of the operation with start/end conditions and key tasks."""

    phase_number: int = Field(
        description="Sequential phase number (1-based)."
    )
    phase_name: str = Field(
        description="Phase name (e.g. 'Shaping', 'Decisive Action', 'Consolidation')."
    )
    purpose: str = Field(
        description="Purpose of the phase — what the force achieves in this phase."
    )
    start_condition: str = Field(
        description="Condition or event that starts the phase."
    )
    end_condition: str = Field(
        description="Condition or event that ends the phase and triggers transition to the next phase."
    )
    main_effort: str = Field(
        description="Designated main effort for the phase."
    )
    key_tasks: list[str] = Field(
        default_factory=list,
        description="Key tasks the force must accomplish during this phase."
    )


class EndState(_Base):
    """Commander's end state broken out into the four ADP 5-0 categories."""

    friendly: str = Field(
        description="Desired condition of friendly forces at end state."
    )
    enemy: str = Field(
        description="Desired condition of enemy forces at end state."
    )
    terrain: str = Field(
        description="Desired condition of terrain at end state."
    )
    civil: str = Field(
        description="Desired condition of civil considerations at end state."
    )


class AnnexCData(_Base):
    """Structured body for Annex C (Operations)."""

    model_config = _annex_config("C", "Operations")

    letter: Literal["C"] = _letter_field("C")
    phases: list[OperationPhase] = Field(
        default_factory=list,
        description="Ordered phases of the operation."
    )
    decision_points: list[DecisionPoint] = Field(
        default_factory=list,
        description="Decision points on the Decision Support Matrix."
    )
    control_measures: list[ControlMeasure] = Field(
        default_factory=list,
        description="Maneuver control measures (PL, OBJ, BP, AA, LD, LOA, DZ/LZ/PZ, NAI/TAI, CP, TRP)."
    )
    end_state: Optional[EndState] = Field(
        default=None,
        description="Commander's end state (friendly, enemy, terrain, civil)."
    )
    airspace_control: Optional[AirspaceControl] = Field(
        default=None,
        description="Stable airspace architecture — geo refs (bullseyes, IPs, CPs, anchors), airspace zones (ROZ/HIDACZ/MEZ/FEZ/JEZ/NFZ/SAR/Safe), CAP tracks, AAR tracks, AWACS orbits, AIC sectors, and ingress corridors. FRAGOs reference these published elements by name when tasking specific sorties."
    )


# ---------------------------------------------------------------------------
# Annex D — Fires
# ---------------------------------------------------------------------------
class PriorityOfFiresEntry(_Base):
    """Priority-of-fires assignment for a single phase."""

    phase: str = Field(
        description="Phase name or number to which this priority applies."
    )
    primary: str = Field(
        description="Unit holding the primary priority of fires during the phase."
    )
    secondary: Optional[str] = Field(
        default=None,
        description="Unit holding the secondary priority of fires during the phase."
    )
    on_order: Optional[str] = Field(
        default=None,
        description="Unit assigned on-order priority of fires during the phase."
    )


class AttackGuidanceEntry(_Base):
    """A row of the Attack Guidance Matrix (AGM) per ATP 3-60."""

    hpt_reference: str = Field(
        description="HPT reference (priority rank or descriptor) this row applies to."
    )
    when: Literal["Immediate", "As Acquired", "Planned"] = Field(
        description="When the HPT is to be engaged relative to acquisition."
    )
    how: str = Field(
        description="Delivery system and method (e.g. 'DIVARTY MLRS', 'CAS 2xGBU-38')."
    )
    effect: Literal["Destroy", "Neutralize", "Suppress", "Harass"] = Field(
        description="Desired target effect per ATP 3-60."
    )
    restrictions: Optional[str] = Field(
        default=None,
        description="Collateral-damage, ROE, or coordination restrictions on engagement."
    )


class CASRequest(_Base):
    """A Close Air Support mission request entry."""

    mission_number: str = Field(
        description="CAS mission number issued by the ASOC/ATO."
    )
    callsign: str = Field(
        description="Flight callsign of the aircraft executing the mission."
    )
    alert_status: str = Field(
        description="Alert status (e.g. 'Ground Alert 15', 'Airborne 30 NM')."
    )
    ordnance: Optional[str] = Field(
        default=None,
        description="Loadout summary (e.g. '2x GBU-38, 2x AIM-120, 1x 20mm')."
    )
    tot_window: Optional[str] = Field(
        default=None,
        description="Time-on-Target window (e.g. '181430Z-181445ZAPR26')."
    )
    control_agency: str = Field(
        description="Controlling agency (e.g. 'DASC', 'JTAC KILO 11')."
    )


class AnnexDData(_Base):
    """Structured body for Annex D (Fires)."""

    model_config = _annex_config("D", "Fires")

    letter: Literal["D"] = _letter_field("D")
    priority_of_fires_by_phase: list[PriorityOfFiresEntry] = Field(
        default_factory=list,
        description="Priority of fires assigned by phase."
    )
    fire_support_coordination_measures: list[FSCM] = Field(
        default_factory=list,
        description="Fire Support Coordination Measures in effect for the operation."
    )
    high_payoff_target_list: list[HVT] = Field(
        default_factory=list,
        description="HPTL — HVTs whose engagement is most critical to mission success."
    )
    attack_guidance_matrix: list[AttackGuidanceEntry] = Field(
        default_factory=list,
        description="Attack Guidance Matrix rows tying HPTs to when/how/effect/restrictions."
    )
    close_air_support_requests: list[CASRequest] = Field(
        default_factory=list,
        description="Preplanned CAS mission requests."
    )
    jpitl: list[JPITLEntry] = Field(
        default_factory=list,
        description="Joint Prioritized Integrated Target List per JP 3-60 / ATP 3-60 — JFC-approved, prioritized, component-integrated target roster with approval state and engagement guidance per target."
    )
    time_sensitive_targets: list[TSTEntry] = Field(
        default_factory=list,
        description="Time-Sensitive Target list per JP 3-60 — targets with compressed F2T2EA timeline and component-level engagement authority."
    )
    cas_nine_lines: list[NineLineCAS] = Field(
        default_factory=list,
        description="9-Line CAS briefs per JP 3-09.3 / AFTTP 3-2.6 — doctrinal tactical-control briefs (IP → heading → distance → elevation → description → location → mark → friendlies → egress) passed from JTAC/FAC(A) to CAS aircraft. Distinct from the preplanned CAS mission requests above."
    )
    cde_guidance: Optional[CDEGuidance] = Field(
        default=None,
        description="Collateral Damage Estimation guidance per CJCSI 3160.01 — CDE level definitions (CDE-1 through CDE-5), engagement authorities, weaponeering methodology, LOAC review authority, and NSL/RTL references. Referenced by every target on the JPITL, TST, HPTL, and 9-line CAS."
    )


# ---------------------------------------------------------------------------
# Annex E — Protection
# ---------------------------------------------------------------------------
class ProtectionPriority(_Base):
    """A single rank-ordered protection priority."""

    rank: int = Field(
        description="Priority rank (1 = highest)."
    )
    asset: str = Field(
        description="Asset receiving protection priority."
    )
    phase_applicability: list[str] = Field(
        default_factory=list,
        description="Phases during which this priority applies."
    )
    justification: str = Field(
        description="Why this asset warrants the assigned priority."
    )


class CriticalAsset(_Base):
    """An entry on the Critical Asset List (CAL) per ATP 3-37.2."""

    asset_name: str = Field(
        description="Asset name."
    )
    category: str = Field(
        description="Asset category (personnel, equipment, facility, capability, information)."
    )
    priority: int = Field(
        description="Rank-ordered priority on the CAL (1 = highest)."
    )
    location: MGRSGrid = Field(
        description="MGRS grid location of the asset."
    )
    owning_unit: str = Field(
        description="Unit owning or operating the asset."
    )
    vulnerability: Optional[str] = Field(
        default=None,
        description="Primary vulnerability or threat vector."
    )
    protection_measures: list[str] = Field(
        default_factory=list,
        description="Protection measures applied to the asset."
    )


class DefendedAsset(_Base):
    """An entry on the Defended Asset List (DAL) — subset of CAL receiving AMD protection."""

    asset_name: str = Field(
        description="Asset name."
    )
    priority: int = Field(
        description="Rank-ordered priority on the DAL (1 = highest)."
    )
    location: MGRSGrid = Field(
        description="MGRS grid location of the asset."
    )


class RiskControl(_Base):
    """A composite-risk-management entry per ATP 5-19."""

    hazard: str = Field(
        description="Identified hazard (tactical or accidental)."
    )
    initial_risk: Literal["EXTREMELY_HIGH", "HIGH", "MODERATE", "LOW"] = Field(
        description="Initial risk level before applying the control."
    )
    control_measure: str = Field(
        description="Control measure applied to reduce risk."
    )
    residual_risk: Literal["EXTREMELY_HIGH", "HIGH", "MODERATE", "LOW"] = Field(
        description="Residual risk level after applying the control."
    )
    implementer: str = Field(
        description="Unit, staff section, or individual responsible for implementing the control."
    )


class AnnexEData(_Base):
    """Structured body for Annex E (Protection)."""

    model_config = _annex_config("E", "Protection")

    letter: Literal["E"] = _letter_field("E")
    protection_priorities: list[ProtectionPriority] = Field(
        default_factory=list,
        description="Rank-ordered protection priorities."
    )
    critical_asset_list: list[CriticalAsset] = Field(
        default_factory=list,
        description="Critical Asset List (CAL)."
    )
    defended_asset_list: list[DefendedAsset] = Field(
        default_factory=list,
        description="Defended Asset List (DAL) — CAL subset receiving AMD protection."
    )
    risk_controls: list[RiskControl] = Field(
        default_factory=list,
        description="Composite-risk-management entries (hazard → control → residual)."
    )


# ---------------------------------------------------------------------------
# Annex F — Sustainment
# ---------------------------------------------------------------------------
class ClassOfSupplyPriority(_Base):
    """Priority-of-support entry for a single class of supply."""

    class_of_supply: Literal[
        "I",
        "II",
        "III_P",
        "III_B",
        "IV",
        "V",
        "VI",
        "VII",
        "VIII",
        "IX",
        "X",
        "WATER",
    ] = Field(
        description="Army class of supply per ADP 4-0 (I=subsistence, II=clothing, III_P=packaged POL, III_B=bulk POL, IV=const., V=ammo, VI=personal demand, VII=major end items, VIII=medical, IX=repair parts, X=non-mil agriculture/econ, WATER=water)."
    )
    description: str = Field(
        description="Short description of what this class covers for this operation."
    )
    daily_quantity: str = Field(
        description="Planned daily consumption or issue quantity."
    )
    source: str = Field(
        description="Source of supply (e.g. 'BSB DISTRO CO', 'Theater SSA')."
    )
    resupply_trigger: str = Field(
        description="Trigger that initiates resupply (on-hand threshold, event, or schedule)."
    )


class AnnexFData(_Base):
    """Structured body for Annex F (Sustainment)."""

    model_config = _annex_config("F", "Sustainment")

    letter: Literal["F"] = _letter_field("F")
    roles_of_care: list[RoleOfCare] = Field(
        default_factory=list,
        description="Role 1–4 medical treatment facilities supporting the operation."
    )
    ambulance_exchange_points: list[AmbulanceExchangePoint] = Field(
        default_factory=list,
        description="Ambulance Exchange Points (AXPs) for casualty handoff."
    )
    msr: Optional[MSRoute] = Field(
        default=None,
        description="Main Supply Route."
    )
    asr: Optional[ASRoute] = Field(
        default=None,
        description="Alternate Supply Route."
    )
    logpac_schedule: Optional[LogisticsSchedule] = Field(
        default=None,
        description="Recurring LOGPAC schedule."
    )
    classes_of_supply_priority: list[ClassOfSupplyPriority] = Field(
        default_factory=list,
        description="Priority-of-support entries by class of supply."
    )


# ---------------------------------------------------------------------------
# Annex G — Engineer
# ---------------------------------------------------------------------------
class BreachLane(_Base):
    """A breach lane specification."""

    name: str = Field(
        description="Lane designator (e.g. 'RED 1')."
    )
    width_m: int = Field(
        description="Lane width in meters."
    )
    entry_grid: MGRSGrid = Field(
        description="MGRS grid of the lane entry point."
    )
    exit_grid: MGRSGrid = Field(
        description="MGRS grid of the lane exit point."
    )


class BreachOperation(_Base):
    """A planned breach operation per ATP 3-90.4."""

    breach_name: str = Field(
        description="Breach operation name (e.g. 'BREACH ALPHA')."
    )
    obstacle_description: str = Field(
        description="Description of the obstacle being breached (type, composition, density)."
    )
    obstacle_grid: MGRSGrid = Field(
        description="MGRS grid of the obstacle."
    )
    breach_method: Literal[
        "inplace",
        "in_stride",
        "deliberate",
        "assault",
        "covert",
    ] = Field(
        description="Breach method per ATP 3-90.4."
    )
    primary_lane: BreachLane = Field(
        description="Primary breach lane."
    )
    alternate_lane: Optional[BreachLane] = Field(
        default=None,
        description="Alternate breach lane if the primary fails."
    )
    reduction_asset_primary: str = Field(
        description="Primary reduction asset (MICLIC, ABV, Bangalore, engineer squad)."
    )
    marking_standard: str = Field(
        description="Lane marking standard (NATO standard or unit SOP)."
    )
    breach_force: str = Field(
        description="Unit designated as the breach force."
    )
    breach_dtg_nlt: DTGString = Field(
        description="Not-Later-Than DTG the breach must be complete."
    )


class SurvivabilityEffort(_Base):
    """A single survivability-position emplacement tasking."""

    location: MGRSGrid = Field(
        description="MGRS grid of the position."
    )
    supported_unit: str = Field(
        description="Unit for whom the position is being dug."
    )
    position_type: str = Field(
        description="Position type (fighting, vehicle, protected, command, weapon system)."
    )
    priority: int = Field(
        description="Rank-ordered survivability priority (1 = highest)."
    )
    emplacing_asset: str = Field(
        description="Emplacing equipment or unit (e.g. 'D7 dozer', 'BCT Sapper Co')."
    )
    nlt_dtg: DTGString = Field(
        description="Not-Later-Than DTG the position must be complete."
    )


class PointObstacle(_Base):
    """A point-obstacle emplacement per ATP 3-90.8."""

    name: str = Field(
        description="Obstacle name (e.g. 'OBST 1')."
    )
    grid: MGRSGrid = Field(
        description="MGRS grid of the obstacle."
    )
    obstacle_type: Literal[
        "wire",
        "abatis",
        "crater",
        "AT_ditch",
        "minefield_conventional",
        "minefield_scatterable",
        "log_crib",
        "dragons_teeth",
        "hasty_protective",
        "complex",
    ] = Field(
        description="Obstacle type per ATP 3-90.8."
    )
    intent: Literal["disrupt", "turn", "fix", "block"] = Field(
        description="Obstacle intent per ATP 3-90.8."
    )
    emplacing_unit: str = Field(
        description="Unit emplacing the obstacle."
    )
    effective_dtg: DTGString = Field(
        description="DTG the obstacle becomes effective."
    )


class AnnexGData(_Base):
    """Structured body for Annex G (Engineer)."""

    model_config = _annex_config("G", "Engineer")

    letter: Literal["G"] = _letter_field("G")
    breach_operations: list[BreachOperation] = Field(
        default_factory=list,
        description="Planned breach operations."
    )
    survivability_efforts: list[SurvivabilityEffort] = Field(
        default_factory=list,
        description="Survivability-position emplacement taskings."
    )
    point_obstacles: list[PointObstacle] = Field(
        default_factory=list,
        description="Planned point-obstacle emplacements."
    )


# ---------------------------------------------------------------------------
# Annex H — Signal
# ---------------------------------------------------------------------------
class PACEPlan(_Base):
    """A PACE (Primary/Alternate/Contingency/Emergency) plan for a single net."""

    net_name: str = Field(
        description="Net name (e.g. 'BN CMD', 'BN O&I', 'FIRES')."
    )
    primary: str = Field(
        description="Primary method of communication."
    )
    alternate: str = Field(
        description="Alternate method of communication."
    )
    contingency: str = Field(
        description="Contingency method of communication."
    )
    emergency: str = Field(
        description="Emergency method of communication."
    )
    shift_criteria: str = Field(
        description="Criteria that trigger a shift to the next method in the PACE."
    )


class COMSECSchedule(_Base):
    """COMSEC key-load and rollover schedule per ATP 6-02.45."""

    load_dtg: DTGString = Field(
        description="DTG of the initial key load for the operation."
    )
    rollover_dtg: DTGString = Field(
        description="DTG of the next scheduled key rollover."
    )
    controlling_authority: str = Field(
        description="COMSEC controlling authority (unit or staff section)."
    )
    zeroize_triggers: list[str] = Field(
        default_factory=list,
        description="Events or conditions that trigger emergency zeroization."
    )


class RetransSite(_Base):
    """A retransmission (RETRANS) site per ATP 6-02.53."""

    site_name: str = Field(
        description="Site designator (e.g. 'RETRANS ECHO')."
    )
    team_callsign: str = Field(
        description="RETRANS team callsign."
    )
    grid: MGRSGrid = Field(
        description="MGRS grid of the RETRANS site."
    )
    parent_unit: str = Field(
        description="Parent unit of the RETRANS team."
    )
    nets_supported: list[str] = Field(
        default_factory=list,
        description="Nets retransmitted from this site."
    )


class AnnexHData(_Base):
    """Structured body for Annex H (Signal). Complements the existing ``call_sign_groups`` on Annex."""

    model_config = _annex_config("H", "Signal")

    letter: Literal["H"] = _letter_field("H")
    pace_plans: list[PACEPlan] = Field(
        default_factory=list,
        description="PACE plans, one per net."
    )
    comsec_schedule: Optional[COMSECSchedule] = Field(
        default=None,
        description="COMSEC key-load and rollover schedule."
    )
    retrans_sites: list[RetransSite] = Field(
        default_factory=list,
        description="RETRANS site list."
    )


# ---------------------------------------------------------------------------
# Annex J — Public Affairs
# ---------------------------------------------------------------------------
class KeyMessage(_Base):
    """An approved key message per FM 3-61."""

    message_id: str = Field(
        description="Message identifier (e.g. 'KM-01')."
    )
    text: str = Field(
        description="The message itself, as approved for release."
    )
    audience: Literal["internal", "external", "hn_partner", "all"] = Field(
        description="Target audience for the message."
    )
    priority: Literal["primary", "secondary", "supporting"] = Field(
        description="Message priority within the communication plan."
    )


class MediaGroundRule(_Base):
    """A ground rule governing media engagement."""

    rule_id: str = Field(
        description="Rule identifier (e.g. 'GR-01')."
    )
    rule_text: str = Field(
        description="The ground rule as written for media."
    )
    rationale: str = Field(
        description="Doctrinal or operational rationale for the rule."
    )
    applies_to: Literal[
        "all_media",
        "hn_press",
        "social_media",
        "embedded_only",
    ] = Field(
        description="Which media category the rule applies to."
    )


class ReleaseAuthority(_Base):
    """Release authority assignment for a topic."""

    topic: str = Field(
        description="Topic covered (e.g. 'Casualties', 'Partner Nation Forces')."
    )
    authority: str = Field(
        description="Duty title of the release authority."
    )
    coordination_required_with: list[str] = Field(
        default_factory=list,
        description="Staff sections or agencies that must coordinate before release."
    )


class AnnexJData(_Base):
    """Structured body for Annex J (Public Affairs)."""

    model_config = _annex_config("J", "Public Affairs")

    letter: Literal["J"] = _letter_field("J")
    key_messages: list[KeyMessage] = Field(
        default_factory=list,
        description="Approved key messages."
    )
    media_ground_rules: list[MediaGroundRule] = Field(
        default_factory=list,
        description="Ground rules governing media engagement."
    )
    release_authority: list[ReleaseAuthority] = Field(
        default_factory=list,
        description="Release-authority assignments by topic."
    )


# ---------------------------------------------------------------------------
# Annex K — Civil Affairs Operations
# ---------------------------------------------------------------------------
class ASCOPEEntry(_Base):
    """An entry in the ASCOPE register per ATP 3-57.60."""

    category: Literal[
        "AREAS",
        "STRUCTURES",
        "CAPABILITIES",
        "ORGANIZATIONS",
        "PEOPLE",
        "EVENTS",
    ] = Field(
        description="ASCOPE category."
    )
    name: str = Field(
        description="Entry name or label."
    )
    description: str = Field(
        description="Narrative description of the entry."
    )
    grid: Optional[MGRSGrid] = Field(
        default=None,
        description="MGRS grid where applicable (areas, structures, events)."
    )
    significance: str = Field(
        description="Operational significance — why the entry matters to the mission."
    )


class KeyLeaderEngagement(_Base):
    """A planned Key Leader Engagement (KLE) per ATP 3-07.5."""

    engagement_id: str = Field(
        description="Engagement identifier (e.g. 'KLE-07')."
    )
    leader_name: str = Field(
        description="Name of the leader being engaged."
    )
    position: str = Field(
        description="Position or role of the leader."
    )
    organization: str = Field(
        description="Organization or community the leader represents."
    )
    engagement_date: str = Field(
        description="Planned engagement date (DTG or calendar date)."
    )
    location: str = Field(
        description="Location of the engagement."
    )
    engaging_officer: str = Field(
        description="Officer conducting the engagement."
    )
    topic: str = Field(
        description="Primary topic of the engagement."
    )
    talking_points: list[str] = Field(
        default_factory=list,
        description="Approved talking points for the engagement."
    )
    desired_outcome: str = Field(
        description="Desired outcome of the engagement."
    )


class ProtectedSite(_Base):
    """A civilian site afforded special protection per LOAC and commander guidance."""

    name: str = Field(
        description="Site name."
    )
    category: Literal[
        "CULTURAL",
        "RELIGIOUS",
        "MEDICAL",
        "EDUCATIONAL",
        "DIPLOMATIC",
        "CIVILIAN_POPULATION",
        "ENVIRONMENTAL",
        "OTHER",
    ] = Field(
        description="Protection category."
    )
    grid: MGRSGrid = Field(
        description="MGRS grid of the site."
    )
    authority: str = Field(
        description="Authority granting protected status (LOAC, HN law, commander)."
    )
    restrictions: list[str] = Field(
        default_factory=list,
        description="Restrictions on friendly action in or near the site."
    )
    enforcing_unit: str = Field(
        description="Unit responsible for enforcing the protected status."
    )


class AnnexKData(_Base):
    """Structured body for Annex K (Civil Affairs Operations)."""

    model_config = _annex_config("K", "Civil Affairs Operations")

    letter: Literal["K"] = _letter_field("K")
    ascope_register: list[ASCOPEEntry] = Field(
        default_factory=list,
        description="ASCOPE register entries."
    )
    key_leader_engagements: list[KeyLeaderEngagement] = Field(
        default_factory=list,
        description="Planned Key Leader Engagements."
    )
    protected_sites: list[ProtectedSite] = Field(
        default_factory=list,
        description="Protected civilian sites."
    )


# ---------------------------------------------------------------------------
# Annex L — Information Collection
# ---------------------------------------------------------------------------
class CollectionRequirement(_Base):
    """A single collection requirement row per ATP 2-01."""

    requirement_number: str = Field(
        description="Requirement identifier (e.g. 'CR-012')."
    )
    linked_pir: str = Field(
        description="Linked PIR identifier (e.g. 'PIR 2')."
    )
    linked_nai: str = Field(
        description="Linked NAI identifier."
    )
    linked_decision_point: Optional[str] = Field(
        default=None,
        description="Linked decision point identifier, if any."
    )
    indicator: str = Field(
        description="Specific observable indicator to collect against."
    )
    collection_asset: str = Field(
        description="Asset tasked to collect (unit, platform, or discipline)."
    )
    start_dtg: DTGString = Field(
        description="DTG collection begins."
    )
    ltiov: str = Field(
        description="Latest Time Information is Of Value."
    )
    reporting_criteria: str = Field(
        description="When and how to report observations back to the intelligence cell."
    )


class ISRSyncRow(_Base):
    """A row of the ISR Synchronization Matrix per ATP 2-01."""

    row_number: int = Field(
        description="Sequential row number."
    )
    time_block: str = Field(
        description="Time block covered by this row."
    )
    asset: str = Field(
        description="ISR asset or collector."
    )
    nai: str = Field(
        description="NAI observed."
    )
    target_or_task: str = Field(
        description="Specific target or task within the NAI."
    )
    linked_pir: str = Field(
        description="PIR the row supports."
    )
    linked_dp: Optional[str] = Field(
        default=None,
        description="Decision point the row supports, if any."
    )
    role: Literal["PRIMARY", "ALTERNATE"] = Field(
        description="Role of the asset in this row (primary or alternate)."
    )
    ltiov: str = Field(
        description="Latest Time Information is Of Value for this row."
    )
    reporting_method: str = Field(
        description="Method used to report observations (net, system, report type)."
    )


class AnnexLData(_Base):
    """Structured body for Annex L (Information Collection)."""

    model_config = _annex_config("L", "Information Collection")

    letter: Literal["L"] = _letter_field("L")
    collection_requirements: list[CollectionRequirement] = Field(
        default_factory=list,
        description="Collection requirements cross-walked to PIR, NAI, and DP."
    )
    named_areas_of_interest: list[NamedAreaOfInterest] = Field(
        default_factory=list,
        description="NAIs defined for this operation."
    )
    isr_sync_rows: list[ISRSyncRow] = Field(
        default_factory=list,
        description="Rows of the ISR Synchronization Matrix."
    )


# ---------------------------------------------------------------------------
# Annex M — Assessment
# ---------------------------------------------------------------------------
class AssessmentPriority(_Base):
    """A single assessment priority tied to an objective and phase."""

    priority_id: str = Field(
        description="Priority identifier (e.g. 'AP-01')."
    )
    priority: str = Field(
        description="Statement of the priority."
    )
    linked_objective: str = Field(
        description="Higher-level objective this priority supports."
    )
    linked_phase: Literal["I", "II", "III", "IV"] = Field(
        description="Operation phase this priority applies to."
    )
    moe_refs: list[str] = Field(
        default_factory=list,
        description="MOE identifiers linked to this priority."
    )
    mop_refs: list[str] = Field(
        default_factory=list,
        description="MOP identifiers linked to this priority."
    )
    owner: str = Field(
        description="Duty position or staff section owning the priority."
    )


class MeasureOfEffectiveness(_Base):
    """A Measure of Effectiveness (MOE) per ADP 5-0."""

    moe_id: str = Field(
        description="MOE identifier (e.g. 'MOE-01')."
    )
    statement: str = Field(
        description="MOE statement — are we doing the right things?"
    )
    linked_objective: str = Field(
        description="Objective the MOE measures progress toward."
    )
    indicator_refs: list[str] = Field(
        default_factory=list,
        description="Indicator identifiers feeding this MOE."
    )
    collection_source: str = Field(
        description="Source from which data is collected."
    )
    frequency: str = Field(
        description="Collection and reporting frequency."
    )
    threshold: str = Field(
        description="Threshold value or condition for assessing effectiveness."
    )
    owner: str = Field(
        description="Duty position or staff section owning the MOE."
    )


class MeasureOfPerformance(_Base):
    """A Measure of Performance (MOP) per ADP 5-0."""

    mop_id: str = Field(
        description="MOP identifier (e.g. 'MOP-01')."
    )
    task: str = Field(
        description="Task whose execution is measured."
    )
    indicator: str = Field(
        description="Indicator used to measure task performance."
    )
    source: str = Field(
        description="Source from which performance data is drawn."
    )
    target_value: str = Field(
        description="Target value or standard."
    )
    frequency: str = Field(
        description="Collection and reporting frequency."
    )
    owner: str = Field(
        description="Duty position or staff section owning the MOP."
    )


class AnnexMData(_Base):
    """Structured body for Annex M (Assessment)."""

    model_config = _annex_config("M", "Assessment")

    letter: Literal["M"] = _letter_field("M")
    assessment_priorities: list[AssessmentPriority] = Field(
        default_factory=list,
        description="Assessment priorities tied to objectives and phases."
    )
    measures_of_effectiveness: list[MeasureOfEffectiveness] = Field(
        default_factory=list,
        description="MOE list."
    )
    measures_of_performance: list[MeasureOfPerformance] = Field(
        default_factory=list,
        description="MOP list."
    )


# ---------------------------------------------------------------------------
# Annex N — Space Operations
# ---------------------------------------------------------------------------
class SpaceCapability(_Base):
    """A friendly space capability supporting the operation per FM 3-14."""

    mission_area: Literal[
        "PNT",
        "SATCOM",
        "MISSILE_WARNING",
        "ISR",
        "ENVIRONMENTAL_MONITORING",
    ] = Field(
        description="Space mission area."
    )
    systems: list[str] = Field(
        default_factory=list,
        description="Space systems providing the capability (e.g. 'GPS III', 'WGS')."
    )
    supported_echelon: str = Field(
        description="Echelon receiving the support."
    )
    availability: str = Field(
        description="Availability window or coverage posture."
    )
    degradation_risk: str = Field(
        description="Risk of degradation (threat, environment, loading)."
    )
    mitigation: str = Field(
        description="Planned mitigation if the capability degrades."
    )


class SpaceSupportRequest(_Base):
    """A Space Support Request (SSR) per FM 3-14."""

    ssr_number: str = Field(
        description="SSR number."
    )
    requesting_unit: str = Field(
        description="Requesting unit."
    )
    submission_dtg: DTGString = Field(
        description="DTG the SSR was submitted."
    )
    required_by_dtg: DTGString = Field(
        description="DTG by which the effect is required."
    )
    priority: Literal["IMMEDIATE", "PRIORITY", "ROUTINE"] = Field(
        description="SSR priority."
    )
    mission_area: Literal[
        "PNT",
        "SATCOM",
        "MISSILE_WARNING",
        "ISR",
        "ENVIRONMENTAL_MONITORING",
    ] = Field(
        description="Space mission area requested."
    )
    effect_requested: str = Field(
        description="Specific space effect requested."
    )
    target_or_area: str = Field(
        description="Target or area the effect applies to."
    )
    status: Literal[
        "DRAFT",
        "SUBMITTED",
        "APPROVED",
        "DENIED",
        "SATISFIED",
    ] = Field(
        description="Current status of the SSR."
    )


class ThreatSpaceAsset(_Base):
    """An adversary space or counter-space capability per FM 3-14."""

    system_designator: str = Field(
        description="System designator (e.g. 'Glonass-K', 'GJ-4')."
    )
    category: Literal[
        "ORBITAL_ISR",
        "ORBITAL_COMMS",
        "ORBITAL_PNT",
        "GROUND_EW_JAMMER",
        "GROUND_EW_SPOOFER",
        "DIRECTED_ENERGY",
        "KINETIC_ASAT",
        "CYBER_SPACE",
    ] = Field(
        description="Threat category."
    )
    target_mission_area: str = Field(
        description="Friendly mission area most at risk from this system."
    )
    effect: str = Field(
        description="Effect the system can achieve (deny, degrade, disrupt, destroy, deceive)."
    )
    friendly_mitigation: str = Field(
        description="Friendly mitigation or counter measures."
    )


class AnnexNData(_Base):
    """Structured body for Annex N (Space Operations)."""

    model_config = _annex_config("N", "Space Operations")

    letter: Literal["N"] = _letter_field("N")
    space_capabilities: list[SpaceCapability] = Field(
        default_factory=list,
        description="Friendly space capabilities supporting the operation."
    )
    space_support_requests: list[SpaceSupportRequest] = Field(
        default_factory=list,
        description="Outstanding and historical SSRs."
    )
    threat_space_assets: list[ThreatSpaceAsset] = Field(
        default_factory=list,
        description="Adversary space and counter-space assets."
    )


# ---------------------------------------------------------------------------
# Annex P — Host-Nation Support
# ---------------------------------------------------------------------------
class HNSAgreement(_Base):
    """A Host-Nation Support agreement per JP 4-08."""

    name: str = Field(
        description="Agreement name or short title."
    )
    type: Literal[
        "SOFA",
        "SOFA_SUPPLEMENT",
        "MOU",
        "MOA",
        "ACSA",
        "TECHNICAL_ARRANGEMENT",
    ] = Field(
        description="Agreement type."
    )
    signatories: list[str] = Field(
        default_factory=list,
        description="Nations or organizations that signed the agreement."
    )
    effective_date: str = Field(
        description="Effective date of the agreement."
    )
    scope: str = Field(
        description="Scope of support provided under the agreement."
    )


class HNSProvider(_Base):
    """A Host-Nation Support provider agency."""

    agency: str = Field(
        description="Providing agency name."
    )
    nation: str = Field(
        description="Host nation the agency belongs to."
    )
    services: list[str] = Field(
        default_factory=list,
        description="Services the agency provides."
    )
    poc_name: Optional[str] = Field(
        default=None,
        description="Point-of-contact name."
    )
    poc_phone: Optional[str] = Field(
        default=None,
        description="Point-of-contact phone number."
    )


class LiaisonElement(_Base):
    """A liaison element embedded with a partner or host-nation unit."""

    lno_title: str = Field(
        description="Liaison officer duty title."
    )
    parent_unit: str = Field(
        description="Parent unit of the LNO."
    )
    embedded_with: str = Field(
        description="Unit or organization the LNO is embedded with."
    )
    rank_required: str = Field(
        description="Minimum rank required for the LNO."
    )
    language_required: list[str] = Field(
        default_factory=list,
        description="Language proficiencies required of the LNO."
    )


class AnnexPData(_Base):
    """Structured body for Annex P (Host-Nation Support)."""

    model_config = _annex_config("P", "Host-Nation Support")

    letter: Literal["P"] = _letter_field("P")
    hns_agreements: list[HNSAgreement] = Field(
        default_factory=list,
        description="HNS agreements in force for the operation."
    )
    hns_providers: list[HNSProvider] = Field(
        default_factory=list,
        description="HNS provider agencies."
    )
    liaison_elements: list[LiaisonElement] = Field(
        default_factory=list,
        description="Liaison elements embedded with partner units."
    )


# ---------------------------------------------------------------------------
# Annex Q — Knowledge Management
# ---------------------------------------------------------------------------
class COPSource(_Base):
    """A Common Operating Picture source system per ATP 6-01.1."""

    cop_system: Literal[
        "CPOF",
        "JBC-P",
        "Nett_Warrior",
        "JADOCS",
        "GCCS-A",
        "TAIS",
    ] = Field(
        description="COP system designator."
    )
    authoritative_instance: str = Field(
        description="Authoritative instance name or location."
    )
    refresh_interval_minutes: int = Field(
        description="Refresh interval in minutes."
    )
    feeder_systems: list[str] = Field(
        default_factory=list,
        description="Upstream feeder systems."
    )


class AnnexQData(_Base):
    """Structured body for Annex Q (Knowledge Management)."""

    model_config = _annex_config("Q", "Knowledge Management")

    letter: Literal["Q"] = _letter_field("Q")
    battle_rhythm: list[BattleRhythmEvent] = Field(
        default_factory=list,
        description="Battle-rhythm events."
    )
    cop_sources: list[COPSource] = Field(
        default_factory=list,
        description="COP source systems."
    )


# ---------------------------------------------------------------------------
# Annex R — Reports
# ---------------------------------------------------------------------------
class ReportDistributionRow(_Base):
    """A distribution row for a single report."""

    report_name: str = Field(
        description="Report name."
    )
    originating_units: list[str] = Field(
        default_factory=list,
        description="Units originating the report."
    )
    destination_section: str = Field(
        description="Receiving staff section."
    )
    net: str = Field(
        description="Radio or data net used for transmission."
    )
    info_addees: list[str] = Field(
        default_factory=list,
        description="Info addressees receiving copies."
    )


class AnnexRData(_Base):
    """Structured body for Annex R (Reports)."""

    model_config = _annex_config("R", "Reports")

    letter: Literal["R"] = _letter_field("R")
    report_definitions: list[ReportDefinition] = Field(
        default_factory=list,
        description="Report definitions (format, frequency, precedence, medium)."
    )
    distribution_rows: list[ReportDistributionRow] = Field(
        default_factory=list,
        description="Report distribution rows."
    )


# ---------------------------------------------------------------------------
# Annex S — Special Technical Operations
# ---------------------------------------------------------------------------
class BCTSTOCellPOC(_Base):
    """BCT STO cell point-of-contact guidance (UNCLASS level only)."""

    cell_name: str = Field(
        description="STO cell name."
    )
    primary_officer_duty_title: str = Field(
        description="Duty title of the primary STO officer."
    )
    primary_officer_rank: str = Field(
        description="Rank of the primary STO officer."
    )
    coordination_guidance: str = Field(
        description="Unclassified coordination guidance."
    )


class AnnexSData(_Base):
    """Structured body for Annex S (Special Technical Operations) — UNCLASS thin wrapper only."""

    model_config = _annex_config("S", "Special Technical Operations")

    letter: Literal["S"] = _letter_field("S")
    applicability_statement: str = Field(
        description="Statement describing whether STO applies to this operation."
    )
    sto_reference_channel: str = Field(
        description="Reference channel for STO coordination (typically a classified annex or SAP)."
    )
    bct_sto_cell_poc: Optional[BCTSTOCellPOC] = Field(
        default=None,
        description="BCT STO cell POC guidance."
    )


# ---------------------------------------------------------------------------
# Annex U — Inspector General
# ---------------------------------------------------------------------------
class IGSupportSource(_Base):
    """IG support relationship per AR 20-1."""

    supporting_ig_office: str = Field(
        description="Supporting IG office name."
    )
    support_relationship: Literal[
        "organic",
        "reachback",
        "attached",
        "direct_support",
    ] = Field(
        description="Support relationship."
    )


class ComplaintProcedure(_Base):
    """Commander's complaint procedure per AR 20-1."""

    open_door_policy: str = Field(
        description="Statement of the commander's open-door policy."
    )
    primary_channel: Literal[
        "chain_of_command",
        "nco_support_channel",
        "ig_direct",
    ] = Field(
        description="Primary complaint channel."
    )
    submission_methods: list[str] = Field(
        default_factory=list,
        description="Accepted submission methods (in person, form, email, phone, hotline)."
    )
    acknowledgement_timeline: str = Field(
        description="Timeline for acknowledging receipt of a complaint."
    )
    confidentiality_and_reprisal_protection: str = Field(
        description="Statement of confidentiality and protection from reprisal."
    )


class AnnexUData(_Base):
    """Structured body for Annex U (Inspector General)."""

    model_config = _annex_config("U", "Inspector General")

    letter: Literal["U"] = _letter_field("U")
    ig_support_source: Optional[IGSupportSource] = Field(
        default=None,
        description="IG support source and relationship."
    )
    complaint_procedure: Optional[ComplaintProcedure] = Field(
        default=None,
        description="Commander's complaint procedure."
    )


# ---------------------------------------------------------------------------
# Annex V — Interagency Coordination
# ---------------------------------------------------------------------------
class InteragencyPartner(_Base):
    """An interagency, intergovernmental, or NGO partner per JP 3-08."""

    agency: str = Field(
        description="Partner agency or organization name."
    )
    partner_type: Literal["USG", "IGO", "NGO", "HN"] = Field(
        description="Partner type."
    )
    poc_name: str = Field(
        description="Primary point-of-contact name."
    )
    coordination_channel: str = Field(
        description="Coordination channel used (email, CMOC, LNO, etc.)."
    )
    authorized_topics: list[str] = Field(
        default_factory=list,
        description="Topics authorized for direct coordination."
    )
    prohibited_topics: list[str] = Field(
        default_factory=list,
        description="Topics explicitly prohibited from coordination."
    )
    bct_hn_lno_required: bool = Field(
        default=True,
        description="Whether the BCT HN LNO must be involved in coordination with this partner."
    )


class AnnexVData(_Base):
    """Structured body for Annex V (Interagency Coordination)."""

    model_config = _annex_config("V", "Interagency Coordination")

    letter: Literal["V"] = _letter_field("V")
    interagency_partners: list[InteragencyPartner] = Field(
        default_factory=list,
        description="Interagency, IGO, NGO, and HN partners."
    )


# ---------------------------------------------------------------------------
# Annex Z — Distribution
# ---------------------------------------------------------------------------
class DistributionEntry(_Base):
    """A single distribution-list entry per FM 6-0 App D."""

    copy_number: int = Field(
        description="Copy number assigned to this recipient."
    )
    recipient_unit: str = Field(
        description="Unit or organization receiving the copy."
    )
    recipient_role: str = Field(
        description="Role or duty position of the recipient."
    )
    type: Literal["action", "info"] = Field(
        description="Action or information addressee."
    )
    receipt_method: Literal[
        "hand_delivery",
        "courier",
        "sipr_email",
        "niprnet_email",
        "secure_fax",
        "tactical_messenger",
    ] = Field(
        description="Delivery method for this copy."
    )
    acknowledgment_required: bool = Field(
        description="Whether the recipient must acknowledge receipt."
    )


class AnnexZData(_Base):
    """Structured body for Annex Z (Distribution)."""

    model_config = _annex_config("Z", "Distribution")

    letter: Literal["Z"] = _letter_field("Z")
    distribution_entries: list[DistributionEntry] = Field(
        default_factory=list,
        description="Per-copy distribution-list entries."
    )


# ---------------------------------------------------------------------------
# Discriminated union
# ---------------------------------------------------------------------------
AnnexTypedBody = Annotated[
    Union[
        AnnexAData,
        AnnexBData,
        AnnexCData,
        AnnexDData,
        AnnexEData,
        AnnexFData,
        AnnexGData,
        AnnexHData,
        AnnexJData,
        AnnexKData,
        AnnexLData,
        AnnexMData,
        AnnexNData,
        AnnexPData,
        AnnexQData,
        AnnexRData,
        AnnexSData,
        AnnexUData,
        AnnexVData,
        AnnexZData,
    ],
    Field(
        discriminator="letter",
        description="Typed structured-content body for an Annex. Discriminated on the 'letter' field (A–Z); reserved letters I/O/T/W/X/Y have no typed body.",
    ),
]
"""Discriminated union of all per-annex typed bodies.

The discriminator field is ``letter``; each ``Annex{Letter}Data`` class
declares ``letter: Literal["X"]`` for its specific letter. Reserved annex
letters (I, O, T, W, X, Y) have no typed body and must leave ``typed_body``
set to ``None`` on :class:`opord_builder.schema.core.Annex`.
"""


__all__ = [
    "AnnexAData",
    "AnnexBData",
    "AnnexCData",
    "AnnexDData",
    "AnnexEData",
    "AnnexFData",
    "AnnexGData",
    "AnnexHData",
    "AnnexJData",
    "AnnexKData",
    "AnnexLData",
    "AnnexMData",
    "AnnexNData",
    "AnnexPData",
    "AnnexQData",
    "AnnexRData",
    "AnnexSData",
    "AnnexUData",
    "AnnexVData",
    "AnnexZData",
    "AnnexTypedBody",
    "StrengthRollup",
    "CrossAttachment",
    "OperationPhase",
    "EndState",
    "PriorityOfFiresEntry",
    "AttackGuidanceEntry",
    "CASRequest",
    "ProtectionPriority",
    "CriticalAsset",
    "DefendedAsset",
    "RiskControl",
    "ClassOfSupplyPriority",
    "BreachLane",
    "BreachOperation",
    "SurvivabilityEffort",
    "PointObstacle",
    "PACEPlan",
    "COMSECSchedule",
    "RetransSite",
    "KeyMessage",
    "MediaGroundRule",
    "ReleaseAuthority",
    "ASCOPEEntry",
    "KeyLeaderEngagement",
    "ProtectedSite",
    "CollectionRequirement",
    "ISRSyncRow",
    "AssessmentPriority",
    "MeasureOfEffectiveness",
    "MeasureOfPerformance",
    "SpaceCapability",
    "SpaceSupportRequest",
    "ThreatSpaceAsset",
    "HNSAgreement",
    "HNSProvider",
    "LiaisonElement",
    "COPSource",
    "ReportDistributionRow",
    "BCTSTOCellPOC",
    "IGSupportSource",
    "ComplaintProcedure",
    "InteragencyPartner",
    "DistributionEntry",
]
