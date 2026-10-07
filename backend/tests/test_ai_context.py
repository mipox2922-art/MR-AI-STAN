from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Conversation, Message
from app.routers.ai import build_model_prompt


def make_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_build_model_prompt_includes_recent_conversation_and_verified_evidence():
    db = make_db()
    conversation = Conversation(user_id=1, title="Test")
    db.add(conversation)
    db.flush()

    db.add_all([
        Message(
            conversation_id=conversation.id,
            role="user",
            content="Naitwa Boss Ferisi.",
        ),
        Message(
            conversation_id=conversation.id,
            role="assistant",
            content="Nimekuelewa boss.",
        ),
    ])
    db.commit()

    prompt = build_model_prompt(
        db,
        conversation.id,
        "Unakumbuka jina langu?",
        {
            "status": "COMPLETED",
            "result": {"verified": True, "source": "test"},
        },
    )

    assert "Naitwa Boss Ferisi." in prompt
    assert "Nimekuelewa boss." in prompt
    assert "Unakumbuka jina langu?" in prompt
    assert '"verified": true' in prompt
    assert "Never invent actions" in prompt or "Never invent" in prompt


def test_build_model_prompt_without_history_stays_usable():
    db = make_db()
    conversation = Conversation(user_id=1, title="Test")
    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    prompt = build_model_prompt(
        db,
        conversation.id,
        "Habari MR AI",
        None,
    )

    assert "CURRENT USER MESSAGE" in prompt
    assert "Habari MR AI" in prompt
    assert "(none)" in prompt
