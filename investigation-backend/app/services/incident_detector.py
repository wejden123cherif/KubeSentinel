from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any


RESTART_THRESHOLD = 3

_WAITING_RULES = {
    "CrashLoopBackOff": (
        "high",
        "The container repeatedly exits or fails to start and Kubernetes is backing off restarts.",
        "Inspect the previous termination state, related events, and application configuration; check dependencies and resource limits.",
    ),
    "ImagePullBackOff": (
        "high",
        "Kubernetes could not pull the configured container image and is retrying with backoff.",
        "Check image name and tag, registry reachability, and image pull credentials.",
    ),
    "ErrImageNeverPull": (
        "high",
        "The image is absent from the node while the pull policy prevents Kubernetes from downloading it.",
        "Verify the image exists in the node's container runtime or use an image reference and pull policy compatible with the deployment.",
    ),
    "CreateContainerConfigError": (
        "high",
        "Kubernetes could not prepare the container configuration.",
        "Inspect the event messages and verify referenced configuration, volumes, and environment sources.",
    ),
}


def _reason(state: Any, state_name: str) -> str | None:
    if not isinstance(state, dict):
        return None
    section = state.get(state_name)
    if not isinstance(section, dict):
        return None
    reason = section.get("reason")
    return reason if isinstance(reason, str) else None


def _message(state: Any, state_name: str) -> str | None:
    if not isinstance(state, dict):
        return None
    section = state.get(state_name)
    if not isinstance(section, dict):
        return None
    message = section.get("message")
    return message[:1024] if isinstance(message, str) and message else None


def _event_is_recent(event: dict[str, Any], now: datetime) -> bool:
    timestamp = event.get("last_timestamp")
    if not isinstance(timestamp, str) or not timestamp:
        return False
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return now - timedelta(hours=1) <= parsed <= now + timedelta(minutes=5)


def _incident(
    *,
    namespace: str,
    pod: dict[str, Any],
    incident_type: str,
    severity: str,
    container: dict[str, Any] | None = None,
    symptoms: list[str],
    evidence: list[str],
    explanation: str,
    steps: list[str],
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    pod_name = str(pod.get("name") or "unknown")
    container_name = str(container.get("name")) if container and container.get("name") else None
    stable_key = "/".join((namespace, pod_name, container_name or "_pod", incident_type))
    incident_id = hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:16]
    return {
        "incident_id": incident_id,
        "namespace": namespace,
        "pod_name": pod_name,
        "container_name": container_name,
        "incident_type": incident_type,
        "severity": severity,
        "observed_symptoms": symptoms,
        "supporting_evidence": evidence,
        "likely_explanation": {"kind": "inference", "statement": explanation},
        "recommended_investigation_steps": steps,
        "evidence_limitations": limitations or [],
    }


