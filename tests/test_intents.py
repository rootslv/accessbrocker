"""Security boundaries for brokered SSH intents."""

import base64
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from broker.execution import SSHExecutor
from broker.intents import Action, IntentPayload, validate_payload
from broker.main import app
from broker.models import AgentIntent
from broker.policy import PolicyDenied, authorize
from server import intent_runner


class IntentTests(unittest.TestCase):
    def test_openapi_exposes_bearer_auth_for_browser_demo(self):
        operation = app.openapi()["paths"]["/execute-intent"]["post"]
        self.assertEqual(operation["security"], [{"HTTPBearer": []}])
        self.assertNotIn("parameters", operation)

    def test_authorized_log_filter_is_literal_and_bound_to_certificate(self):
        intent = AgentIntent(
            task_id="INC-1842", action=Action.READ_SERVICE_LOGS,
            target="nutricio-server",
            params={"unit": "nutricio-api", "contains": "; touch /tmp/owned", "lines": 20},
        )
        capability = authorize("devin-prod", intent)
        self.assertIn("; touch /tmp/owned", capability.payload)
        with patch("broker.execution.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "ok", "")) as run:
            SSHExecutor(Path("/fake/ca"), Path("/fake/known_hosts")).execute(capability)
        signing_args = run.call_args_list[1].args[0]
        forced = next(option for option in signing_args if option.startswith("force-command="))
        self.assertNotIn("; touch", forced)
        encoded = forced.rsplit(" ", 1)[1]
        bound = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        self.assertEqual(json.loads(bound)["params"]["contains"], "; touch /tmp/owned")
        ssh_args = run.call_args_list[2].args[0]
        self.assertEqual(ssh_args[-1], "ignored-by-certificate-force-command")
        self.assertIn("StrictHostKeyChecking=yes", ssh_args)

    def test_wrong_agent_target_and_unit_are_denied(self):
        for agent, target, unit in (
            ("devin-prod", "root-vpn-node-1", "vpn"),
            ("devin-prod", "nutricio-server", "vpn"),
            ("vpn-support-agent", "nutricio-server", "nutricio-api"),
        ):
            with self.subTest(agent=agent, target=target, unit=unit):
                with self.assertRaises(PolicyDenied):
                    authorize(agent, AgentIntent(
                        task_id="INC-1842", action=Action.READ_SERVICE_LOGS,
                        target=target, params={"unit": unit},
                    ))

    def test_invalid_or_extra_parameters_are_denied(self):
        for params in (
            {"unit": "nutricio-api", "lines": 10000},
            {"unit": "nutricio-api", "lines": True},
            {"unit": "nutricio-api", "contains": "hello\nworld"},
            {"unit": "nutricio-api", "shell": "id"},
        ):
            with self.subTest(params=params):
                with self.assertRaises(PolicyDenied):
                    authorize("devin-prod", AgentIntent(
                        task_id="INC-1842", action=Action.READ_SERVICE_LOGS,
                        target="nutricio-server", params=params,
                    ))
        with self.assertRaises(ValidationError):
            AgentIntent.model_validate({
                "task_id": "INC-1842", "action": "restart_nutricio",
                "target": "nutricio-server", "command": "id",
            })

    def test_target_revalidates_payload_and_ignores_original_command(self):
        with tempfile.TemporaryDirectory() as directory:
            logfile = Path(directory) / "nutricio.log"
            logfile.write_text(f"{datetime.now(timezone.utc).isoformat()} ERROR sample event\n")
            payload = validate_payload(IntentPayload(
                action=Action.READ_SERVICE_LOGS, target="nutricio-server",
                params={"unit": "nutricio-api", "contains": "ERROR"},
            ))
            encoded = base64.urlsafe_b64encode(payload.model_dump_json().encode()).decode().rstrip("=")
            with (
                patch.object(intent_runner, "LOG_FILES", {"nutricio-api": logfile}),
                patch.object(intent_runner.pwd, "getpwuid", return_value=SimpleNamespace(pw_name="deploy_user")),
                patch.object(intent_runner.sys, "argv", ["intent_runner.py", encoded]),
                patch.dict(os.environ, {"SSH_ORIGINAL_COMMAND": "rm -rf /"}),
                redirect_stdout(io.StringIO()) as output,
            ):
                intent_runner.main()
            self.assertEqual(output.getvalue(), "ERROR sample event\n")
            forged = base64.urlsafe_b64encode(json.dumps({
                "action": "read_service_logs", "target": "nutricio-server",
                "params": {"unit": "vpn"},
            }).encode()).decode().rstrip("=")
            with (
                patch.object(intent_runner.sys, "argv", ["intent_runner.py", forged]),
                patch.object(intent_runner.pwd, "getpwuid", return_value=SimpleNamespace(pw_name="deploy_user")),
                patch.object(intent_runner.sys, "stderr", io.StringIO()),
            ):
                with self.assertRaises(SystemExit):
                    intent_runner.main()


if __name__ == "__main__":
    unittest.main()
