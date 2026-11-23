from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.api.routes.incidents import router as incidents_router
from app.api.routes.kubernetes import router as kubernetes_router
from app.services.kubernetes_service import KubernetesService

app = FastAPI(
    title="Kubernetes Investigation API",
    description="Read-only collection of Kubernetes evidence for investigations.",
    version="0.1.0",
)
app.include_router(health_router, prefix="/api")
app.include_router(kubernetes_router, prefix="/api")
app.include_router(incidents_router, prefix="/api")
app.state.kubernetes_service = KubernetesService()
