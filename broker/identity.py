"""Demo agent authentication; identity never comes from the request body."""

import os
import secrets

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


_DEMO_TOKENS = {
    os.getenv("BROKER_DEVIN_TOKEN", "demo-devin-token"): "devin-prod",
    os.getenv("BROKER_SUPPORT_TOKEN", "demo-support-token"): "vpn-support-agent",
}
_BEARER = HTTPBearer(auto_error=False)


def authenticate(credentials: HTTPAuthorizationCredentials | None = Depends(_BEARER)) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = credentials.credentials.strip()
    for known_token, agent in _DEMO_TOKENS.items():
        if secrets.compare_digest(token, known_token):
            return agent
    raise HTTPException(status_code=401, detail="Unknown agent token")
