from datetime import datetime, timedelta, timezone

from app.services.incident_detector import detect_incidents


def pod(**overrides):
    result = {
        "name": "sample-0",
        "phase": "Running",
        "conditions": [],
        "containers": [
            {
                "name": "app",
                "image": "example/app:v1",
                "image_pull_policy": "IfNotPresent",
                "status_available": True,
                "ready": True,
                "restart_count": 0,
                "state": {"running": {"started_at": "now"}},
                "last_state": {},
            }
        ],
        "init_containers": [],
        "events": [],
    }
    result.update(overrides)
    return result


def container(**overrides):
    result = {
        "name": "app",
        "image": "example/app:v1",
        "image_pull_policy": "IfNotPresent",
        "status_available": True,
        "ready": False,
        "restart_count": 0,
        "state": {},
        "last_state": {},
    }
    result.update(overrides)
    return result


def classify(item):
    incidents = detect_incidents({"namespace": "ecommerce", "items": [item]})
    return {incident["incident_type"] for incident in incidents}, incidents


def test_healthy_running_pod_has_no_incident():
    types, _ = classify(pod())
    assert types == set()


def test_crash_loop_backoff_is_detected():
    types, incidents = classify(
        pod(
            containers=[
                container(
                    restart_count=4,
                    state={"waiting": {"reason": "CrashLoopBackOff", "message": "backing off"}},
                    last_state={"terminated": {"reason": "Error", "exit_code": 1}},
                )
            ]
        )
    )
    assert "CrashLoopBackOff" in types
    assert "FailedContainer" not in types
    assert incidents[0]["likely_explanation"]["kind"] == "inference"


def test_err_image_never_pull_includes_image_and_policy_evidence():
    types, incidents = classify(
        pod(
            containers=[
                container(
                    image="ecommerce-gateway:v1",
                    image_pull_policy="Never",
                    state={"waiting": {"reason": "ErrImageNeverPull", "message": "not present"}},
                )
            ]
        )
    )
    assert "ErrImageNeverPull" in types
    assert "Configured image: ecommerce-gateway:v1." in incidents[0]["supporting_evidence"]
    assert "Image pull policy: Never." in incidents[0]["supporting_evidence"]


def test_image_pull_backoff_is_detected():
    types, _ = classify(pod(containers=[container(state={"waiting": {"reason": "ImagePullBackOff"}})]))
    assert "ImagePullBackOff" in types


def test_oom_killed_previous_termination_is_detected():
    types, _ = classify(
        pod(containers=[container(last_state={"terminated": {"reason": "OOMKilled", "exit_code": 137}})])
    )
    assert "OOMKilled" in types
    assert "FailedContainer" not in types


def test_repeated_restarts_are_detected_at_threshold():
    types, incidents = classify(pod(containers=[container(ready=True, restart_count=3, state={"running": {}})]))
    assert "RepeatedContainerRestarts" in types
    finding = next(item for item in incidents if item["incident_type"] == "RepeatedContainerRestarts")
    assert any("does not indicate a restart rate" in limit for limit in finding["evidence_limitations"])


def test_unschedulable_condition_is_detected():
    types, _ = classify(
        pod(
            phase="Pending",
            conditions=[{"type": "PodScheduled", "status": "False", "reason": "Unschedulable", "message": "insufficient cpu"}],
            events=[{"reason": "FailedScheduling", "message": "insufficient cpu"}],
        )
    )
    assert "UnschedulablePod" in types


def test_successfully_completed_job_is_not_an_incident():
    types, _ = classify(
        pod(
            phase="Succeeded",
            containers=[container(restart_count=7, state={"terminated": {"reason": "Completed", "exit_code": 0}})],
        )
    )
    assert types == set()


def test_missing_container_status_is_reported_as_incomplete_not_failure():
    types, incidents = classify(pod(containers=[container(status_available=False, state={}, last_state={})]))
    assert types == {"IncompleteContainerStatus"}
    assert incidents[0]["severity"] == "low"
    assert "does not establish a container failure" in incidents[0]["likely_explanation"]["statement"]


def test_container_status_unknown_is_uncertain_not_a_root_cause():
    types, incidents = classify(
        pod(
            containers=[
                container(
                    state={
                        "terminated": {
                            "reason": "ContainerStatusUnknown",
                            "message": "container missing",
                            "exit_code": 137,
                        }
                    },
                    last_state={"terminated": {"reason": "Error", "exit_code": 1}},
                )
            ]
        )
    )
    assert types == {"ContainerStatusUnknown"}
    assert "does not identify a root cause" in incidents[0]["likely_explanation"]["statement"]


def test_missing_events_does_not_block_status_based_detection():
    types, _ = classify(pod(containers=[container(state={"waiting": {"reason": "ErrImageNeverPull"}})], events=[]))
    assert types == {"ErrImageNeverPull"}


def test_recent_image_event_preserves_incident_when_container_status_is_unknown():
    item = pod(
        phase="Failed",
        containers=[
            container(
                image="ecommerce-gateway:v1",
                image_pull_policy="Never",
                state={"terminated": {"reason": "ContainerStatusUnknown", "exit_code": 137}},
            )
        ],
        events=[
            {
                "reason": "ErrImageNeverPull",
                "message": 'Container image "ecommerce-gateway:v1" is not present with pull policy of Never',
                "count": 25,
                "last_timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ],
    )
    types, incidents = classify(item)
    assert "ContainerStatusUnknown" in types
    assert "ErrImageNeverPull" in types
    finding = next(incident for incident in incidents if incident["incident_type"] == "ErrImageNeverPull")
    assert finding["severity"] == "medium"
    assert any("does not prove the condition is still active" in limitation for limitation in finding["evidence_limitations"])


def test_stale_image_event_does_not_create_an_active_image_incident():
    item = pod(
        phase="Failed",
        containers=[
            container(state={"terminated": {"reason": "ContainerStatusUnknown", "exit_code": 137}})
        ],
        events=[
            {
                "reason": "ErrImageNeverPull",
                "message": "image missing",
                "last_timestamp": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
            }
        ],
    )
    types, _ = classify(item)
    assert "ErrImageNeverPull" not in types


def test_stale_scheduling_event_does_not_flag_a_scheduled_pod():
    types, _ = classify(
        pod(
            phase="Pending",
            conditions=[{"type": "PodScheduled", "status": "True", "reason": None, "message": None}],
            events=[{"reason": "FailedScheduling", "message": "old failure"}],
        )
    )
    assert "UnschedulablePod" not in types


def test_failed_scheduling_event_detects_pending_pod_without_condition():
    types, _ = classify(
        pod(
            phase="Pending",
            conditions=[],
            events=[
                {
                    "reason": "FailedScheduling",
                    "message": "no capacity",
                    "last_timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ],
        )
    )
    assert "UnschedulablePod" in types


def test_failed_nonzero_container_termination_is_detected():
    types, _ = classify(
        pod(containers=[container(state={"terminated": {"reason": "Error", "exit_code": 1}})])
    )
    assert "FailedContainer" in types


def test_create_container_config_error_is_detected_for_init_container():
    types, _ = classify(
        pod(init_containers=[container(name="prepare", state={"waiting": {"reason": "CreateContainerConfigError"}})])
    )
    assert "CreateContainerConfigError" in types
