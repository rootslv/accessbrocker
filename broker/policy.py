"""Default-deny policy and intent-to-command compilation."""

from dataclasses import dataclass

from broker.models import Action, AgentIntent


@dataclass(frozen=True)
class Capability:
    agent: str
    task_id: str
    action: str
    target: str
    network_host: str
    principal: str
    command: str
    ttl: str


_RULES = {
    ("devin-prod", Action.RESTART_NUTRICIO, "nutricio-server"): {
        "network_host": "localhost", "principal": "deploy_user",
        "command": "/usr/local/bin/restart_app.sh", "ttl": "30s",
    },
    ("vpn-support-agent", Action.SHOW_VPN_LOGS, "root-vpn-node-1"): {
        "network_host": "localhost", "principal": "readonly_user",
        "command": "/usr/local/bin/show_logs.sh", "ttl": "30s",
    },
}


class PolicyDenied(Exception):
    pass


def authorize(agent: str, intent: AgentIntent) -> Capability:
    rule = _RULES.get((agent, intent.action, intent.target))
    if rule is None:
        raise PolicyDenied("This agent is not permitted to perform this action on this target")
    return Capability(agent=agent, task_id=intent.task_id, action=intent.action.value, target=intent.target, **rule)
