"""Strict, agent-facing request models."""

from pydantic import BaseModel, ConfigDict, Field

from broker.intents import Action


class AgentIntent(BaseModel):
    """An agent may express an intent, never a shell command or SSH settings."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")
    action: Action
    target: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    params: dict[str, object] = Field(default_factory=dict)
