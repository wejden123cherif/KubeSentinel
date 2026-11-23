from kubernetes.client.exceptions import ApiException


def test_health_does_not_need_kubernetes(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_namespace_listing(client):
    response = client.get("/api/namespaces")
    assert response.status_code == 200
    assert response.json()["items"][0]["name"] == "ecommerce"


def test_pod_listing_passes_requested_namespace(client):
    response = client.get("/api/pods", params={"namespace": "ecommerce"})
    assert response.status_code == 200
    assert response.json() == {"namespace": "ecommerce", "items": []}


def test_incidents_returns_empty_list_for_healthy_namespace(client):
    response = client.get("/api/incidents?namespace=ecommerce")
    assert response.status_code == 200
    assert response.json() == {
        "namespace": "ecommerce",
        "scanned_pods": 0,
        "incidents": [],
        "evidence_warnings": [],
    }


def test_incidents_sanitizes_kubernetes_permission_failures(client, monkeypatch):
    def denied(self, namespace):
        raise ApiException(status=403, reason="private server detail")

    monkeypatch.setattr(type(client.app.state.kubernetes_service), "list_incident_evidence", denied)
    response = client.get("/api/incidents?namespace=ecommerce")
    assert response.status_code == 403
    assert response.json()["detail"] == "Kubernetes access denied"


def test_incidents_returns_status_findings_when_events_are_unavailable(client, monkeypatch):
    def partial_evidence(self, namespace):
        return {
            "namespace": namespace,
            "items": [],
            "events_error": "Namespace events are unavailable; incident detection used Pod status only.",
        }

    monkeypatch.setattr(type(client.app.state.kubernetes_service), "list_incident_evidence", partial_evidence)
    response = client.get("/api/incidents?namespace=ecommerce")
    assert response.status_code == 200
    assert response.json()["evidence_warnings"] == [
        "Namespace events are unavailable; incident detection used Pod status only."
    ]


def test_diagnostics_returns_structured_evidence(client):
    response = client.get("/api/pods/ecommerce/api-0/diagnostics")
    assert response.status_code == 200
    assert response.json()["pod"]["name"] == "api-0"
    assert response.json()["logs"]["app"] == "ready"


def test_missing_pod_is_reported_without_internal_details(client):
    response = client.get("/api/pods/ecommerce/missing/diagnostics")
    assert response.status_code == 404
    assert response.json()["detail"] == "Kubernetes resource not found"


def test_diagnostics_tail_is_bounded(client):
    response = client.get("/api/pods/ecommerce/api-0/diagnostics?tail_lines=1000")
    assert response.status_code == 422


def test_permission_error_is_sanitized(client, monkeypatch):
    def denied(self, namespace):
        raise ApiException(status=403, reason="private server detail")

    monkeypatch.setattr(type(client.app.state.kubernetes_service), "list_pods", denied)
    response = client.get("/api/pods")
    assert response.status_code == 403
    assert response.json()["detail"] == "Kubernetes access denied"
