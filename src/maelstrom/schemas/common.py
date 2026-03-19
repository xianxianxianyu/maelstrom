from enum import Enum


class ProviderEnum(str, Enum):
    """Deprecated — kept for migration only."""
    openai = "openai"
    anthropic = "anthropic"
    local = "local"


class ProtocolEnum(str, Enum):
    openai_chat = "openai_chat"
    openai_responses = "openai_responses"
    anthropic_messages = "anthropic_messages"


class SessionStatus(str, Enum):
    active = "active"
    archived = "archived"


class RunStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class ResearchPhase(str, Enum):
    ideation = "ideation"
    grounding = "grounding"
    planning = "planning"
    execution = "execution"
