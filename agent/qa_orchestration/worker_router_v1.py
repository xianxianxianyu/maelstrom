from __future__ import annotations

from .contracts_v1 import WorkerRole, WorkerV1
from .worker_registry_v1 import WorkerRegistryV1


class WorkerRouterV1:
    def __init__(self, registry: WorkerRegistryV1) -> None:
        self.registry = registry

    def resolve(self, role: WorkerRole, capability: str) -> WorkerV1:
        try:
            return self.registry.resolve_by_capability(capability)
        except KeyError:
            return self.registry.resolve_by_role(role)
