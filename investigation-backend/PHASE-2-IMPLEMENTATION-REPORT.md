# Kubernetes Incident Detection — Phase 2 Report

**Date:** 13 November 2026  
**Implementation environment:** Ubuntu 24.04 VMware, `/home/wejden/k8s_project/investigation-backend`  
**Windows review copy:** `ecommerce-aws-deployment/investigation-backend`  
**Status:** Implemented, unit/API tests passing, and verified against the live K3s cluster through the read-only identity.

## Summary

Phase 2 adds deterministic incident detection to the existing FastAPI Kubernetes Investigation Backend. The new `GET /api/incidents?namespace=ecommerce` endpoint collected live Pod and Event evidence and returned structured findings without fetching logs or changing cluster state.

The API detected the existing `ErrImageNeverPull` condition even when the container status had changed to `ContainerStatusUnknown`. It relied on a recent, Pod-associated Kubernetes Event showing image `ecommerce-gateway:v1` was not present with pull policy `Never`. The response preserves the distinction: it labels the likely explanation as an inference, gives the event and image configuration as evidence, and says the current container state is uncertain.

## Files created or modified

- `app/services/incident_detector.py` — pure, deterministic rule evaluation over normalized evidence.
- `app/services/kubernetes_service.py` — adds bounded Pod/Event evidence collection. It lists namespace Pods once, lists at most 500 Events once, associates Events by Pod UID, limits each Pod to 20 Events, and does not request logs.
- `app/schemas/incidents.py` — typed response models for the incident list, finding, and explicitly labeled inference.
- `app/api/routes/incidents.py` — adds `GET /api/incidents`; the namespace defaults to `ecommerce`.
- `app/api/errors.py` — shared sanitized Kubernetes-to-HTTP error mapping.
- `app/api/routes/kubernetes.py` — reuses the shared error mapping; existing route behavior and response schemas remain unchanged.
- `app/main.py` — registers the incidents router.
- `tests/conftest.py` — fixes the pre-existing missing `pytest` import found by the baseline run and adds fake incident evidence support.
- `tests/test_incident_detector.py` — covers detector rules, uncertain/missing data, event recency, successful completion, and false-positive safeguards.
- `tests/test_service.py` — verifies one Pod list plus one bounded Event list and confirms no log reads occur during incident evidence collection.
- `tests/test_api.py` — verifies empty results and safe permission/evidence-gap behavior.
- `README.md` — documents the endpoint, rule scope, recency policy, and limitations.
- `PHASE-2-IMPLEMENTATION-REPORT.md` — this implementation and verification record.

## Detection rules

The detector reports:

- `CrashLoopBackOff`, `ImagePullBackOff`, `ErrImageNeverPull`, and `CreateContainerConfigError` from current container waiting reasons.
- `OOMKilled` from current or previous termination state.
- `RepeatedContainerRestarts` at restart count 3 or greater. The finding states that this is a cumulative count, not a rate.
- `UnschedulablePod` from a `PodScheduled=False / Unschedulable` condition, or a recent `FailedScheduling` Event only when no current `PodScheduled` condition exists.
- `FailedContainer` for a non-zero termination not better described by a specific status reason.
- `ContainerStatusUnknown` and `IncompleteContainerStatus` as low-severity uncertainty findings, not as asserted root causes.
- A recent (within one hour) explicit Kubernetes Event for a known waiting reason can retain an evidence-based finding when the current container status is unknown. Such findings have reduced severity and an explicit limitation that the event does not prove the condition is still active.

Pods with phase `Succeeded` are excluded, including Jobs that had earlier restarts but completed successfully. Stale scheduling events do not mark a Pod unschedulable when a current `PodScheduled` condition is present. Stable incident IDs are derived from namespace, Pod, container, and incident type.

## Response shape

The endpoint returns `namespace`, `scanned_pods`, `incidents`, and `evidence_warnings`. Each incident includes a stable ID, namespace, Pod/container, type, severity, symptoms, evidence, an inference-labeled explanation, investigation steps, and limitations.

Representative live `ErrImageNeverPull` finding (event-backed because the container status was uncertain):

```json
{
  "incident_id": "70f78bf33d5bf996",
  "namespace": "ecommerce",
  "pod_name": "api-gateway-59747cd798-85kvc",
  "container_name": "api-gateway",
  "incident_type": "ErrImageNeverPull",
  "severity": "medium",
  "observed_symptoms": [
    "A recent Kubernetes event reports ErrImageNeverPull; current container status may be incomplete."
  ],
  "supporting_evidence": [
    "Recent Kubernetes event reason: ErrImageNeverPull.",
    "Kubernetes event message: ecommerce-gateway:v1 is not present with pull policy of Never.",
    "Event occurrence count: 895.",
    "Last event time: 2026-11-13 12:20:33+00:00.",
    "Configured image: ecommerce-gateway:v1.",
    "Image pull policy: Never."
  ],
  "likely_explanation": {
    "kind": "inference",
    "statement": "A recent Kubernetes event reports this condition. The image is absent from the node while the pull policy prevents Kubernetes from downloading it. This event is supporting evidence and does not by itself confirm the container's current state."
  },
  "evidence_limitations": [
    "The container status is uncertain; this recent event does not prove the condition is still active."
  ]
}
```

The API also returns recommended investigation steps on each finding. The `incident_id` and live event count/timestamp above are specific to the observed cluster snapshot and can differ on later requests.

## Automated test results

The initial Phase 1 test run found `tests/conftest.py` referenced `pytest.fixture` without importing `pytest`. After adding the missing import, the original 10 tests passed. The final Ubuntu test run completed with:

```text
31 passed, 1 warning
```

The warning is a Starlette deprecation warning from the installed `fastapi.testclient` integration with `httpx`; it did not cause test failures.

## Real-cluster verification

Verification used the live K3s API and the dedicated read-only kubeconfig. No Kubernetes write operation was issued.

- Windows localhost health: HTTP 200 through the SSH tunnel.
- Windows localhost Swagger docs: HTTP 200 at `http://localhost:8000/docs`.
- OpenAPI document includes `GET /api/incidents`.
- `GET /api/incidents?namespace=ecommerce`: HTTP 200.
- At the final verification snapshot, the endpoint scanned 21 Pods and returned 29 findings: 13 `ContainerStatusUnknown`, 15 event-backed `ErrImageNeverPull`, and 1 `FailedContainer`. During earlier checks, it also correctly reported unschedulable and incomplete-status findings as the live Pod set changed.
- The gateway image finding included the configured image `ecommerce-gateway:v1`, pull policy `Never`, a recent Event timestamp, and an explicit uncertainty limitation.
- These counts are a live snapshot and may change as Pod/Event state changes. During the test session the cluster transitioned containers from waiting states to `ContainerStatusUnknown`; the event-backed rule retained recent image failure evidence without claiming certainty about the current runtime state.

## Limitations and next steps

- Rule-based explanations are triage guidance, not confirmed root causes. Confirm them against workload configuration, node/runtime health, and current cluster state.
- Restart count has no time window. Missing Events reduce diagnostic context; an Events permission/API failure appears as `evidence_warnings` while status-based detection continues.
- Event-backed active findings are limited to explicit known reasons in the preceding hour. Older Events are not used to claim an active failure.
- Logs are intentionally excluded from automatic incident scans. Use the existing per-Pod diagnostics endpoint when a human needs bounded log evidence.
- The next phase can add detection for more event/status patterns and improve evidence correlation, while keeping analysis deterministic and read-only. Any LLM explanation or remediation remains out of scope unless separately designed and approved.
