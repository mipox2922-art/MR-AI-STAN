from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import Memory
from ..schemas import MemoryCreate, MemoryUpdate

router = APIRouter(prefix="/memory", tags=["Memory"])


@router.post("")
def create_memory(
    data: MemoryCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    memory = Memory(
        user_id=current_user.id,
        key=data.key,
        value=data.value,
    )

    db.add(memory)
    db.commit()
    db.refresh(memory)

    return memory


@router.get("")
def list_memories(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(Memory)
        .filter(Memory.user_id == current_user.id)
        .order_by(Memory.id.desc())
        .all()
    )


@router.get("/search")
def search_memory(
    q: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(Memory)
        .filter(
            Memory.user_id == current_user.id,
            (
                Memory.key.contains(q)
                | Memory.value.contains(q)
            ),
        )
        .all()
    )


@router.put("/{memory_id}")
def update_memory(
    memory_id: int,
    data: MemoryUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    memory = (
        db.query(Memory)
        .filter(
            Memory.id == memory_id,
            Memory.user_id == current_user.id,
        )
        .first()
    )

    if not memory:
        raise HTTPException(404, "Memory not found")

    memory.value = data.value
    db.commit()

    return memory


@router.delete("/{memory_id}")
def delete_memory(
    memory_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    memory = (
        db.query(Memory)
        .filter(
            Memory.id == memory_id,
            Memory.user_id == current_user.id,
        )
        .first()
    )

    if not memory:
        raise HTTPException(404, "Memory not found")

    db.delete(memory)
    db.commit()

    return {"deleted": True}
