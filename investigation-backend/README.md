# Kubernetes Investigation API

A local, read-only FastAPI prototype that gathers Kubernetes evidence. It does not diagnose root causes, change cluster state, or integrate an LLM. Keep it bound to loopback and use a least-privilege Kubernetes identity.

## Structure

- `app/main.py`: FastAPI application and router setup.
- `app/api/routes/`: health, namespace, Pod, and diagnostic endpoints.
- `app/services/kubernetes_service.py`: official Kubernetes Python client integration and evidence collection.
- `app/services/incident_detector.py`: deterministic, evidence-based incident rules.
- `app/schemas/`: response models.
- `tests/`: unit and mocked API tests; no cluster changes are made by tests.

## Ubuntu setup

From the backend directory on Ubuntu 24.04:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The client first tries in-cluster authentication (for a future Kubernetes deployment), then uses the standard local Kubernetes configuration, honoring `KUBECONFIG` and the normal client default.

### Dedicated read-only access to the real cluster

The `k8s/readonly-rbac.yaml` manifest creates the `investigation-reader` ServiceAccount in `ecommerce`. It can list and get Pods, read Pod logs, list namespace events, and list/get namespaces. It has no write permissions and cannot read Secrets, Deployments, or resources in other namespaces. Namespace listing is cluster-scoped; the other permissions are limited to `ecommerce`.

After installing Python's venv support (Ubuntu: `sudo apt update && sudo apt install python3.12-venv`), run the helper from this backend directory:

```bash
bash scripts/setup_local_readonly_kubeconfig.sh
```

The helper applies only the RBAC manifest above, requests a one-hour ServiceAccount token, and writes a dedicated mode-600 kubeconfig to `~/.kube/investigation-reader.kubeconfig`. It does not copy or expose the administrator kubeconfig. The token is short-lived; rerun the helper to renew it. The backend uses the generated config when `KUBECONFIG` is set:

```bash
export KUBECONFIG="$HOME/.kube/investigation-reader.kubeconfig"
```

Keep Uvicorn bound to loopback as shown below. The cluster smoke check should use this identity.

Run locally on Ubuntu:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In VS Code, forward port `8000` from the Remote SSH session. On Windows, open `http://localhost:8000/docs`; the backend listener stays on Ubuntu loopback. Health is available at `/api/health` and does not require Kubernetes access.

## Endpoints

- `GET /api/health`
- `GET /api/namespaces`
- `GET /api/pods?namespace=ecommerce`
- `GET /api/pods/{namespace}/{pod_name}/diagnostics?tail_lines=100`
- `GET /api/incidents?namespace=ecommerce`

Diagnostics include Pod metadata, conditions, current and previous container state, restart counts, related events, and per-container recent logs. Log collection is capped at 200 lines and 16 KiB per container. Unavailable events or logs are returned as evidence gaps rather than causing the whole diagnostics request to fail. Kubernetes API failures are mapped to sanitized HTTP errors.

The incidents endpoint lists Pods once and namespace Events once, then applies local deterministic rules; it does not retrieve container logs or make one diagnostics call per Pod. It returns a stable ID, severity, observed symptoms, supporting evidence, an explicitly labeled inference, recommended investigation steps, and evidence limitations. The initial rules cover `CrashLoopBackOff`, `ImagePullBackOff`, `ErrImageNeverPull`, `OOMKilled`, `CreateContainerConfigError`, repeated restarts (restart count of at least 3), unschedulable Pods, failed container termination states, uncertain `ContainerStatusUnknown`, and missing container status. Succeeded Pods are excluded. When the current container state is unknown, an explicit matching Kubernetes Event from the last hour can preserve a lower-severity evidence-based finding; the response states that this event does not prove the condition remains active. Events older than one hour are not used to assert an active container incident.

This is rule-based triage, not a definitive root-cause analysis. Restart counts have no time window, missing events reduce available context, and `ContainerStatusUnknown` or absent status is reported as uncertainty. Explanations are labeled as inferences and should be checked against cluster events, node health, and application evidence.

## Test

```bash
python -m pytest
```

Tests use mocked Kubernetes responses and do not contact or mutate the cluster. A real-cluster smoke check should use the dedicated kubeconfig above to query namespaces, ecommerce Pods, diagnostics for an existing Pod, and `/api/incidents?namespace=ecommerce`, without changing cluster state.

## Known limits and next steps

This prototype has no authentication layer of its own, so keep Uvicorn on `127.0.0.1` and access it through SSH port forwarding. Kubernetes read permissions can expose sensitive workload metadata and logs; restrict RBAC and local access accordingly. Prometheus metrics, Loki/Alloy logs, Falco alerts, an LLM investigation agent, frontend integration, and human-approved remediation are future modules and are not implemented here.
