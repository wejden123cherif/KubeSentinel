from fastapi import APIRouter, HTTPException, Query, Request

from app.api.errors import translate_kubernetes_error
from app.schemas.incidents import IncidentList
from app.services.incident_detector import detect_incidents

router = APIRouter(tags=["incidents"])


@router.get("/incidents", response_model=IncidentList)
def incidents(request: Request, namespace: str = Query(default="ecommerce", min_length=1, max_length=63)):
    try:
        evidence = request.app.state.kubernetes_service.list_incident_evidence(namespace)
        return {
            "namespace": namespace,
            "scanned_pods": len(evidence.get("items") or []),
            "incidents": detect_incidents(evidence),
            "evidence_warnings": [evidence["events_error"]] if evidence.get("events_error") else [],
        }
    except Exception as exc:
        raise translate_kubernetes_error(exc) from exc
