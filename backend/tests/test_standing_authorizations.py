from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.authorizations import (
    authorization_enabled,
    list_standing_authorizations,
    set_standing_authorization,
)
from app.database import Base
from app.models import ActivityLog, Setting
from app.orchestration.executor import _is_safe_for_autonomous_execution
from app.routers.agents import _browser_result_is_verified


def make_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def test_standing_authorizations_are_owner_scoped_and_disabled_by_default():
    db = make_db()

    owner_rules = list_standing_authorizations(db, 101)
    other_rules = list_standing_authorizations(db, 202)
    owner_browser = next(row for row in owner_rules["rules"] if row["id"] == "browser.fill_non_sensitive")
    owner_gmail = next(row for row in owner_rules["rules"] if row["id"] == "gmail.routine_reply")

    assert owner_browser["enabled"] is False
    assert owner_gmail["enabled"] is False

    set_standing_authorization(db, 101, "browser.fill_non_sensitive", True)
    assert authorization_enabled(db, 101, "browser.fill_non_sensitive") is True
    assert authorization_enabled(db, 202, "browser.fill_non_sensitive") is False

    assert db.query(ActivityLog).filter_by(
        user_id=101, action="STANDING_AUTHORIZATION_CHANGED"
    ).count() == 1
    db.close()


def test_browser_non_sensitive_typing_requires_explicit_standing_authorization():
    db = make_db()
    plan = {"steps": [{"agent": "browser", "tools": ["browser_hands"]}]}

    assert _is_safe_for_autonomous_execution(
        plan, "type #full-name: Boss Ferisi", 11, db
    ) is False

    set_standing_authorization(db, 11, "browser.fill_non_sensitive", True)
    assert _is_safe_for_autonomous_execution(
        plan, "type #full-name: Boss Ferisi", 11, db
    ) is True

    # Standing browser-fill permission cannot authorize job submission or a different agent.
    assert _is_safe_for_autonomous_execution(
        {"steps": [{"agent": "jobs", "tools": ["public_job_feeds"]}]},
        "apply for remote jobs",
        11,
        db,
    ) is False
    db.close()


def test_gmail_routine_reply_rule_syncs_existing_auto_reply_setting():
    db = make_db()

    set_standing_authorization(db, 15, "gmail.routine_reply", True)
    row = db.query(Setting).filter_by(
        user_id=15, key="gmail_assistant.auto_send_enabled"
    ).one()
    assert row.value == "true"
    assert authorization_enabled(db, 15, "gmail.routine_reply") is True

    set_standing_authorization(db, 15, "gmail.routine_reply", False)
    db.refresh(row)
    assert row.value == "false"
    assert authorization_enabled(db, 15, "gmail.routine_reply") is False
    db.close()


def test_existing_gmail_auto_reply_opt_in_is_preserved_as_legacy_rule():
    db = make_db()
    db.add(Setting(
        user_id=16,
        key="gmail_assistant.auto_send_enabled",
        value="true",
    ))
    db.commit()

    assert authorization_enabled(db, 16, "gmail.routine_reply") is True
    db.close()


def _type_result(value_length, *, tag="input", input_type="text", content_editable=False):
    return {
        "action": "TYPE",
        "verified": True,
        "targetHost": "jobs.example.test",
        "targetUrl": "https://jobs.example.test/apply",
        "element": {
            "tag": tag,
            "type": input_type,
            "autocomplete": "",
            "contentEditable": content_editable,
            "id": "full-name",
            "name": "full-name",
            "ariaLabel": "Full name",
            "placeholder": "",
        },
        "valueLength": value_length,
    }


def test_browser_type_verification_checks_expected_value_and_non_sensitive_target():
    command = {"action": "TYPE", "payload": {"value": "Boss Ferisi"}}

    assert _browser_result_is_verified(command, _type_result(len("Boss Ferisi"))) is True
    assert _browser_result_is_verified(command, _type_result(3)) is False
    assert _browser_result_is_verified(
        command, _type_result(len("Boss Ferisi"), input_type="password")
    ) is False
    assert _browser_result_is_verified(
        command,
        _type_result(len("Boss Ferisi"), tag="div", content_editable=True),
    ) is True
    assert _browser_result_is_verified(
        command,
        _type_result(len("Boss Ferisi"), tag="div", content_editable=False),
    ) is False
    assert _browser_result_is_verified(
        command,
        _type_result(len("Boss Ferisi"), input_type="hidden"),
    ) is False

    emoji_value = "Boss 🚀"
    utf16_length = len(emoji_value.encode("utf-16-le")) // 2
    emoji_command = {"action": "TYPE", "payload": {"value": emoji_value}}
    assert _browser_result_is_verified(emoji_command, _type_result(utf16_length)) is True
