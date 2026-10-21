import pytest
from pydantic import ValidationError

from app.schemas import TaskUpdate


def test_task_update_accepts_only_nonterminal_workflow_states():
    update = TaskUpdate(status="WAITING_FOR_HAND", priority="HIGH")
    assert update.status == "WAITING_FOR_HAND"
    assert update.priority == "HIGH"


@pytest.mark.parametrize("status", ["COMPLETED", "FAILED", "SUCCEEDED", "DONE"])
def test_task_update_rejects_terminal_or_unknown_statuses(status):
    with pytest.raises(ValidationError):
        TaskUpdate(status=status)


@pytest.mark.parametrize("progress", [-1, 0, 1, 50, 99, 100, 101])
def test_task_update_rejects_client_forged_progress(progress):
    with pytest.raises(ValidationError):
        TaskUpdate.model_validate({"progress": progress})


@pytest.mark.parametrize("field", ["result", "error", "verified", "approved_by", "approved_at", "source", "requested_by"])
def test_task_update_rejects_client_supplied_execution_evidence_or_provenance(field):
    with pytest.raises(ValidationError):
        TaskUpdate.model_validate({field: "forged client evidence"})
