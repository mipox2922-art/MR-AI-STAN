import pytest
from pydantic import ValidationError

from app.schemas import TaskUpdate


def test_task_update_accepts_only_nonterminal_workflow_states():
    update = TaskUpdate(status="WAITING_FOR_HAND", progress=95, priority="HIGH")
    assert update.status == "WAITING_FOR_HAND"
    assert update.progress == 95


@pytest.mark.parametrize("status", ["COMPLETED", "FAILED", "SUCCEEDED"])
def test_task_update_rejects_terminal_or_unknown_statuses(status):
    with pytest.raises(ValidationError):
        TaskUpdate(status=status)


@pytest.mark.parametrize("progress", [-1, 100, 101])
def test_task_update_rejects_out_of_range_progress(progress):
    with pytest.raises(ValidationError):
        TaskUpdate(progress=progress)


@pytest.mark.parametrize("field", ["result", "error", "verified"])
def test_task_update_rejects_client_supplied_execution_evidence(field):
    with pytest.raises(ValidationError):
        TaskUpdate.model_validate({field: "forged client evidence"})
