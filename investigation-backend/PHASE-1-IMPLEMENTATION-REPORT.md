# Kubernetes Investigation Backend — Phase 1 Report

**Date:** 13 November 2026  
**Environment:** Windows development copy and Ubuntu 24.04 VMware guest running K3s  
**Phase status:** Backend prototype implemented and successfully queried against the real K3s cluster using the dedicated read-only identity. The live API smoke check passed for namespaces, ecommerce Pods, and Pod diagnostics. Mocked pytest execution remains unconfirmed.

## 1. Purpose and scope

This phase establishes a read-only backend that collects evidence from the existing Kubernetes cluster to support investigation of unhealthy workloads. The initial target is the `ecommerce` namespace. The API returns observed Kubernetes state; it does not infer a root cause, restart workloads, change manifests, or remediate failures.

Work was prepared in the Windows project at `ecommerce-aws-deployment/investigation-backend` and copied to the Ubuntu project at `/home/wejden/k8s_project/investigation-backend`. The Kubernetes workload itself was not intentionally changed in this phase. The new RBAC manifest is designed to create one dedicated ServiceAccount and its read-only permissions when the VM helper is run.

## 2. Existing cluster context

The user reported the following observations from the VM:

- `k3s` service was active and the node `wejden` was `Ready`.
- In `ecommerce`, PostgreSQL was running, while several application Pods showed `ErrImageNeverPull`, `ContainerStatusUnknown`, or `Completed` states.
- In `monitoring`, several Prometheus/Grafana components were running, alongside older failed or unknown Pods.

Those observations motivated collecting Pod status, container state, events, and logs. They are a snapshot reported before this implementation; they have not been refreshed by the API in this phase.

## 3. Backend implementation

The backend is a FastAPI application in `app/` using the official Kubernetes Python client.

### Endpoints

| Method and path | Purpose |
| --- | --- |
| `GET /api/health` | Confirms the API process responds; does not contact Kubernetes. |
| `GET /api/namespaces` | Lists namespace names and status. |
| `GET /api/pods?namespace=ecommerce` | Lists Pods in the requested namespace (defaults to `ecommerce`) with phase, node, readiness, container states, and restart counts. |
| `GET /api/pods/{namespace}/{pod_name}/diagnostics?tail_lines=100` | Returns evidence for a single Pod. `tail_lines` is bounded to 1–200. |

The diagnostics response includes selected Pod metadata, conditions, current and previous container states, restart counts, related events, and recent per-container logs. Event messages are capped at 2,048 characters. Log retrieval is capped at 200 lines and 16 KiB per container, for up to the first eight containers in a Pod. If events or logs cannot be read, the response reports an evidence gap rather than failing the entire diagnostics request. Kubernetes errors are mapped to sanitized API errors.

The service lazily tries in-cluster credentials first, then standard local kubeconfig loading. It honors `KUBECONFIG`. For this VM workflow, the intended value points to the dedicated read-only kubeconfig described below.

### Tests

`tests/` contains unit/API tests using fake Kubernetes responses. These cover health, namespace/Pod routes, diagnostics payload shape, error handling, and log-tail bounds. Mock tests validate application behavior without relying on cluster state; they do **not** prove connectivity or permissions against the live K3s API. Python bytecode compilation was reported as passing on Ubuntu. The pytest suite has not been confirmed as run. Separate live API smoke checks are now confirmed below.

## 4. Dedicated read-only Kubernetes identity

The files `k8s/readonly-rbac.yaml` and `scripts/setup_local_readonly_kubeconfig.sh` prepare least-privilege access for the API.

### Identity and permissions

- **Identity (“who”):** ServiceAccount `investigation-reader` in namespace `ecommerce`.
- **Namespaced Role (“what” within ecommerce):** `get` and `list` Pods, `get` Pod logs, and `list` Events.
- **RoleBinding:** attaches that Role to the ServiceAccount in `ecommerce`.
- **ClusterRole and ClusterRoleBinding:** allow `get` and `list` on Namespace objects, so the namespaces endpoint can work.
- **Explicitly not granted:** write actions, Secrets, Deployments, and access to Pods/events in other namespaces.

Namespace names and status are cluster-scoped metadata, so listing namespaces is the one permission outside `ecommerce`. Pod, log, and event permissions are namespace-scoped. Kubernetes RBAC is additive; these rules are intended to grant the stated actions, assuming the ServiceAccount has no other bindings.

### Kubeconfig and token lifetime

A kubeconfig is client connection configuration: it identifies the API server and CA certificate and supplies credentials for a Kubernetes identity. The helper is designed to write a separate file at `~/.kube/investigation-reader.kubeconfig`, protected with mode `0600`. It obtains a one-hour ServiceAccount token and places that token in this file. It does not copy the administrator kubeconfig or its credential.

