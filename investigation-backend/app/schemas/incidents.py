from typing import Literal

from pydantic import BaseModel, Field


class Inference(BaseModel):
    kind: Literal["inference"] = "inference"
    statement: str


class IncidentFinding(BaseModel):
    incident_id: str
    namespace: str
    pod_name: str
    container_name: str | None = None
    incident_type: str
    severity: Literal["low", "medium", "high", "critical"]
    observed_symptoms: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    likely_explanation: Inference
    recommended_investigation_steps: list[str] = Field(default_factory=list)
    evidence_limitations: list[str] = Field(default_factory=list)


class IncidentList(BaseModel):
    namespace: str
    scanned_pods: int
    incidents: list[IncidentFinding] = Field(default_factory=list)
    evidence_warnings: list[str] = Field(default_factory=list)
