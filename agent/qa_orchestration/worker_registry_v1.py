from __future__ import annotations

from typing import Any

from .contracts_v1 import WorkerRole, WorkerV1


class WorkerRegistryV1:
    def __init__(self) -> None:
        self._workers: dict[str, WorkerV1] = {}
        self._capability_map: dict[str, str] = {}
        self._role_map: dict[WorkerRole, str] = {}

    def register(self, worker: WorkerV1) -> None:
        self._workers[worker.name] = worker
        self._role_map[worker.role] = worker.name
        for capability in worker.capabilities:
            self._capability_map[capability] = worker.name

    def resolve_by_capability(self, capability: str) -> WorkerV1:
        worker_name = self._capability_map.get(capability)
        if not worker_name:
            raise KeyError(f"worker capability not registered: {capability}")
        return self._workers[worker_name]

    def resolve_by_role(self, role: WorkerRole) -> WorkerV1:
        worker_name = self._role_map.get(role)
        if not worker_name:
            raise KeyError(f"worker role not registered: {role}")
        return self._workers[worker_name]

    def snapshot(self) -> dict[str, Any]:
        return {
            "workers": sorted(self._workers.keys()),
            "capabilities": dict(sorted(self._capability_map.items())),
            "roles": {role.value: name for role, name in self._role_map.items()},
        }
