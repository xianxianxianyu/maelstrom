from __future__ import annotations

from typing import Any

from .contracts import Subagent


class SubagentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, Subagent] = {}
        self._capability_map: dict[str, str] = {}

    def register(self, agent: Subagent) -> None:
        self._agents[agent.name] = agent
        for capability in agent.capabilities:
            self._capability_map[capability] = agent.name

    def resolve(self, capability: str) -> Subagent:
        name = self._capability_map.get(capability)
        if not name:
            raise KeyError(f"capability not registered: {capability}")
        return self._agents[name]

    def get(self, name: str) -> Subagent:
        agent = self._agents.get(name)
        if not agent:
            raise KeyError(f"subagent not found: {name}")
        return agent

    def snapshot(self) -> dict[str, Any]:
        return {
            "agents": sorted(self._agents.keys()),
            "capabilities": dict(sorted(self._capability_map.items())),
        }
