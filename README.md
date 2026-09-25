# Access Broker (MVP) — temporary SSH access for AI agents

The idea: the agent never receives a permanent root key, nor even a temporary
SSH certificate. Instead, it sends the broker a structured intent tied to a
specific task. The broker verifies identity and policy, issues a one-time
ephemeral credential itself, executes only the strictly allowed command, and
returns just the result to the agent.

## Problem

AI agents (Devin, Claude Code, Cursor) increasingly get direct access to
production infrastructure. Today's standard practice is to hand the agent a
permanent SSH key, often with root privileges, because proper access scoping
requires manual setup (a separate user, sudoers, rotation) — and there is never
time for that.

Consequences:
- **Access never expires.** The key works indefinitely until someone remembers
  to revoke it by hand.
- **No boundaries on actions.** A hallucination, a misread task, or a prompt
  injection — and the agent has enough privileges to do anything, not just
  what the task requires.
- **No separation in logs.** It is impossible to tell what a human did from
  what an agent did during a specific task.

## Solution

Access Broker issues not a key but a **temporary, narrowly scoped
permission**:
- **Time-boxed** — the certificate lives for minutes (seconds in the demo),
  then simply stops working. Nothing needs to be revoked manually.
- **Intent-scoped** — the agent sends a typed action with parameters, e.g.
  `read_service_logs(unit=nutricio-api, since_minutes=30, lines=20)`.
  The broker validates policy and parameters, then signs an SSH certificate
  that carries the *validated intent* in its `force-command`. The server
  re-validates the intent and executes only the pre-approved operation.
- **Authenticated** — agent identity is derived from the bearer token, not
  from a client-supplied `agent_name`.
- **Audit by default** — every allow/deny and execution result lands in a
  hash-chained receipt with the task ID, parameters, and certificate serial.

This is not a replacement for system prompts / `AGENTS.md` — it is a second,
hard line of defense on top of them: if a prompt instruction fails (rewritten
by an injection, ignored by the model), the infrastructure-level boundary still
holds.

## What it gives you

| | Today (static root key) | With Access Broker |
|---|---|---|
| Access lifetime | Indefinite | Seconds to minutes, expires on its own |
| What can be done | Anything | One allowed command |
| Revocation on offboarding / task change | Manual, easy to forget | Not needed — access has already expired |
| Visibility (who did what) | Shared root log, agent and human indistinguishable | A separate record for every access request |

**Pitch line:**
> Agents get root keys because scoping access takes too long.
> We make scoped, expiring access as fast as handing over a static key.

## Setup (do this ahead of the demo)

```bash
# 1. Create the CA
./setup_ca.sh
cp ca/ca_key.pub server/ca_key.pub

# 2. Start the test server (requires Docker)
docker compose up -d --build

# 3. Pin the test server's public host key into a trusted known_hosts
printf '[localhost]:2222 %s\n' "$(docker exec access-broker-demo-server cat /etc/ssh/ssh_host_ed25519_key.pub)" > known_hosts

# 4. Start the broker (separate terminal, from the project root)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn broker.main:app --host 127.0.0.1 --port 8000
```

The server generates fresh log lines when the container starts. If you rebuild
the image, repeat the pin step for the new host key. Never fetch a host key
over an untrusted connection without verifying its fingerprint.

### Option: a real VPS instead of Docker

The target only needs `sshd` with `TrustedUserCAKeys /etc/ssh/ca_key.pub`,
password-less `deploy_user`/`readonly_user`, `pydantic==2.10.4`,
`broker/intents.py` in `/opt/access-broker/broker/`, `server/intent_runner.py`
in `/opt/access-broker/`, `/usr/local/bin/restart_app.sh` and the demo logs in
`/var/log/access-broker/` (mirror `server/Dockerfile` and
`server/start-demo.sh`). The private CA key stays on the broker machine.
Obtain the VPS host key over a trusted channel and pin it in `known_hosts` as
`<host> ssh-ed25519 ...`. Point the broker at the VPS via environment:

```bash
BROKER_TARGET_HOST=<vps-ip> BROKER_TARGET_PORT=22 \
  .venv/bin/uvicorn broker.main:app --host 127.0.0.1 --port 8000
```

## Demo scenario: Devin requests scoped access

Open a Devin session on this repository and ask: "For task INC-1842, check
nutricio-api errors from the last 30 minutes via Access Broker. Then try to
fetch the vpn logs on the same server. Show the receipts."
Devin can run the client from the repository root:

```bash
.venv/bin/python client/agent_ssh.py read_service_logs --task-id INC-1842 \
  --params '{"unit":"nutricio-api","since_minutes":30,"lines":20,"contains":"ERROR"}'
```
Expected result: the line `ERROR nutricio-api timeout connecting to database`.
The output also includes the audit receipt ID. The agent never receives an SSH
credential.

Policy check: the same agent cannot pick someone else's target or unit:
```bash
.venv/bin/python client/agent_ssh.py read_service_logs --target root-vpn-node-1 \
  --params '{"unit":"vpn"}' --task-id INC-1843
.venv/bin/python client/agent_ssh.py read_service_logs \
  --params '{"unit":"vpn"}' --task-id INC-1844
```
Expected result: `403` and a separate receipt for each denial.

The filter treats special characters literally (no shell involved):
```bash
.venv/bin/python client/agent_ssh.py read_service_logs \
  --params '{"unit":"nutricio-api","contains":"; touch /tmp/owned"}'
docker exec access-broker-demo-server test ! -e /tmp/owned
```
The command does not create the file even though the filter contains shell
syntax. The legacy actions still work too: `restart_nutricio` and
`show_vpn_logs` (use `--agent vpn-support-agent` for the latter).

Verify the receipt chain:

```bash
curl -s http://127.0.0.1:8000/audit/verify
curl -s http://127.0.0.1:8000/audit
```

To run Devin on a **different** machine, put the broker behind HTTPS with
authentication and restrict access to a trusted network; set `BROKER_URL` and
`BROKER_DEVIN_TOKEN` as session secrets. By default the client and broker run
locally with publicly known demo tokens; that setup is only suitable for a
single-machine demo. For a remote Devin you can also bring up the whole demo
environment inside its session using the steps above.

## Why a CA is needed even with two scripts

The CA signs the *exact parameters* of the operation, its validity window, and
the Unix principal. Tampering with the original SSH command via
`SSH_ORIGINAL_COMMAND` does not change the operation baked into the
certificate's `force-command`. The payload is encoded as URL-safe base64 so
dynamic data never reaches the shell as syntax; the schema is validated again
on the server. Log reading uses a fixed unit → file mapping and a literal
substring search, bounded by line count and output size. No agent parameter is
ever passed to a command interpreter.

## Pitch line

> AI agents get permanent root SSH keys because scoping access takes too
> long. We built a broker that issues short-lived, task-scoped SSH
> certificates in seconds — the agent can only run the allowed command,
> for a limited time, and every request is logged.

## What was deliberately simplified for the 3-hour build

- Identity uses well-known demo bearer tokens; production needs OIDC or mTLS
  and separate agent credentials. The HTTP audit API has no auth yet.
- Restart is only a demo script. Logs are files inside the container, not the
  host's real `journalctl`: the container does not run systemd. For real hosts
  you can keep the same schemas and unit whitelist but replace the fixed file
  reader with `subprocess.run` using a constant argv such as
  `["journalctl", "-u", unit, "-n", str(lines), "--no-pager"]`, `shell=False`,
  a timeout, and an output limit.
- Policy is a Python dict with no external approval workflow; the cert is
  valid for 30s, but an operation already running is not interrupted when the
  certificate expires.
- The CA key sits on the broker's disk. Production needs a protected signer,
  host key pinning outside local Docker, and external immutable storage of the
  audit head: the local chain can be rewritten entirely.