The one-hour token lifetime limits the usefulness of a leaked credential. Rerunning the helper reapplies the intended RBAC declarations (idempotently), requests a fresh one-hour token, and replaces this dedicated config. The backend must be started with `KUBECONFIG` set to that path. If the token expires while the process is running, requests will fail authorization; renew it and restart the backend to ensure it loads the fresh config.

### Setup command on Ubuntu

The helper requires `k3s kubectl` and interactive sudo access. Python venv support is also needed for the backend. From the VM:

```bash
sudo apt update
sudo apt install python3.12-venv
cd /home/wejden/k8s_project/investigation-backend
bash scripts/setup_local_readonly_kubeconfig.sh
```

The helper applies only `k8s/readonly-rbac.yaml`, requests the short-lived token, and writes the dedicated kubeconfig. This is a cluster change (creation of the ServiceAccount and RBAC objects), explicitly approved by the user. The helper has now been run, and the kubeconfig exists on the VM with mode `0600`.

## 5. Running and viewing the API

After the identity setup, install the Python dependencies and start Uvicorn on the VM loopback interface:

```bash
cd /home/wejden/k8s_project/investigation-backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export KUBECONFIG="$HOME/.kube/investigation-reader.kubeconfig"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The app has no independent user authentication layer, so it is intended to stay bound to `127.0.0.1`. Forward port 8000 from the VS Code Remote SSH session, then open `http://localhost:8000/docs` on Windows. Other useful URLs are `/api/health`, `/api/namespaces`, `/api/pods?namespace=ecommerce`, and a diagnostics URL of the form `/api/pods/ecommerce/<pod-name>/diagnostics?tail_lines=100`.

## 6. Windows and VMware workflow

The user requested that files be available in the Windows workspace while working with the VMware-hosted cluster. An SSH key and `k3s-vm` host alias were configured locally, and SSH connectivity was verified. The backend implementation and subsequently added RBAC/helper documentation files were copied into the Ubuntu project. The Windows project remains the convenient local review copy.

The API is intended to run on Ubuntu next to K3s and be viewed from Windows through an SSH port-forward. The admin kubeconfig remains root-only; no administrator credentials were copied to Windows or used by the backend.

## 7. Verification and outstanding work

### Confirmed

- K3s/node and Pod state were reported by the user from the real VM cluster.
- SSH key-based access from the Windows environment to the VM was verified.
- Backend files exist in both the Windows project and Ubuntu project.
- The read-only helper passed `bash -n` syntax validation on Windows and Ubuntu.
- The helper is configured to write a dedicated kubeconfig with restrictive file permissions and a one-hour token.
- The app binds to loopback in the documented run command.
- The user ran the environment setup, installed dependencies, created the one-hour read-only kubeconfig, and started Uvicorn on `127.0.0.1:8000`.
- `GET /api/health` returned HTTP 200 from the VM.
- `GET /api/namespaces` returned HTTP 200 with the live namespace list, including `ecommerce` and `monitoring`.
- `GET /api/pods?namespace=ecommerce` returned HTTP 200 and live Pod/container status. Current results included `ErrImageNeverPull` for some Pods and `ContainerStatusUnknown`/failed states for older Pods.
- `GET /api/pods/ecommerce/api-gateway-59747cd798-mcw7g/diagnostics?tail_lines=5` returned HTTP 200 with live Pod conditions, container state, and Kubernetes events. The Pod was `Pending`; the container wait reason was `ErrImageNeverPull`, with an event stating image `ecommerce-gateway:v1` was not present while pull policy was `Never`. Logs were unavailable because the container had not started.
- These API results establish that the backend authenticated to the real Kubernetes API with sufficient read access for the exercised endpoints. They do not establish that the application workloads themselves are healthy.

### Still pending

1. Run the mocked pytest suite (not yet confirmed).
2. Confirm VS Code forwards port 8000 to Windows and open the docs UI there.
3. Continue investigation of the observed workload failures. The API has collected evidence but has not remediated anything.

The real-cluster API connection is now verified for the exercised read-only endpoints. The broader application investigation and any remediation remain separate work.

## 8. Security and operational notes

- Do not expose Uvicorn on a network interface; use loopback plus SSH port forwarding.
- The API has no application-level authentication. Anyone able to reach its local forwarded port can query the permissions of the configured Kubernetes identity.
- Pod logs and workload metadata may contain sensitive information; keep the VM account and kubeconfig private.
- The dedicated token expires after one hour. Renew it by rerunning the setup helper, then restart Uvicorn.
- The backend is read-only by design. Automated remediation, LLM analysis, dashboards, Prometheus/Loki/Falco integration, and frontend integration are outside this phase.
- The user's previously shared Ubuntu password should be rotated; it was disclosed in the chat. Do not place credentials in project files or this report.
