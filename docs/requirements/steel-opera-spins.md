# Operation Steel Opera SPINS

## Purpose and scope

Produce a readable SPINS draft from the exact `Operation Steel Opera.miz` in Saved Games/DCS.openbeta/Missions. Use the existing SPINS schema and generator. The newer hyphenated filename is a different source and is not substituted.

## Definitions and constraints

Configured behavior is data or code present in the source archive. Observed runtime behavior requires a DCS session and is not established by this work. Draft procedures are newly authored coordination instructions, identified as proposals in the publication.

The integration is an external, read-only archive inspection. Mission scripts are inspected as text, not executed. No DCS installation or mission archive is changed. The local terrain radio database supplements airfield frequencies; it is identified separately from mission data. Local DCS logs identify build 2.9.29.27468.

TACAN planning calculations use the Persian Gulf projection checked against installed beacon coordinates and an offline invocation of the installed DCS Lua magnetic-variation module. The module is initialized to June 2018 using the Mission Editor's documented call pattern. No simulator mission is started. The 1,000-ft military planning margin is an authored draft policy; it is not a source-mission setting or an asserted real-world separation standard.

## Requirements and verification

| ID | Requirement | Acceptance method |
|---|---|---|
| SO-001 | The source archive shall remain unchanged. | Compare its SHA-256 before and after work; inspection. |
| SO-002 | The publication shall distinguish source facts, proposed procedures, and unresolved decisions. | Trace airspaces, traffic routes, frequencies, and support limitations to source notes; inspection. |
| SO-003 | The publication shall use generated numbering and cross-references. | Validate the authored schema and inspect HTML links and actual PDF text; demonstration. |
| SO-004 | The deliverable shall include editable YAML, standalone HTML, and PDF. | Render with the repository task; verify local HTTP links from Windows; demonstration. |
| SO-005 | The Al Dhafra section shall include the mission's drawn HI/LO entry-route layout. | Check all eight relevant generic line objects and ten HI/LO/altitude annotations, preserve the source geometry in a dedicated figure, and verify the section in HTML and PDF; inspection and demonstration. |
| SO-006 | The publication shall identify the western and southern DME arcs with their reference aid and nominal distance. | Calculate ranges from the source vertices to MA, distinguish nominal 15 DME from approximate map geometry and slant range, and check both arc descriptions in the output; analysis and inspection. |
| SO-007 | Each Al Dhafra arrival shall have a distinct mission procedure name and a traceable source mapping. | Verify OPERA ONE, MINHA ONE, TENOR ONE, LYRIC ONE, and shared transition names in prose, tables, and the route figure; inspection. |
| SO-008 | The SPINS shall state how military flights remain above or below the civil traffic volumes. | Derive under/over limits from each configured floor and ceiling; explain ground-based areas, overlapping volumes, boundary crossings, and route-specific applicability; analysis and inspection. |
| SO-009 | The SPINS shall provide TACAN-only navigation guidance for the named arrivals and arcs. | Verify MA selection, FROM-radial versus TO-bearing usage, arc technique, range limitations, and navigation-reference calculations against source data; analysis and demonstration. |

## Interfaces and data

The authored source is `examples/operation-steel-opera/spins.yaml`. Supporting geometry comes from the archive's map drawings. `docs:steel-opera` renders to `docs/operation-steel-opera/`.

The document is a complete standing baseline for this mission version. The file provides a 1 June 2018, 06:00 scenario start but no SPINS expiry or verified UTC offset. A dated mission amendment is not fabricated to satisfy a timestamp field.

## Risks and out of scope

No live DCS run, mission rewrite, automated MIZ importer, flight tasking, payload selection, or invented operational clearance is included. The source has no authored player flights. Carrier/tanker briefing discrepancies, inactive support templates, and CATCC geometry require mission-maker decisions. Human coordination procedures in the draft do not create controllers or simulator enforcement.

Applicable standards: RQM-001–007; COMM-015–022; DCS-001/003/005/016/023/031/032/034/035. Live DCS verification under DCS-032 remains unperformed; file and source inspection establish configuration only.

The user identifies Line-11 and the end of Line-10 as DME arcs. The nominal distance is reconstructed from their geometry. The names are authored mission procedures, using a name-and-number arrival convention; they do not claim real-world publication or obstacle assessment. Procedure revision ONE is distinct from automatic paragraph numbering and from the document revision.
