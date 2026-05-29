"""Kubernetes Python client wrapper — graceful no-op without cluster."""
from __future__ import annotations
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from kubernetes import client as k8s_client, config as k8s_config
    _K8S_OK = True
except ImportError:
    _K8S_OK = False
    logger.info("kubernetes client not installed — deployment routes return degraded responses")


def _unavailable(reason: str = "k8s_client_not_available") -> dict:
    return {"ok": False, "reason": reason, "k8s_available": False}


class K8sClient:
    def __init__(self):
        self._connected = False
        if _K8S_OK:
            try:
                k8s_config.load_incluster_config()
                self._connected = True
                logger.info("K8sClient: in-cluster config loaded")
            except Exception:
                try:
                    k8s_config.load_kube_config()
                    self._connected = True
                    logger.info("K8sClient: kubeconfig loaded")
                except Exception as e:
                    logger.info("K8sClient: no cluster available (%s)", e)

    def available(self) -> bool:
        return _K8S_OK and self._connected

    def _base(self) -> dict:
        return {"k8s_available": self.available()}

    def get_deployments(self, namespace: str = "default") -> dict:
        if not self.available():
            return {**_unavailable(), "deployments": []}
        try:
            apps = k8s_client.AppsV1Api()
            deps = apps.list_namespaced_deployment(namespace)
            result = []
            for d in deps.items:
                result.append({
                    "name": d.metadata.name,
                    "replicas": d.spec.replicas,
                    "ready": d.status.ready_replicas or 0,
                    "updated": d.status.updated_replicas or 0,
                })
            return {"ok": True, "k8s_available": True, "deployments": result}
        except Exception as e:
            return {**_unavailable(str(e)), "deployments": []}

    def get_pods(self, namespace: str = "default") -> dict:
        if not self.available():
            return {**_unavailable(), "pods": []}
        try:
            v1 = k8s_client.CoreV1Api()
            pods = v1.list_namespaced_pod(namespace)
            result = []
            for p in pods.items:
                result.append({
                    "name": p.metadata.name,
                    "phase": p.status.phase,
                    "node": p.spec.node_name,
                    "ip": p.status.pod_ip,
                    "ready": all(
                        c.ready for c in (p.status.container_statuses or [])
                    ),
                })
            return {"ok": True, "k8s_available": True, "pods": result}
        except Exception as e:
            return {**_unavailable(str(e)), "pods": []}

    def scale(self, deployment: str, replicas: int, namespace: str = "default") -> dict:
        if not self.available():
            return _unavailable()
        try:
            apps = k8s_client.AppsV1Api()
            body = {"spec": {"replicas": replicas}}
            apps.patch_namespaced_deployment_scale(deployment, namespace, body)
            return {"ok": True, "k8s_available": True,
                    "deployment": deployment, "replicas": replicas}
        except Exception as e:
            return _unavailable(str(e))

    def rollback(self, deployment: str, namespace: str = "default") -> dict:
        if not self.available():
            return _unavailable()
        try:
            # Trigger rollback by annotating (actual rollback via helm or kubectl rollout undo)
            apps = k8s_client.AppsV1Api()
            import time
            body = {"metadata": {"annotations": {
                "kubectl.kubernetes.io/last-applied-configuration": str(time.time())
            }}}
            apps.patch_namespaced_deployment(deployment, namespace, body)
            return {"ok": True, "k8s_available": True, "deployment": deployment,
                    "message": "Rollback annotation applied — run helm rollback for full rollback"}
        except Exception as e:
            return _unavailable(str(e))

    def get_resource_metrics(self, namespace: str = "default") -> dict:
        if not self.available():
            return {**_unavailable(), "metrics": []}
        try:
            # metrics-server via CustomObjectsApi
            co = k8s_client.CustomObjectsApi()
            metrics = co.list_namespaced_custom_object(
                "metrics.k8s.io", "v1beta1", namespace, "pods"
            )
            result = []
            for item in metrics.get("items", []):
                pod_name = item["metadata"]["name"]
                containers = item.get("containers", [])
                result.append({
                    "pod": pod_name,
                    "containers": [
                        {"name": c["name"], "cpu": c["usage"].get("cpu", "?"),
                         "memory": c["usage"].get("memory", "?")}
                        for c in containers
                    ]
                })
            return {"ok": True, "k8s_available": True, "metrics": result}
        except Exception as e:
            return {**_unavailable(str(e)), "metrics": []}


_k8s: Optional[K8sClient] = None


def get_k8s_client() -> K8sClient:
    global _k8s
    if _k8s is None:
        _k8s = K8sClient()
    return _k8s
