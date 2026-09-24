"""
Access Broker — минимальный MVP.

Логика в одном месте:
1. Агент просит доступ по scope_name (какая задача, для чего).
2. Broker проверяет policy: разрешён ли вообще такой scope.
3. Если да — подписывает короткоживущий SSH-сертификат через ssh-keygen,
   с force-command (агент физически не может выполнить ничего, кроме
   разрешённой команды) и TTL.
4. Каждая выдача пишется в audit.log.

Запуск: uvicorn main:app --reload --port 8000
"""

import subprocess
import uuid
import time
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Access Broker (MVP)")

BASE_DIR = Path(__file__).resolve().parent.parent
CA_KEY = BASE_DIR / "ca" / "ca_key"
CERT_OUT_DIR = BASE_DIR / "logs" / "certs"
AUDIT_LOG = BASE_DIR / "logs" / "audit.log"
CERT_OUT_DIR.mkdir(parents=True, exist_ok=True)

# --- Policy: единственное место, где решается "что кому можно" -----------
# Для демо — простой словарь. В реальном проекте это был бы YAML/DB.
SCOPES = {
    "deploy-nutricio": {
        "host": "nutricio-server",
        "principal": "deploy_user",
        "ttl": "30s",  # для демо специально коротко — в проде было бы 15m
        "allowed_command": "/usr/local/bin/restart_app.sh",
    },
    "debug-vpn": {
        "host": "root-vpn-node-1",
        "principal": "readonly_user",
        "ttl": "30s",
        "allowed_command": "/usr/local/bin/show_logs.sh",
    },
}


class AccessRequest(BaseModel):
    scope: str
    agent_name: str
    task_id: str
    public_key: str  # содержимое agent_key.pub, присланное клиентом


def _write_audit(entry: dict) -> None:
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


@app.post("/request-access")
def request_access(req: AccessRequest):
    scope = SCOPES.get(req.scope)

    # --- Уровень 1 проверки прав: сам вопрос "можно ли вообще" -----------
    if scope is None:
        _write_audit({
            "event": "denied",
            "reason": "unknown_scope",
            "scope": req.scope,
            "agent": req.agent_name,
            "task_id": req.task_id,
            "ts": time.time(),
        })
        raise HTTPException(status_code=403, detail="Scope not permitted")

    cert_id = f"{req.scope}-{uuid.uuid4().hex[:8]}"
    pubkey_path = CERT_OUT_DIR / f"{cert_id}.pub"
    pubkey_path.write_text(req.public_key)
    cert_path = CERT_OUT_DIR / f"{cert_id}-cert.pub"

    # --- Уровень 2 проверки прав: вшито прямо в сертификат ---------------
    # force-command — сервер выполнит ТОЛЬКО эту команду, что бы клиент
    # ни прислал после `ssh host ...`. Это гарантия SSH-протокола, не нашего кода.
    cmd = [
        "ssh-keygen", "-s", str(CA_KEY),
        "-I", cert_id,
        "-n", scope["principal"],
        "-V", f"+{scope['ttl']}",
        "-O", f"force-command={scope['allowed_command']}",
        "-O", "no-port-forwarding",
        "-O", "no-pty",
        "-O", "no-x11-forwarding",
        str(pubkey_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        _write_audit({
            "event": "issue_failed",
            "scope": req.scope,
            "agent": req.agent_name,
            "task_id": req.task_id,
            "error": result.stderr,
            "ts": time.time(),
        })
        raise HTTPException(status_code=500, detail=f"Signing failed: {result.stderr}")

    _write_audit({
        "event": "issued",
        "cert_id": cert_id,
        "scope": req.scope,
        "agent": req.agent_name,
        "task_id": req.task_id,
        "host": scope["host"],
        "principal": scope["principal"],
        "ttl": scope["ttl"],
        "allowed_command": scope["allowed_command"],
        "ts": time.time(),
    })

    return {
        "cert_id": cert_id,
        "certificate": cert_path.read_text(),
        "principal": scope["principal"],
        "host": scope["host"],
        "ttl": scope["ttl"],
    }


@app.get("/audit")
def get_audit():
    """Для демо-дашборда — отдать весь лог как JSON-строки."""
    if not AUDIT_LOG.exists():
        return []
    lines = AUDIT_LOG.read_text().strip().splitlines()
    return [json.loads(line) for line in lines if line]
