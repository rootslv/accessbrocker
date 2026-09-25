# Access Broker demo for Devin

Use `client/agent_ssh.py` to request task-scoped infrastructure operations.
Do not use a direct SSH key or SSH into the demo target. The demo broker runs
locally by default; follow README.md to start Docker, pin the SSH host key,
and start the broker first.

Example for incident INC-1842:

```bash
.venv/bin/python client/agent_ssh.py read_service_logs --task-id INC-1842 \
  --params '{"unit":"nutricio-api","since_minutes":30,"lines":20,"contains":"ERROR"}'
```

Use `restart_nutricio` only if the user asks to restart the demo service.
The broker decides which identities can use which targets; never substitute
a different token or principal to bypass a denial. Explain a 403 and show
its receipt ID. Query `http://127.0.0.1:8000/audit/verify` for the local
audit-chain check. For an external broker, use session secrets
`BROKER_URL` and `BROKER_DEVIN_TOKEN`; never print their values.
