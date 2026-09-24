"""Demo AI agent: it submits an intent and never receives SSH credentials."""

import argparse
import sys

import requests

BROKER_URL = "http://localhost:8000"
DEMO_TOKENS = {
    "devin-prod": "demo-devin-token",
    "vpn-support-agent": "demo-support-token",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Request one brokered infrastructure action")
    parser.add_argument("action", choices=["restart_nutricio", "show_vpn_logs"])
    parser.add_argument("--task-id", default="INC-1842")
    parser.add_argument("--target", default=None)
    parser.add_argument("--agent", choices=DEMO_TOKENS, default="devin-prod")
    args = parser.parse_args()

    defaults = {
        "restart_nutricio": "nutricio-server",
        "show_vpn_logs": "root-vpn-node-1",
    }
    intent = {"task_id": args.task_id, "action": args.action, "target": args.target or defaults[args.action]}
    print(f"[agent] requesting intent: {intent}")
    response = requests.post(
        f"{BROKER_URL}/execute-intent", json=intent,
        headers={"Authorization": f"Bearer {DEMO_TOKENS[args.agent]}"}, timeout=20,
    )
    if response.status_code != 200:
        print(f"[DENIED] {response.status_code}: {response.json().get('detail')}")
        sys.exit(1)
    result = response.json()
    print(f"[receipt] {result['receipt_id']} | exit={result['exit_code']}")
    print(result["stdout"], end="")
    if result["stderr"]:
        print(result["stderr"], file=sys.stderr, end="")


if __name__ == "__main__":
    main()
