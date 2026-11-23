import pytest

from fastapi.testclient import TestClient

from app.main import app


class FakeService:
    def list_namespaces(self):
        return {"items": [{"name": "ecommerce", "status": "Active"}]}

    def list_pods(self, namespace):
        return {"namespace": namespace, "items": []}

    def list_incident_evidence(self, namespace):
        return {"namespace": namespace, "items": [], "events_error": None}

    def diagnostics(self, namespace, pod_name, tail_lines=100):
        if pod_name == "missing":
            from kubernetes.client.exceptions import ApiException

            raise ApiException(status=404)
        return {
            "pod": {"name": pod_name, "namespace": namespace, "phase": "Running"},
            "conditions": [],
            "containers": [],
            "events": [],
            "events_error": None,
            "logs": {"app": "ready"},
            "logs_errors": {},
        }


@pytest.fixture
def client():
    app.state.kubernetes_service = FakeService()
    with TestClient(app) as test_client:
        yield test_client
