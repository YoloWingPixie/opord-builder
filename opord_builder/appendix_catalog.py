"""Doctrinal catalog of canonical appendices for each U.S. Army OPORD annex.

This module encodes the authoritative appendix inventory defined by
FM 6-0 (May 2022) Appendix D and ATP 5-0.2-1 (Dec 2020), plus the functional
manual governing each annex (FM 2-0, FM 3-0, FM 3-09, FM 3-37, FM 4-0,
FM 3-34, FM 6-02, FM 3-61, FM 3-57, FM 3-55, ADP 5-0, FM 3-14, ATP 6-01.1,
FM 6-99, JP 3-08).

For every canonical annex letter (A-Z minus reserved I, O, T, W, X, Y) the
catalog exposes the ordered list of numbered appendices that doctrine
prescribes, each described by:

* ``number``    - the doctrinal appendix number within the annex.
* ``title``     - the canonical doctrinal title.
* ``purpose``   - one-to-two sentences summarizing content and intent.
* ``doctrine_reference`` - source publication and paragraph/chapter.
* ``fields``    - 4-12 canonical structured fields drawn from doctrine,
  typed using the short human-readable ``type_hint`` strings that align
  with the shared sub-types in :mod:`opord_builder.schema.shared`.

Annexes whose doctrinal template has no numbered appendices (A, P, S, U, Z)
are present with an empty list so callers can iterate the full canonical
alphabet without special-casing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AppendixField:
    """A single canonical field inside an appendix.

    ``type_hint`` is a short human-readable type string (e.g. ``"str"``,
    ``"list[PIR]"``, ``"DTGString"``) - it is intentionally a string rather
    than a live type so this catalog stays decoupled from the Pydantic
    models and can be consumed by renderers, prompt scaffolders, or UI
    form builders without importing the schema package.
    """

    name: str
    type_hint: str
    required: bool
    description: str


@dataclass(frozen=True)
class AppendixSpec:
    """A canonical numbered appendix within an annex."""

    number: int
    title: str
    purpose: str
    doctrine_reference: str
    fields: list[AppendixField]


# ---------------------------------------------------------------------------
# Annex B (Intelligence) - 8 appendices
# Source: FM 2-0 (Jul 2018), ATP 2-01.3 (Mar 2019), ATP 2-22.2-1/-2, FM 6-0 App D
# ---------------------------------------------------------------------------
_ANNEX_B: list[AppendixSpec] = [
    AppendixSpec(
        number=1,
        title="Intelligence Estimate",
        purpose=(
            "Running intelligence estimate covering the AO, threat, civil "
            "considerations, and analytic support to COA development."
        ),
        doctrine_reference="FM 2-0 Ch 3; ATP 2-01.3 Ch 5; FM 6-0 App D",
        fields=[
            AppendixField("as_of_dtg", "DTGString", True, "DTG the estimate was last updated."),
            AppendixField("area_of_operations", "str", True, "Description of the AO and area of interest that frames the estimate."),
            AppendixField("operational_environment_summary", "str", True, "PMESII-PT and METT-TC summary of the operational environment."),
            AppendixField("threat_characteristics", "str", True, "Threat composition, disposition, strength, doctrine, and capabilities."),
            AppendixField("enemy_coas", "list[EnemyCOA]", True, "Enemy COAs produced in IPB step 4 with MLCOA and MDCOA identified."),
            AppendixField("civil_considerations", "str", True, "ASCOPE analysis of the civil component of the AO."),
            AppendixField("weather_effects", "str", True, "Five-military-aspects-of-weather effects on friendly and threat operations."),
            AppendixField("terrain_effects", "str", True, "OAKOC terrain analysis and effects on friendly and threat operations."),
            AppendixField("intelligence_gaps", "list[str]", True, "Key unanswered intelligence requirements driving PIR and collection."),
            AppendixField("assessment_of_threat_coa_adoption", "str", True, "Analyst assessment of which enemy COA the threat is most likely to adopt and why."),
        ],
    ),
    AppendixSpec(
        number=2,
        title="Counterintelligence",
        purpose=(
            "Identifies foreign intelligence entity (FIE) threats, "
            "counterintelligence (CI) operations, and CI support to force protection."
        ),
        doctrine_reference="FM 2-0 Ch 6; FM 2-22.2; FM 6-0 App D",
        fields=[
            AppendixField("fie_threat_assessment", "str", True, "Assessment of foreign intelligence entity threats directed at friendly forces."),
            AppendixField("ci_priorities", "list[str]", True, "Prioritized CI objectives supporting the commander's intent."),
            AppendixField("ci_tasks", "list[SubordinateTaskItem]", True, "CI tasks assigned to subordinate CI elements."),
            AppendixField("cfso_coordination", "str", False, "Coordination requirements for CI force protection source operations."),
            AppendixField("insider_threat_measures", "list[str]", True, "Measures to detect, deter, and mitigate insider threats."),
            AppendixField("opsec_linkage", "str", True, "How CI findings feed Annex E Appendix 2 (OPSEC) and the OPSEC program."),
            AppendixField("ci_reporting_requirements", "list[ReportDefinition]", True, "Reports required from CI elements (e.g. SAEDA, TALON-equivalent)."),
            AppendixField("coordinating_instructions", "str", False, "CI coordinating instructions to subordinate and supporting units."),
        ],
    ),
    AppendixSpec(
        number=3,
        title="Signals Intelligence",
        purpose=(
            "Plans SIGINT collection, processing, exploitation, and dissemination "
            "in support of PIR and targeting."
        ),
        doctrine_reference="FM 2-0 Ch 4; ATP 2-22.2-1; FM 6-0 App D",
        fields=[
            AppendixField("sigint_task_organization", "str", True, "Task organization of SIGINT units, teams, and platforms supporting the operation."),
            AppendixField("collection_objectives", "list[str]", True, "SIGINT collection objectives linked to PIR and HVT/HPTs."),
            AppendixField("linked_pirs", "list[PIR]", True, "PIR that SIGINT is tasked to answer."),
            AppendixField("linked_hvts", "list[HVT]", False, "HVTs and HPTs whose signatures SIGINT will exploit."),
            AppendixField("sigint_platforms", "list[str]", True, "Airborne, ground, and national SIGINT platforms in support."),
            AppendixField("technical_control_measures", "list[str]", True, "Tipper, tasking, and technical control procedures (e.g. TECHCON)."),
            AppendixField("processing_exploitation_dissemination", "str", True, "PED architecture including supporting TROJAN, DCGS-A, and national elements."),
            AppendixField("reporting_channels", "list[ReportDefinition]", True, "SIGINT reporting formats, precedence, and dissemination paths."),
            AppendixField("release_and_sharing_authorities", "str", True, "Release, sanitization, and foreign-disclosure authorities governing SIGINT."),
        ],
    ),
    AppendixSpec(
        number=4,
        title="Human Intelligence",
        purpose=(
            "Plans HUMINT collection operations, source operations, "
            "interrogations, and debriefings in support of PIR."
        ),
        doctrine_reference="FM 2-0 Ch 4; ATP 2-22.3; FM 6-0 App D",
        fields=[
            AppendixField("humint_task_organization", "str", True, "HUMINT Collection Teams (HCTs), OMTs, and supporting elements."),
            AppendixField("collection_objectives", "list[str]", True, "Prioritized HUMINT collection objectives supporting PIR."),
            AppendixField("linked_pirs", "list[PIR]", True, "PIR assigned to HUMINT for collection."),
            AppendixField("source_operations_guidance", "str", True, "Commander's guidance and authorities for HUMINT source operations."),
            AppendixField("interrogation_guidance", "str", True, "Guidance for detainee interrogation IAW FM 2-22.3 and applicable law."),
            AppendixField("debriefing_operations", "str", False, "Debriefing plan for friendly forces, refugees, and local nationals."),
            AppendixField("document_media_exploitation", "str", False, "DOMEX procedures and supporting units."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", True, "HUMINT reports (IIR, SPOT, SALUTE) with submission instructions."),
            AppendixField("coordinating_instructions", "str", False, "Deconfliction with CI, MP, SOF, and partner-nation collection."),
        ],
    ),
    AppendixSpec(
        number=5,
        title="Geospatial Intelligence",
        purpose=(
            "Plans GEOINT production and dissemination - imagery, imagery "
            "intelligence, and geospatial information - supporting the operation."
        ),
        doctrine_reference="FM 2-0 Ch 4; ATP 2-22.7; FM 3-34.230",
        fields=[
            AppendixField("geoint_task_organization", "str", True, "GEOINT cells, imagery analysts, and supporting NGA/NSG elements."),
            AppendixField("foundation_geoint_products", "list[str]", True, "Foundation GEOINT products required (controlled imagery, DTED, urban 3D)."),
            AppendixField("collection_requirements", "list[str]", True, "Prioritized imagery and GEOINT collection requirements."),
            AppendixField("linked_pirs", "list[PIR]", True, "PIR supported by GEOINT collection and analysis."),
            AppendixField("nai_coverage_plan", "list[NamedAreaOfInterest]", True, "NAIs with required imagery revisit rates and resolutions."),
            AppendixField("production_priorities", "list[str]", True, "Prioritized GEOINT analytic products (BDA, change detection, pattern-of-life)."),
            AppendixField("dissemination_architecture", "str", True, "Dissemination path via DCGS-A, GETS, and unit portals."),
            AppendixField("coordinating_instructions", "str", False, "Coordination with Annex G Appendix 3 (Geospatial Engineering) and supporting agencies."),
        ],
    ),
    AppendixSpec(
        number=6,
        title="Measurement and Signature Intelligence",
        purpose=(
            "Plans MASINT collection - electro-optical, radar, nuclear, "
            "geophysical, materials, and RF - in support of PIR and targeting."
        ),
        doctrine_reference="FM 2-0 Ch 4; DIAM 58-11; FM 6-0 App D",
        fields=[
            AppendixField("masint_disciplines_employed", "list[str]", True, "Disciplines in use (electro-optical, radar, geophysical, nuclear, materials, RF)."),
            AppendixField("collection_objectives", "list[str]", True, "MASINT collection objectives linked to PIR and HVT signatures."),
            AppendixField("linked_pirs", "list[PIR]", True, "PIR supported by MASINT collection."),
            AppendixField("sensor_inventory", "list[str]", True, "MASINT sensors (UGS, REMBASS, IREMBASS, ACOUSTIC) in support."),
            AppendixField("signature_library_references", "list[str]", False, "Signature libraries and databases referenced for exploitation."),
            AppendixField("processing_and_exploitation", "str", True, "PED flow including national MASINT reach-back."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", True, "MASINT reporting formats and dissemination."),
            AppendixField("coordinating_instructions", "str", False, "Deconfliction with SIGINT, GEOINT, and HUMINT collection."),
        ],
    ),
    AppendixSpec(
        number=7,
        title="Open-Source Intelligence",
        purpose=(
            "Plans OSINT collection, validation, and integration - publicly "
            "available information (PAI), social media, and commercial imagery."
        ),
        doctrine_reference="FM 2-0 Ch 4; ATP 2-22.9; FM 6-0 App D",
        fields=[
            AppendixField("osint_task_organization", "str", True, "OSINT cells, analysts, and supporting contracted or partner elements."),
            AppendixField("collection_objectives", "list[str]", True, "OSINT collection objectives tied to PIR."),
            AppendixField("linked_pirs", "list[PIR]", True, "PIR supported by OSINT."),
            AppendixField("approved_sources", "list[str]", True, "Approved PAI sources, vendors, and social-media platforms."),
            AppendixField("tradecraft_and_attribution_controls", "str", True, "Attribution, managed-attribution, and tradecraft measures for OSINT collection."),
            AppendixField("authorities_and_legal_review", "str", True, "Legal authorities, US persons review, and Intelligence Oversight compliance."),
            AppendixField("production_requirements", "list[str]", True, "OSINT products required (daily digest, named-entity tracking, narrative analysis)."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", False, "OSINT reporting formats and dissemination."),
        ],
    ),
    AppendixSpec(
        number=8,
        title="Technical Intelligence",
        purpose=(
            "Plans TECHINT exploitation of captured enemy materiel (CEM) and "
            "documents to inform force protection and countermeasure development."
        ),
        doctrine_reference="FM 2-0 Ch 4; ATP 2-22.4; FM 6-0 App D",
        fields=[
            AppendixField("techint_task_organization", "str", True, "TECHINT teams, supporting labs, and reach-back to NGIC/DIA."),
            AppendixField("cem_priorities", "list[str]", True, "Prioritized captured-enemy-materiel categories for exploitation."),
            AppendixField("collection_and_evacuation_plan", "str", True, "Procedures to tag, preserve, and evacuate CEM from point of capture to exploitation site."),
            AppendixField("linked_hvts", "list[HVT]", False, "HVTs whose capture would generate priority TECHINT."),
            AppendixField("exploitation_sites", "list[str]", True, "Forward and rear exploitation sites with MGRS or named location."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", True, "TECHINT reporting (Preliminary Technical Report, Complementary TECHINT Report)."),
            AppendixField("countermeasure_dissemination", "str", True, "Procedures to push countermeasures and warnings to the force."),
            AppendixField("coordinating_instructions", "str", False, "EOD, CBRN, and CI coordination for CEM handling."),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Annex C (Operations) - 16 appendices
# Source: FM 3-0, FM 5-0, FM 6-0 App D, functional pubs per appendix
# ---------------------------------------------------------------------------
_ANNEX_C: list[AppendixSpec] = [
    AppendixSpec(
        number=1,
        title="Design Concept",
        purpose=(
            "Captures the Army design methodology products - environmental "
            "frame, problem frame, and operational approach - that underpin "
            "the concept of operations."
        ),
        doctrine_reference="ADP 5-0 Ch 2; ATP 5-0.1; FM 6-0 App D",
        fields=[
            AppendixField("environmental_frame", "str", True, "Narrative describing the current state of the operational environment."),
            AppendixField("problem_frame", "str", True, "Statement of the problem the operation must solve."),
            AppendixField("operational_approach", "str", True, "Description of how the force will transform the current state to the desired end state."),
            AppendixField("desired_end_state", "str", True, "Conditions that define success and termination criteria."),
            AppendixField("lines_of_effort", "list[str]", True, "Lines of effort or lines of operation that structure the approach."),
            AppendixField("decisive_points", "list[str]", False, "Decisive points arrayed along the LOEs/LOOs."),
            AppendixField("assumptions", "list[str]", True, "Design-level assumptions about the OE and actors."),
            AppendixField("reframing_triggers", "list[str]", False, "Conditions or events that would require reframing the problem."),
        ],
    ),
    AppendixSpec(
        number=2,
        title="Operation Overlay",
        purpose=(
            "Consolidated graphic depicting maneuver control measures, unit "
            "locations, and phasing that visualizes the concept of operations."
        ),
        doctrine_reference="FM 3-90; ADP 1-02; FM 6-0 App D",
        fields=[
            AppendixField("overlay_reference_map", "str", True, "Reference map sheet, scale, and datum for the overlay."),
            AppendixField("effective_dtg", "DTGString", True, "DTG the overlay becomes effective."),
            AppendixField("control_measures", "list[ControlMeasure]", True, "Maneuver control measures (PLs, BDYs, OBJs, BPs, LD, LOA, AA, DZ/LZ/PZ)."),
            AppendixField("unit_boundaries", "list[str]", True, "Subordinate unit boundaries keyed to task organization."),
            AppendixField("phase_graphics", "list[str]", False, "Phase-by-phase overlay references or embedded graphics."),
            AppendixField("classification", "ClassificationMarking", True, "Overall classification and handling caveats of the overlay."),
            AppendixField("remarks", "Optional[str]", False, "Free-text remarks or legend entries."),
        ],
    ),
    AppendixSpec(
        number=3,
        title="Decision Support Products",
        purpose=(
            "Decision Support Matrix (DSM) and Decision Support Template (DST) "
            "that tie CCIR, NAIs, TAIs, and decision points to commander's "
            "options during execution."
        ),
        doctrine_reference="FM 6-0 App D; ATP 5-0.1 Ch 4",
        fields=[
            AppendixField("decision_points", "list[DecisionPoint]", True, "Decision points with triggers, criteria, and actions."),
            AppendixField("named_areas_of_interest", "list[NamedAreaOfInterest]", True, "NAIs supporting DP triggers and CCIR."),
            AppendixField("targeted_areas_of_interest", "list[str]", False, "TAIs where friendly action creates the desired effect."),
            AppendixField("linked_ccir", "list[str]", True, "CCIR (PIR and FFIR) that feed the DSM."),
            AppendixField("dst_overlay_reference", "Optional[str]", False, "Reference to the Decision Support Template overlay or file."),
            AppendixField("commander_decision_authority", "str", True, "Identification of the commander or delegated authority for each class of decision."),
            AppendixField("dsm_review_cadence", "str", False, "Battle-rhythm cadence for DSM update and review."),
        ],
    ),
    AppendixSpec(
        number=4,
        title="Gap Crossing",
        purpose=(
            "Plan for hasty or deliberate gap crossing operations - wet or dry - "
            "including approach, assault, bridgehead, and exploitation."
        ),
        doctrine_reference="ATP 3-90.4 / ATP 3-21.51; FM 6-0 App D",
        fields=[
            AppendixField("crossing_type", "str", True, "Hasty or deliberate; wet or dry gap."),
            AppendixField("crossing_sites", "list[str]", True, "Primary and alternate crossing site locations (MGRS)."),
            AppendixField("crossing_area_commander", "str", True, "Designated crossing area commander and boundaries of the crossing area."),
            AppendixField("task_organization", "str", True, "Crossing force, support force, and bridgehead force organization."),
            AppendixField("timeline", "str", True, "Phased timeline: approach, assault, bridgehead, exploitation."),
            AppendixField("engineer_assets", "list[str]", True, "Bridging assets, rafts, bridge erection boats, and supporting engineer units."),
            AppendixField("traffic_control_plan", "str", True, "Traffic control posts, routes, and priority of movement."),
            AppendixField("far_shore_objectives", "list[str]", True, "Bridgehead line and far-shore objectives."),
            AppendixField("contingencies", "list[str]", False, "Branches and sequels if the crossing is contested or compromised."),
        ],
    ),
    AppendixSpec(
        number=5,
        title="Air Assault",
        purpose=(
            "Air assault operation plan covering the five planning stages and "
            "the air movement / ground tactical plan linkage."
        ),
        doctrine_reference="ATP 3-18.12; FM 3-99; FM 6-0 App D",
        fields=[
            AppendixField("ground_tactical_plan", "str", True, "Ground tactical plan at the objective - the basis from which all other plans derive."),
            AppendixField("landing_plan", "str", True, "Sequence and method of landing forces on LZs."),
            AppendixField("air_movement_plan", "str", True, "Air movement tables, routes, and air control measures."),
            AppendixField("loading_plan", "str", True, "Aircraft loads (chalks), pickup zones, and bump plan."),
            AppendixField("staging_plan", "str", True, "PZ operations and pre-combat inspections at staging areas."),
            AppendixField("pz_and_lz_data", "list[ControlMeasure]", True, "PZ, LZ, and supporting control measures (points, grids, markings)."),
            AppendixField("aviation_task_organization", "str", True, "Supporting aviation task organization and mission command relationships."),
            AppendixField("air_movement_table", "str", True, "Air movement table or reference to published ATM."),
            AppendixField("abort_criteria", "list[str]", True, "Abort criteria and decision authority for canceling the assault."),
        ],
    ),
    AppendixSpec(
        number=6,
        title="Airborne",
        purpose=(
            "Airborne operation plan covering marshalling, air movement, drop, "
            "assembly, and ground-tactical phases of a parachute assault."
        ),
        doctrine_reference="FM 3-99; ATP 3-18.5; FM 6-0 App D",
        fields=[
            AppendixField("ground_tactical_plan", "str", True, "Ground tactical plan on the DZ and subsequent objectives."),
            AppendixField("landing_plan", "str", True, "Drop and assembly plan to transition from parachute landing to ground combat."),
            AppendixField("air_movement_plan", "str", True, "Air movement routes, formations, and control measures."),
            AppendixField("marshalling_plan", "str", True, "Marshalling and departure airfield operations."),
            AppendixField("dz_data", "list[ControlMeasure]", True, "DZs, alternate DZs, CARP/GMRS data, and marking schemes."),
            AppendixField("aircraft_and_chalks", "str", True, "Aircraft types, chalks, and cross-load plan."),
            AppendixField("abort_criteria", "list[str]", True, "Abort criteria, no-drop criteria, and decision authority."),
            AppendixField("link_up_plan", "Optional[str]", False, "Link-up plan with follow-on forces or linked elements."),
        ],
    ),
    AppendixSpec(
        number=7,
        title="Amphibious",
        purpose=(
            "Amphibious operation plan for landing forces from the sea, "
            "integrating naval, air, and landing-force maneuver."
        ),
        doctrine_reference="JP 3-02; FM 3-99; FM 6-0 App D",
        fields=[
            AppendixField("amphibious_force_organization", "str", True, "CATF/CLF task organization and mission command relationships."),
            AppendixField("landing_plan", "str", True, "Landing plan including beaches, waves, serials, and H-hour."),
            AppendixField("ship_to_shore_movement", "str", True, "Ship-to-shore movement scheme: surface, vertical, and combination."),
            AppendixField("beach_and_lz_data", "list[ControlMeasure]", True, "Landing beaches, color-coded beach lanes, and supporting LZs."),
            AppendixField("naval_support", "str", True, "Naval surface fire support, air support, and logistics over-the-shore."),
            AppendixField("rehearsal_plan", "str", False, "Rehearsals required prior to execution (ROC drill, backbrief, live)."),
            AppendixField("shaping_operations", "str", True, "Pre-assault shaping: fires, deception, and SOF enabling actions."),
            AppendixField("transition_ashore", "str", True, "Transition of command ashore and termination criteria for the amphibious phase."),
        ],
    ),
    AppendixSpec(
        number=8,
        title="Information Operations",
        purpose=(
            "Integrates information-related capabilities (IRCs) to create "
            "effects on threat and relevant-actor perception, decision-making, "
            "and will to fight."
        ),
        doctrine_reference="FM 3-13; ADP 3-13; FM 6-0 App D",
        fields=[
            AppendixField("information_environment_assessment", "str", True, "Assessment of the information environment including audiences and narratives."),
            AppendixField("information_objectives", "list[str]", True, "Information objectives tied to the commander's end state."),
            AppendixField("target_audiences", "list[str]", True, "Relevant actors and target audiences for information efforts."),
            AppendixField("irc_task_organization", "list[str]", True, "Information-related capabilities (MISO, MILDEC, CEMA, PA, CA, OPSEC) synchronized."),
            AppendixField("synchronization_matrix", "str", True, "Information synchronization matrix linking IRCs, timing, and effects."),
            AppendixField("measures_of_effectiveness", "list[str]", True, "MOEs assessing whether information objectives are achieved."),
            AppendixField("coordination_requirements", "str", True, "Coordination with higher, adjacent, partner, and interagency information efforts."),
            AppendixField("authorities_and_approvals", "str", True, "Execution authorities and approval chains for information activities."),
        ],
    ),
    AppendixSpec(
        number=9,
        title="Military Deception",
        purpose=(
            "Planned, closely-held military deception (MILDEC) to induce the "
            "threat commander to take actions favorable to friendly objectives."
        ),
        doctrine_reference="FM 3-13.4; JP 3-13.4; FM 6-0 App D",
        fields=[
            AppendixField("deception_goal", "str", True, "Deception goal supporting the higher operational objective."),
            AppendixField("deception_objective", "str", True, "Specific action or inaction the deception target must take."),
            AppendixField("deception_target", "str", True, "Named threat decision-maker or element whose decision is the focus."),
            AppendixField("deception_story", "str", True, "Story the friendly force wants the target to believe."),
            AppendixField("deception_means", "list[str]", True, "Physical, technical, and administrative means used to convey the story."),
            AppendixField("observables", "list[str]", True, "Observables the threat must detect for the story to be credible."),
            AppendixField("feedback_mechanisms", "list[str]", True, "Collection that confirms the target is perceiving and acting on the story."),
            AppendixField("termination_criteria", "str", True, "Conditions that end the MILDEC or require reframing."),
            AppendixField("access_and_compartmentation", "str", True, "Need-to-know list and compartmentation controls for the MILDEC plan."),
        ],
    ),
    AppendixSpec(
        number=10,
        title="Airspace Control",
        purpose=(
            "Airspace control plan within the AO - ACMs, airspace users, "
            "and procedures that integrate Army and joint airspace users."
        ),
        doctrine_reference="FM 3-52; ATP 3-52.1; JP 3-52",
        fields=[
            AppendixField("airspace_control_authority", "str", True, "Designated airspace control authority and area airspace control plan reference."),
            AppendixField("acm_inventory", "list[ACM]", True, "Airspace Coordinating Measures in effect (ROZ, MRR, SAAFR, HIDACZ, WEZ, BDZ)."),
            AppendixField("airspace_users", "list[str]", True, "Rotary, fixed-wing, UAS, indirect-fire trajectory, and cruise-missile users."),
            AppendixField("coordinating_altitude", "str", False, "Coordinating altitude between fixed and rotary-wing users."),
            AppendixField("airspace_control_procedures", "str", True, "Procedural control measures and positive-control procedures."),
            AppendixField("uas_airspace_management", "str", True, "UAS airspace integration and deconfliction procedures."),
            AppendixField("activation_deactivation", "str", True, "Procedures to activate, deactivate, and modify ACMs during execution."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", False, "Airspace reporting requirements (ACO, ATO, ACPs)."),
        ],
    ),
    AppendixSpec(
        number=11,
        title="Rules of Engagement",
        purpose=(
            "Rules of Engagement governing the use of force, positive "
            "identification, and escalation of force for the operation."
        ),
        doctrine_reference="CJCSI 3121.01B (SROE); FM 6-27; FM 6-0 App D",
        fields=[
            AppendixField("applicable_sroe", "str", True, "Reference to the Standing ROE and any theater-specific supplemental measures in effect."),
            AppendixField("mission_specific_roe", "list[str]", True, "Mission-specific ROE approved for this operation."),
            AppendixField("pid_standards", "str", True, "Positive identification standards for engagement."),
            AppendixField("escalation_of_force", "list[str]", True, "Escalation-of-force procedures at checkpoints and during maneuver."),
            AppendixField("declared_hostile_forces", "list[str]", False, "Forces declared hostile under SROE (if any)."),
            AppendixField("protected_persons_and_sites", "list[str]", True, "Protected persons, cultural property, and no-strike list references."),
            AppendixField("delegation_of_authority", "str", True, "Authority to engage, grant weapons-free, and approve cross-boundary fires."),
            AppendixField("collateral_damage_methodology", "str", True, "CDE methodology and level of authority for each CDE category."),
            AppendixField("training_and_cards", "str", True, "Soldier-card issue and mandatory pre-mission ROE training."),
        ],
    ),
    AppendixSpec(
        number=12,
        title="Cyberspace Electromagnetic Activities",
        purpose=(
            "Integrates cyberspace operations, electromagnetic warfare, and "
            "spectrum management to enable friendly operations and deny "
            "threat use of cyberspace and the EMS."
        ),
        doctrine_reference="FM 3-12; ADP 3-13; FM 6-0 App D",
        fields=[
            AppendixField("cema_task_organization", "str", True, "CEMA cell, EW units, and supporting cyber units in the task organization."),
            AppendixField("cyberspace_objectives", "list[str]", True, "Offensive, defensive, and DODIN-operations cyberspace objectives."),
            AppendixField("ew_objectives", "list[str]", True, "Electromagnetic attack, protect, and support objectives."),
            AppendixField("target_list", "list[HVT]", False, "Cyber and EW targets nominated to the targeting process."),
            AppendixField("spectrum_management", "str", True, "Linkage to Annex H Appendix 5 (Spectrum Management Operations) and JRFL."),
            AppendixField("deconfliction_procedures", "str", True, "Procedures to deconflict EW and cyber effects with SIGINT, comms, and allies."),
            AppendixField("authorities_and_approvals", "str", True, "Cyberspace and EW authorities, pre-approved effects, and approval chains."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", True, "CEMA reports (e.g. MIJI, TACREP)."),
        ],
    ),
    AppendixSpec(
        number=13,
        title="Military Information Support Operations",
        purpose=(
            "Plans MISO (formerly PSYOP) to influence the perception, attitude, "
            "and behavior of approved foreign target audiences."
        ),
        doctrine_reference="FM 3-53; ATP 3-53.1; FM 6-0 App D",
        fields=[
            AppendixField("miso_objectives", "list[str]", True, "Approved MISO objectives for the operation."),
            AppendixField("target_audiences", "list[str]", True, "Approved foreign target audiences with supporting analysis."),
            AppendixField("series_and_products", "list[str]", True, "Approved MISO series and product references."),
            AppendixField("dissemination_means", "list[str]", True, "Dissemination means (loudspeaker, leaflet, broadcast, digital)."),
            AppendixField("measures_of_effectiveness", "list[str]", True, "MOEs for assessing behavioral change in target audiences."),
            AppendixField("approval_authorities", "str", True, "MISO product and program approval authorities and review timelines."),
            AppendixField("coordination_with_pa_and_ca", "str", True, "Coordination with Annex J (PA) and Annex K (CA) to avoid message conflict."),
            AppendixField("legal_and_policy_review", "str", True, "Legal and policy review requirements per applicable EXORDs and directives."),
        ],
    ),
    AppendixSpec(
        number=14,
        title="Space Operations",
        purpose=(
            "Integrates space capabilities - PNT, SATCOM, MW, ISR, "
            "environmental monitoring - in support of the operation."
        ),
        doctrine_reference="FM 3-14; ADP 3-14; FM 6-0 App D",
        fields=[
            AppendixField("space_task_organization", "str", True, "Supporting space elements (Army Space Forces, theater space cells, SMDC)."),
            AppendixField("space_support_requests", "list[str]", True, "Space Support Requests (SSRs) submitted or required for the operation."),
            AppendixField("space_force_enhancement_areas", "list[str]", True, "PNT, SATCOM, ISR, MW, environmental monitoring tasks supported."),
            AppendixField("threat_space_considerations", "str", True, "Threat space and counterspace capabilities affecting friendly space use."),
            AppendixField("friendly_space_protection", "str", True, "Defensive measures for friendly space capabilities (anti-jam, PNT backup)."),
            AppendixField("coordinating_instructions", "str", False, "Coordination with Annex N (Space Operations) and supporting JFCC SPACE."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", False, "Space reports (GPS interference, SATCOM outage, space weather)."),
        ],
    ),
    AppendixSpec(
        number=15,
        title="Special Technical Operations",
        purpose=(
            "Identifies integration of Special Technical Operations (STO) at the "
            "appropriate classification level; detail resides in compartmented "
            "annexes or separate publications."
        ),
        doctrine_reference="FM 6-0 App D; CJCSI 3211.01 series (STO)",
        fields=[
            AppendixField("sto_pointer_statement", "str", True, "Unclassified pointer statement acknowledging STO integration and referencing compartmented guidance."),
            AppendixField("sto_officer_of_primary_responsibility", "str", True, "STO officer (STOO) or equivalent responsible for integration."),
            AppendixField("access_requirements", "str", True, "Access, compartmentation, and handling requirements for STO details."),
            AppendixField("coordination_channel", "str", True, "Secure channel through which subordinates receive STO direction."),
            AppendixField("deconfliction_with_standard_ops", "str", True, "Procedures to deconflict STO effects with conventional fires, cyber, and EW."),
            AppendixField("classification", "ClassificationMarking", True, "Classification of this appendix (normally UNCLASSIFIED pointer; supporting plan compartmented)."),
        ],
    ),
    AppendixSpec(
        number=16,
        title="Special Operations",
        purpose=(
            "Integrates special operations forces (SOF) activities - SR, DA, UW, "
            "FID, CT - with conventional operations."
        ),
        doctrine_reference="ADP 3-05; FM 3-05; FM 6-0 App D",
        fields=[
            AppendixField("sof_task_organization", "str", True, "Supporting SOF elements (SFG/A, Ranger, CA, MISO, 160th SOAR) and command relationships."),
            AppendixField("sof_mission_set", "list[str]", True, "SOF core activities conducted (SR, DA, UW, FID, CT, CWMD, hostage rescue)."),
            AppendixField("conventional_sof_integration", "str", True, "Conventional Forces-SOF integration, interoperability, and interdependence (CF-SOF I3)."),
            AppendixField("battlespace_deconfliction", "str", True, "Fires, airspace, and ground deconfliction between SOF and CF."),
            AppendixField("liaison_and_lno_plan", "str", True, "SOF liaison element (SOLE/SOCCE/SOFLE) placement and responsibilities."),
            AppendixField("support_requirements", "list[str]", False, "Conventional force support (fires, sustainment, MEDEVAC, aviation) required by SOF."),
            AppendixField("authorities_and_caveats", "str", True, "SOF-specific authorities, caveats, and restrictions."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", False, "SOF reporting into the CF common operating picture."),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Annex D (Fires) - 5 appendices
# Source: FM 3-09 (May 2022); ATP 3-09.32; FM 3-01; JP 3-09
# ---------------------------------------------------------------------------
_ANNEX_D: list[AppendixSpec] = [
    AppendixSpec(
        number=1,
        title="Field Artillery Support",
        purpose=(
            "Field artillery support plan including task organization, "
            "positioning, and the essential field artillery tasks (EFATs)."
        ),
        doctrine_reference="FM 3-09 Ch 4; ATP 3-09.23/24/42",
        fields=[
            AppendixField("fa_task_organization", "str", True, "FA units in DS, GS, GSR, and R relationships."),
            AppendixField("essential_field_artillery_tasks", "list[str]", True, "EFATs supporting the essential fire support tasks (EFSTs)."),
            AppendixField("position_areas_for_artillery", "list[str]", True, "PAAs, primary and alternate firing positions, by phase."),
            AppendixField("ammunition_plan", "str", True, "CSR, RSR, ammunition priorities, and Class V resupply triggers."),
            AppendixField("target_list", "list[HVT]", True, "Prioritized FA targets and triggers from the HPTL."),
            AppendixField("fire_support_coordination_measures", "list[FSCM]", True, "FA-related FSCMs (RFA, NFA, CFZ, FFA)."),
            AppendixField("counterfire_plan", "str", True, "Counterfire architecture: sensor-to-shooter, radar zones, and attack guidance."),
            AppendixField("survey_and_meteorology", "str", False, "Survey and MET support to firing units."),
            AppendixField("coordinating_instructions", "str", False, "Priorities of fire by phase, clearance procedures, and no-fire coordination."),
        ],
    ),
    AppendixSpec(
        number=2,
        title="Air Support",
        purpose=(
            "Integrates joint air support - CAS, AI, SCAR, AR - and links "
            "ground-force requests to the joint ATO cycle."
        ),
        doctrine_reference="FM 3-09 Ch 5; ATP 3-09.32; JP 3-09.3",
        fields=[
            AppendixField("air_support_apportionment", "str", True, "Apportionment and allocation of joint air to the operation."),
            AppendixField("ato_cycle_integration", "str", True, "ATO cycle integration, including AIRSUPREQ and JTAR submission timelines."),
            AppendixField("cas_priorities", "list[str]", True, "CAS priorities by phase and supported unit."),
            AppendixField("tacp_and_jtac_plan", "str", True, "TACP and JTAC allocation, certification, and responsibilities."),
            AppendixField("air_control_measures", "list[ACM]", True, "Airspace Coordinating Measures governing air support missions."),
            AppendixField("kill_box_procedures", "str", False, "Kill box establishment, activation, and clearance procedures."),
            AppendixField("suppression_of_enemy_air_defenses", "str", True, "SEAD/DEAD plan supporting air support missions."),
            AppendixField("coordinating_instructions", "str", False, "Check-in procedures, tactics authorizations, and medevac launch authority."),
        ],
    ),
    AppendixSpec(
        number=3,
        title="Naval Surface Fire Support",
        purpose=(
            "Plans naval surface fire support (NSFS) - naval gunfire and "
            "surface-launched munitions - in littoral and amphibious operations."
        ),
        doctrine_reference="FM 3-09 Ch 6; JP 3-09; NTTP 3-09.2",
        fields=[
            AppendixField("nsfs_assets", "list[str]", True, "NSFS ships, allocated tubes, and expected on-station periods."),
            AppendixField("sfcp_organization", "str", True, "Supporting Arms Coordination Center / Shore Fire Control Party organization."),
            AppendixField("nsfs_priorities", "list[str]", True, "NSFS priorities of fire by phase and supported unit."),
            AppendixField("fire_support_areas", "list[str]", True, "Fire Support Areas (FSA) and Fire Support Stations (FSS) assigned to NSFS."),
            AppendixField("target_list", "list[HVT]", False, "NSFS targets from the joint integrated target list."),
            AppendixField("fscm_and_acm_integration", "list[FSCM]", True, "FSCMs governing NSFS, integrated with land-force FSCMs."),
            AppendixField("ammunition_and_expenditure", "str", True, "Approved ammunition types, CSR, and expenditure limits."),
            AppendixField("coordinating_instructions", "str", False, "Check-in, clearance of fires, and ship-shore communications plan."),
        ],
    ),
    AppendixSpec(
        number=4,
        title="Air and Missile Defense",
        purpose=(
            "Air and missile defense (AMD) plan - active defense, passive "
            "defense, and attack operations - supporting the defended asset list."
        ),
        doctrine_reference="FM 3-01; ATP 3-01.50; FM 3-09 Ch 7",
        fields=[
            AppendixField("amd_task_organization", "str", True, "ADA units (Patriot, THAAD, SHORAD, C-RAM) and supporting joint AMD."),
            AppendixField("defended_asset_list", "list[str]", True, "DAL items (prioritized) and required level of protection."),
            AppendixField("critical_asset_list", "list[str]", True, "CAL items requiring active and passive defense."),
            AppendixField("active_defense_plan", "str", True, "Active defense engagement areas, weapons control status, and firing doctrine."),
            AppendixField("passive_defense_measures", "list[str]", True, "Passive defense measures (dispersion, camouflage, hardening, early warning)."),
            AppendixField("attack_operations_contribution", "str", True, "AMD contribution to attack operations against threat air and missile capabilities."),
            AppendixField("wcs_and_weapons_free_criteria", "str", True, "Weapons Control Status settings and criteria for changes."),
            AppendixField("amd_acms", "list[ACM]", True, "AMD-related ACMs (BDZ, WEZ, ROZ) and coordinating altitudes."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", False, "AMD reporting (TBMD, ADWARN, WEAPONS RED/FREE/TIGHT/HOLD)."),
        ],
    ),
    AppendixSpec(
        number=5,
        title="Targeting",
        purpose=(
            "Targeting process products - HPTL, attack guidance matrix, "
            "target selection standards, and the targeting battle rhythm."
        ),
        doctrine_reference="ATP 3-60; FM 3-09 Ch 3; FM 6-0 App D",
        fields=[
            AppendixField("high_payoff_target_list", "list[HVT]", True, "HPTL ordered by priority with category and engagement guidance."),
            AppendixField("attack_guidance_matrix", "str", True, "AGM linking HPTs to timing (when), effects (how), and restrictions (if)."),
            AppendixField("target_selection_standards", "str", True, "TSS defining accuracy, timeliness, and source standards for engagement."),
            AppendixField("no_strike_list", "list[str]", True, "No-strike list (NSL) entries protected by ROE, law, or policy."),
            AppendixField("restricted_target_list", "list[str]", True, "Restricted Target List (RTL) entries with restrictions and approval authority."),
            AppendixField("targeting_working_group", "BattleRhythmEvent", True, "Targeting WG, targeting board, and approval cadence in the battle rhythm."),
            AppendixField("assessment_plan", "str", True, "Combat assessment (BDA, MEA, reattack recommendation) responsibilities and products."),
            AppendixField("cde_and_collateral_controls", "str", True, "Collateral damage estimate methodology and approval authorities by level."),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Annex E (Protection) - 14 appendices
# Source: FM 3-37; ATP 3-37.2 / .11 / .34; FM 3-11; FM 3-01; FM 3-50; FM 6-0 App D
# ---------------------------------------------------------------------------
_ANNEX_E: list[AppendixSpec] = [
    AppendixSpec(
        number=1,
        title="Antiterrorism",
        purpose=(
            "Antiterrorism (AT) plan protecting personnel, information, and "
            "critical resources from terrorist acts."
        ),
        doctrine_reference="ATP 3-37.2; AR 525-13; FM 6-0 App D",
        fields=[
            AppendixField("at_officer", "str", True, "Designated antiterrorism officer (ATO) and alternates."),
            AppendixField("threat_assessment", "str", True, "AT threat assessment (DIA threat levels + local assessment)."),
            AppendixField("fpcon_measures", "str", True, "Baseline FPCON and site-specific random antiterrorism measures (RAMs)."),
            AppendixField("vulnerability_assessment", "str", True, "Installation/site vulnerability assessment summary and mitigation."),
            AppendixField("critical_asset_protection", "list[str]", True, "Critical assets receiving AT protection."),
            AppendixField("incident_response_plan", "str", True, "Response procedures for terrorist incidents (active shooter, VBIED, kidnapping)."),
            AppendixField("awareness_training", "str", True, "Level I AT awareness training compliance and refresher schedule."),
            AppendixField("coordinating_instructions", "str", False, "Coordination with host-nation, interagency, and law enforcement."),
        ],
    ),
    AppendixSpec(
        number=2,
        title="Operations Security",
        purpose=(
            "OPSEC plan to identify critical information, analyze threats and "
            "vulnerabilities, and apply countermeasures."
        ),
        doctrine_reference="AR 530-1; ATP 3-13.3; FM 6-0 App D",
        fields=[
            AppendixField("critical_information_list", "list[str]", True, "Commander-approved Critical Information List (CIL)."),
            AppendixField("threat_analysis", "str", True, "Adversary collection threat to critical information."),
            AppendixField("vulnerability_analysis", "str", True, "Friendly indicators that reveal critical information."),
            AppendixField("risk_assessment", "str", True, "Risk assessment and OPSEC risk decisions."),
            AppendixField("opsec_measures", "list[str]", True, "Countermeasures applied to eliminate or mitigate vulnerabilities."),
            AppendixField("ee_fi", "list[str]", False, "Essential Elements of Friendly Information (EEFI)."),
            AppendixField("opsec_officer", "str", True, "Designated OPSEC officer and program management responsibilities."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", False, "OPSEC incident and compromise reporting."),
        ],
    ),
    AppendixSpec(
        number=3,
        title="Intelligence Support to Protection",
        purpose=(
            "Intelligence support tailored to the protection warfighting "
            "function - threat actor analysis, indications and warning, and "
            "vulnerability-to-threat matching."
        ),
        doctrine_reference="FM 3-37 Ch 3; ATP 3-37.2; FM 2-0",
        fields=[
            AppendixField("threat_actors_to_protection", "list[str]", True, "Named threat actors relevant to protection (terrorists, insider, criminal, FIE)."),
            AppendixField("critical_asset_threat_matching", "str", True, "Matching of CAL/DAL entries to threat capabilities."),
            AppendixField("indications_and_warning", "list[str]", True, "Indications and warning indicators of imminent threats to the force."),
            AppendixField("linked_pirs", "list[PIR]", True, "PIR that drive intelligence support to protection."),
            AppendixField("ci_integration", "str", True, "Integration with Annex B App 2 (Counterintelligence)."),
            AppendixField("fusion_and_reporting", "str", True, "Protection-focused fusion cell and reporting channels."),
            AppendixField("coordinating_instructions", "str", False, "Coordination with force-protection working group and provost marshal."),
        ],
    ),
    AppendixSpec(
        number=4,
        title="Explosive Ordnance Disposal",
        purpose=(
            "EOD support plan for UXO/IED/CBRN munitions rendering safe and "
            "disposal in support of maneuver and force protection."
        ),
        doctrine_reference="ATP 4-32; FM 3-37 Ch 5",
        fields=[
            AppendixField("eod_task_organization", "str", True, "EOD companies, platoons, and teams in the task organization."),
            AppendixField("eod_priorities", "list[str]", True, "Priorities of EOD support by phase and supported unit."),
            AppendixField("response_times", "str", True, "Response-time standards by category (A/B/C/D) and supported unit."),
            AppendixField("uxo_ied_reporting", "list[ReportDefinition]", True, "9-line UXO and 10-line IED reporting procedures."),
            AppendixField("wti_exploitation", "str", False, "Weapons Technical Intelligence (WTI) handling and exploitation requirements."),
            AppendixField("cwmd_support", "str", False, "EOD support to countering WMD, including CBRN munitions."),
            AppendixField("coordinating_instructions", "str", False, "Coordination with engineers, route clearance, CBRN, and law enforcement."),
        ],
    ),
    AppendixSpec(
        number=5,
        title="CBRN Operations",
        purpose=(
            "Chemical, biological, radiological, and nuclear (CBRN) defense "
            "plan - hazard awareness, contamination avoidance, protection, "
            "and decontamination."
        ),
        doctrine_reference="FM 3-11; ATP 3-11.32; FM 6-0 App D",
        fields=[
            AppendixField("cbrn_threat_assessment", "str", True, "Threat CBRN capabilities, delivery means, and likely employment."),
            AppendixField("mopp_guidance", "str", True, "MOPP levels by phase and area, with automatic-masking criteria."),
            AppendixField("hazard_prediction", "str", True, "CBRN hazard prediction, warning, and reporting (CBRN WARN/REPORT)."),
            AppendixField("detection_and_reconnaissance", "list[str]", True, "Detection assets, CBRN recon teams, and supported NAIs."),
            AppendixField("decontamination_plan", "str", True, "Patient, operational, and thorough decontamination plan and sites."),
            AppendixField("medical_cbrn_support", "str", True, "Medical CBRN support (prophylaxis, diagnostics, casualty management)."),
            AppendixField("consequence_management", "str", False, "Consequence management responsibilities if employment occurs."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", True, "CBRN 1-6 reports and NBCWRS reporting flows."),
            AppendixField("coordinating_instructions", "str", False, "Coordination with Annex F (medical) and host-nation CBRN authorities."),
        ],
    ),
    AppendixSpec(
        number=6,
        title="Safety",
        purpose=(
            "Composite risk management and safety program integrated into the "
            "operation - hazards, controls, and residual risk acceptance."
        ),
        doctrine_reference="ATP 5-19; FM 3-37 Ch 8",
        fields=[
            AppendixField("safety_officer", "str", True, "Designated safety officer / command safety representative."),
            AppendixField("hazards", "list[str]", True, "Identified operational and accidental hazards."),
            AppendixField("risk_assessment", "str", True, "Risk assessment (probability x severity) with initial and residual risk."),
            AppendixField("controls", "list[str]", True, "Controls (engineering, administrative, PPE) applied to hazards."),
            AppendixField("risk_decision_authority", "str", True, "Commander with authority to accept residual risk per ATP 5-19."),
            AppendixField("composite_risk_level", "str", True, "Overall composite risk level after controls (low, moderate, high, extremely high)."),
            AppendixField("safety_reporting", "list[ReportDefinition]", False, "Safety incident and near-miss reporting (DA 285 / mishap reports)."),
        ],
    ),
    AppendixSpec(
        number=7,
        title="Fratricide Avoidance",
        purpose=(
            "Fratricide prevention measures - positive identification, "
            "recognition signals, and fires/maneuver deconfliction."
        ),
        doctrine_reference="FM 3-37 Ch 9; ATP 3-09.32",
        fields=[
            AppendixField("combat_identification", "str", True, "Combat identification procedures, IFF, and blue-force tracking architecture."),
            AppendixField("recognition_signals", "list[str]", True, "Visual, audio, and electronic recognition signals by phase."),
            AppendixField("far_recognition_and_vs17_panels", "str", False, "Far-recognition panels, IR strobes, and marking schemes."),
            AppendixField("clearance_of_fires", "str", True, "Clearance of fires procedures and authorities."),
            AppendixField("rehearsals_and_drills", "str", True, "Fratricide-focused rehearsals, backbriefs, and drills."),
            AppendixField("investigations_and_lessons", "str", False, "Procedures if a fratricide incident occurs (investigation, AR 15-6)."),
            AppendixField("coordinating_instructions", "str", False, "Coordination with joint/partner forces on CID and deconfliction."),
        ],
    ),
    AppendixSpec(
        number=8,
        title="Air and Missile Defense",
        purpose=(
            "Protection-focused AMD plan; cross-references the fires AMD "
            "plan (Annex D Appendix 4) while detailing local active and "
            "passive defense of protected assets."
        ),
        doctrine_reference="FM 3-01; ATP 3-01.50; FM 3-37 Ch 6",
        fields=[
            AppendixField("protected_assets", "list[str]", True, "Protected assets derived from the DAL/CAL."),
            AppendixField("active_defense_posture", "str", True, "Local active defense: SHORAD, MANPADS, C-RAM, counter-UAS."),
            AppendixField("passive_defense", "list[str]", True, "Camouflage, concealment, hardening, dispersion, and EW-counter-detection measures."),
            AppendixField("early_warning_architecture", "str", True, "Early-warning sensors, dissemination path, and alert means."),
            AppendixField("wcs_by_phase", "str", True, "Weapons Control Status by phase and engagement area."),
            AppendixField("counter_uas_plan", "str", True, "Counter-small-UAS plan (detection, tracking, engagement, reporting)."),
            AppendixField("cross_reference_annex_d", "str", True, "Cross-reference to Annex D Appendix 4 for joint/theater AMD integration."),
        ],
    ),
    AppendixSpec(
        number=9,
        title="Personnel Recovery",
        purpose=(
            "Personnel recovery (PR) plan - report, locate, support, recover, "
            "and reintegrate isolated personnel."
        ),
        doctrine_reference="FM 3-50; ATP 3-50.3; JP 3-50",
        fields=[
            AppendixField("pr_architecture", "str", True, "PR architecture: PRCC, JPRC, and reach-back to higher PR staffs."),
            AppendixField("isolation_prevention_and_preparation", "str", True, "ISOPREP, EPA, and personnel recovery training requirements."),
            AppendixField("recovery_methods", "list[str]", True, "Recovery methods: diplomatic, military, civil, unassisted."),
            AppendixField("recovery_forces", "list[str]", True, "Dedicated and designated recovery forces with response times."),
            AppendixField("authentication", "str", True, "Authentication procedures (numerical, letter, SAR dot) for isolated personnel."),
            AppendixField("reintegration", "str", True, "Reintegration plan and supporting facilities."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", True, "Isolated-personnel reports (EVASIONPLAN, SARIR, SITREP-PR)."),
            AppendixField("coordinating_instructions", "str", False, "Coordination with SOF, partner-nation PR, and interagency."),
        ],
    ),
    AppendixSpec(
        number=10,
        title="Detention Operations",
        purpose=(
            "Detention operations plan covering capture, processing, holding, "
            "and transfer of detainees IAW U.S. and international law."
        ),
        doctrine_reference="FM 3-63; AR 190-8; FM 6-27",
        fields=[
            AppendixField("detention_authority", "str", True, "Authority under which detention is conducted (Geneva, CFR, policy directive)."),
            AppendixField("capture_and_processing", "str", True, "Capture-tag-bag, sensitive-site exploitation, and initial processing procedures."),
            AppendixField("detainee_collection_points", "list[str]", True, "Unit detainee collection points, DHAs, and theater internment facility references."),
            AppendixField("medical_screening", "str", True, "Detainee medical screening and treatment responsibilities."),
            AppendixField("interrogation_coordination", "str", False, "Coordination with HUMINT for authorized interrogations."),
            AppendixField("transfer_and_release", "str", True, "Transfer and release criteria, chain-of-custody, and documentation."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", True, "Detainee reports (capture tag, DA 2823, DA 4137)."),
            AppendixField("legal_and_icrc_access", "str", True, "Legal review and ICRC notification/access requirements."),
        ],
    ),
    AppendixSpec(
        number=11,
        title="Force Health Protection",
        purpose=(
            "Force health protection plan - preventive medicine, health "
            "surveillance, combat and operational stress control, and dental."
        ),
        doctrine_reference="FM 4-02; ATP 4-02.8; FM 3-37 Ch 11",
        fields=[
            AppendixField("disease_nonbattle_injury_threats", "list[str]", True, "Endemic disease and non-battle injury threats in the AO."),
            AppendixField("preventive_medicine_measures", "list[str]", True, "Preventive medicine measures (immunizations, chemoprophylaxis, vector control)."),
            AppendixField("health_surveillance", "str", True, "Health surveillance plan and reporting through DRSi / theater systems."),
            AppendixField("field_sanitation", "str", True, "Field sanitation team employment and water/waste management."),
            AppendixField("combat_operational_stress_control", "str", True, "COSC plan, restoration teams, and unit behavioral-health support."),
            AppendixField("dental_readiness", "str", False, "Dental readiness, class III prevention, and treatment priorities."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", False, "DNBI, disease outbreak, and heat/cold casualty reporting."),
        ],
    ),
    AppendixSpec(
        number=12,
        title="Critical Asset List and Defended Asset List",
        purpose=(
            "Commander-approved Critical Asset List (CAL) and Defended Asset "
            "List (DAL) that prioritize protection efforts and AMD."
        ),
        doctrine_reference="FM 3-37 Ch 4; ATP 3-37.34; FM 3-01",
        fields=[
            AppendixField("critical_asset_list", "list[str]", True, "CAL entries with rationale and criticality tier."),
            AppendixField("defended_asset_list", "list[str]", True, "DAL entries derived from the CAL with required defense level."),
            AppendixField("criticality_criteria", "str", True, "Criteria (CARVER or equivalent) used to rank criticality."),
            AppendixField("vulnerability_assessment", "str", True, "Vulnerability assessment summary for CAL/DAL entries."),
            AppendixField("protection_prioritization", "str", True, "Prioritization of protection resources across the CAL/DAL."),
            AppendixField("review_cycle", "str", True, "CAL/DAL review cycle within the protection working group."),
            AppendixField("approval_authority", "str", True, "Commander approval authority for CAL/DAL changes."),
        ],
    ),
    AppendixSpec(
        number=13,
        title="Physical Security",
        purpose=(
            "Physical security plan - access control, barriers, lighting, and "
            "intrusion detection - at fixed sites and assembly areas."
        ),
        doctrine_reference="AR 190-13; ATP 3-39.32; FM 3-37 Ch 7",
        fields=[
            AppendixField("protected_sites", "list[str]", True, "Sites requiring physical security (CPs, ASPs, AAs, fuel points, comm sites)."),
            AppendixField("access_control", "str", True, "Access control procedures, badging, and visitor management."),
            AppendixField("barrier_and_standoff_plan", "str", True, "Barriers, standoff distances, and entry control points."),
            AppendixField("lighting_and_sensors", "str", True, "Lighting, CCTV, and intrusion-detection systems."),
            AppendixField("guard_force", "str", True, "Guard force organization, posts, and patrols."),
            AppendixField("key_and_lock_control", "str", False, "Key and lock control program per AR 190-51."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", False, "Physical-security incident reporting (serious incident reports, AR 190-45)."),
        ],
    ),
    AppendixSpec(
        number=14,
        title="Cybersecurity",
        purpose=(
            "Cybersecurity plan protecting the DODIN footprint from the "
            "installation to the tactical edge, including RMF compliance and "
            "incident response."
        ),
        doctrine_reference="AR 25-2; FM 6-02; FM 3-12",
        fields=[
            AppendixField("authorizing_official", "str", True, "Authorizing Official (AO) and Information System Security Manager (ISSM)."),
            AppendixField("system_inventory", "list[str]", True, "Authorized systems and networks in scope with RMF authorizations."),
            AppendixField("boundary_defense", "str", True, "Network boundary defense, firewalls, and cross-domain solutions."),
            AppendixField("endpoint_protection", "str", True, "Endpoint protection, patching, and vulnerability management."),
            AppendixField("identity_and_access_management", "str", True, "PKI, CAC/TISS, and privileged-access management."),
            AppendixField("incident_response", "str", True, "Cyber incident response, reporting, and DCO liaison."),
            AppendixField("continuous_monitoring", "str", False, "Continuous monitoring program and reporting into enterprise sensors."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", True, "Cyber incident reports (USCYBERCOM CCIRs, ARCYBER spot reports)."),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Annex F (Sustainment) - 9 appendices
# Source: FM 4-0; ATP 4-90; ATP 1-0.2; ATP 4-02; FM 1-04; FM 1-05; ATP 4-10;
#         ATP 4-46; ATP 4-10.1
# ---------------------------------------------------------------------------
_ANNEX_F: list[AppendixSpec] = [
    AppendixSpec(
        number=1,
        title="Logistics",
        purpose=(
            "Logistics plan integrating supply, maintenance, transportation, "
            "distribution, field services, and general-engineering-supporting "
            "sustainment."
        ),
        doctrine_reference="FM 4-0 Ch 3; ATP 4-90; FM 6-0 App D",
        fields=[
            AppendixField("logistics_task_organization", "str", True, "Sustainment task organization (BSB, CSSB, ESC, TSC) and support relationships."),
            AppendixField("supply_plan_by_class", "str", True, "Supply plan by class of supply (I-X) with priorities and CSRs."),
            AppendixField("distribution_plan", "str", True, "Distribution plan: supply points, throughput, and sustainment lanes."),
            AppendixField("logpac_schedule", "list[LogisticsSchedule]", True, "LOGPAC schedule, intervals, and link-up points."),
            AppendixField("main_supply_routes", "list[MSRoute]", True, "Main supply routes with checkpoints and hazards."),
            AppendixField("alternate_supply_routes", "list[ASRoute]", True, "Alternate supply routes."),
            AppendixField("maintenance_plan", "str", True, "Field and sustainment-level maintenance plan and evacuation criteria."),
            AppendixField("transportation_plan", "str", True, "Motor, rail, air, and water transportation and MCB coordination."),
            AppendixField("host_nation_and_contracting_linkage", "str", False, "Linkage to Annex F App 7 (OCS) and Annex F App 9 (HNS)."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", True, "LOGSTAT, LOGSYNC, and red/amber/green reporting."),
        ],
    ),
    AppendixSpec(
        number=2,
        title="Personnel Services Support",
        purpose=(
            "Personnel services plan - HR functions including personnel "
            "accountability, casualty operations, EPS, postal, and MWR."
        ),
        doctrine_reference="FM 1-0; ATP 1-0.1; ATP 1-0.2",
        fields=[
            AppendixField("hr_task_organization", "str", True, "HR task organization (HRSC, MMT, HR Company, S-1) and support relationships."),
            AppendixField("personnel_accountability", "str", True, "Personnel accountability and strength reporting (PSR/PAR) procedures."),
            AppendixField("casualty_operations", "str", True, "Casualty reporting, notification, and assistance plan."),
            AppendixField("essential_personnel_services", "list[str]", True, "Essential Personnel Services (awards, evaluations, promotions, transitions)."),
            AppendixField("postal_operations", "str", True, "Postal operations plan and MPS support."),
            AppendixField("replacement_operations", "str", True, "Replacement receiving, processing, and forward movement plan."),
            AppendixField("mwr_band_support", "str", False, "Morale, welfare, recreation, and Army Band support."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", True, "PSR, PAR, and DCIPS casualty reports."),
        ],
    ),
    AppendixSpec(
        number=3,
        title="Army Health System Support",
        purpose=(
            "Army Health System (AHS) support plan - medical treatment, "
            "medical evacuation, medical logistics, and veterinary services - "
            "arrayed across roles of care."
        ),
        doctrine_reference="FM 4-02; ATP 4-02.2; ATP 4-02.5",
        fields=[
            AppendixField("ahs_task_organization", "str", True, "Medical task organization and command/support relationships."),
            AppendixField("roles_of_care", "list[RoleOfCare]", True, "Role 1-4 facilities supporting the operation."),
            AppendixField("medical_evacuation", "str", True, "MEDEVAC plan: ground and air, 9-line procedures, launch authority."),
            AppendixField("ambulance_exchange_points", "list[AmbulanceExchangePoint]", True, "AXPs established to support patient flow."),
            AppendixField("medical_logistics", "str", True, "Class VIII supply, blood support, and medical maintenance."),
            AppendixField("patient_movement", "str", True, "Patient movement across roles, including TRAC2ES and strategic evacuation."),
            AppendixField("preventive_medicine_linkage", "str", False, "Linkage to Annex E App 11 (Force Health Protection)."),
            AppendixField("veterinary_services", "str", False, "Veterinary food-protection, animal care, and zoonotic disease surveillance."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", True, "Medical situation reports (MEDSITREP) and patient regulating reports."),
        ],
    ),
    AppendixSpec(
        number=4,
        title="Financial Management",
        purpose=(
            "Financial management plan - resource management, disbursing, "
            "and commercial-vendor payments in support of the operation."
        ),
        doctrine_reference="FM 1-06; ATP 1-06.1",
        fields=[
            AppendixField("fm_task_organization", "str", True, "FM units (FM Support Unit, FMSU-D, FMCoy) and relationships."),
            AppendixField("resource_management", "str", True, "Resource management, funding streams, and reimbursement authorities."),
            AppendixField("disbursing_operations", "str", True, "Disbursing operations including paying agents, currency, and EFT."),
            AppendixField("commercial_vendor_services", "str", True, "Commercial vendor services, SPV, and micro-purchase procedures."),
            AppendixField("banking_and_currency", "str", False, "Banking support, currency control, and host-nation currency policy."),
            AppendixField("cerp_and_similar_programs", "str", False, "CERP/equivalent programs: authorities, project approval, and oversight."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", False, "FM reports (obligation, disbursement, and AAR of paying agents)."),
        ],
    ),
    AppendixSpec(
        number=5,
        title="Legal Support",
        purpose=(
            "Legal support plan covering operational law, military justice, "
            "administrative law, claims, and legal assistance."
        ),
        doctrine_reference="FM 1-04; AR 27-10; AR 27-20",
        fields=[
            AppendixField("sja_task_organization", "str", True, "Staff Judge Advocate office, LSO, and paralegal support structure."),
            AppendixField("operational_law", "str", True, "Operational law: ROE, LOAC review, targeting CDE, and ISR authorities."),
            AppendixField("military_justice", "str", True, "Military justice plan: GCM/SPCM convening authorities and discipline flow."),
            AppendixField("claims", "str", True, "Claims support (FCA, PCA, SCRA) and contact procedures."),
            AppendixField("administrative_law", "str", False, "Administrative law: investigations (AR 15-6), ethics, and environmental law."),
            AppendixField("legal_assistance", "str", False, "Legal assistance for Soldiers and Family members deploying forward."),
            AppendixField("detainee_legal_review", "str", True, "Legal review supporting detention operations (Annex E App 10)."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", False, "Legal reporting, serious-incident reports, and investigation status."),
        ],
    ),
    AppendixSpec(
        number=6,
        title="Religious Support",
        purpose=(
            "Religious support plan - unit ministry team (UMT) coverage, "
            "area religious support, and denominational / liturgical support."
        ),
        doctrine_reference="FM 1-05; ATP 1-05.01",
        fields=[
            AppendixField("chaplain_task_organization", "str", True, "UMTs assigned and area religious support responsibilities."),
            AppendixField("religious_services_plan", "str", True, "Schedule and locations of religious services by tradition."),
            AppendixField("pastoral_care_and_counseling", "str", True, "Pastoral care, counseling, and critical-event ministry plan."),
            AppendixField("casualty_and_memorial_support", "str", True, "Support to casualty notification, memorial services, and repatriation."),
            AppendixField("advisement_to_command", "str", True, "Chaplain advisement to the commander on religion, morals, and morale."),
            AppendixField("coordination_with_host_nation_clergy", "str", False, "Coordination with local religious leaders per JP 1-05."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", False, "Religious support reporting into the unit battle rhythm."),
        ],
    ),
    AppendixSpec(
        number=7,
        title="Operational Contract Support",
        purpose=(
            "Operational contract support (OCS) plan - contracting, "
            "contractor management, and integration of contracted capabilities."
        ),
        doctrine_reference="ATP 4-10; JP 4-10",
        fields=[
            AppendixField("ocs_integration_cell", "str", True, "OCS Integration Cell / CSB organization and responsibilities."),
            AppendixField("theater_support_contracts", "list[str]", True, "Theater support contracts, external support contracts, and systems support contracts in use."),
            AppendixField("contractor_management", "str", True, "Contractor management plan: APO, SPOT-ES accountability, and GFE/GFP."),
            AppendixField("requirements_development", "str", True, "Requirements development, PWS/SOW review, and acceptance procedures."),
            AppendixField("cor_program", "str", True, "Contracting Officer's Representative (COR) program and oversight."),
            AppendixField("lead_service_contracting", "str", False, "Lead-service contracting designations and cross-service utilization."),
            AppendixField("contractor_protection_and_life_support", "str", True, "Contractor force protection, life support, and MEDEVAC eligibility."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", False, "OCS reporting (contractor personnel census, contract status)."),
        ],
    ),
    AppendixSpec(
        number=8,
        title="Mortuary Affairs",
        purpose=(
            "Mortuary affairs plan - search, recovery, evacuation, processing, "
            "and return of remains."
        ),
        doctrine_reference="ATP 4-46; JP 4-06",
        fields=[
            AppendixField("ma_task_organization", "str", True, "Mortuary Affairs Company, collection points, and JMAC/TMAO structure."),
            AppendixField("collection_points", "list[str]", True, "Mortuary affairs collection points and theater mortuary affairs collection points."),
            AppendixField("search_and_recovery", "str", True, "Search, recovery, and tentative identification procedures."),
            AppendixField("personal_effects", "str", True, "Personal effects processing and Summary Court-Martial Officer responsibilities."),
            AppendixField("contaminated_remains", "str", False, "Contaminated-remains procedures (CBRN, hazardous material)."),
            AppendixField("return_of_remains", "str", True, "Return-of-remains flow through the Armed Forces Medical Examiner System."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", True, "MA reporting and coordination with casualty operations."),
        ],
    ),
    AppendixSpec(
        number=9,
        title="Host-Nation Support",
        purpose=(
            "Host-Nation Support (HNS) plan - agreements, capabilities, and "
            "coordination of HN-provided sustainment."
        ),
        doctrine_reference="ATP 4-10.1; JP 4-0",
        fields=[
            AppendixField("hns_agreements", "list[str]", True, "HNS agreements (SOFA, ACSA, implementing arrangements) in force."),
            AppendixField("hn_capabilities_utilized", "list[str]", True, "HN capabilities used (facilities, labor, transportation, utilities, medical)."),
            AppendixField("liaison_architecture", "str", True, "Liaison architecture with HN military, government, and commercial entities."),
            AppendixField("acsa_transactions", "str", False, "ACSA transaction procedures, approval authorities, and reimbursement."),
            AppendixField("limitations_and_restrictions", "list[str]", True, "Limitations, restrictions, and diplomatic caveats on HNS use."),
            AppendixField("coordination_with_ocs", "str", True, "Deconfliction with OCS (Annex F App 7) to avoid duplication."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", False, "HNS status reporting into the sustainment common operating picture."),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Annex G (Engineer) - 4 appendices
# Source: FM 3-34; ATP 3-34.5; ATP 3-34.80; FM 3-34.170
# ---------------------------------------------------------------------------
_ANNEX_G: list[AppendixSpec] = [
    AppendixSpec(
        number=1,
        title="Mobility/Countermobility/Survivability",
        purpose=(
            "Combat engineering plan - mobility, countermobility, and "
            "survivability tasks supporting maneuver."
        ),
        doctrine_reference="FM 3-34 Ch 3; ATP 3-90.4; ATP 3-37.34",
        fields=[
            AppendixField("engineer_task_organization", "str", True, "Combat engineer units in DS, GS, or OPCON relationships."),
            AppendixField("mobility_tasks", "list[str]", True, "Mobility tasks: breaching, clearance, gap crossing, route construction."),
            AppendixField("countermobility_tasks", "list[str]", True, "Countermobility tasks: obstacles, minefields, and blocking positions."),
            AppendixField("survivability_tasks", "list[str]", True, "Survivability tasks: fighting positions, hardening, and camouflage."),
            AppendixField("obstacle_plan_reference", "str", True, "Reference to obstacle plan / overlay, including obstacle belts and groups."),
            AppendixField("route_clearance_plan", "str", True, "Route clearance plan and supporting sapper/route-clearance patrols."),
            AppendixField("priorities_of_work", "list[str]", True, "Priorities of engineer work by phase and supported unit."),
            AppendixField("coordinating_instructions", "str", False, "Coordination with fires (obstacle integration with FSCMs) and EOD."),
        ],
    ),
    AppendixSpec(
        number=2,
        title="General Engineering",
        purpose=(
            "General engineering plan - construction, base camp development, "
            "vertical/horizontal construction, and contracting support."
        ),
        doctrine_reference="ATP 3-34.40; ATP 3-34.48",
        fields=[
            AppendixField("general_engineering_task_organization", "str", True, "Horizontal, vertical, and utilities units in support."),
            AppendixField("base_camp_construction", "str", True, "Base camp master plan and construction priorities."),
            AppendixField("real_estate_management", "str", False, "Real-estate requirements, acquisition, and disposal."),
            AppendixField("horizontal_construction", "list[str]", True, "Horizontal projects: roads, airfields, bridges, expedient runways."),
            AppendixField("vertical_construction", "list[str]", True, "Vertical projects: billets, admin facilities, hardstands."),
            AppendixField("utilities_and_power", "str", True, "Water, wastewater, power generation, and distribution plans."),
            AppendixField("linkage_to_ocs", "str", False, "Integration with Annex F App 7 (OCS) for contracted construction."),
            AppendixField("priorities_and_funding", "str", True, "Prioritized project list and funding source for each project."),
        ],
    ),
    AppendixSpec(
        number=3,
        title="Geospatial Engineering",
        purpose=(
            "Geospatial engineering plan - terrain analysis, map production, "
            "and foundation geospatial data distribution to the force."
        ),
        doctrine_reference="ATP 3-34.80; FM 3-34 Ch 4",
        fields=[
            AppendixField("geospatial_task_organization", "str", True, "Geospatial planning cells, teams, and supporting NGA elements."),
            AppendixField("terrain_analysis_products", "list[str]", True, "Terrain analysis products required (OAKOC, CCM, cross-country mobility)."),
            AppendixField("map_production_and_distribution", "str", True, "Map production priorities and distribution to supported units."),
            AppendixField("foundation_geospatial_data", "list[str]", True, "Foundation geospatial data (DTED, controlled imagery, SRTM) in use."),
            AppendixField("standard_shared_geospatial_architecture", "str", True, "SSGA and theater geospatial database architecture."),
            AppendixField("coordination_with_geoint", "str", True, "Coordination with Annex B App 5 (GEOINT) and Annex C App 2 (Operation Overlay)."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", False, "Geospatial product request and dissemination reporting."),
        ],
    ),
    AppendixSpec(
        number=4,
        title="Environmental Considerations",
        purpose=(
            "Environmental considerations plan - compliance, protection, and "
            "mitigation to protect health, safety, and mission capability."
        ),
        doctrine_reference="ATP 3-34.5; AR 200-1; JP 3-34",
        fields=[
            AppendixField("environmental_baseline", "str", True, "Baseline environmental conditions survey (EBS) summary."),
            AppendixField("applicable_standards", "list[str]", True, "Applicable environmental standards (FGS, OEBGD, HN law)."),
            AppendixField("hazardous_material_management", "str", True, "HAZMAT management: storage, handling, disposal, and spill response."),
            AppendixField("waste_management", "str", True, "Solid, medical, and hazardous waste management plan."),
            AppendixField("cultural_resources", "str", True, "Cultural and historical resource protection measures."),
            AppendixField("environmental_officer", "str", True, "Designated environmental officer and compliance responsibilities."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", False, "Environmental incident and spill reporting."),
            AppendixField("coordinating_instructions", "str", False, "Coordination with HN environmental authorities and EPA liaison as applicable."),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Annex H (Signal) - 7 appendices
# Source: FM 6-02; ATP 6-02.53/.54/.70/.71/.75; CJCSM 6510.01B
# ---------------------------------------------------------------------------
_ANNEX_H: list[AppendixSpec] = [
    AppendixSpec(
        number=1,
        title="Network Operations (Communications Plan)",
        purpose=(
            "Network operations plan - operate, secure, and defend the DODIN-A "
            "footprint supporting the operation, with service levels and PACE."
        ),
        doctrine_reference="FM 6-02; ATP 6-02.71",
        fields=[
            AppendixField("signal_task_organization", "str", True, "Signal units (ESB, ESB-E, strategic signal) and support relationships."),
            AppendixField("network_architecture", "str", True, "Unclassified, secret, and mission-partner network architecture."),
            AppendixField("pace_plan", "str", True, "Primary, Alternate, Contingency, Emergency (PACE) plan by warfighting function."),
            AppendixField("service_levels", "list[str]", True, "Service-level objectives for voice, data, and mission applications."),
            AppendixField("frequency_and_spectrum_linkage", "str", True, "Linkage to Annex H App 5 (Spectrum Management) and JRFL."),
            AppendixField("cyber_linkage", "str", True, "Linkage to Annex E App 14 (Cybersecurity) and DODIN operations."),
            AppendixField("network_management_tools", "list[str]", False, "Tools used to monitor, configure, and defend the network."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", True, "Network SITREPs, outages, and MIJI reports."),
        ],
    ),
    AppendixSpec(
        number=2,
        title="Voice, Video, and Data Network Diagrams",
        purpose=(
            "Detailed network diagrams depicting voice, video, and data "
            "connectivity from the strategic enterprise to the tactical edge."
        ),
        doctrine_reference="FM 6-02; ATP 6-02.71",
        fields=[
            AppendixField("logical_diagrams", "list[str]", True, "Logical network diagrams (routing, IP, AS numbers) included."),
            AppendixField("physical_diagrams", "list[str]", True, "Physical diagrams (cable plant, racks, locations)."),
            AppendixField("voice_architecture", "str", True, "Voice architecture: VoIP, MSE/TRI-TAC, SIP trunks, conferencing."),
            AppendixField("video_architecture", "str", True, "VTC architecture, bridges, and encryption."),
            AppendixField("data_architecture", "str", True, "Data architecture: WAN links, satellite, mission-partner environments."),
            AppendixField("classification", "ClassificationMarking", True, "Overall classification of the diagrams set."),
            AppendixField("change_management", "str", False, "Configuration/change management authority and approval process."),
        ],
    ),
    AppendixSpec(
        number=3,
        title="Satellite Communications",
        purpose=(
            "SATCOM plan - accesses, networks, terminals, and control of "
            "military and commercial satellite capabilities."
        ),
        doctrine_reference="ATP 6-02.54; JP 6-0",
        fields=[
            AppendixField("satcom_accesses", "list[str]", True, "Authorized SATCOM accesses (GBS, WGS, MUOS, commercial) and GARs."),
            AppendixField("terminal_inventory", "list[str]", True, "Assigned terminals, baseband equipment, and operators."),
            AppendixField("network_control", "str", True, "Network control station / hub responsibilities and SATCOM control."),
            AppendixField("crypto_and_keying", "str", True, "Crypto, keying, and rekeying plan for SATCOM networks."),
            AppendixField("ema_procedures", "str", False, "Electromagnetic attack mitigation and anti-jam procedures."),
            AppendixField("bandwidth_management", "str", True, "Bandwidth prioritization and precedence across SATCOM links."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", True, "SATCOM outage, interference (MIJI), and usage reporting."),
        ],
    ),
    AppendixSpec(
        number=4,
        title="Foreign Data Exchange",
        purpose=(
            "Mission-partner environment (MPE) and foreign data exchange plan "
            "for sharing data with allies and coalition partners."
        ),
        doctrine_reference="FM 6-02; CJCSI 6731.01; DODI 8110.01",
        fields=[
            AppendixField("authorized_partners", "list[str]", True, "Authorized mission partners and applicable information sharing agreements."),
            AppendixField("sharing_environments", "list[str]", True, "Sharing environments (BICES, CENTRIXS, MPE, national MPE partitions) in use."),
            AppendixField("cross_domain_solutions", "str", True, "CDS architecture authorizing the data flow between domains."),
            AppendixField("release_authorities", "str", True, "Foreign disclosure and release authorities (FDO) and delegation."),
            AppendixField("data_tagging_and_marking", "str", True, "Data tagging and marking requirements for shared content."),
            AppendixField("incident_response", "str", False, "Incident response for compromise or unauthorized disclosure."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", False, "Foreign disclosure and data-sharing incident reporting."),
        ],
    ),
    AppendixSpec(
        number=5,
        title="Spectrum Management Operations",
        purpose=(
            "Spectrum management operations (SMO) plan - frequency assignment, "
            "deconfliction, and electromagnetic interference resolution."
        ),
        doctrine_reference="ATP 6-02.70; CJCSM 3320.02",
        fields=[
            AppendixField("smo_task_organization", "str", True, "JSME, theater SMO cells, and unit spectrum managers."),
            AppendixField("frequency_plan", "str", True, "Assigned frequencies and frequency allocation by net and phase."),
            AppendixField("jrfl", "str", True, "Joint Restricted Frequency List (JRFL) coordination and maintenance."),
            AppendixField("emi_reporting", "str", True, "Electromagnetic interference (MIJI) reporting and resolution procedures."),
            AppendixField("host_nation_coordination", "str", True, "Host-nation spectrum coordination and diplomatic clearance."),
            AppendixField("cema_integration", "str", True, "Integration with Annex C App 12 (CEMA) for EW effects."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", True, "Spectrum reports (SFAF, JRFL updates, MIJI)."),
        ],
    ),
    AppendixSpec(
        number=6,
        title="Information Services",
        purpose=(
            "Information services plan - collaboration services, data services, "
            "enterprise applications, and content management supporting the force."
        ),
        doctrine_reference="FM 6-02; ATP 6-02.60",
        fields=[
            AppendixField("service_catalog", "list[str]", True, "Authorized enterprise services (email, collaboration, content, identity)."),
            AppendixField("content_and_knowledge_management_linkage", "str", True, "Linkage to Annex Q (Knowledge Management) and unit KM plan."),
            AppendixField("mission_applications", "list[str]", True, "Command and control mission applications (CPCE, JBC-P, etc.) in use."),
            AppendixField("help_desk_architecture", "str", True, "Help desk, incident management, and trouble-ticket flow."),
            AppendixField("access_and_account_management", "str", True, "Account provisioning, roles, and privileged access."),
            AppendixField("data_backup_and_continuity", "str", True, "Backup, continuity of operations, and disaster recovery plan."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", False, "Service-level reporting and outage reporting."),
        ],
    ),
    AppendixSpec(
        number=7,
        title="COMSEC",
        purpose=(
            "Communications security (COMSEC) plan - key management, "
            "distribution, accounting, and incident reporting."
        ),
        doctrine_reference="ATP 6-02.75; AR 380-40; CJCSI 6510.01F",
        fields=[
            AppendixField("comsec_account", "str", True, "COMSEC account(s) supporting the operation and custodians."),
            AppendixField("key_management_plan", "str", True, "Key management plan including KMI/EKMS, key production, and distribution."),
            AppendixField("rekey_schedule", "str", True, "Scheduled and emergency rekey plan by net and device."),
            AppendixField("distribution_procedures", "str", True, "Physical and over-the-network key distribution procedures."),
            AppendixField("comsec_incident_reporting", "list[ReportDefinition]", True, "COMSEC incident reporting (TSR, KMI, loss/compromise)."),
            AppendixField("storage_and_destruction", "str", True, "COMSEC storage, handling, and destruction procedures."),
            AppendixField("training_and_inspections", "str", False, "Training requirements and inspection program for custodians and users."),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Annex J (Public Affairs) - 1 appendix
# Source: FM 3-61; ATP 3-61.1
# ---------------------------------------------------------------------------
_ANNEX_J: list[AppendixSpec] = [
    AppendixSpec(
        number=1,
        title="Public Affairs Running Estimate and Media Engagement Plan",
        purpose=(
            "PA running estimate plus the media engagement plan - media "
            "facilitation, command information, and community engagement - "
            "that enables informing audiences with timely, accurate information."
        ),
        doctrine_reference="FM 3-61 Ch 3; ATP 3-61.1; FM 6-0 App D",
        fields=[
            AppendixField("pa_running_estimate_summary", "str", True, "PA running estimate summary of the media and information environment."),
            AppendixField("pa_objectives", "list[str]", True, "PA objectives tied to the commander's intent and end state."),
            AppendixField("themes_and_messages", "list[str]", True, "Approved themes and messages for the operation."),
            AppendixField("media_engagement_plan", "str", True, "Media engagement plan: facilitation, embeds, interviews, and press conferences."),
            AppendixField("command_information", "str", True, "Internal command information plan for Soldiers, Families, and civilians."),
            AppendixField("community_engagement", "str", False, "Community engagement activities with HN and local audiences."),
            AppendixField("release_authorities", "str", True, "Information release authorities (PAO, SJA, G-2, OPSEC)."),
            AppendixField("coordination_with_miso_and_io", "str", True, "Coordination with Annex C App 8 (IO) and App 13 (MISO) to avoid message conflict."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", False, "Media query logs, daily PA assessments, and social-media monitoring reports."),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Annex K (Civil Affairs Operations) - 6 appendices
# Source: FM 3-57; ATP 3-57.10; ATP 3-57.20; ATP 3-57.30; ATP 3-57.40; ATP 3-57.60/70
# ---------------------------------------------------------------------------
_ANNEX_K: list[AppendixSpec] = [
    AppendixSpec(
        number=1,
        title="Civil-Military Operations Estimate",
        purpose=(
            "Running civil-military operations estimate summarizing civil "
            "considerations, CA task organization, and CMO impacts on the "
            "operation."
        ),
        doctrine_reference="FM 3-57 Ch 3; ATP 3-57.60",
        fields=[
            AppendixField("as_of_dtg", "DTGString", True, "DTG the CMO estimate was last updated."),
            AppendixField("civil_considerations", "str", True, "ASCOPE analysis of civil components (areas, structures, capabilities, organizations, people, events)."),
            AppendixField("ca_task_organization", "str", True, "Civil Affairs units and teams supporting the operation."),
            AppendixField("cmo_objectives", "list[str]", True, "CMO objectives tied to the commander's end state."),
            AppendixField("cmo_tasks", "list[SubordinateTaskItem]", True, "CMO tasks assigned to CA and conventional units."),
            AppendixField("key_leaders_and_networks", "list[str]", True, "Key leaders, tribal/governmental networks, and civil-social power dynamics."),
            AppendixField("indicators_and_metrics", "list[str]", True, "Indicators/MOEs for the civil component of the OE."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", False, "CA reporting requirements (CA SITREP, CIM inputs)."),
        ],
    ),
    AppendixSpec(
        number=2,
        title="Civil Information Management",
        purpose=(
            "Civil Information Management (CIM) plan - collect, collate, "
            "process, analyze, and disseminate civil information supporting "
            "the common operating picture."
        ),
        doctrine_reference="ATP 3-57.50",
        fields=[
            AppendixField("cim_architecture", "str", True, "CIM architecture: CAT, CA planning team, and supporting databases/portals."),
            AppendixField("collection_plan", "str", True, "Civil information collection plan and priorities."),
            AppendixField("data_standards", "str", True, "Data standards (geospatial, categorical) governing civil information."),
            AppendixField("analysis_products", "list[str]", True, "CIM analytic products (civil common operating picture, civil incident tracker)."),
            AppendixField("dissemination", "str", True, "Dissemination to staff, subordinates, interagency, and partners."),
            AppendixField("privacy_and_pii_handling", "str", True, "Privacy/PII handling controls and US persons rules compliance."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", False, "CIM reporting cadence and formats."),
        ],
    ),
    AppendixSpec(
        number=3,
        title="Populace and Resources Control",
        purpose=(
            "Populace and resources control (PRC) plan - dislocated civilians, "
            "curfews, movement control, and control of commodities."
        ),
        doctrine_reference="ATP 3-57.10",
        fields=[
            AppendixField("prc_objectives", "list[str]", True, "PRC objectives and intended civilian effects."),
            AppendixField("populace_control_measures", "list[str]", True, "Curfews, ID checks, registration, movement restrictions, and noncombatant evacuation."),
            AppendixField("resources_control_measures", "list[str]", True, "Rationing, licensing, price control, and commodity checkpoints."),
            AppendixField("dislocated_civilian_plan", "str", True, "DC routing, camps, humanitarian assistance, and repatriation."),
            AppendixField("coordination_with_host_nation", "str", True, "HN government coordination for PRC authorities and enforcement."),
            AppendixField("legal_review", "str", True, "Legal review of PRC measures IAW LOAC and HN law."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", False, "PRC reporting (DC counts, checkpoint logs, commodity status)."),
        ],
    ),
    AppendixSpec(
        number=4,
        title="Foreign Humanitarian Assistance",
        purpose=(
            "Foreign humanitarian assistance (FHA) plan - relief operations, "
            "dislocated civilians, and support to humanitarian actors."
        ),
        doctrine_reference="ATP 3-57.20; JP 3-29",
        fields=[
            AppendixField("fha_objectives", "list[str]", True, "FHA objectives and approved end state for humanitarian relief."),
            AppendixField("supported_population", "str", True, "Population to be supported, estimated size, and vulnerabilities."),
            AppendixField("coordination_with_iccos", "str", True, "Coordination with IOs, NGOs, and host-nation authorities (e.g. HCCC, CMOC)."),
            AppendixField("logistics_support", "str", True, "Logistics support: distribution sites, commodities, and sustainment footprint."),
            AppendixField("medical_support", "str", True, "Medical support (preventive, treatment, evacuation) to the humanitarian effort."),
            AppendixField("security_support", "str", True, "Security support to relief operations and humanitarian actors."),
            AppendixField("transition_and_termination", "str", True, "Transition of FHA responsibilities to civil authorities and termination criteria."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", False, "FHA reporting (population counts, distribution, medical)."),
        ],
    ),
    AppendixSpec(
        number=5,
        title="Military Government / Transitional Military Authority",
        purpose=(
            "Transitional Military Authority plan - establishment, operation, "
            "and transition of military government over civil authorities."
        ),
        doctrine_reference="ATP 3-57.40; JP 3-57",
        fields=[
            AppendixField("authority_basis", "str", True, "Legal basis for military government (LOAC, UNSCR, SOFA)."),
            AppendixField("governance_functions", "list[str]", True, "Governance functions assumed (security, justice, essential services, economy)."),
            AppendixField("governance_architecture", "str", True, "Governance architecture: civil-affairs planning team, functional specialists, and civil liaisons."),
            AppendixField("interagency_integration", "str", True, "Interagency integration (DOS, USAID, DOJ) and coordination mechanisms."),
            AppendixField("transition_plan", "str", True, "Transition plan to HN or international civil authority."),
            AppendixField("end_state_criteria", "str", True, "End state and criteria that terminate military government."),
            AppendixField("legal_review", "str", True, "Standing legal review of military government acts per LOAC."),
        ],
    ),
    AppendixSpec(
        number=6,
        title="Civil-Military Operations Center (CMOC) Operations",
        purpose=(
            "CMOC organization and procedures to coordinate civil-military "
            "activities with HN, IOs, NGOs, and interagency partners."
        ),
        doctrine_reference="ATP 3-57.70; JP 3-57",
        fields=[
            AppendixField("cmoc_locations", "list[str]", True, "CMOC locations (primary, subordinate) and hours of operation."),
            AppendixField("cmoc_organization", "str", True, "CMOC internal organization, watch-desks, and liaison seats."),
            AppendixField("attendees_and_liaison", "list[str]", True, "Standing participants: HN, IO, NGO, interagency, and partner-nation representation."),
            AppendixField("request_management", "str", True, "Civil assistance request (CAR) flow, tracking, and disposition."),
            AppendixField("information_sharing", "str", True, "Information sharing policies governing releasability to civilian actors."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", True, "CMOC situation reports and working-group outputs."),
            AppendixField("coordinating_instructions", "str", False, "Coordination with Annex V (Interagency Coordination) and Annex J (Public Affairs)."),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Annex L (Information Collection) - 4 appendices
# Source: FM 3-55; ATP 2-01; FM 6-0 App D
# ---------------------------------------------------------------------------
_ANNEX_L: list[AppendixSpec] = [
    AppendixSpec(
        number=1,
        title="Information Collection Plan",
        purpose=(
            "Consolidated Information Collection Plan (ICP) assigning "
            "requirements to collection assets and tying them to PIR, NAIs, "
            "and indicators."
        ),
        doctrine_reference="FM 3-55 Ch 3; ATP 2-01; FM 6-0 App D",
        fields=[
            AppendixField("priority_intelligence_requirements", "list[PIR]", True, "PIR driving the collection effort."),
            AppendixField("indicators", "list[str]", True, "Indicators mapped to PIR that observers will look for."),
            AppendixField("named_areas_of_interest", "list[NamedAreaOfInterest]", True, "NAIs where collection will occur."),
            AppendixField("specific_information_requirements", "list[str]", True, "SIRs derived from the PIR/indicators."),
            AppendixField("collection_tasks", "list[SubordinateTaskItem]", True, "Collection tasks assigned to units and assets."),
            AppendixField("ltiov", "str", True, "Aggregate LTIOV guidance for the collection effort."),
            AppendixField("reporting_channels", "list[ReportDefinition]", True, "Reporting channels and formats for collection results."),
            AppendixField("coordinating_instructions", "str", False, "Deconfliction with joint, SOF, and partner-nation collection."),
        ],
    ),
    AppendixSpec(
        number=2,
        title="Information Collection Overlay",
        purpose=(
            "Graphic overlay depicting NAIs, collection assets, orbits, and "
            "supporting control measures for the ICP."
        ),
        doctrine_reference="FM 3-55 App B; ATP 2-01",
        fields=[
            AppendixField("overlay_reference_map", "str", True, "Reference map and scale for the overlay."),
            AppendixField("nais", "list[NamedAreaOfInterest]", True, "NAIs plotted on the overlay."),
            AppendixField("collection_assets_locations", "list[str]", True, "Asset locations, orbit points, and ingress/egress routes."),
            AppendixField("acms_and_fscms", "list[str]", False, "ACMs and FSCMs relevant to collection asset operations."),
            AppendixField("phases_depicted", "list[str]", True, "Phases or time blocks represented on the overlay."),
            AppendixField("classification", "ClassificationMarking", True, "Overall classification and handling caveats."),
        ],
    ),
    AppendixSpec(
        number=3,
        title="Reconnaissance and Surveillance",
        purpose=(
            "Reconnaissance and surveillance tasks to subordinate units - "
            "scouts, cavalry, UAS, and infantry - with commander's recon "
            "guidance."
        ),
        doctrine_reference="FM 3-55 Ch 4; FM 3-98",
        fields=[
            AppendixField("commander_recon_guidance", "str", True, "Commander's reconnaissance guidance (focus, tempo, engagement/disengagement)."),
            AppendixField("recon_objectives", "list[str]", True, "Reconnaissance objectives tied to CCIR."),
            AppendixField("surveillance_tasks", "list[SubordinateTaskItem]", True, "Surveillance tasks assigned to units and UAS."),
            AppendixField("cavalry_and_scout_tasks", "list[SubordinateTaskItem]", True, "Cavalry/scout tasks with purpose and endstate."),
            AppendixField("uas_employment", "str", True, "UAS employment plan (orbits, handoffs, airspace)."),
            AppendixField("handover_criteria", "str", True, "Criteria and procedures for handing off NAIs and targets between assets."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", True, "SALUTE, SPOT, and contact reporting formats."),
        ],
    ),
    AppendixSpec(
        number=4,
        title="ISR Synchronization Matrix",
        purpose=(
            "Time-phased ISR synchronization matrix coordinating sensors, "
            "NAIs, PIR, and reporting across the operation timeline."
        ),
        doctrine_reference="FM 3-55 Ch 3; ATP 2-01",
        fields=[
            AppendixField("time_blocks", "list[str]", True, "Ordered time blocks or phases covered by the matrix."),
            AppendixField("nai_by_time", "list[str]", True, "NAIs active by time block with primary/alternate collector."),
            AppendixField("pir_coverage", "list[str]", True, "PIR coverage showing which asset answers which PIR in each time block."),
            AppendixField("sensor_tasking", "list[SubordinateTaskItem]", True, "Sensor/asset tasking by time block."),
            AppendixField("report_triggers", "list[str]", True, "Reporting triggers and LTIOVs in each time block."),
            AppendixField("matrix_reference", "Optional[str]", False, "Reference to the formal matrix document or file."),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Annex M (Assessment) - 2 appendices
# Source: ADP 5-0 Ch 5; FM 6-0 App D; ATP 5-0.3
# ---------------------------------------------------------------------------
_ANNEX_M: list[AppendixSpec] = [
    AppendixSpec(
        number=1,
        title="Assessment Framework",
        purpose=(
            "Assessment framework - assessment working group, assessment "
            "plan, and linkage to the commander's critical-information "
            "requirements and decision points."
        ),
        doctrine_reference="ADP 5-0 Ch 5; FM 6-0 App D; ATP 5-0.3",
        fields=[
            AppendixField("assessment_purpose", "str", True, "Purpose of assessment in the context of the operation."),
            AppendixField("assessment_working_group", "BattleRhythmEvent", True, "Assessment working group cadence, chair, and outputs."),
            AppendixField("assessment_questions", "list[str]", True, "Assessment questions derived from the commander's intent and LOEs."),
            AppendixField("assessment_responsibilities", "list[SubordinateTaskItem]", True, "Assessment responsibilities assigned to staff sections."),
            AppendixField("linkage_to_dsm", "str", True, "Linkage between assessment outputs and the Decision Support Matrix (Annex C App 3)."),
            AppendixField("reporting_cadence", "str", True, "Cadence for recurring assessment reports to the commander."),
            AppendixField("data_sources", "list[str]", True, "Primary and alternate data sources feeding assessment."),
            AppendixField("reframing_criteria", "str", False, "Criteria that would trigger operational reframing based on assessment."),
        ],
    ),
    AppendixSpec(
        number=2,
        title="MOE/MOP Matrices",
        purpose=(
            "Measures of Effectiveness (MOE) and Measures of Performance "
            "(MOP) matrices with indicators, data sources, and thresholds."
        ),
        doctrine_reference="ADP 5-0 Ch 5; ATP 5-0.3",
        fields=[
            AppendixField("moes", "list[str]", True, "MOEs assessing changes in the OE and progress toward the end state."),
            AppendixField("mops", "list[str]", True, "MOPs measuring task performance."),
            AppendixField("indicators", "list[str]", True, "Indicators supporting each MOE/MOP."),
            AppendixField("data_sources", "list[str]", True, "Data sources and collection responsibility for each indicator."),
            AppendixField("thresholds_and_benchmarks", "list[str]", True, "Thresholds, benchmarks, and red/amber/green criteria."),
            AppendixField("collection_cadence", "str", True, "Cadence for indicator collection and refresh."),
            AppendixField("presentation_format", "str", False, "How matrices are presented in the battle rhythm (dashboard, running slide)."),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Annex N (Space Operations) - 3 appendices
# Source: FM 3-14; ADP 3-14; JP 3-14
# ---------------------------------------------------------------------------
_ANNEX_N: list[AppendixSpec] = [
    AppendixSpec(
        number=1,
        title="Space Support Requests",
        purpose=(
            "Space Support Request (SSR) plan - standing and mission-specific "
            "SSRs submitted to higher and theater space staffs."
        ),
        doctrine_reference="FM 3-14 Ch 5; JP 3-14",
        fields=[
            AppendixField("ssr_list", "list[str]", True, "SSRs submitted with identifier, purpose, and supported operation."),
            AppendixField("approval_authorities", "str", True, "SSR approval chain (theater space staff, JFCC SPACE) and timelines."),
            AppendixField("priorities", "list[str]", True, "Commander's SSR priorities and tiebreakers."),
            AppendixField("linked_requirements", "list[str]", True, "Operational requirements each SSR supports."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", False, "SSR status reports and completion criteria."),
            AppendixField("coordinating_instructions", "str", False, "Coordination with Annex C App 14 (Space Operations) for execution."),
        ],
    ),
    AppendixSpec(
        number=2,
        title="Friendly Space Order of Battle",
        purpose=(
            "Friendly space order of battle - capabilities, unit assignments, "
            "and availability windows supporting the operation."
        ),
        doctrine_reference="FM 3-14 Ch 3",
        fields=[
            AppendixField("friendly_space_units", "list[str]", True, "Army, joint, and partner space units in support."),
            AppendixField("capabilities_by_mission_area", "list[str]", True, "Capabilities by space mission area (SATCOM, PNT, MW, ISR, environmental)."),
            AppendixField("availability_windows", "str", True, "Availability windows and constellation coverage over the AO."),
            AppendixField("points_of_contact", "list[str]", True, "Space cell and liaison points of contact."),
            AppendixField("ssa_coverage", "str", False, "Space situational awareness coverage of the AO."),
            AppendixField("coordinating_instructions", "str", False, "Coordination channels for space capability requests."),
        ],
    ),
    AppendixSpec(
        number=3,
        title="Threat Space Order of Battle",
        purpose=(
            "Threat space and counterspace order of battle - capabilities, "
            "employment doctrine, and impact on friendly operations."
        ),
        doctrine_reference="FM 3-14 Ch 2; ATP 3-14.3",
        fields=[
            AppendixField("threat_space_capabilities", "list[str]", True, "Threat space capabilities (SATCOM, ISR, PNT) by provider state."),
            AppendixField("threat_counterspace_capabilities", "list[str]", True, "Threat counterspace (kinetic, electronic, cyber, directed-energy) capabilities."),
            AppendixField("threat_doctrine", "str", True, "Threat doctrine and likely employment of space and counterspace."),
            AppendixField("impacts_on_friendly_ops", "str", True, "Assessed impacts on friendly space-dependent operations."),
            AppendixField("indicators_and_warning", "list[str]", True, "Indications and warning of threat counterspace activity."),
            AppendixField("linked_pirs", "list[PIR]", False, "PIR covering threat space and counterspace."),
            AppendixField("coordinating_instructions", "str", False, "Coordination with Annex B (Intelligence) for space IPB."),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Annex Q (Knowledge Management) - 3 appendices
# Source: ATP 6-01.1
# ---------------------------------------------------------------------------
_ANNEX_Q: list[AppendixSpec] = [
    AppendixSpec(
        number=1,
        title="Knowledge Management Plan",
        purpose=(
            "Knowledge management plan - people, process, tools, and "
            "organization - that enables shared understanding across the staff."
        ),
        doctrine_reference="ATP 6-01.1 Ch 2",
        fields=[
            AppendixField("km_objectives", "list[str]", True, "KM objectives supporting the commander's intent and staff efficiency."),
            AppendixField("km_roles_and_responsibilities", "list[str]", True, "KMO, KM cell, and staff-section KM representative responsibilities."),
            AppendixField("knowledge_requirements", "list[str]", True, "Knowledge requirements: what must be known by whom, when."),
            AppendixField("tools_and_platforms", "list[str]", True, "KM tools and platforms (portals, CoPs, content services) in use."),
            AppendixField("content_management_plan", "str", True, "Content management plan: taxonomy, lifecycle, and ownership."),
            AppendixField("lessons_learned_integration", "str", True, "CALL and unit lessons-learned integration in the KM cycle."),
            AppendixField("metrics", "list[str]", False, "KM metrics and indicators of program health."),
        ],
    ),
    AppendixSpec(
        number=2,
        title="Battle Rhythm",
        purpose=(
            "Unit battle rhythm - recurring briefs, boards, working groups, "
            "and sync meetings - sequenced to enable commander decisions."
        ),
        doctrine_reference="ATP 6-01.1 Ch 3; ATP 6-0.5",
        fields=[
            AppendixField("battle_rhythm_events", "list[BattleRhythmEvent]", True, "All recurring battle-rhythm events with chair, cadence, and outputs."),
            AppendixField("decision_forums", "list[str]", True, "Decision forums in the battle rhythm (e.g. targeting board, CUB)."),
            AppendixField("higher_hq_integration", "str", True, "Integration with higher headquarters battle rhythm and deadlines."),
            AppendixField("shift_changes", "str", True, "Shift-change procedures and required hand-over products."),
            AppendixField("review_cycle", "str", True, "Battle rhythm review cycle and change-approval authority."),
            AppendixField("tempo_adjustments", "str", False, "Adjustments to tempo during execution (e.g. surge, contact)."),
        ],
    ),
    AppendixSpec(
        number=3,
        title="Information Management",
        purpose=(
            "Information management (IM) plan - how data and information "
            "flow, are stored, and are managed across the staff."
        ),
        doctrine_reference="ATP 6-01.1 Ch 4",
        fields=[
            AppendixField("information_flows", "str", True, "Information flows between staff sections, subordinates, and higher HQ."),
            AppendixField("data_standards", "str", True, "Data standards, naming conventions, and metadata requirements."),
            AppendixField("records_management", "str", True, "Records management per AR 25-400-2 and unit SOP."),
            AppendixField("dissemination_policies", "str", True, "Information dissemination and releasability policies (FOUO, CUI)."),
            AppendixField("storage_architecture", "str", True, "Primary and alternate storage architecture for unit information."),
            AppendixField("retention_and_destruction", "str", False, "Retention schedules and authorized destruction procedures."),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Annex R (Reports) - 1 appendix
# Source: FM 6-99
# ---------------------------------------------------------------------------
_ANNEX_R: list[AppendixSpec] = [
    AppendixSpec(
        number=1,
        title="Report Formats",
        purpose=(
            "Consolidated report formats referenced by Annex R - required "
            "Army, joint, and unit reports with format, precedence, and flow."
        ),
        doctrine_reference="FM 6-99",
        fields=[
            AppendixField("required_reports", "list[ReportDefinition]", True, "Required reports with submitter, recipient, frequency, and precedence."),
            AppendixField("format_references", "list[str]", True, "References to USMTF, SOP, and doctrinal formats for each report."),
            AppendixField("precedence_and_timeliness", "str", True, "Precedence and timeliness standards for reporting (FLASH/IMMEDIATE/PRIORITY/ROUTINE)."),
            AppendixField("transmission_means", "list[str]", True, "Transmission means and alternate paths (SIPR email, JBC-P, FM voice)."),
            AppendixField("classification_guidance", "str", True, "Classification guidance by report type."),
            AppendixField("discrepancies_and_corrections", "str", False, "Procedures for handling late, missing, or corrected reports."),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Annex V (Interagency Coordination) - 1 appendix
# Source: JP 3-08; FM 3-08
# ---------------------------------------------------------------------------
_ANNEX_V: list[AppendixSpec] = [
    AppendixSpec(
        number=1,
        title="Interagency Partner Liaison",
        purpose=(
            "Interagency partner liaison plan - liaison architecture, "
            "authorities, and coordinating mechanisms with U.S. and "
            "international partners."
        ),
        doctrine_reference="JP 3-08; FM 3-08",
        fields=[
            AppendixField("interagency_partners", "list[str]", True, "U.S. Government agencies and international partners represented."),
            AppendixField("liaison_architecture", "str", True, "Liaison architecture: placements, reach-back, and reporting lines."),
            AppendixField("coordinating_mechanisms", "list[str]", True, "Coordinating mechanisms (JIACG, country team, CMOC) in use."),
            AppendixField("authorities_and_agreements", "list[str]", True, "Authorities, SOFAs, and MOUs governing interagency cooperation."),
            AppendixField("information_sharing", "str", True, "Information sharing policies and classification handling across partners."),
            AppendixField("points_of_contact", "list[str]", True, "Primary and alternate POCs for each partner organization."),
            AppendixField("reporting_requirements", "list[ReportDefinition]", False, "Reporting into the interagency common operating picture."),
            AppendixField("coordinating_instructions", "str", False, "Coordination with Annex K (Civil Affairs) and Annex J (Public Affairs)."),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Final catalog
# ---------------------------------------------------------------------------
APPENDIX_CATALOG: dict[str, list[AppendixSpec]] = {
    "A": [],  # Task Organization - no appendices
    "B": _ANNEX_B,
    "C": _ANNEX_C,
    "D": _ANNEX_D,
    "E": _ANNEX_E,
    "F": _ANNEX_F,
    "G": _ANNEX_G,
    "H": _ANNEX_H,
    "J": _ANNEX_J,
    "K": _ANNEX_K,
    "L": _ANNEX_L,
    "M": _ANNEX_M,
    "N": _ANNEX_N,
    "P": [],  # Host-Nation Support - body-only; sustainment HNS detail lives in Annex F App 9
    "Q": _ANNEX_Q,
    "R": _ANNEX_R,
    "S": [],  # Special Technical Operations - body-only pointer; detail in compartmented publications
    "U": [],  # Inspector General - body-only
    "V": _ANNEX_V,
    "Z": [],  # Distribution - body-only
}


__all__ = [
    "AppendixField",
    "AppendixSpec",
    "APPENDIX_CATALOG",
]
