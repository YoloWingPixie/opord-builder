"""Standalone data-source document schemas.

Each document type wraps a list of structured entries (reusing existing
Pydantic models from ``shared.py``) with provenance metadata.  Documents
are authored in separate YAML files, validated independently, and bound
into the OPORD tree at render time via a ``data_sources:`` block.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from opord_builder.schema._base import _Base
from opord_builder.schema.core import ClassificationLevel
from opord_builder.schema.shared import (
    AARTrack,
    AICSector,
    AWACSOrbit,
    AirspaceZone,
    CAPTrack,
    DTGString,
    GeoRef,
    HVT,
    JPITLEntry,
    MinimumRiskRoute,
    TSTEntry,
)


class DataSourceMeta(_Base):
    """Provenance header carried by every standalone data-source document."""

    title: str = Field(
        description="Document title (e.g. 'JPITL for OP IRON STRIKE').",
    )
    classification: Optional[ClassificationLevel] = Field(
        default=None,
        description="Classification level of this data source.",
    )
    as_of_dtg: Optional[DTGString] = Field(
        default=None,
        description="Date-time group the data was current as of.",
    )
    approved_by: Optional[str] = Field(
        default=None,
        description="Approving authority (e.g. 'JTCB', 'BN CDR').",
    )
    version: Optional[str] = Field(
        default=None,
        description="Version identifier for tracking revisions.",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Freeform notes or caveats.",
    )


class DataTableDocument(_Base):
    """Base for any standalone data source that wraps a list of structured entries."""

    kind: str = Field(
        description="Data-source type discriminator.",
    )
    meta: DataSourceMeta = Field(
        description="Provenance metadata for this data source.",
    )


class JPITLDocument(DataTableDocument):
    """Standalone Joint Prioritized Integrated Target List per JP 3-60 / ATP 3-60."""

    kind: Literal["jpitl"] = "jpitl"
    entries: list[JPITLEntry] = Field(
        default_factory=list,
        description="Joint Prioritized Integrated Target List entries.",
    )


class TSTDocument(DataTableDocument):
    """Standalone Time-Sensitive Target list per JP 3-60."""

    kind: Literal["tst"] = "tst"
    entries: list[TSTEntry] = Field(
        default_factory=list,
        description="Time-Sensitive Target entries.",
    )


class HPTDocument(DataTableDocument):
    """Standalone High-Payoff Target list."""

    kind: Literal["hpt"] = "hpt"
    entries: list[HVT] = Field(
        default_factory=list,
        description="High-Payoff Target list entries.",
    )


class CAPTrackDocument(DataTableDocument):
    """Standalone Combat Air Patrol track list."""

    kind: Literal["cap_tracks"] = "cap_tracks"
    entries: list[CAPTrack] = Field(
        default_factory=list,
        description="CAP station / orbit definitions.",
    )


class AARTrackDocument(DataTableDocument):
    """Standalone Air-to-Air Refueling track list."""

    kind: Literal["aar_tracks"] = "aar_tracks"
    entries: list[AARTrack] = Field(
        default_factory=list,
        description="AAR track definitions with altitude, method, and frequencies.",
    )


class AWACSOrbitDocument(DataTableDocument):
    """Standalone AWACS / airborne-C2 orbit list."""

    kind: Literal["awacs_orbits"] = "awacs_orbits"
    entries: list[AWACSOrbit] = Field(
        default_factory=list,
        description="Persistent AWACS orbit definitions.",
    )


class AICSectorDocument(DataTableDocument):
    """Standalone Air Intercept Controller sector list."""

    kind: Literal["aic_sectors"] = "aic_sectors"
    entries: list[AICSector] = Field(
        default_factory=list,
        description="AIC sub-sector definitions.",
    )


class IngressCorridorDocument(DataTableDocument):
    """Standalone Minimum-Risk Route / ingress-egress corridor list."""

    kind: Literal["ingress_corridors"] = "ingress_corridors"
    entries: list[MinimumRiskRoute] = Field(
        default_factory=list,
        description="MRR / ingress-egress corridor definitions.",
    )


class AirspaceZoneDocument(DataTableDocument):
    """Standalone airspace zone list (ROZ, HIDACZ, MEZ, NFZ, etc.)."""

    kind: Literal["airspace_zones"] = "airspace_zones"
    entries: list[AirspaceZone] = Field(
        default_factory=list,
        description="Published airspace zone definitions.",
    )


class GeoRefDocument(DataTableDocument):
    """Standalone geographic reference point list (bullseye, IP, CP, waypoints)."""

    kind: Literal["geo_refs"] = "geo_refs"
    entries: list[GeoRef] = Field(
        default_factory=list,
        description="Named geographic reference point definitions.",
    )


DATA_SOURCE_REGISTRY: dict[str, type[DataTableDocument]] = {
    "jpitl": JPITLDocument,
    "tst": TSTDocument,
    "hpt": HPTDocument,
    "cap_tracks": CAPTrackDocument,
    "aar_tracks": AARTrackDocument,
    "awacs_orbits": AWACSOrbitDocument,
    "aic_sectors": AICSectorDocument,
    "ingress_corridors": IngressCorridorDocument,
    "geo_refs": GeoRefDocument,
    "airspace_zones": AirspaceZoneDocument,
}
