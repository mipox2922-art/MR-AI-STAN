from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import ActivityLog, Task
from ..realtime import manager
from ..schemas import TaskCreate, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post("")
async def create_task(
    data: TaskCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = Task(
        user_id=current_user.id,
        title=data.title,
        description=data.description,
        priority=data.priority,
        deadline=data.deadline,
        agent=data.agent,
    )

    db.add(task)
    db.add(
        ActivityLog(
            user_id=current_user.id,
            action="TASK_CREATED",
            details=data.title,
        )
    )

    db.commit()
    db.refresh(task)

    await manager.broadcast(
        "TASK_CREATED",
        {"task_id": task.id},
        user_id=current_user.id,
    )

    return task


@router.get("")
def list_tasks(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(Task)
        .filter(Task.user_id == current_user.id)
        .order_by(Task.id.desc())
        .all()
    )


@router.patch("/{task_id}")
async def update_task(
    task_id: int,
    data: TaskUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = (
        db.query(Task)
        .filter(
            Task.id == task_id,
            Task.user_id == current_user.id,
        )
        .first()
    )

    if not task:
        raise HTTPException(404, "Task not found")

    updates = data.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(task, key, value)

    db.add(
        ActivityLog(
            user_id=current_user.id,
            action="TASK_UPDATED",
            details=f"Task {task.id}",
        )
    )

    db.commit()
    db.refresh(task)

    if task.status == "COMPLETED":
        event = "TASK_COMPLETED"
    elif task.status in {"FAILED", "WAITING_FOR_HAND", "WAITING_APPROVAL"}:
        event = "TASK_WAITING"
    else:
        event = "TASK_PROGRESS"

    await manager.broadcast(
        event,
        {
            "task_id": task.id,
            "status": task.status,
            "progress": task.progress,
            "result": task.result,
            "error": task.error,
        },
        user_id=current_user.id,
    )

    return task
