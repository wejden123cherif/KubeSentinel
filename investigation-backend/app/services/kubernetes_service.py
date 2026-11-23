from __future__ import annotations

from typing import Any

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException


class KubernetesUnavailable(RuntimeError):
    """Raised when no Kubernetes client can be initialized."""


def _plain(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return {key: _plain(item) for key, item in value.to_dict().items()}
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _state(value: Any) -> dict[str, Any] | None:
    return _plain(value) if value is not None else None


def _container_statuses(pod: Any) -> list[dict[str, Any]]:
    status = getattr(pod, "status", None)
    return [
        {
            "name": item.name,
            "ready": bool(item.ready),
            "restart_count": int(item.restart_count or 0),
            "state": _state(item.state),
            "last_state": _state(item.last_state),
        }
        for item in ((status.container_statuses if status else None) or [])
    ]


def _incident_containers(specs: list[Any] | None, statuses: list[Any] | None) -> list[dict[str, Any]]:
    status_by_name = {item.name: item for item in statuses or [] if getattr(item, "name", None)}
    result = []
    for spec in specs or []:
        name = spec.name
        status = status_by_name.pop(name, None)
        result.append(
            {
                "name": name,
                "status_available": status is not None,
                "image": getattr(spec, "image", None),
                "image_pull_policy": getattr(spec, "image_pull_policy", None),
                "ready": bool(status.ready) if status else False,
                "restart_count": int(status.restart_count or 0) if status else 0,
                "state": _state(status.state) if status else {},
                "last_state": _state(status.last_state) if status else {},
            }
        )
    # Keep reported runtime statuses even if the spec/status are temporarily
    # inconsistent during a Pod update.
    for name, status in status_by_name.items():
        result.append(
            {
                "name": name,
                "status_available": True,
                "image": None,
                "image_pull_policy": None,
                "ready": bool(status.ready),
                "restart_count": int(status.restart_count or 0),
                "state": _state(status.state) or {},
                "last_state": _state(status.last_state) or {},
            }
        )
    return result


class KubernetesService:
    """Small read-only wrapper around the official Kubernetes Python client."""

    def __init__(self, core_api: Any | None = None):
        self._core_api = core_api

    @property
    def core_api(self):
        if self._core_api is None:
            try:
                try:
                    config.load_incluster_config()
                except config.ConfigException:
                    config.load_kube_config()
                self._core_api = client.CoreV1Api()
            except (config.ConfigException, OSError) as exc:
                raise KubernetesUnavailable() from exc
        return self._core_api

    def list_namespaces(self) -> dict[str, Any]:
        result = self.core_api.list_namespace(_request_timeout=5)
        return {
            "items": [
                {"name": item.metadata.name, "status": item.status.phase if item.status else None}
                for item in result.items
            ]
        }

    def list_pods(self, namespace: str) -> dict[str, Any]:
        result = self.core_api.list_namespaced_pod(namespace, _request_timeout=5)
        items = []
        for pod in result.items:
            statuses = _container_statuses(pod)
            expected = len(pod.spec.containers or [])
            items.append(
                {
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "phase": pod.status.phase if pod.status else None,
                    "node": pod.spec.node_name,
                    "ready": expected > 0 and len(statuses) == expected and all(c["ready"] for c in statuses),
                    "containers": statuses,
                }
            )
        return {"namespace": namespace, "items": items}

    def list_incident_evidence(self, namespace: str) -> dict[str, Any]:
        """Fetch bounded Pod status/configuration and Events without fetching logs."""
        pod_result = self.core_api.list_namespaced_pod(namespace, _request_timeout=5)
        pods = list(pod_result.items or [])
        events_by_uid: dict[str, list[dict[str, Any]]] = {}
        events_error = None
        try:
            event_result = self.core_api.list_namespaced_event(namespace, limit=500, _request_timeout=5)
            for event in (event_result.items or []):
                involved = getattr(event, "involved_object", None)
                uid = getattr(involved, "uid", None)
                if not uid:
                    continue
                bucket = events_by_uid.setdefault(str(uid), [])
                if len(bucket) >= 20:
                    continue
                bucket.append(
                    {
                        "type": getattr(event, "type", None),
                        "reason": getattr(event, "reason", None),
                        "message": (getattr(event, "message", None) or "")[:2048],
                        "count": getattr(event, "count", None),
                        "last_timestamp": str(
                            getattr(event, "last_timestamp", None)
                            or getattr(event, "event_time", None)
                            or ""
                        ) or None,
                    }
                )
        except (ApiException, OSError, TimeoutError):
            events_error = "Namespace events are unavailable; incident detection used Pod status only."

        items = []
        for pod in pods:
            metadata = pod.metadata
            spec = pod.spec
            status = pod.status
            uid = getattr(metadata, "uid", None)
            conditions = [
                {
                    "type": getattr(item, "type", None),
                    "status": getattr(item, "status", None),
                    "reason": getattr(item, "reason", None),
                    "message": (getattr(item, "message", None) or "")[:2048],
                }
                for item in ((status.conditions if status else None) or [])
            ]
            items.append(
                {
                    "name": metadata.name,
                    "uid": uid,
                    "phase": status.phase if status else None,
                    "reason": status.reason if status else None,
                    "message": (status.message or "")[:2048] if status else "",
                    "conditions": conditions,
                    "containers": _incident_containers(
                        spec.containers,
                        status.container_statuses if status else None,
                    ),
                    "init_containers": _incident_containers(
                        spec.init_containers,
                        status.init_container_statuses if status else None,
                    ),
                    "events": events_by_uid.get(str(uid), []) if uid else [],
                }
            )
        return {
            "namespace": namespace,
            "items": items,
            "events_error": events_error,
            "event_limit": 500,
        }

    def diagnostics(self, namespace: str, pod_name: str, tail_lines: int = 100) -> dict[str, Any]:
        pod = self.core_api.read_namespaced_pod(pod_name, namespace, _request_timeout=5)
        uid = pod.metadata.uid
        events: list[dict[str, Any]] = []
        events_error = None
        try:
            event_result = self.core_api.list_namespaced_event(
                namespace,
                field_selector=f"involvedObject.uid={uid}",
                _request_timeout=5,
            )
            events = [
                {
                    "type": e.type,
                    "reason": e.reason,
                    "message": (e.message or "")[:2048],
                    "count": e.count,
                    "first_timestamp": e.first_timestamp,
                    "last_timestamp": e.last_timestamp,
                    "source": e.source.component if e.source else None,
                }
                for e in event_result.items[:100]
            ]
        except (ApiException, OSError, TimeoutError):
            events_error = "Events are unavailable with current access or API state"

        logs: dict[str, str | None] = {}
        logs_errors: dict[str, str] = {}
        containers = pod.spec.containers or []
        for container in containers[:8]:
            try:
                logs[container.name] = self.core_api.read_namespaced_pod_log(
                    pod_name,
                    namespace,
                    container=container.name,
                    tail_lines=tail_lines,
                    limit_bytes=16_384,
                    timestamps=True,
                    _request_timeout=5,
                )
            except (ApiException, OSError, TimeoutError):
                logs[container.name] = None
                logs_errors[container.name] = "Container logs are unavailable"
        for container in containers[8:]:
            logs[container.name] = None
            logs_errors[container.name] = "Log collection is limited to the first 8 containers"

        metadata = pod.metadata
        status = pod.status
        spec = pod.spec
        return {
            "pod": {
                "name": metadata.name,
                "namespace": metadata.namespace,
                "uid": uid,
                "creation_timestamp": metadata.creation_timestamp,
                "labels": metadata.labels or {},
                "phase": status.phase if status else None,
                "node": spec.node_name,
                "pod_ip": status.pod_ip if status else None,
            },
            "conditions": [_plain(condition) for condition in (status.conditions or [])] if status else [],
            "containers": _container_statuses(pod),
            "events": events,
            "events_error": events_error,
            "logs": logs,
            "logs_errors": logs_errors,
        }