def detect_incidents(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    """Apply deterministic rules to normalized Pod and event evidence."""
    namespace = str(evidence.get("namespace") or "")
    findings: list[dict[str, Any]] = []

    for pod in evidence.get("items") or []:
        if not isinstance(pod, dict):
            continue
        # A successfully completed Pod is not an incident even if a container
        # had earlier restarts before completing its Job.
        if pod.get("phase") == "Succeeded":
            continue

        conditions = pod.get("conditions") or []
        events = pod.get("events") or []
        has_pod_scheduled_condition = any(
            isinstance(item, dict) and item.get("type") == "PodScheduled" for item in conditions
        )
        unschedulable_condition = next(
            (
                item
                for item in conditions
                if isinstance(item, dict)
                and item.get("type") == "PodScheduled"
                and str(item.get("status")).lower() == "false"
                and item.get("reason") == "Unschedulable"
            ),
            None,
        )
        failed_scheduling_events = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("reason") == "FailedScheduling"
            and _event_is_recent(event, datetime.now(timezone.utc))
        ]
        scheduler_reports_unschedulable = bool(unschedulable_condition) or (
            pod.get("phase") == "Pending"
            and not has_pod_scheduled_condition
            and bool(failed_scheduling_events)
        )
        if scheduler_reports_unschedulable:
            evidence_items = []
            if unschedulable_condition:
                evidence_items.append("PodScheduled condition is False with reason Unschedulable.")
                if unschedulable_condition.get("message"):
                    evidence_items.append(str(unschedulable_condition["message"])[:1024])
            evidence_items.extend(
                f"FailedScheduling event: {str(event.get('message') or '')[:1024]}"
                for event in failed_scheduling_events[:5]
            )
            findings.append(
                _incident(
                    namespace=namespace,
                    pod=pod,
                    incident_type="UnschedulablePod",
                    severity="medium",
                    symptoms=["The Pod has not been scheduled onto a node."],
                    evidence=evidence_items,
                    explanation="The scheduler reports that the Pod currently cannot be placed; the specific constraint is indicated only when present in the evidence.",
                    steps=["Review the PodScheduled condition and FailedScheduling events for resource, affinity, taint, or volume constraints."],
                    limitations=[] if evidence_items else ["No scheduling condition or event message was available."],
                )
            )

        for container in [*(pod.get("init_containers") or []), *(pod.get("containers") or [])]:
            if not isinstance(container, dict):
                continue
            state = container.get("state") or {}
            last_state = container.get("last_state") or {}
            waiting_reason = _reason(state, "waiting")
            current_termination = state.get("terminated") if isinstance(state, dict) else None
            previous_termination = last_state.get("terminated") if isinstance(last_state, dict) else None
            termination_reason = (
                current_termination.get("reason") if isinstance(current_termination, dict) else None
            ) or (previous_termination.get("reason") if isinstance(previous_termination, dict) else None)
            restart_count = int(container.get("restart_count") or 0)
            uncertain_status = waiting_reason == "ContainerStatusUnknown" or termination_reason == "ContainerStatusUnknown"

            if container.get("status_available") is False:
                findings.append(
                    _incident(
                        namespace=namespace,
                        pod=pod,
                        container=container,
                        incident_type="IncompleteContainerStatus",
                        severity="low",
                        symptoms=["A container is declared in the Pod spec but has no matching runtime status."],
                        evidence=[f"Container {container.get('name') or 'unknown'} has no status entry."],
                        explanation="The kubelet has not provided a status entry for this container; this alone does not establish a container failure.",
                        steps=["Check whether the Pod is still initializing and review later Pod status and events."],
                        limitations=["Missing status can be transient during startup or reflect incomplete node reporting."],
                    )
                )

            if uncertain_status:
                message = _message(state, "terminated") or _message(last_state, "terminated") or _message(state, "waiting")
                evidence_items = ["Kubernetes reports ContainerStatusUnknown for this container."]
                if message:
                    evidence_items.append(message)
                findings.append(
                    _incident(
                        namespace=namespace,
                        pod=pod,
                        container=container,
                        incident_type="ContainerStatusUnknown",
                        severity="low",
                        symptoms=["The container's actual runtime state is uncertain."],
                        evidence=evidence_items,
                        explanation="The control plane cannot confirm the container state; this observation alone does not identify a root cause.",
                        steps=["Check node readiness and kubelet/container-runtime health, then compare with current Pod events."],
                        limitations=["ContainerStatusUnknown is not sufficient to determine whether the container is currently running or why it became unreachable."],
                    )
                )
            elif waiting_reason in _WAITING_RULES:
                severity, explanation, step = _WAITING_RULES[waiting_reason]
                evidence_items = [f"Container is waiting with reason {waiting_reason}."]
                message = _message(state, "waiting")
                if message:
                    evidence_items.append(message)
                if container.get("image"):
                    evidence_items.append(f"Configured image: {container['image']}.")
                if container.get("image_pull_policy"):
                    evidence_items.append(f"Image pull policy: {container['image_pull_policy']}.")
                evidence_items.append(f"Restart count: {restart_count}.")
                termination = previous_termination or current_termination
                if isinstance(termination, dict) and termination.get("reason"):
                    evidence_items.append(
                        f"Previous termination: {termination.get('reason')} (exit code {termination.get('exit_code')})."
                    )
                findings.append(
                    _incident(
                        namespace=namespace,
                        pod=pod,
                        container=container,
                        incident_type=waiting_reason,
                        severity=severity,
                        symptoms=[f"The container is waiting ({waiting_reason})."],
                        evidence=evidence_items,
                        explanation=explanation,
                        steps=[step],
                    )
                )
            elif termination_reason == "OOMKilled":
                findings.append(
                    _incident(
                        namespace=namespace,
                        pod=pod,
                        container=container,
                        incident_type="OOMKilled",
                        severity="high",
                        symptoms=["The current or previous container termination was reported as OOMKilled."],
                        evidence=["Container termination reason: OOMKilled."],
                        explanation="The container was terminated after exceeding an available memory limit or under memory pressure; the precise trigger requires further evidence.",
                        steps=["Review container memory limits and usage near the termination, then inspect application memory behavior and node pressure."],
                        limitations=["The Pod status does not by itself establish the exact memory usage or whether a configured container limit was reached."],
                    )
                )
            if waiting_reason in _WAITING_RULES and termination_reason == "OOMKilled":
                findings.append(
                    _incident(
                        namespace=namespace,
                        pod=pod,
                        container=container,
                        incident_type="OOMKilled",
                        severity="high",
                        symptoms=["The previous container termination was reported as OOMKilled."],
                        evidence=["Container termination reason: OOMKilled."],
                        explanation="The container was terminated after exceeding an available memory limit or under memory pressure; the precise trigger requires further evidence.",
                        steps=["Review container memory limits and usage near the termination, then inspect application memory behavior and node pressure."],
                        limitations=["The Pod status does not by itself establish the exact memory usage or whether a configured container limit was reached."],
                    )
                )
            elif (
                isinstance(current_termination, dict)
                and not uncertain_status
                and current_termination.get("reason")
                and waiting_reason not in _WAITING_RULES
                and current_termination.get("reason") not in {"Completed", "ContainerStatusUnknown", "OOMKilled"}
                and int(current_termination.get("exit_code") or 0) != 0
            ) or (
                isinstance(previous_termination, dict)
                and not uncertain_status
                and waiting_reason not in _WAITING_RULES
                and previous_termination.get("reason")
                and previous_termination.get("reason") not in {"Completed", "OOMKilled", "ContainerStatusUnknown"}
                and int(previous_termination.get("exit_code") or 0) != 0
            ):
                reason = termination_reason or "unspecified termination"
                findings.append(
                    _incident(
                        namespace=namespace,
                        pod=pod,
                        container=container,
                        incident_type="FailedContainer",
                        severity="high",
                        symptoms=["The container has a non-zero failed termination state."],
                        evidence=[f"Container termination reason: {reason}.", f"Restart count: {restart_count}."],
                        explanation="The container process exited unsuccessfully; the exit code and application logs may help identify why.",
                        steps=["Inspect the termination exit code, previous container logs if available, and events for this Pod."],
                    )
                )

            if restart_count >= RESTART_THRESHOLD and waiting_reason != "ContainerStatusUnknown" and termination_reason != "ContainerStatusUnknown":
                findings.append(
                    _incident(
                        namespace=namespace,
                        pod=pod,
                        container=container,
                        incident_type="RepeatedContainerRestarts",
                        severity="medium",
                        symptoms=[f"The container has restarted {restart_count} times."],
                        evidence=[f"Kubernetes restartCount is {restart_count}; the rule threshold is {RESTART_THRESHOLD}."],
                        explanation="The container has restarted repeatedly, but the count alone does not establish the cause or timing of those restarts.",
                        steps=["Review current and previous container states, termination details, and recent Pod events."],
                        limitations=["Kubernetes restartCount is a cumulative count for this Pod and does not indicate a restart rate or time window."],
                    )
                )

        # A recent Event can preserve useful evidence after the kubelet loses
        # the container's current status. Only use explicit known waiting
        # reasons, and never let an old event turn a healthy/Succeeded Pod into
        # an active incident.
        all_containers = [*(pod.get("init_containers") or []), *(pod.get("containers") or [])]
        for event in events:
            if not isinstance(event, dict) or event.get("reason") not in _WAITING_RULES:
                continue
            if not _event_is_recent(event, datetime.now(timezone.utc)):
                continue
            message = str(event.get("message") or "")[:1024]
            reason = event["reason"]
            matching_containers = [
                container
                for container in all_containers
                if isinstance(container, dict)
                and not container.get("ready")
                and (
                    (container.get("image") and container["image"] in message)
                    or (container.get("name") and container["name"] in message)
                )
            ]
            if not matching_containers and len(all_containers) == 1:
                only_container = all_containers[0]
                if isinstance(only_container, dict) and not only_container.get("ready"):
                    matching_containers = [only_container]
            for container in matching_containers:
                state = container.get("state") or {}
                current_reason = _reason(state, "waiting")
                if current_reason in _WAITING_RULES:
                    continue  # The current status already provides the finding.
                direct_severity, direct_explanation, direct_step = _WAITING_RULES[reason]
                event_time = event.get("last_timestamp")
                evidence_items = [
                    f"Recent Kubernetes event reason: {reason}.",
                    message or "The event did not include a message.",
                ]
                if event.get("count") is not None:
                    evidence_items.append(f"Event occurrence count: {event['count']}.")
                if event_time:
                    evidence_items.append(f"Last event time: {event_time}.")
                if container.get("image"):
                    evidence_items.append(f"Configured image: {container['image']}.")
                if container.get("image_pull_policy"):
                    evidence_items.append(f"Image pull policy: {container['image_pull_policy']}.")
                is_unknown = (
                    current_reason == "ContainerStatusUnknown"
                    or termination_reason == "ContainerStatusUnknown"
                    or container.get("status_available") is False
                )
                findings.append(
                    _incident(
                        namespace=namespace,
                        pod=pod,
                        container=container,
                        incident_type=reason,
                        severity="medium" if is_unknown else direct_severity,
                        symptoms=[f"A recent Kubernetes event reports {reason}; current container status may be incomplete."],
                        evidence=evidence_items,
                        explanation=(
                            f"A recent Kubernetes event reports this condition. {direct_explanation} "
                            "This event is supporting evidence and does not by itself confirm the container's current state."
                        ),
                        steps=[direct_step],
                        limitations=["The container status is uncertain; this recent event does not prove the condition is still active."],
                    )
                )

    # Preserve a deterministic response order between requests.
    return sorted(findings, key=lambda item: (item["pod_name"], item["container_name"] or "", item["incident_type"]))
