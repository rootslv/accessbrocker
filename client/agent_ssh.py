"""
Клиент для "агента" — вместо того, чтобы иметь постоянный root-ключ,
агент каждый раз просит у broker'а временный сертификат под конкретную задачу.

Использование:
    python agent_ssh.py deploy-nutricio --task-id my-task-1
    python agent_ssh.py deploy-nutricio --task-id my-task-1 --try-forbidden
"""

import argparse
import subprocess
import sys
from pathlib import Path

import requests

BROKER_URL = "http://localhost:8000"
KEY_DIR = Path(__file__).resolve().parent / "keys"
KEY_DIR.mkdir(exist_ok=True)

SSH_PORT = "2222"
SSH_HOST = "localhost"  # для демо — контейнер проброшен на localhost:2222


def ensure_keypair() -> tuple[Path, Path]:
    priv = KEY_DIR / "agent_key"
    pub = KEY_DIR / "agent_key.pub"
    if not priv.exists():
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-f", str(priv), "-N", ""],
            check=True,
        )
    return priv, pub


def request_certificate(scope: str, task_id: str, pub_key_path: Path) -> dict:
    resp = requests.post(
        f"{BROKER_URL}/request-access",
        json={
            "scope": scope,
            "agent_name": "devin",
            "task_id": task_id,
            "public_key": pub_key_path.read_text(),
        },
        timeout=10,
    )
    if resp.status_code != 200:
        print(f"[DENIED] {resp.status_code}: {resp.json().get('detail')}")
        sys.exit(1)
    return resp.json()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("scope", help="Например: deploy-nutricio")
    parser.add_argument("--task-id", default="demo-task")
    parser.add_argument(
        "--try-forbidden",
        action="store_true",
        help="Демо: попытаться выполнить НЕ разрешённую команду через тот же сертификат",
    )
    args = parser.parse_args()

    priv_key, pub_key = ensure_keypair()

    print(f"[agent] Requesting access for scope='{args.scope}', task='{args.task_id}'...")
    result = request_certificate(args.scope, args.task_id, pub_key)

    cert_path = KEY_DIR / f"{result['cert_id']}-cert.pub"
    cert_path.write_text(result["certificate"])

    print(f"[agent] Got certificate. principal={result['principal']} ttl={result['ttl']}")
    print(f"[agent] Connecting to {result['host']} as {result['principal']}...")

    command = "echo THIS SHOULD BE BLOCKED; rm -rf /tmp/whatever" if args.try_forbidden else ""

    ssh_cmd = [
        "ssh",
        "-i", str(priv_key),
        "-o", f"CertificateFile={cert_path}",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-p", SSH_PORT,
        f"{result['principal']}@{SSH_HOST}",
    ]
    if command:
        ssh_cmd.append(command)

    print(f"[agent] Running: ssh ... {'<forbidden command attempt>' if command else '(allowed command)'}")
    subprocess.run(ssh_cmd)


if __name__ == "__main__":
    main()
