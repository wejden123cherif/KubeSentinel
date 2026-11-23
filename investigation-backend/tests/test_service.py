from types import SimpleNamespace as NS

from app.services.kubernetes_service import KubernetesService


def make_pod(state, last_state=None, ready=False, restarts=2):
    container_status = NS(
        name="api",
        ready=ready,
        restart_count=restarts,
        state=state,
        last_state=last_state,
    )
    return NS(
        metadata=NS(
            name="api-0",
            namespace="ecommerce",
            uid="uid-1",
            creation_timestamp=None,
            labels={"app": "api"},
        ),
        spec=NS(node_name="wejden", containers=[NS(name="api")]),
        status=NS(
            phase="Running",
            pod_ip="10.0.0.5",
            container_statuses=[container_status],
            conditions=[],
        ),
    )


class Core:
    def __init__(self, pod):
        self.pod = pod

    def read_namespaced_pod(self, name, namespace, **kwargs):
        return self.pod

    def list_namespaced_event(self, namespace, **kwargs):
        return NS(items=[])

    def read_namespaced_pod_log(self, *args, **kwargs):
        return "container output"


def test_healthy_pod_evidence_includes_readiness_and_logs():
    service = KubernetesService(Core(make_pod({"running": {"started_at": None}}, ready=True, restarts=0)))
    result = service.diagnostics("ecommerce", "api-0")
    assert result["pod"]["phase"] == "Running"
    assert result["containers"][0]["ready"] is True
    assert result["containers"][0]["restart_count"] == 0
    assert result["logs"]["api"] == "container output"


def test_failing_container_evidence_keeps_waiting_and_last_termination_reasons():
    pod = make_pod(
        {"waiting": {"reason": "ImagePullBackOff", "message": "image unavailable"}},
        {"terminated": {"reason": "Error", "exit_code": 1}},
    )
    result = KubernetesService(Core(pod)).diagnostics("ecommerce", "api-0")
    container = result["containers"][0]
    assert container["state"]["waiting"]["reason"] == "ImagePullBackOff"
    assert container["last_state"]["terminated"]["reason"] == "Error"
    assert container["restart_count"] == 2


def test_log_tail_is_passed_to_kubernetes_client():
    class RecordingCore(Core):
        def read_namespaced_pod_log(self, *args, **kwargs):
            assert kwargs["tail_lines"] == 25
            assert kwargs["limit_bytes"] == 16_384
            return "bounded"

    result = KubernetesService(RecordingCore(make_pod({"running": {}}))).diagnostics(
        "ecommerce", "api-0", tail_lines=25
    )
    assert result["logs"]["api"] == "bounded"


def test_incident_evidence_uses_one_pod_and_event_list_without_logs():
    pod = NS(
        metadata=NS(name="gateway-0", uid="pod-uid"),
        spec=NS(
            containers=[NS(name="gateway", image="gateway:v1", image_pull_policy="Never")],
            init_containers=[],
        ),
        status=NS(
            phase="Pending",
            reason=None,
            message=None,
            conditions=[NS(type="PodScheduled", status="True", reason=None, message=None)],
            container_statuses=[
                NS(
                    name="gateway",
                    ready=False,
                    restart_count=0,
                    state={"waiting": {"reason": "ErrImageNeverPull", "message": "image absent"}},
                    last_state={},
                )
            ],
            init_container_statuses=[],
        ),
    )
    event = NS(
        involved_object=NS(uid="pod-uid"),
        type="Warning",
        reason="ErrImageNeverPull",
        message="image absent",
        count=3,
    )

    class RecordingCore:
        pod_calls = 0
        event_calls = 0

        def list_namespaced_pod(self, namespace, **kwargs):
            self.pod_calls += 1
            assert namespace == "ecommerce"
            return NS(items=[pod])

        def list_namespaced_event(self, namespace, **kwargs):
            self.event_calls += 1
            assert kwargs["limit"] == 500
            return NS(items=[event])

        def read_namespaced_pod_log(self, *args, **kwargs):
            raise AssertionError("incident evidence collection must not fetch logs")

    core = RecordingCore()
    result = KubernetesService(core).list_incident_evidence("ecommerce")
    assert core.pod_calls == 1
    assert core.event_calls == 1
    assert result["items"][0]["containers"][0]["image"] == "gateway:v1"
    assert result["items"][0]["containers"][0]["image_pull_policy"] == "Never"
    assert result["items"][0]["events"][0]["reason"] == "ErrImageNeverPull"
    assert result["events_error"] is None
