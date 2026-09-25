"""Execute only the operation embedded in the signed SSH certificate."""

import base64
import binascii
import os
import pwd
import sys
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import ValidationError

from broker.intents import Action, IntentPayload, LogParams, validate_payload

LOG_FILES = {
    "nutricio-api": Path("/var/log/access-broker/nutricio-api.log"),
    "vpn": Path("/var/log/access-broker/vpn.log"),
}
ALLOWED = {
    ("deploy_user", Action.RESTART_NUTRICIO, "nutricio-server"),
    ("deploy_user", Action.READ_SERVICE_LOGS, "nutricio-server"),
    ("readonly_user", Action.SHOW_VPN_LOGS, "root-vpn-node-1"),
    ("readonly_user", Action.READ_SERVICE_LOGS, "root-vpn-node-1"),
}


def read_logs(params: LogParams) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=params.since_minutes)
    matching: deque[str] = deque(maxlen=params.lines)
    with LOG_FILES[params.unit].open(encoding="utf-8") as logfile:
        for line in logfile:
            timestamp, separator, message = line.partition(" ")
            if not separator:
                continue
            try:
                logged_at = datetime.fromisoformat(timestamp)
            except ValueError:
                continue
            if logged_at < cutoff or (params.contains is not None and params.contains not in message):
                continue
            matching.append(message.rstrip("\n")[:1024])
    output = 0
    for line in matching:
        if output + len(line) > 32768:
            break
        print(line)
        output += len(line) + 1


def main() -> None:
    try:
        if len(sys.argv) != 2 or len(sys.argv[1]) > 4096:
            raise ValueError("Expected a single certificate-bound payload")
        encoded = sys.argv[1]
        data = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
        payload = validate_payload(IntentPayload.model_validate_json(data))
        principal = pwd.getpwuid(os.getuid()).pw_name
        if (principal, payload.action, payload.target) not in ALLOWED:
            raise ValueError("Principal cannot perform this operation")
        if payload.action == Action.RESTART_NUTRICIO:
            os.execv("/usr/local/bin/restart_app.sh", ["/usr/local/bin/restart_app.sh"])
        if payload.action == Action.SHOW_VPN_LOGS:
            read_logs(LogParams(unit="vpn"))
        else:
            read_logs(LogParams.model_validate(payload.params))
    except (binascii.Error, OSError, ValidationError, ValueError) as error:
        print(f"Intent rejected: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
