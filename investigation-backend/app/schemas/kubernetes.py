from typing import Any

from pydantic import BaseModel


class NamespaceInfo(BaseModel):
    name: str
    status: str | None = None


class NamespaceList(BaseModel):
    items: list[NamespaceInfo]


class ContainerInfo(BaseModel):
    name: str
    ready: bool
    restart_count: int
    state: dict[str, Any] | None = None
    last_state: dict[str, Any] | None = None


class PodInfo(BaseModel):
    name: str
    namespace: str
    phase: str | None = None
    node: str | None = None
    ready: bool
    containers: list[ContainerInfo]


class PodList(BaseModel):
    namespace: str
    items: list[PodInfo]


class PodDiagnostics(BaseModel):
    pod: dict[str, Any]
    conditions: list[dict[str, Any]]
    containers: list[ContainerInfo]
    events: list[dict[str, Any]]
    events_error: str | None = None
    logs: dict[str, str | None]
    logs_errors: dict[str, str]
