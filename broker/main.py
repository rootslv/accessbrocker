"""Access Broker: authenticated intent → forced, ephemeral SSH capability."""

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException

from broker.execution import SSHExecutor
from broker.identity import authenticate
from broker.models import AgentIntent
from broker.policy import PolicyDenied, authorize
from broker.receipts import ReceiptLog

app = FastAPI(title="Access Broker — AI Capability Firewall")

BASE_DIR = Path(__file__).resolve().parent.parent
AUDIT = ReceiptLog(BASE_DIR / "logs" / "audit_receipts.log")
EXECUTOR = SSHExecutor(BASE_DIR / "ca" / "ca_key", BASE_DIR / "known_hosts")


@app.post("/execute-intent")
def execute_intent(intent: AgentIntent, agent: str = Depends(authenticate)):
    """Authorize and execute exactly one predefined operational action."""
    try:
        capability = authorize(agent, intent)
    except PolicyDenied as error:
        receipt = AUDIT.append(
            "intent_denied", agent=agent, task_id=intent.task_id,
            action=intent.action.value, target=intent.target, params=intent.params,
            reason=str(error),
        )
        raise HTTPException(status_code=403, detail={"reason": str(error), "receipt_id": receipt["receipt_id"]})

    try:
        result = EXECUTOR.execute(capability)
    except (RuntimeError, OSError) as error:
        receipt = AUDIT.append(
            "execution_failed", agent=agent, task_id=intent.task_id,
            action=intent.action.value, target=intent.target, params=intent.params,
            error=str(error),
        )
        raise HTTPException(status_code=502, detail={"reason": "Broker execution failed", "receipt_id": receipt["receipt_id"]})

    receipt = AUDIT.append(
        "action_executed", agent=agent, task_id=intent.task_id,
        action=intent.action.value, target=intent.target,
        params=intent.params, principal=capability.principal,
        certificate_serial=result.certificate_serial, exit_code=result.exit_code,
        output_hash=result.output_hash,
    )
    return {
        "receipt_id": receipt["receipt_id"], "task_id": intent.task_id,
        "action": intent.action.value, "target": intent.target,
        "exit_code": result.exit_code, "stdout": result.stdout, "stderr": result.stderr,
    }


@app.get("/audit")
def get_audit():
    return AUDIT.read()


@app.get("/audit/verify")
def verify_audit():
    return AUDIT.verify()
