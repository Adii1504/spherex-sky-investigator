from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, model_validator

class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

class Sky(Model):
    ra_deg: float = Field(ge=0, lt=360)
    dec_deg: float = Field(ge=-90, le=90)
    fov_arcmin: float = Field(gt=0)

class Search(Sky):
    start_utc: AwareDatetime | None = None
    end_utc: AwareDatetime | None = None

    @model_validator(mode="after")
    def dates(self):
        if self.start_utc and self.end_utc and self.start_utc > self.end_utc:
            raise ValueError("start_utc must precede end_utc")
        return self

class Provenance(Model):
    archive: str
    source_url: str
    citation: str | None = None

class Observation(Model):
    id: str
    exposure_id: str
    observed_at: AwareDatetime
    release: str
    product_id: str
    detector: str | None = None
    provenance: Provenance
    file_wavelength_um: tuple[float, float] | None = None
    position_wavelength_um: float | None = None
    quality: dict[str, Any] | None = None

class SearchResult(Model):
    observations: list[Observation]
    coverage_summary: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)

class Selection(Sky):
    search_id: str
    observation_ids: list[str] = Field(min_length=1)

class Investigation(Selection):
    sequence_job_id: str | None = None

class Verify(Model):
    training_observation_ids: list[str] = Field(min_length=1)
    reserved_observation_ids: list[str] = Field(min_length=1)

class Cutout(Model):
    observation_id: str
    data: bytes
    media_type: str
    metadata: dict[str, Any] = Field(default_factory=dict)

class Preview(Model):
    observation_id: str
    png: bytes
    metadata: dict[str, Any] = Field(default_factory=dict)

class ProcessedSequence(Model):
    previews: list[Preview]
    processing_version: str
    processing_settings: dict[str, Any]
    shared_display_settings: dict[str, Any]
    measurements: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

class VerificationResult(Model):
    outcome: Literal["supported", "not_supported", "insufficient_evidence"]
    measurements: dict[str, Any]
    assumptions: list[str]
    limitations: list[str]
    warnings: list[str] = Field(default_factory=list)
    processing_version: str
