"""Demo agent authentication; identity never comes from the request body."""

import os
import secrets

from fastapi import Header, HTTPException


_DEMO_TOKENS = {
    os.getenv("BROKER_DEVIN_TOKEN", "demo-devin-token"): "devin-prod",
    os.getenv("BROKER_SUPPORT_TOKEN", "demo-support-token"): "vpn-support-agent",
}


def authenticate(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = authorization.removeprefix("Bearer ").strip()
    for known_token, agent in _DEMO_TOKENS.items():
        if secrets.compare_digest(token, known_token):
            return agent
    raise HTTPException(status_code=401, detail="Unknown agent token")
