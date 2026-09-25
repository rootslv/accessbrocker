"""Shared schemas for operations allowed on the demo SSH target."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Action(str, Enum):
    RESTART_NUTRICIO = "restart_nutricio"
    SHOW_VPN_LOGS = "show_vpn_logs"
    READ_SERVICE_LOGS = "read_service_logs"


class NoParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LogParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit: Literal["nutricio-api", "vpn"]
    since_minutes: int = Field(default=30, ge=1, le=120, strict=True)
    lines: int = Field(default=100, ge=1, le=500, strict=True)
    contains: str | None = Field(default=None, max_length=80, pattern=r"^[^\x00-\x1f\x7f]*$")


class IntentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Action
    target: Literal["nutricio-server", "root-vpn-node-1"]
    params: dict[str, object] = Field(default_factory=dict)


def validate_payload(payload: IntentPayload) -> IntentPayload:
    if payload.action == Action.RESTART_NUTRICIO:
        if payload.target != "nutricio-server":
            raise ValueError("Restart is restricted to the nutricio server")
        params = NoParams.model_validate(payload.params)
    elif payload.action == Action.SHOW_VPN_LOGS:
        if payload.target != "root-vpn-node-1":
            raise ValueError("VPN logs are restricted to the VPN node")
        params = NoParams.model_validate(payload.params)
    else:
        params = LogParams.model_validate(payload.params)
        if (payload.target, params.unit) not in {
            ("nutricio-server", "nutricio-api"),
            ("root-vpn-node-1", "vpn"),
        }:
            raise ValueError("Unit is not available on this target")
    return payload.model_copy(update={"params": params.model_dump(exclude_none=True)})
