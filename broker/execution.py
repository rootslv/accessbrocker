"""Broker-mediated SSH: credentials are never returned to the AI agent."""

import base64
import hashlib
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from broker.policy import Capability


@dataclass(frozen=True)
class ExecutionResult:
    certificate_serial: str
    exit_code: int
    stdout: str
    stderr: str

    @property
    def output_hash(self) -> str:
        return hashlib.sha256((self.stdout + self.stderr).encode()).hexdigest()


class SSHExecutor:
    def __init__(self, ca_key: Path, known_hosts: Path, ssh_port: str = "2222"):
        self.ca_key, self.known_hosts, self.ssh_port = ca_key, known_hosts, ssh_port

    def execute(self, capability: Capability) -> ExecutionResult:
        serial = str(uuid.uuid4().int % 2_000_000_000)
        encoded = base64.urlsafe_b64encode(capability.payload.encode("utf-8")).decode("ascii").rstrip("=")
        forced_command = f"/usr/bin/python3 /opt/access-broker/intent_runner.py {encoded}"
        with tempfile.TemporaryDirectory(prefix="access-broker-") as runtime_dir:
            private_key = Path(runtime_dir) / "operation_key"
            public_key = private_key.with_suffix(".pub")
            self._run(["ssh-keygen", "-q", "-t", "ed25519", "-f", str(private_key), "-N", ""])
            self._run(["ssh-keygen", "-q", "-s", str(self.ca_key), "-I", f"{capability.action}-{uuid.uuid4().hex[:8]}",
                       "-z", serial, "-n", capability.principal, "-V", f"+{capability.ttl}",
                       "-O", f"force-command={forced_command}", "-O", "no-port-forwarding",
                       "-O", "no-pty", "-O", "no-x11-forwarding", str(public_key)])
            result = subprocess.run([
                "ssh", "-i", str(private_key), "-o", f"CertificateFile={private_key}-cert.pub",
                "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                "-o", f"UserKnownHostsFile={self.known_hosts}", "-o", "GlobalKnownHostsFile=/dev/null",
                "-p", self.ssh_port, f"{capability.principal}@{capability.network_host}",
                "ignored-by-certificate-force-command",
            ], capture_output=True, text=True, timeout=15)
            if result.returncode == 255:
                raise RuntimeError(result.stderr.strip() or "SSH connection failed")
            return ExecutionResult(serial, result.returncode, result.stdout, result.stderr)

    @staticmethod
    def _run(command: list[str]) -> None:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "Command failed")
