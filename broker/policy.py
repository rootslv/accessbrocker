"""Default-deny policy for typed operations."""

import os
from dataclasses import dataclass

from pydantic import ValidationError

from broker.intents import Action, IntentPayload, validate_payload
from broker.models import AgentIntent


@dataclass(frozen=True)
class Capability:
    agent: str
    task_id: str
    action: str
    target: str
    network_host: str
    principal: str
    payload: str
    ttl: str


_TARGET_HOST = os.getenv("BROKER_TARGET_HOST", "localhost")

_RULES = {
    ("devin-prod", Action.RESTART_NUTRICIO, "nutricio-server"): {
        "network_host": _TARGET_HOST, "principal": "deploy_user",
        "ttl": "30s",
    },
    ("vpn-support-agent", Action.SHOW_VPN_LOGS, "root-vpn-node-1"): {
        "network_host": _TARGET_HOST, "principal": "readonly_user",
        "ttl": "30s",
    },
    ("devin-prod", Action.READ_SERVICE_LOGS, "nutricio-server"): {
        "network_host": _TARGET_HOST, "principal": "deploy_user", "ttl": "30s",
    },
    ("vpn-support-agent", Action.READ_SERVICE_LOGS, "root-vpn-node-1"): {
        "network_host": _TARGET_HOST, "principal": "readonly_user", "ttl": "30s",
    },
}


class PolicyDenied(Exception):
    pass


def authorize(agent: str, intent: AgentIntent) -> Capability:
    rule = _RULES.get((agent, intent.action, intent.target))
    if rule is None:
        raise PolicyDenied("This agent is not permitted to perform this action on this target")
    try:
        payload = validate_payload(IntentPayload.model_validate({
            "action": intent.action, "target": intent.target, "params": intent.params,
        }))
    except (ValidationError, ValueError) as error:
        raise PolicyDenied(f"Invalid intent parameters: {error}") from error
    return Capability(
        agent=agent, task_id=intent.task_id, action=intent.action.value,
        target=intent.target, payload=payload.model_dump_json(), **rule,
    )
