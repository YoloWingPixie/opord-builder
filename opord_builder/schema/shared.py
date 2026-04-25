"""Shared sub-types used by multiple annex typed bodies.

These types are referenced by :mod:`opord_builder.schema.annexes` and capture
doctrinal concepts that recur across annexes — control measures, FSCMs, ACMs,
PIR, HVTs, decision points, NAIs, medical roles of care, logistics schedules,
reports, and classification markings. They are separate from the core 5-paragraph
models so that the structured-content layer can grow without bloating
:mod:`opord_builder.schema.core`.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import Field

from opord_builder.schema._base import _Base


# ---------------------------------------------------------------------------
# String-typed primitives
# ---------------------------------------------------------------------------
DTGString = Annotated[
    str,
    Field(
        pattern=r"^\d{6}Z[A-Z]{3}\d{2}$",
        description="Military date-time group in DDHHMMZMONYY form (e.g. '181200ZAPR26').",
    ),
]
"""Type alias for a strict military DTG string (DDHHMMZMONYY)."""


MGRSGrid = Annotated[
    str,
    Field(
        pattern=r"^[0-9]{1,2}[A-Z]{3}[0-9]{2,10}$|^[A-Z]{2}[0-9]{2,10}$",
        description="Military Grid Reference System (MGRS) grid; 2-, 4-, 6-, 8-, or 10-digit precision. Examples: '38SMB4578', '38SMB45780789'.",
    ),
]
"""Type alias for a loose MGRS grid-coordinate string."""


# ---------------------------------------------------------------------------
# References and citations
# ---------------------------------------------------------------------------
class DoctrinalReference(_Base):
    """A citation to an Army doctrinal publication or external reference."""

    citation: str = Field(
        description="Short citation (e.g. 'FM 6-0', 'ATP 3-09.32', 'JP 3-60')."
    )
    title: str = Field(
        description="Publication title (e.g. 'Commander and Staff Organization and Operations')."
    )
    date: Optional[str] = Field(
        default=None,
        description="Publication or revision date in 'MON YYYY' form (e.g. 'May 2022').",
    )
    paragraph: Optional[str] = Field(
        default=None,
        description="Specific paragraph, chapter, or appendix reference (e.g. 'App D, para D-10').",
    )


# ---------------------------------------------------------------------------
# Control / coordination measures
# ---------------------------------------------------------------------------
class ControlMeasure(_Base):
    """A maneuver-graphic control measure: PL, objective, boundary, BP, AA, LD, LOA, DZ/LZ/PZ, NAI/TAI, checkpoint, TRP, etc."""

    name: str = Field(
        description="Control-measure label as it appears on the overlay (e.g. 'PL DAGGER', 'OBJ SWORD', 'CP 21')."
    )
    type: Literal[
        "axis",
        "phase_line",
        "objective",
        "boundary",
        "battle_position",
        "assembly_area",
        "line_of_departure",
        "limit_of_advance",
        "drop_zone",
        "landing_zone",
        "pickup_zone",
        "named_area_of_interest",
        "targeted_area_of_interest",
        "checkpoint",
        "trp",
        "other",
    ] = Field(
        description="Doctrinal type of the control measure per FM 3-90 / ADP 1-02.",
    )
    grid_or_trace: str = Field(
        description="MGRS grid (point measures) or ordered list of grids defining the trace (linear/area measures).",
    )
    effective_dtg: Optional[DTGString] = Field(
        default=None,
        description="DTG at which the control measure becomes effective; omit if effective on order receipt.",
    )
    termination_dtg: Optional[DTGString] = Field(
        default=None,
        description="DTG at which the control measure terminates; omit for indefinite.",
    )
    purpose: str = Field(
        description="Why this control measure exists — the tactical task or synchronization it enables.",
    )


class FSCM(_Base):
    """A Fire Support Coordination Measure per ATP 3-09.32 / JP 3-09."""

    type: Literal[
        "CFL",
        "NFA",
        "RFA",
        "ROZ",
        "FSCL",
        "CFZ",
        "NFZ",
        "ACA",
        "SFA",
        "RFZ",
        "FFA",
    ] = Field(
        description="FSCM type: Coordinated Fire Line, No Fire Area, Restrictive Fire Area, Restricted Operations Zone, Fire Support Coordination Line, Critical Friendly Zone, No Fire Zone, Airspace Coordination Area, Sensitive Fire Area, Restricted Fire Zone, or Free Fire Area.",
    )
    name: str = Field(
        description="Name or designator of the measure as it appears on the fires overlay.",
    )
    effective_dtg_start: DTGString = Field(
        description="DTG the measure becomes effective.",
    )
    effective_dtg_end: Optional[DTGString] = Field(
        default=None,
        description="DTG the measure terminates; omit for indefinite.",
    )
    grid_or_coords: str = Field(
        description="MGRS grid(s) or ordered coordinates that define the measure's geometry.",
    )
    establishing_hq: Optional[str] = Field(
        default=None,
        description="Headquarters that established the measure (required when different from the issuing HQ).",
    )
    remarks: Optional[str] = Field(
        default=None,
        description="Free-text remarks: protected units/assets, special coordination, or exceptions.",
    )


class ACM(_Base):
    """An Airspace Coordinating Measure per ATP 3-52.1 / JP 3-52."""

    type: Literal[
        "restricted_operations_zone",
        "air_corridor",
        "minimum_risk_route",
        "saafr",
        "hidacz",
        "coordinating_altitude",
        "weapons_engagement_zone",
        "base_defense_zone",
    ] = Field(
        description="ACM type: ROZ, air corridor, MRR, SAAFR, HIDACZ, coordinating altitude, WEZ, or BDZ.",
    )
    name: str = Field(
        description="Name or designator of the ACM as it appears on the airspace overlay.",
    )
    horizontal_boundary: str = Field(
        description="Horizontal geometry (MGRS grids, radials, or named points) bounding the ACM.",
    )
    vertical_boundary: str = Field(
        description="Vertical limits of the ACM (floor and ceiling in MSL or AGL with units).",
    )
    effective_dtg: DTGString = Field(
        description="DTG the ACM becomes effective.",
    )
    termination_dtg: Optional[DTGString] = Field(
        default=None,
        description="DTG the ACM terminates; omit for indefinite.",
    )
    controlling_agency: str = Field(
        description="Agency responsible for controlling traffic within or activating the ACM.",
    )
    purpose: str = Field(
        description="Why the ACM exists — the mission, unit, or effect it protects or enables.",
    )


# ---------------------------------------------------------------------------
# Intelligence primitives
# ---------------------------------------------------------------------------
class PIR(_Base):
    """Priority Intelligence Requirement per ADP 2-0 / ATP 2-01."""

    number: int = Field(
        description="Sequential PIR number within the order (PIR 1, PIR 2, ...).",
    )
    statement: str = Field(
        description="PIR statement phrased as a question the commander needs answered to make a decision.",
    )
    decision_supported: Optional[str] = Field(
        default=None,
        description="The specific decision (often a decision point) this PIR informs.",
    )
    nai: list[str] = Field(
        default_factory=list,
        description="Named Areas of Interest that will be observed to answer this PIR.",
    )
    ltiov: str = Field(
        description="Latest Time Information is Of Value; after this the answer is no longer useful.",
    )
    indicators: list[str] = Field(
        default_factory=list,
        description="Observable indicators whose presence or absence answers this PIR.",
    )
    primary_collector: Optional[str] = Field(
        default=None,
        description="Primary collection asset or unit tasked to answer this PIR.",
    )


class HVT(_Base):
    """High-Value Target (or High-Payoff Target when hpt_nomination is True) per ATP 3-60."""

    priority_rank: int = Field(
        description="Rank-ordered priority within the HVT/HPT list (1 = highest).",
    )
    category: Literal[
        "C2",
        "FIRES",
        "MANEUVER",
        "AIR_DEFENSE",
        "ISR",
        "ENGINEER",
        "LOGISTICS",
        "CBRN",
        "INFORMATION",
    ] = Field(
        description="Warfighting-function category the target belongs to.",
    )
    target_description: str = Field(
        description="Narrative description of the target: system, unit, facility, or individual.",
    )
    signature: str = Field(
        description="Detectable signature(s) of the target (electronic, thermal, visual, pattern-of-life).",
    )
    likely_locations: list[str] = Field(
        default_factory=list,
        description="MGRS grids or named areas where the target is most likely to appear.",
    )
    engagement_guidance: str = Field(
        description="Commander's guidance for engaging this target (restrictions, priority, delivery).",
    )
    linked_pir: list[int] = Field(
        default_factory=list,
        description="PIR numbers whose answer depends on observing or engaging this target.",
    )
    hpt_nomination: bool = Field(
        default=False,
        description="True when the target is nominated to the High-Payoff Target List (HPTL).",
    )


# ---------------------------------------------------------------------------
# Joint targeting products — JPITL and TST per JP 3-60 / ATP 3-60
# ---------------------------------------------------------------------------
DesiredEffect = Literal[
    "DESTROY", "NEUTRALIZE", "SUPPRESS", "DISRUPT", "DEGRADE", "DENY", "DIVERT",
]
"""Desired effect on target per JP 3-60."""

CDELevel = Literal["CDE-1", "CDE-2", "CDE-3", "CDE-4", "CDE-5"]
"""Collateral Damage Estimation level per CJCSI 3160.01."""

TargetComponent = Literal["LAND", "AIR", "MARITIME", "SOF", "CYBER", "SPACE", "IO"]
"""Joint force component tasked to prosecute the target."""

JPITLStatus = Literal["APPROVED", "PENDING", "DENIED", "EXECUTED", "EXPIRED"]
"""Lifecycle state of a JPITL entry on the current targeting cycle."""

TSTPriorityClass = Literal["TST-1", "TST-2", "TST-3"]
"""TST priority class; TST-1 is highest and typically retains engagement authority at component or higher."""

TSTCategory = Literal[
    "ENEMY_LEADERSHIP",
    "WMD",
    "HVT_C2",
    "AIR_DEFENSE",
    "LRF",              # Long-Range Fires (SRBM/MRBM/cruise)
    "SOF_COMPROMISE",
    "SENSOR_NODE",
    "OTHER",
]
"""TST functional category per JP 3-60 / doctrinal TST matrices."""


class JPITLEntry(_Base):
    """One row on the Joint Prioritized Integrated Target List (JPITL) per JP 3-60 / ATP 3-60.

    The JPITL is the JFC-approved, prioritized, integrated target list across
    all joint force components. Each row carries approval state, engagement
    means, and commander's effect guidance. TST entries live on a separate
    list (:class:`TSTEntry`) because their authority and timeline differ."""

    target_number: str = Field(
        description="Target identifier — basic-encyclopedia number (e.g. 'BE-0042-01') or locally assigned 'TGT 0042'.",
    )
    priority_rank: int = Field(
        description="Rank-ordered priority on the JPITL (1 = highest).",
    )
    target_name: str = Field(
        description="Short target name (e.g. 'ENY MRC CP, OBJ HAMMER').",
    )
    target_description: str = Field(
        description="Narrative target description: what the target is and why it matters.",
    )
    category: Literal[
        "C2",
        "FIRES",
        "MANEUVER",
        "AIR_DEFENSE",
        "ISR",
        "ENGINEER",
        "LOGISTICS",
        "CBRN",
        "INFORMATION",
        "LEADERSHIP",
        "WMD",
        "CYBER",
    ] = Field(
        description="Warfighting-function category; superset of HVT categories to include joint-level targets.",
    )
    location: MGRSGrid = Field(
        description="Target MGRS grid — point location at time of approval; update on dynamic re-tasking.",
    )
    component_tasked: TargetComponent = Field(
        description="Joint force component assigned to prosecute this target.",
    )
    desired_effect: DesiredEffect = Field(
        description="Commander's desired effect on the target.",
    )
    authorized_engagement_means: list[str] = Field(
        default_factory=list,
        description="Delivery systems cleared to engage (e.g. 'M777', 'HIMARS', 'F-16 CAS', 'Cyber').",
    )
    engagement_guidance: str = Field(
        description="Commander's intent / restrictions for engaging this target.",
    )
    cde_level: Optional[CDELevel] = Field(
        default=None,
        description="CDE level determined during targeting-approval board.",
    )
    approval_authority: str = Field(
        description="Authority that approved this target (e.g. 'JFC', 'JTCB', 'Component Cdr', 'BN CDR').",
    )
    status: JPITLStatus = Field(
        default="APPROVED",
        description="Current lifecycle state.",
    )
    no_strike_crossref: Optional[str] = Field(
        default=None,
        description="No-Strike List / Restricted Target List entry this target was deconflicted against.",
    )
    roe_constraints: Optional[str] = Field(
        default=None,
        description="Explicit ROE or LOAC constraints beyond baseline guidance.",
    )
    review_dtg: Optional[DTGString] = Field(
        default=None,
        description="DTG the approval expires and must be re-validated (target cycle review point).",
    )
    linked_hvt_rank: Optional[int] = Field(
        default=None,
        description="Optional cross-reference to an HVT/HPTL priority_rank for traceability.",
    )


class TSTEntry(_Base):
    """One row on the Time-Sensitive Target list per JP 3-60 / ATP 3-60.

    TSTs are targets of such importance that engagement authority is retained
    at (or near) the component commander level and the F2T2EA loop operates
    on a compressed timeline regardless of the normal targeting cycle."""

    tst_number: str = Field(
        description="TST identifier (e.g. 'TST-01', 'TST-02').",
    )
    priority_class: TSTPriorityClass = Field(
        description="TST-1/2/3. TST-1 is the highest and typically retains component-level engagement authority.",
    )
    category: TSTCategory = Field(
        description="TST functional category driving matrix-based engagement authority.",
    )
    target_description: str = Field(
        description="Narrative description of the target type and observable form.",
    )
    expected_activity: str = Field(
        description="Behavior or indicator that triggers F2T2EA (e.g. 'TEL erects for launch').",
    )
    expected_locations: list[str] = Field(
        default_factory=list,
        description="Likely NAIs, grids, or named areas where the target will appear.",
    )
    activity_window: Optional[str] = Field(
        default=None,
        description="DTG range when the target is expected (e.g. '190500ZAPR26 – 190800ZAPR26') or free-form.",
    )
    pid_standard: str = Field(
        description="Positive-identification standard required before engagement (e.g. '2 independent sensors + visual').",
    )
    engagement_authority: str = Field(
        description="Who authorizes the engagement (e.g. 'JFACC', 'JSOTF Cdr', 'BCT Cdr'). Usually component-level for TST-1.",
    )
    authorized_engagement_means: list[str] = Field(
        default_factory=list,
        description="Delivery systems cleared for TST prosecution.",
    )
    cde_level: Optional[CDELevel] = Field(
        default=None,
        description="Pre-approved CDE ceiling; engagements beyond this ceiling require additional approval.",
    )
    roe_constraints: Optional[str] = Field(
        default=None,
        description="TST-specific ROE constraints beyond baseline.",
    )
    collection_requirements: list[str] = Field(
        default_factory=list,
        description="Collection assets cued on this TST (ISR platforms, SIGINT, HUMINT reports).",
    )
    notification_requirements: list[str] = Field(
        default_factory=list,
        description="Entities to notify immediately on detection or prosecution (e.g. 'JFACC', 'adjacent JSOTF').",
    )
    expiration_criteria: Optional[str] = Field(
        default=None,
        description="Conditions under which this TST is removed from the list (e.g. 'neutralization confirmed via BDA' or DTG).",
    )
    linked_pir: list[int] = Field(
        default_factory=list,
        description="PIR numbers whose answer depends on finding or engaging this TST.",
    )


# ---------------------------------------------------------------------------
# Airspace architecture — stable CAS/DCA/OCA structure published in OPORD.
# Sortie-level tasking against these (TOT, loadout, callsign) lives in FRAGOs.
# ---------------------------------------------------------------------------
AirspaceZoneKind = Literal[
    "ROZ",       # Restricted Operations Zone (typ. CAS stack)
    "HIDACZ",    # High-Density Airspace Control Zone
    "MEZ",       # Missile Engagement Zone
    "FEZ",       # Fighter Engagement Zone
    "JEZ",       # Joint Engagement Zone
    "NFZ",       # No-Fly Zone
    "SAR",       # Search-and-Rescue corridor
    "SAFE",      # Safe Area for Evasion
]

RefuelingMethod = Literal["BOOM", "DROGUE", "BOTH"]

OrbitGeometry = Literal["RACETRACK", "FIGURE_EIGHT", "CIRCLE", "LINEAR"]

GeoRefKind = Literal[
    "BULLSEYE",    # Named reference for BRAA / bearing-range calls
    "IP",          # Initial Point (strike run-in origin)
    "CP",          # Contact Point (inbound airspace entry)
    "ANCHOR",      # Anchor point for a CAP / AAR orbit
    "WAYPOINT",    # Generic named steerpoint
    "EGRESS_PT",   # Egress reference
    "FIX",         # Navigation fix
    "NAVAID",      # Ground-based VOR / TACAN / NDB
]


class GeoRef(_Base):
    """Named geographic reference point — bullseye, IP, CP, anchor, waypoint,
    NAVAID. Pilots call positions BRAA or bearing/range from these. An OPORD
    may publish multiple (primary bullseye + backup + named waypoints)."""

    name: str = Field(description="Callsign or designator (e.g. 'BULLSEYE', 'IP ALPHA', 'CP DOG').")
    kind: GeoRefKind = Field(description="Reference-point category.")
    coordinates: str = Field(description="MGRS, L/L, or game-specific coordinate string.")
    altitude_ft: Optional[int] = Field(
        default=None, description="Altitude in feet MSL when applicable (NAVAIDs, elevated fixes)."
    )
    tacan_channel: Optional[str] = Field(
        default=None, description="TACAN channel + band when the reference is a NAVAID (e.g. '73X')."
    )
    effective_dtg: Optional[DTGString] = Field(
        default=None, description="DTG this reference becomes effective; omit for always-active."
    )
    notes: Optional[str] = Field(
        default=None, description="Freeform notes (e.g. 'Primary bullseye; all BRAA calls reference this point')."
    )


class AirspaceZone(_Base):
    """Published airspace zone with a single ``kind`` discriminator covering
    ROZ / HIDACZ / weapon engagement zones / no-fly / SAR / safe areas. Shape
    is either a circle (anchor + radius) or a polygon (ordered vertex list)."""

    name: str = Field(description="Zone designator (e.g. 'ROZ HAMMER', 'MEZ NORTH', 'NFZ ALTENSTADT').")
    kind: AirspaceZoneKind = Field(description="Zone category.")
    anchor_point: Optional[str] = Field(
        default=None, description="Circle anchor (coordinates); used when the zone is radial."
    )
    radius_nm: Optional[float] = Field(
        default=None, description="Circle radius in nautical miles; used with ``anchor_point``."
    )
    polygon_vertices: list[str] = Field(
        default_factory=list,
        description="Ordered polygon vertices (coordinate strings); used when the zone is non-circular."
    )
    altitude_floor_ft: int = Field(description="Floor altitude (feet MSL).")
    altitude_ceiling_ft: int = Field(description="Ceiling altitude (feet MSL).")
    active_dtg_start: Optional[DTGString] = Field(
        default=None, description="DTG zone becomes active; omit for always-active."
    )
    active_dtg_end: Optional[DTGString] = Field(
        default=None, description="DTG zone becomes inactive; omit for duration of operation."
    )
    purpose: str = Field(description="Short purpose statement (e.g. 'CAS stack over OBJ HAMMER').")
    engagement_rules: Optional[str] = Field(
        default=None,
        description="WEZ variants only — engagement authority/constraints (e.g. 'Patriot missile layer; fighters stay above 25000ft')."
    )


class CAPTrack(_Base):
    """Named Combat Air Patrol orbit. FRAGOs assign flights to these by name
    (e.g. 'FLY ANCHOR 1') rather than re-publishing the track geometry."""

    name: str = Field(description="Track/station designator (e.g. 'ANCHOR 1', 'CAP EAST').")
    anchor_point: str = Field(description="Anchor coordinates.")
    altitude_floor_ft: int = Field(description="Floor altitude (feet MSL).")
    altitude_ceiling_ft: int = Field(description="Ceiling altitude (feet MSL).")
    orbit_geometry: OrbitGeometry = Field(
        default="RACETRACK", description="Orbit pattern."
    )
    orbit_heading: Optional[int] = Field(
        default=None, description="Primary orbit heading in degrees true (for RACETRACK/LINEAR)."
    )
    orbit_leg_length_nm: Optional[float] = Field(
        default=None, description="Leg length in nautical miles (for RACETRACK / FIGURE_EIGHT)."
    )
    controller_callsign: str = Field(
        description="Controlling agency callsign (usually AWACS or AIC, e.g. 'MAGIC')."
    )
    primary_freq: str = Field(description="Primary tactical frequency (e.g. '251.0 AM', 'V15').")
    sector_of_responsibility: Optional[str] = Field(
        default=None, description="Responsible sector / engagement area."
    )


class AARTrack(_Base):
    """Named Air-to-Air Refueling track. Tanker assignments to the track are
    made in FRAGOs; the OPORD publishes the enduring geometry + radios."""

    name: str = Field(description="Track designator (e.g. 'TRACK ARCO', 'TRACK SHELL').")
    anchor_primary: str = Field(description="Primary anchor coordinates.")
    anchor_secondary: Optional[str] = Field(
        default=None, description="Secondary anchor (end of track for racetrack tracks)."
    )
    track_heading: Optional[int] = Field(
        default=None, description="Track heading in degrees true (when not defined by two anchors)."
    )
    track_length_nm: Optional[float] = Field(
        default=None, description="Track length in nautical miles."
    )
    altitude_floor_ft: int = Field(description="Altitude block floor (feet MSL).")
    altitude_ceiling_ft: int = Field(description="Altitude block ceiling (feet MSL).")
    refueling_method: RefuelingMethod = Field(description="Boom, drogue, or both (track-dependent).")
    tanker_types_supported: list[str] = Field(
        default_factory=list,
        description="Airframes that can occupy this track (e.g. 'KC-135R', 'KC-46A', 'KC-130J', 'S-3B')."
    )
    tacan_channel: Optional[str] = Field(
        default=None, description="Track TACAN channel (e.g. '63Y')."
    )
    primary_freq: str = Field(description="Primary track frequency.")
    secondary_freq: Optional[str] = Field(
        default=None, description="Backup / boom-talk frequency."
    )
    active_dtg_start: Optional[DTGString] = Field(
        default=None, description="Track active from this DTG."
    )
    active_dtg_end: Optional[DTGString] = Field(
        default=None, description="Track inactive after this DTG."
    )


class AWACSOrbit(_Base):
    """Persistent AWACS / airborne-C2 orbit. Daily ATO tasks specific airframes
    into these orbits; the OPORD publishes the station framework."""

    callsign: str = Field(description="AWACS callsign (e.g. 'MAGIC', 'OVERLORD', 'DARKSTAR').")
    platform: str = Field(description="Airframe (e.g. 'E-3G Sentry', 'E-2D Hawkeye', 'KJ-2000').")
    orbit_center: str = Field(description="Orbit center coordinates.")
    orbit_radius_nm: float = Field(description="Orbit radius in nautical miles.")
    altitude_ft: int = Field(description="Orbit altitude (feet MSL).")
    on_station_dtg: Optional[DTGString] = Field(
        default=None, description="On-station DTG."
    )
    off_station_dtg: Optional[DTGString] = Field(
        default=None, description="Off-station DTG."
    )
    sector_of_responsibility: Optional[str] = Field(
        default=None, description="Primary airspace sector covered."
    )
    primary_freq: str = Field(description="Primary control frequency.")
    datalink_channel: Optional[str] = Field(
        default=None, description="Link-16 channel / MIDS net / DCS datalink ID."
    )
    owns_bullseye: Optional[str] = Field(
        default=None,
        description="Bullseye GeoRef name this orbit publishes (matches a GeoRef entry)."
    )


class AICSector(_Base):
    """Air Intercept Controller sector — sub-sector inside an AWACS orbit's
    coverage, assigned to a named controller."""

    sector_name: str = Field(description="Sector designator (e.g. 'SECTOR NORTH', 'RED 1').")
    controller_callsign: str = Field(description="Controller callsign.")
    responsible_geography: str = Field(
        description="Sector definition (e.g. '090-180 from BULLSEYE, 0-200nm, 0-45000ft')."
    )
    primary_freq: str = Field(description="Sector primary frequency.")
    secondary_freq: Optional[str] = Field(
        default=None, description="Backup frequency."
    )
    reports_to: str = Field(description="Parent AWACS callsign this controller reports to.")


class MinimumRiskRoute(_Base):
    """Minimum-Risk Route (MRR) / ingress or egress corridor. Published with
    named waypoints that flights follow to avoid friendly fires and SAM rings."""

    name: str = Field(description="Route designator (e.g. 'MRR BRAVO', 'INGRESS CORRIDOR 1').")
    direction: Literal["INGRESS", "EGRESS", "BIDIRECTIONAL"] = Field(
        description="Authorized direction of travel."
    )
    waypoints: list[str] = Field(
        default_factory=list,
        description="Ordered waypoints along the route (coordinate strings or GeoRef names)."
    )
    altitude_floor_ft: int = Field(description="Minimum altitude (feet MSL).")
    altitude_ceiling_ft: int = Field(description="Maximum altitude (feet MSL).")
    active_dtg_start: Optional[DTGString] = Field(
        default=None, description="Route active from this DTG."
    )
    active_dtg_end: Optional[DTGString] = Field(
        default=None, description="Route inactive after this DTG."
    )
    purpose: str = Field(
        description="Purpose / use case (e.g. 'Rotary-wing ingress to OBJ HAMMER')."
    )


class AirspaceControl(_Base):
    """Stable airspace architecture published in Annex C Operations. FRAGOs
    reference these by name when tasking sorties into specific tracks, stations,
    or zones — the OPORD publishes geometry, radios, and controller callsigns
    once and FRAGOs consume them by reference."""

    geo_refs: list[GeoRef] = Field(
        default_factory=list,
        description="Named geographic reference points (bullseye, IP, CP, anchor, waypoint, NAVAID). Multiple bullseyes allowed — e.g. a primary + alternate for split-sector BRAA calls."
    )
    airspace_zones: list[AirspaceZone] = Field(
        default_factory=list,
        description="Published airspace zones (ROZ, HIDACZ, MEZ/FEZ/JEZ, NFZ, SAR corridor, Safe Area) with geometry + altitude block + active window."
    )
    cap_tracks: list[CAPTrack] = Field(
        default_factory=list,
        description="Combat Air Patrol stations / orbits. FRAGOs assign flights to these by name."
    )
    aar_tracks: list[AARTrack] = Field(
        default_factory=list,
        description="Air-to-Air Refueling tracks with altitude block, refueling method, frequencies, and supported tanker types."
    )
    awacs_orbits: list[AWACSOrbit] = Field(
        default_factory=list,
        description="Persistent AWACS / airborne-C2 orbits with callsign, platform, orbit center, and station window."
    )
    aic_sectors: list[AICSector] = Field(
        default_factory=list,
        description="Air Intercept Controller sub-sectors inside AWACS coverage, each with a named controller and freq."
    )
    ingress_corridors: list[MinimumRiskRoute] = Field(
        default_factory=list,
        description="Minimum-Risk Routes / published ingress/egress corridors."
    )


# ---------------------------------------------------------------------------
# Collateral Damage Estimation per CJCSI 3160.01.
# Defines the five escalating CDE levels, engagement authority at each level,
# and operation-specific CDE posture (methodology, LOAC review, NSL/RTL).
# ---------------------------------------------------------------------------
class CDELevelDefinition(_Base):
    """One row defining a Collateral Damage Estimation level per CJCSI 3160.01."""

    level: CDELevel = Field(
        description="CDE level identifier (CDE-1 through CDE-5)."
    )
    name: str = Field(
        description="Short doctrinal name (e.g. 'Target Validation', 'Casualty Estimation')."
    )
    description: str = Field(
        description="What this CDE step entails and the conditions under which it applies."
    )
    engagement_authority: str = Field(
        description="Baseline engagement-approval echelon for this level (e.g. 'BN CDR', 'JFLCC', 'CJCS/SECDEF')."
    )
    documentation_required: list[str] = Field(
        default_factory=list,
        description="Documentation required to satisfy this level (imagery, target folder, weaponeering worksheet, LOAC review)."
    )


class CDEGuidance(_Base):
    """Collateral Damage Estimation guidance block per CJCSI 3160.01.

    Published in Annex D (Fires) so the CDE level referenced on every JPITL,
    TST, HPTL, and 9-line CAS entry ties back to a single operation-wide
    definition of levels, engagement authorities, weaponeering methodology,
    LOAC review authority, and No-Strike / Restricted Target List references."""

    levels: list[CDELevelDefinition] = Field(
        default_factory=list,
        description="Per-level CDE definitions. Typically all five levels are included with doctrinal text so readers understand each reference."
    )
    commanders_guidance: Optional[str] = Field(
        default=None,
        description="Commander's narrative guidance on CDE posture for this operation (e.g. 'favor precision delivery; CDE-3 default for all dynamic targeting')."
    )
    weaponeering_methodology: Optional[str] = Field(
        default=None,
        description="Weaponeering methodology in use (e.g. 'JMEM', 'Precision Strike Suite (PSS-SOF) v6.1')."
    )
    loac_review_authority: Optional[str] = Field(
        default=None,
        description="LOAC review authority for target packets at CDE-3 and above (e.g. 'CJTF SJA', 'OSJA')."
    )
    no_strike_list_reference: Optional[str] = Field(
        default=None,
        description="Current No-Strike List (NSL) version/date in effect for this operation."
    )
    restricted_target_list_reference: Optional[str] = Field(
        default=None,
        description="Current Restricted Target List (RTL) version/date in effect for this operation."
    )
    documentation_requirements: list[str] = Field(
        default_factory=list,
        description="Common documentation expected on every target-approval packet (target folder, imagery, PID evidence, weaponeering worksheet, CDE worksheet, LOAC review memo)."
    )
    additional_notes: Optional[str] = Field(
        default=None,
        description="Additional CDE-related policy or notes specific to this operation (dynamic-targeting abort authorities, NGO proximity policies, etc.)."
    )


# ---------------------------------------------------------------------------
# 9-Line CAS brief per JP 3-09.3 / AFTTP(I) 3-2.6.
# Tactical terminal-control brief passed from JTAC/FAC(A) to CAS aircraft.
# Distinct from CASRequest (preplanned mission request) — this is the run-in
# instruction tied to a specific target engagement.
# ---------------------------------------------------------------------------
CASControlType = Literal["TYPE_1", "TYPE_2", "TYPE_3"]
"""CAS terminal control type per JP 3-09.3.
TYPE_1 = JTAC visual on both target and aircraft;
TYPE_2 = JTAC visual on one of the two;
TYPE_3 = bulk-clearance for a target area / time window."""

CASMarkType = Literal[
    "LASER", "IR_POINTER", "SMOKE", "WP", "GOGGLES", "FLARE", "NONE",
]
"""Target-marking methods available to a JTAC/FAC(A)."""


class NineLineCAS(_Base):
    """9-Line CAS brief — structured tactical brief passed from JTAC/FAC(A)
    to CAS aircraft per JP 3-09.3 / AFTTP 3-2.6.

    Line order follows doctrinal format: IP → heading → distance → target
    elevation → target description → target location → mark → friendlies →
    egress. Remarks follow after line 9 (threats, hazards, laser code, TOT,
    danger-close ground-commander initials, terminal-control type)."""

    # Line 1 — IP / BP
    ip_or_bp: str = Field(
        description="Initial Point or Battle Position — named reference or coordinates where the aircraft starts the attack run. May reference a published GeoRef (e.g. 'IP ALPHA')."
    )
    # Line 2 — Heading (magnetic, IP to target)
    heading_magnetic: int = Field(
        description="Magnetic heading from IP/BP to target, in degrees (000-359)."
    )
    heading_offset: Optional[Literal["L", "R"]] = Field(
        default=None,
        description="Offset side (L or R) when a non-direct attack geometry is required."
    )
    # Line 3 — Distance
    distance_nm: float = Field(
        description="Distance from IP/BP to target in nautical miles (tenths permitted)."
    )
    # Line 4 — Target elevation
    target_elevation_ft: int = Field(
        description="Target elevation in feet MSL."
    )
    # Line 5 — Target description
    target_description: str = Field(
        description="Target type and configuration (e.g. '3x T-72 tanks in hasty defense vic tree line')."
    )
    # Line 6 — Target location
    target_location: str = Field(
        description="Target location — MGRS, L/L, or offset from IP (bearing/distance). Match the format in use for the AO."
    )
    # Line 7 — Mark type
    mark_type: CASMarkType = Field(
        description="How the target will be marked for the aircraft."
    )
    laser_code: Optional[str] = Field(
        default=None,
        description="4-digit laser PRF code (e.g. '1688') when mark_type is LASER."
    )
    # Line 8 — Friendlies
    friendlies_distance_m: int = Field(
        description="Distance from target to nearest friendlies, in METERS."
    )
    friendlies_direction: str = Field(
        description="Direction from target to friendlies (cardinal or octant, e.g. 'N', 'SW')."
    )
    friendlies_marking: Optional[str] = Field(
        default=None,
        description="How friendlies are marked (VS-17 panel, IR strobe, chemlight color, smoke, etc.)."
    )
    # Line 9 — Egress
    egress: str = Field(
        description="Egress direction / instructions after weapons release (e.g. 'SOUTH LOW', 'TRACK NORTH TO IP ALPHA')."
    )

    # Remarks block (appended after line 9)
    final_attack_heading: Optional[int] = Field(
        default=None,
        description="Final Attack Heading (FAH) in degrees magnetic, if restricted for deconfliction or terrain."
    )
    time_on_target: Optional[DTGString] = Field(
        default=None,
        description="Planned Time On Target (TOT) DTG."
    )
    time_to_target_min: Optional[int] = Field(
        default=None,
        description="Time To Target (TTT) in minutes from push, if a relative timing is in use instead of TOT."
    )
    type_of_control: Optional[CASControlType] = Field(
        default=None,
        description="CAS terminal control type per JP 3-09.3 (Type 1/2/3)."
    )
    control_agency: Optional[str] = Field(
        default=None,
        description="Controlling JTAC / FAC(A) callsign (e.g. 'DAGGER 11', 'VIPER 11 FAC(A)')."
    )
    cas_callsign: Optional[str] = Field(
        default=None,
        description="CAS flight callsign being briefed (e.g. 'UZI 11 flight of 2 F-16C')."
    )
    threats: list[str] = Field(
        default_factory=list,
        description="Known or suspected threats in the target area (SA-13, ZU-23-2, MANPADS, etc.)."
    )
    hazards: list[str] = Field(
        default_factory=list,
        description="Weather, terrain, or artificial hazards (low ceilings, wires, balloons, restricted airspace)."
    )
    danger_close: bool = Field(
        default=False,
        description="True when friendlies are inside danger-close distance for the planned ordnance; requires ground commander initials."
    )
    ground_commander_initials: Optional[str] = Field(
        default=None,
        description="Initials of the ground commander authorizing the strike; required when danger_close is True."
    )
    remarks: Optional[str] = Field(
        default=None,
        description="Freeform remarks appended to the brief (abort code, restrictions, rules of engagement nuances)."
    )


class EnemyCOA(_Base):
    """An Enemy Course of Action produced by IPB step 4 per ATP 2-01.3."""

    designation: Literal["MLCOA", "MDCOA", "COA_3", "COA_4"] = Field(
        description="Standard designator: Most Likely, Most Dangerous, or additional analytic COAs.",
    )
    title: str = Field(
        description="Short descriptive title of the COA (e.g. 'Defend from KUMOR RIDGE').",
    )
    narrative: str = Field(
        description="Narrative of how the enemy is assessed to execute this COA.",
    )
    indicators: list[str] = Field(
        default_factory=list,
        description="Observable indicators that, if seen, suggest the enemy has adopted this COA.",
    )
    adoption_probability: Optional[Literal["high", "medium", "low"]] = Field(
        default=None,
        description="Analyst confidence that the enemy will adopt this COA.",
    )
    associated_nais: list[str] = Field(
        default_factory=list,
        description="NAIs whose observation confirms or denies this COA.",
    )


# ---------------------------------------------------------------------------
# Decision Support / collection
# ---------------------------------------------------------------------------
class DecisionPoint(_Base):
    """A Decision Point on the Decision Support Matrix per FM 6-0 App D."""

    dp_number: int = Field(
        description="Sequential decision-point number (DP 1, DP 2, ...).",
    )
    name: str = Field(
        description="Short descriptive name for the decision (e.g. 'Commit Reserve').",
    )
    location_or_nai: str = Field(
        description="Physical location (grid) or NAI whose observation triggers the decision.",
    )
    latest_time_info_of_value: str = Field(
        description="LTIOV for the information required to make this decision.",
    )
    trigger: str = Field(
        description="The observable event or condition that forces a decision at this point.",
    )
    criteria: list[str] = Field(
        default_factory=list,
        description="Criteria evaluated when the trigger fires to select the action.",
    )
    action: str = Field(
        description="Action executed when the criteria are met.",
    )
    alternate_action: Optional[str] = Field(
        default=None,
        description="Alternate action if criteria are not met or conditions change.",
    )
    linked_ccir: list[str] = Field(
        default_factory=list,
        description="CCIR (PIR or FFIR) identifiers whose answers inform this decision.",
    )
    responsible_staff: str = Field(
        description="Staff section or cell responsible for recommending the decision.",
    )
    phase: int = Field(
        description="Operation phase in which this DP is active (1-based).",
    )


class NamedAreaOfInterest(_Base):
    """A Named Area of Interest (NAI) on the intelligence collection overlay."""

    name: str = Field(
        description="NAI designator (e.g. 'NAI 101').",
    )
    grid_or_boundary: str = Field(
        description="MGRS grid (point) or ordered coordinates (line/area) that define the NAI.",
    )
    shape: Literal["POINT", "LINE", "AREA"] = Field(
        description="Geometric shape of the NAI.",
    )
    linked_pir: list[str] = Field(
        default_factory=list,
        description="PIR identifiers (e.g. 'PIR 1') this NAI supports.",
    )
    linked_dp: Optional[str] = Field(
        default=None,
        description="Decision-point identifier this NAI supports, if any.",
    )
    activation_dtg: DTGString = Field(
        description="DTG the NAI becomes active for collection.",
    )
    deactivation_dtg: DTGString = Field(
        description="DTG the NAI ceases collection.",
    )
    primary_collector: str = Field(
        description="Primary collection asset or unit assigned to this NAI.",
    )
    alternate_collector: Optional[str] = Field(
        default=None,
        description="Alternate collector used if the primary is unavailable.",
    )


# ---------------------------------------------------------------------------
# Tasks, battle rhythm, reports
# ---------------------------------------------------------------------------
class SubordinateTaskItem(_Base):
    """A single task assigned to a subordinate unit, used inside typed_body structured lists.

    Note: the core 5-paragraph model uses :class:`opord_builder.schema.core.SubordinateTask`
    which groups multiple tasks per unit. This lighter variant is used where a flat list of
    unit/task/purpose triples is more natural (e.g. Annex C phase tasks).
    """

    unit: str = Field(
        description="Subordinate unit receiving the task.",
    )
    task: str = Field(
        description="Specified task phrased with a doctrinal tactical-task verb.",
    )
    purpose: str = Field(
        description="Purpose tying the task to the higher mission and intent.",
    )
    nlt_dtg: Optional[DTGString] = Field(
        default=None,
        description="Not-Later-Than DTG by which the task must be complete.",
    )


class BattleRhythmEvent(_Base):
    """A recurring command-and-staff event on the battle rhythm per ATP 6-0.5."""

    event_name: str = Field(
        description="Event name (e.g. 'CUB', 'Targeting WG', 'Sustainment SYNC').",
    )
    event_type: Literal[
        "brief",
        "working_group",
        "board",
        "sync",
        "shift_change",
        "decision_board",
    ] = Field(
        description="Doctrinal event type.",
    )
    dtg_or_cadence: str = Field(
        description="Cadence (e.g. 'Daily 0700', 'Tu/Th 1400') or specific DTG.",
    )
    duration_minutes: Optional[int] = Field(
        default=None,
        description="Scheduled duration in minutes.",
    )
    location: str = Field(
        description="Physical or virtual location (CP, VTC room, etc.).",
    )
    chair: str = Field(
        description="Officer or duty position chairing the event.",
    )
    attendees: list[str] = Field(
        default_factory=list,
        description="Required attendees by duty title or staff section.",
    )
    inputs: list[str] = Field(
        default_factory=list,
        description="Required inputs brought to the event (products, estimates, reports).",
    )
    outputs: list[str] = Field(
        default_factory=list,
        description="Products or decisions the event produces.",
    )


class ReportDefinition(_Base):
    """A reporting requirement per ATP 6-02.x and unit SOP."""

    name: str = Field(
        description="Report name (e.g. 'SITREP', 'LOGSTAT', 'CASREP').",
    )
    format_ref: Optional[str] = Field(
        default=None,
        description="Reference to the format specification (SOP paragraph, USMTF form, etc.).",
    )
    submitter: str = Field(
        description="Unit or staff section required to submit the report.",
    )
    recipient: str = Field(
        description="Recipient of the report.",
    )
    frequency: str = Field(
        description="Submission frequency (e.g. 'Daily NLT 0600', 'On event').",
    )
    precedence: Literal["FLASH", "IMMEDIATE", "PRIORITY", "ROUTINE"] = Field(
        description="Message precedence per JP 6-0.",
    )
    medium: str = Field(
        description="Transmission medium (e.g. 'SIPR email', 'FM voice', 'JBC-P').",
    )
    trigger: str = Field(
        description="Event or schedule that triggers submission.",
    )
    classification: Optional[str] = Field(
        default=None,
        description="Maximum classification of the report content.",
    )


# ---------------------------------------------------------------------------
# Classification marking
# ---------------------------------------------------------------------------
class ClassificationMarking(_Base):
    """An overall classification marking with dissemination controls and SCI compartments."""

    overall_classification: Literal[
        "UNCLASSIFIED",
        "CUI",
        "CONFIDENTIAL",
        "SECRET",
        "TOP SECRET",
    ] = Field(
        description="Overall classification level per AR 380-5 / EO 13526.",
    )
    dissemination_controls: list[str] = Field(
        default_factory=list,
        description="Dissemination-control markings (e.g. 'NOFORN', 'REL TO USA, FVEY', 'ORCON').",
    )
    sci_compartments: list[str] = Field(
        default_factory=list,
        description="SCI compartments and subcompartments (e.g. 'SI', 'TK', 'G').",
    )
    declassify_on: Optional[str] = Field(
        default=None,
        description="Declassification instruction (date, event, or exemption code).",
    )


# ---------------------------------------------------------------------------
# Medical / health services (Annex F)
# ---------------------------------------------------------------------------
class RoleOfCare(_Base):
    """A Role 1–4 medical treatment facility per ATP 4-02 / FM 4-02."""

    role_level: Literal["Role 1", "Role 2", "Role 3", "Role 4"] = Field(
        description="Doctrinal role of care.",
    )
    facility_name: str = Field(
        description="Facility name (BAS, FST, CSH, etc.).",
    )
    location: MGRSGrid = Field(
        description="MGRS grid of the facility.",
    )
    operator_unit: str = Field(
        description="Unit operating the facility.",
    )
    capabilities: list[str] = Field(
        default_factory=list,
        description="Clinical capabilities present (e.g. 'damage control surgery', 'FWB transfusion', 'dental').",
    )
    bed_capacity: Optional[int] = Field(
        default=None,
        description="Patient bed capacity of the facility.",
    )


class AmbulanceExchangePoint(_Base):
    """An Ambulance Exchange Point (AXP) where casualty handoff occurs between evac assets."""

    axp_name: str = Field(
        description="AXP designator (e.g. 'AXP BLUE').",
    )
    grid: MGRSGrid = Field(
        description="MGRS grid of the AXP.",
    )
    operator_unit: str = Field(
        description="Unit operating the AXP.",
    )
    alternate_axp: Optional[str] = Field(
        default=None,
        description="Alternate AXP name if the primary is non-functional.",
    )
    established_nlt: DTGString = Field(
        description="DTG by which the AXP must be operational.",
    )
    comms_net: str = Field(
        description="Radio net used to coordinate casualty handoff at this AXP.",
    )


class LogisticsSchedule(_Base):
    """A recurring logistics schedule (e.g. LOGPAC)."""

    logpac_interval_hours: int = Field(
        description="Interval in hours between successive logistics packages.",
    )
    first_logpac_dtg: DTGString = Field(
        description="DTG of the first scheduled LOGPAC.",
    )
    link_up_point: str = Field(
        description="Named link-up point or grid where LOGPACs meet supported units.",
    )
    composition: list[str] = Field(
        default_factory=list,
        description="Standard LOGPAC composition (trucks, fuel, water, ammo, mail, personnel).",
    )
    escort_requirement: Optional[str] = Field(
        default=None,
        description="Required escort posture (none, DS platoon, GS section) based on threat assessment.",
    )


class MSRoute(_Base):
    """A Main Supply Route (MSR) per ATP 4-16."""

    name: str = Field(
        description="MSR designator (e.g. 'MSR IRON').",
    )
    start_point: str = Field(
        description="Start-point grid or named location.",
    )
    release_point: str = Field(
        description="Release-point grid or named location.",
    )
    checkpoints: list[str] = Field(
        default_factory=list,
        description="Ordered checkpoints along the route.",
    )
    hazards: list[str] = Field(
        default_factory=list,
        description="Known hazards (choke points, known-IED grids, restricted bridges).",
    )
    controlling_hq: str = Field(
        description="Headquarters responsible for movement control on this route.",
    )


# Alternate Supply Routes share the same shape as MSRs per ATP 4-16; the
# distinction is purely which route is primary vs. alternate at planning time.
ASRoute = MSRoute


# ---------------------------------------------------------------------------
# WARNO planning timeline (FM 6-0 / ATP 5-0.2-1)
# ---------------------------------------------------------------------------
class PlanningMilestone(_Base):
    """A single planning milestone on a WARNO's parallel-planning timeline.

    WARNOs publish these to orient subordinates on recon LDs, confirmation
    briefs, rehearsals, OPORD issue, and LD so parallel planning can begin
    before the full OPORD is available."""

    event: str = Field(
        description="Short event name (e.g. 'Recon LD', 'Confirmation Brief', 'Combined-Arms Rehearsal', 'OPORD Issue', 'LD')."
    )
    dtg: str = Field(
        description="Scheduled DTG for the event (DDHHMMZMONYY or free-form if approximate)."
    )
    responsible: Optional[str] = Field(
        default=None,
        description="Unit or staff element responsible for executing the event."
    )
    notes: Optional[str] = Field(
        default=None,
        description="Free-text notes (location, attendees, preconditions)."
    )


RehearsalType = Literal[
    "full-dress",
    "reduced-force",
    "terrain-model",
    "map",
    "sketch-map",
    "radio",
    "backbrief",
]
"""Doctrinal rehearsal type per FM 6-0 Appendix F."""


class RehearsalPlan(_Base):
    """Rehearsal guidance published in Coordinating Instructions per FM 6-0 App F."""

    type: Optional[RehearsalType] = Field(
        default=None,
        description="Rehearsal type per FM 6-0 Appendix F.",
    )
    dtg: Optional[str] = Field(
        default=None,
        description="Scheduled DTG of the rehearsal (DDHHMMZMONYY).",
    )
    location: Optional[str] = Field(
        default=None,
        description="Rehearsal location (TOC, terrain-model site, AA, grid).",
    )
    participants: Optional[str] = Field(
        default=None,
        description="Required participants by duty title, staff section, or subordinate unit.",
    )
    method_notes: Optional[str] = Field(
        default=None,
        description="Method and sequence notes (script, actions-on drills, priority of rehearsal, uniform/kit).",
    )


class OrdersGroup(_Base):
    """Commander's orders group meeting per FM 6-0 / ATP 5-0.2-1.

    The orders group is the session at which the commander personally issues
    the order to subordinate commanders and key staff. Coordinating
    Instructions publish purpose, DTG, location, attendees, and products
    distributed so subordinates arrive prepared."""

    purpose: Optional[str] = Field(
        default=None,
        description="Purpose of the orders group (issue OPORD, confirmation brief, back-brief).",
    )
    dtg: Optional[str] = Field(
        default=None,
        description="DTG the orders group convenes (DDHHMMZMONYY).",
    )
    location: Optional[str] = Field(
        default=None,
        description="Physical or virtual location (TOC, VTC room, map-brief site).",
    )
    attendees: Optional[str] = Field(
        default=None,
        description="Required attendees by duty title, subordinate commander, or staff section.",
    )
    products_distributed: Optional[str] = Field(
        default=None,
        description="Products handed out at the orders group (OPORD, overlays, matrices, keys).",
    )


# ---------------------------------------------------------------------------
# Kneeboard card — DCS World / print kneeboard generation
# ---------------------------------------------------------------------------
class KneeboardPosition(_Base):
    """Single aircraft position within a flight."""

    number: int = Field(
        description="Position in flight (1 = lead, 2 = wingman, etc.)."
    )
    modex: str = Field(
        default="",
        description="Aircraft modex / side number (e.g. '420').",
    )
    pers: str = Field(
        default="",
        description="Pilot name, initials, or callsign.",
    )
    laser: str = Field(
        default="",
        description="Laser PRF code (4-digit, e.g. '1781').",
    )


class KneeboardTACAN(_Base):
    """TACAN channel plan for the flight."""

    lead: str = Field(
        default="",
        description="Lead TACAN channel (e.g. '14Y').",
    )
    flight: str = Field(
        default="",
        description="Flight common TACAN channel (e.g. '77Y').",
    )


class KneeboardFuelPlan(_Base):
    """Fuel planning figures in pounds."""

    msn_req_lbs: int = Field(
        description="Mission-required fuel in pounds.",
    )
    joker_lbs: int = Field(
        description="Joker fuel state in pounds.",
    )
    bingo_lbs: int = Field(
        description="Bingo fuel state in pounds.",
    )
    rcv_tank_lbs: int = Field(
        default=0,
        description="Receive-tank fuel in pounds (carrier ops).",
    )


class KneeboardCommsPhase(_Base):
    """Radio assignments for one mission phase."""

    phase: str = Field(
        description="Phase name (e.g. 'DECK OPS', 'REJOIN', 'PUSH', 'EGRESS', 'RECOVERY').",
    )
    comm1: str = Field(
        default="",
        description="COMM 1 radio assignment for this phase.",
    )
    comm2: str = Field(
        default="",
        description="COMM 2 radio assignment for this phase.",
    )


class KneeboardTanker(_Base):
    """Tanker information entry."""

    callsign: str = Field(
        description="Tanker callsign (e.g. 'SHELL21').",
    )
    frequency: str = Field(
        default="",
        description="Tanker primary frequency (e.g. '240.100 MHz').",
    )
    tacan: str = Field(
        default="",
        description="Tanker TACAN channel (e.g. '41Y').",
    )
    button: str = Field(
        default="",
        description="Radio button/preset reference (e.g. 'BTN 16').",
    )


class KneeboardATCEntry(_Base):
    """Single ATC / control agency frequency entry."""

    name: str = Field(
        description="Agency name (e.g. 'MARSHAL', 'TOWER', 'DEPARTURE', 'AI CV CONTROLLER').",
    )
    frequency: str = Field(
        default="",
        description="Frequency with optional button (e.g. '241.600 MHz (BTN 19)').",
    )


class KneeboardCommsPlan(_Base):
    """Complete communications plan for the kneeboard card."""

    phases: list[KneeboardCommsPhase] = Field(
        default_factory=list,
        description="Radio assignments by mission phase.",
    )
    intra: str = Field(
        default="",
        description="Intraflight frequency (e.g. '276.500 MHz').",
    )
    mids: str = Field(
        default="",
        description="MIDS / Link-16 assignment.",
    )


class KneeboardCard(_Base):
    """A single kneeboard card for DCS World (768×1024 PNG) or print.

    Captures the tactical data a pilot needs on the knee: flight lineup,
    comms plan, fuel plan, objectives, tanker info, and ATC frequencies.
    Values can reference OPORD/FRAGO variables via Jinja2 interpolation."""

    title: str = Field(
        default="",
        description="Card title / header line (defaults to flight_callsign if blank).",
    )
    flight_callsign: str = Field(
        description="Flight callsign (e.g. 'LINER32').",
    )
    msn_number: str = Field(
        default="",
        description="Mission or serial number.",
    )
    positions: list[KneeboardPosition] = Field(
        default_factory=list,
        description="Aircraft positions in the flight (lead, wingmen).",
    )
    tacan: Optional[KneeboardTACAN] = Field(
        default=None,
        description="TACAN channel plan.",
    )
    primary_objectives: list[str] = Field(
        default_factory=list,
        description="Primary mission objectives.",
    )
    secondary_objectives: list[str] = Field(
        default_factory=list,
        description="Secondary mission objectives.",
    )
    weaponeering: str = Field(
        default="",
        description="Weaponeering notes / loadout.",
    )
    fuel_plan: Optional[KneeboardFuelPlan] = Field(
        default=None,
        description="Fuel planning figures.",
    )
    comms: Optional[KneeboardCommsPlan] = Field(
        default=None,
        description="Communications plan by phase.",
    )
    tankers: list[KneeboardTanker] = Field(
        default_factory=list,
        description="Tanker assignments.",
    )
    atc: list[KneeboardATCEntry] = Field(
        default_factory=list,
        description="ATC / control agency frequencies.",
    )
    baro_alt: str = Field(
        default="",
        description="Barometric altimeter setting (e.g. '29.92').",
    )
    notes: str = Field(
        default="",
        description="Freeform notes.",
    )


__all__ = [
    "DTGString",
    "MGRSGrid",
    "DoctrinalReference",
    "ControlMeasure",
    "FSCM",
    "ACM",
    "PIR",
    "HVT",
    "JPITLEntry",
    "TSTEntry",
    "DesiredEffect",
    "CDELevel",
    "TargetComponent",
    "JPITLStatus",
    "TSTPriorityClass",
    "TSTCategory",
    "GeoRef",
    "GeoRefKind",
    "AirspaceZone",
    "AirspaceZoneKind",
    "CAPTrack",
    "AARTrack",
    "AWACSOrbit",
    "AICSector",
    "MinimumRiskRoute",
    "RefuelingMethod",
    "OrbitGeometry",
    "AirspaceControl",
    "NineLineCAS",
    "CASControlType",
    "CASMarkType",
    "CDEGuidance",
    "CDELevelDefinition",
    "EnemyCOA",
    "DecisionPoint",
    "NamedAreaOfInterest",
    "SubordinateTaskItem",
    "BattleRhythmEvent",
    "ReportDefinition",
    "ClassificationMarking",
    "RoleOfCare",
    "AmbulanceExchangePoint",
    "LogisticsSchedule",
    "MSRoute",
    "ASRoute",
    "PlanningMilestone",
    "RehearsalPlan",
    "RehearsalType",
    "OrdersGroup",
    "KneeboardPosition",
    "KneeboardTACAN",
    "KneeboardFuelPlan",
    "KneeboardCommsPhase",
    "KneeboardTanker",
    "KneeboardATCEntry",
    "KneeboardCommsPlan",
    "KneeboardCard",
]
