from fastapi import APIRouter, Query, Request

from app.api.errors import translate_kubernetes_error
from app.schemas.kubernetes import NamespaceList, PodDiagnostics, PodList
from app.services.kubernetes_service import KubernetesService

router = APIRouter(tags=["kubernetes"])


def service(request: Request) -> KubernetesService:
    return request.app.state.kubernetes_service


@router.get("/namespaces", response_model=NamespaceList)
def namespaces(request: Request):
    try:
        return service(request).list_namespaces()
    except Exception as exc:
        raise translate_kubernetes_error(exc) from exc


@router.get("/pods", response_model=PodList)
def pods(request: Request, namespace: str = Query(default="ecommerce", min_length=1, max_length=63)):
    try:
        return service(request).list_pods(namespace)
    except Exception as exc:
        raise translate_kubernetes_error(exc) from exc


@router.get("/pods/{namespace}/{pod_name}/diagnostics", response_model=PodDiagnostics)
def diagnostics(
    request: Request,
    namespace: str,
    pod_name: str,
    tail_lines: int = Query(default=100, ge=1, le=200),
):
    try:
        return service(request).diagnostics(namespace, pod_name, tail_lines=tail_lines)
    except Exception as exc:
        raise translate_kubernetes_error(exc) from exc
