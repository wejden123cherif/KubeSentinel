from fastapi import HTTPException
from kubernetes.client.exceptions import ApiException
from kubernetes.config.config_exception import ConfigException
from urllib3.exceptions import HTTPError as Urllib3Error

from app.services.kubernetes_service import KubernetesUnavailable


def translate_kubernetes_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ApiException):
        if exc.status == 403:
            return HTTPException(status_code=403, detail="Kubernetes access denied")
        if exc.status == 404:
            return HTTPException(status_code=404, detail="Kubernetes resource not found")
        return HTTPException(status_code=502, detail="Kubernetes API request failed")
    if isinstance(exc, (KubernetesUnavailable, ConfigException, OSError, TimeoutError, Urllib3Error)):
        return HTTPException(status_code=503, detail="Kubernetes API is unavailable or not configured")
    return HTTPException(status_code=502, detail="Could not retrieve Kubernetes evidence")
