"""Strict, agent-facing request models."""

from enum import Enum

from pydantic import BaseModel, Field


class Action(str, Enum):
    RESTART_NUTRICIO = "restart_nutricio"
    SHOW_VPN_LOGS = "show_vpn_logs"


class AgentIntent(BaseModel):
    """An agent may express an intent, never a shell command or SSH settings."""

    task_id: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")
    action: Action
    target: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
