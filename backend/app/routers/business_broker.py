from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import ActivityLog, BusinessOpportunity, Memory, Task

router = APIRouter(prefix="/broker", tags=["Business Broker"])

OpportunityType = Literal["CLIENT_LEAD", "SUPPLIER", "REMOTE_WORK", "PRODUCT", "AFFILIATE", "GENERAL"]
ALLOWED_STATUSES = {
    "UNVERIFIED", "RESEARCHED", "SHORTLISTED", "CONTACT_DRAFTED",
    "CONTACTED", "FOLLOW_UP_DUE", "WON", "LOST",
}
MONEY_FIELDS = {"selling_price", "supplier_cost", "shipping_cost", "fees_taxes", "commission", "required_capital", "actual_revenue", "actual_cost"}
STOP_WORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "your", "you",
    "find", "search", "research", "please", "need", "want", "looking", "online",
    "business", "opportunity", "opportunities", "available", "legitimate", "realistic",
    "tafuta", "nitafutie", "na", "ya", "za", "kwa", "hii", "kuhusu", "fursa",
    "kazi", "wateja", "biashara", "ambazo", "wanahitaji", "mtandaoni",
}


class BrokerResearchRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=500)
    opportunity_type: OpportunityType | None = None
    max_results: int = Field(default=15, ge=1, le=25)
    prepare_workflow: bool = True
    offer: str | None = Field(default=None, max_length=800)


class BrokerOpportunityCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    opportunity_type: OpportunityType = "GENERAL"
    organization: str | None = Field(default=None, max_length=255)
    summary: str = Field(default="", max_length=6000)
    source_name: str = Field(min_length=2, max_length=120)
    source_url: str = Field(min_length=8, max_length=2000)
    currency: str | None = Field(default=None, max_length=12)
    selling_price: float | None = Field(default=None, ge=0)
    supplier_cost: float | None = Field(default=None, ge=0)
    shipping_cost: float | None = Field(default=None, ge=0)
    fees_taxes: float | None = Field(default=None, ge=0)
    commission: float | None = Field(default=None, ge=0)
    required_capital: float | None = Field(default=None, ge=0)


class OutreachRequest(BaseModel):
    offer: str | None = Field(default=None, max_length=800)
    follow_up_days: int = Field(default=3, ge=1, le=90)


class OpportunityUpdate(BaseModel):
    status: Literal["UNVERIFIED", "RESEARCHED", "SHORTLISTED", "CONTACT_DRAFTED", "CONTACTED", "FOLLOW_UP_DUE", "WON", "LOST"] | None = None
    currency: str | None = Field(default=None, max_length=12)
    selling_price: float | None = Field(default=None, ge=0)
    supplier_cost: float | None = Field(default=None, ge=0)
    shipping_cost: float | None = Field(default=None, ge=0)
    fees_taxes: float | None = Field(default=None, ge=0)
    commission: float | None = Field(default=None, ge=0)
    required_capital: float | None = Field(default=None, ge=0)
    actual_revenue: float | None = Field(default=None, ge=0)
    actual_cost: float | None = Field(default=None, ge=0)


def infer_opportunity_type(goal: str) -> OpportunityType:
    value = str(goal or "").casefold()
    if any(term in value for term in ("supplier", "suppliers", "manufacturer", "wholesale", "wasambazaji", "kiwanda", "muuzaji", "sourcing")):
        return "SUPPLIER"
    if any(term in value for term in ("affiliate", "referral", "commission program", "ushirika wa tume")):
        return "AFFILIATE"
    if any(term in value for term in ("client", "clients", "customer", "customers", "buyer", "buyers", "lead", "leads", "wateja", "biashara zinazohitaji", "businesses that need")):
        return "CLIENT_LEAD"
    if any(term in value for term in ("product", "products", "bidhaa", "sell this", "selling price")):
        return "PRODUCT"
    if any(term in value for term in ("job", "jobs", "remote work", "freelance", "employment", "ajira", "kazi", "online income", "earn online", "mapato mtandaoni", "graphic design work")):
        return "REMOTE_WORK"
    return "REMOTE_WORK" if any(term in value for term in ("income", "earning", "money", "pesa", "mapato", "opportunity", "opportunities", "fursa")) else "GENERAL"


def is_business_broker_request(goal: str) -> bool:
    value = str(goal or "").casefold()
    return any(term in value for term in (
        "business opportunity", "business opportunities", "business broker", "client lead",
        "client leads", "potential clients", "find clients", "find customers", "supplier",
        "suppliers", "manufacturer", "wholesale", "affiliate", "referral program",
        "fursa", "wateja", "wasambazaji", "bidhaa", "online income", "earn online",
        "mapato mtandaoni", "businesses that need", "customers for", "prospects",
    ))


def _https_url(value: str) -> bool:
    try:
        parsed = urlparse(str(value or "").strip())
        return parsed.scheme.lower() == "https" and bool(parsed.netloc) and not parsed.username and not parsed.password
    except (TypeError, ValueError):
        return False


def _score(goal: str, title: str, summary: str, organization: str | None, source_url: str) -> tuple[int, str]:
    tokens = {
        token for token in re.findall(r"[a-z0-9]{3,}", goal.casefold())
        if token not in STOP_WORDS
    }
    haystack = f"{title} {summary} {organization or ''}".casefold()
    matched = sorted(token for token in tokens if token in haystack)
    # This is a transparent heuristic, not an AI prediction or a guarantee of profit.
    score = min(72, 28 + len(matched) * 8)
    if _https_url(source_url):
        score += 12
    if len(summary.strip()) >= 80:
        score += 8
    if organization and organization.strip():
        score += 8
    score = min(100, score)
    rationale = (
        f"Rule-based fit score {score}/100: {len(matched)} goal term(s) matched"
        + (f" ({', '.join(matched[:8])})" if matched else "")
        + "; HTTPS source link " + ("present" if _https_url(source_url) else "missing")
        + f"; descriptive evidence {'present' if len(summary.strip()) >= 80 else 'limited'}."
    )
    return score, rationale


def _money(value: float | None) -> float | None:
    return round(float(value), 2) if value is not None else None


def _serialize(row: BusinessOpportunity) -> dict[str, Any]:
    gross = None
    gross_percent = None
    net = None
    if row.selling_price is not None and row.supplier_cost is not None:
        gross = row.selling_price - row.supplier_cost
        if row.selling_price > 0:
            gross_percent = gross / row.selling_price * 100
    if all(value is not None for value in (row.selling_price, row.supplier_cost, row.shipping_cost, row.fees_taxes)):
        net = row.selling_price - row.supplier_cost - row.shipping_cost - row.fees_taxes
        if row.commission is not None:
            net += row.commission
    try:
        evidence = json.loads(row.evidence or "{}")
    except (TypeError, ValueError):
        evidence = {"parse_warning": "Stored evidence could not be decoded."}
    return {
        "id": row.id,
        "opportunity_type": row.opportunity_type,
        "title": row.title,
        "organization": row.organization,
        "summary": row.summary,
        "source_name": row.source_name,
        "source_url": row.source_url,
        "source_checked_at": row.source_checked_at.isoformat() if row.source_checked_at else None,
        "evidence": evidence,
        "status": row.status,
        "fit_score": row.fit_score,
        "fit_rationale": row.fit_rationale,
        "risk_level": row.risk_level,
        "currency": row.currency,
        "selling_price": _money(row.selling_price),
        "supplier_cost": _money(row.supplier_cost),
        "shipping_cost": _money(row.shipping_cost),
        "fees_taxes": _money(row.fees_taxes),
        "commission": _money(row.commission),
        "required_capital": _money(row.required_capital),
        "gross_margin_amount": _money(gross),
        "gross_margin_percent": round(gross_percent, 2) if gross_percent is not None else None,
        "net_margin_amount": _money(net),
        "actual_revenue": _money(row.actual_revenue),
        "actual_cost": _money(row.actual_cost),
        "outreach_subject": row.outreach_subject,
        "outreach_body": row.outreach_body,
        "follow_up_at": row.follow_up_at.isoformat() if row.follow_up_at else None,
        "follow_up_task_id": row.follow_up_task_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def _fetch_broker_sources(goal: str, opportunity_type: OpportunityType, limit: int) -> dict[str, Any]:
    """Use the existing public job APIs or configured SearXNG; never invent fallbacks."""
    if opportunity_type == "REMOTE_WORK":
        from .jobs import research_public_jobs

        query = _remote_query(goal)
        result = await research_public_jobs(query, limit=limit)
        items = []
        for job in result.get("results") or []:
            items.append({
                "title": job.get("title") or "Untitled public job",
                "organization": job.get("company"),
                "summary": " ".join(part for part in [
                    str(job.get("description") or ""),
                    "Location: " + str(job.get("location") or "") if job.get("location") else "",
                    "Tags: " + ", ".join(job.get("tags") or []) if job.get("tags") else "",
                ] if part).strip(),
                "source_name": job.get("source") or "Public job feed",
                "source_url": job.get("url") or "",
                "evidence": {
                    "published_at": job.get("published_at"),
                    "location": job.get("location"),
                    "tags": job.get("tags") or [],
                    "feed_record_id": job.get("id"),
                },
            })
        return {
            "status": result.get("status", "FAILED"),
            "query": query,
            "source_names": result.get("sources") or [],
            "source_warnings": result.get("source_warnings") or [],
            "items": items,
            "note": result.get("note"),
        }

    from ..config import settings
    if not settings.searxng_url.strip():
        return {
            "status": "NOT_CONNECTED",
            "query": goal,
            "source_names": [],
            "source_warnings": [],
            "items": [],
            "message": "SearXNG haijaunganishwa. Hakuna supplier/client wa kubuniwa; weka SEARXNG_URL au chagua remote-work research inayotumia public job feeds.",
        }

    from .tools import _search_searxng
    query = _build_search_query(goal, opportunity_type)
    result = await _search_searxng(query)
    items = []
    for found in (result.get("results") or [])[:limit]:
        url = str(found.get("url") or "").strip()
        if not _https_url(url):
            continue
        items.append({
            "title": str(found.get("title") or "Untitled search result")[:255],
            "organization": None,
            "summary": str(found.get("content") or "")[:5000],
            "source_name": str(found.get("engine") or "SearXNG")[:120],
            "source_url": url,
            "evidence": {"search_query": query, "engine": found.get("engine"), "result_excerpt": str(found.get("content") or "")[:1500]},
        })
    return {
        "status": result.get("status", "FAILED"),
        "query": query,
        "source_names": sorted({str(item["source_name"]) for item in items}),
        "source_warnings": [],
        "items": items,
        "message": result.get("message"),
    }


def _remote_query(goal: str) -> str:
    value = str(goal or "").strip()
    value = re.sub(r"^(?:tafuta|nitafutie|tafutia|find(?: me)?|search(?: for)?|research|look for)\s+", "", value, flags=re.IGNORECASE)
    niche_patterns = (
        r"graphic\s+design(?:er|ers)?", r"web\s+design(?:er|ers)?", r"web\s+developer",
        r"data\s+annotation", r"virtual\s+assistant", r"customer\s+support",
        r"print(?:ing)?", r"garden(?:ing)?", r"cleaning", r"painting",
    )
    matched = []
    for pattern in niche_patterns:
        found = re.search(pattern, value, flags=re.IGNORECASE)
        if found:
            matched.append(found.group(0))
    if matched:
        return " ".join(dict.fromkeys(matched))[:180]
    meaningful = [
        token for token in re.findall(r"[A-Za-z0-9+#.-]+", value)
        if len(token) > 2 and token.casefold() not in STOP_WORDS
    ]
    query = " ".join(meaningful[:6])
    return query or "graphic designer remote"


def _build_search_query(goal: str, opportunity_type: OpportunityType) -> str:
    prefixes = {
        "CLIENT_LEAD": "potential customers or businesses requesting services",
        "SUPPLIER": "suppliers and manufacturers; compare public catalogues and trade terms",
        "PRODUCT": "product listings, current published prices and source pages",
        "AFFILIATE": "official affiliate or referral program terms and eligibility",
        "GENERAL": "legitimate public business opportunities and official source pages",
        "REMOTE_WORK": "remote work opportunities",
    }
    return f"{prefixes[opportunity_type]}: {goal}"[:450]


def _draft_outreach(row: BusinessOpportunity, offer: str | None) -> tuple[str, str]:
    company = (row.organization or "the relevant team").strip()
    subject_title = row.title[:120]
    if row.opportunity_type == "SUPPLIER":
        subject = f"Supplier information request: {subject_title}"
        body = (
            f"Hello {company} team,\n\n"
            f"I am researching possible supply options related to {subject_title}. Could you confirm your current catalogue, "
            "unit price and currency, minimum order quantity, delivery options and cost to Tanzania, lead time, applicable taxes/fees, "
            "sample policy, and the business documents available for due diligence?\n\n"
            "This is an information request only, not an order or a commitment to purchase.\n\n"
            "Kind regards,\nBoss Ferisi"
        )
    elif row.opportunity_type == "REMOTE_WORK":
        subject = f"Question about opportunity: {subject_title}"
        body = (
            f"Hello {company} hiring team,\n\n"
            f"I found the public listing for {subject_title} through {row.source_name}. Could you confirm whether the role is still open, "
            "whether applicants based in Tanzania are eligible, and the official application steps? I will review the stated requirements "
            "and provide accurate information about my relevant skills in any application.\n\n"
            "Kind regards,\nBoss Ferisi"
        )
    else:
        offered = (offer or "[specific service you want to offer]").strip()
        subject = f"Question about {subject_title}"
        body = (
            f"Hello {company} team,\n\n"
            f"I found your public listing about {subject_title} ({row.source_url}). I am checking whether you are currently open to support with "
            f"{offered}. If this is relevant, I can prepare a short scope and quotation after learning your requirements, timeline and budget. "
            "I have not assumed any of those details.\n\n"
            "Kind regards,\nBoss Ferisi"
        )
    return subject, body


def _prepare_workflow(
    db: Session,
    row: BusinessOpportunity,
    user_id: int,
    offer: str | None = None,
    follow_up_days: int = 3,
) -> dict[str, Any]:
    if not row.outreach_body:
        row.outreach_subject, row.outreach_body = _draft_outreach(row, offer)
        if row.status in {"RESEARCHED", "UNVERIFIED"}:
            row.status = "CONTACT_DRAFTED"
    due_at = datetime.utcnow() + timedelta(days=follow_up_days)
    existing = db.query(Task).filter(
        Task.user_id == user_id,
        Task.source == "business_broker",
        Task.requested_by == f"business_broker:opportunity:{row.id}",
    ).order_by(Task.id.desc()).first()
    if existing is None:
        task = Task(
            user_id=user_id,
            title=f"Follow up: {row.title}"[:255],
            description=json.dumps({
                "opportunity_id": row.id,
                "source_url": row.source_url,
                "next_action": "Review source and draft, verify details, then contact manually if appropriate.",
                "outreach_is_draft_only": True,
            }, ensure_ascii=False),
            status="PENDING",
            priority="NORMAL",
            deadline=due_at,
            agent="research",
            source="business_broker",
            requested_by=f"business_broker:opportunity:{row.id}",
        )
        db.add(task)
        db.flush()
        follow_up_task_id = task.id
    else:
        existing.deadline = existing.deadline or due_at
        follow_up_task_id = existing.id
    row.follow_up_at = row.follow_up_at or due_at
    row.follow_up_task_id = follow_up_task_id
    return {
        "outreach_prepared": True,
        "message_sent": False,
        "follow_up_task_id": follow_up_task_id,
        "follow_up_at": row.follow_up_at.isoformat(),
    }


async def research_business_opportunities(
    db: Session,
    user_id: int,
    goal: str,
    opportunity_type: OpportunityType | None = None,
    max_results: int = 15,
    prepare_workflow: bool = True,
    offer: str | None = None,
) -> dict[str, Any]:
    chosen_type: OpportunityType = opportunity_type or infer_opportunity_type(goal)
    sources = await _fetch_broker_sources(goal, chosen_type, max(1, min(int(max_results), 25)))
    status = str(sources.get("status") or "FAILED").upper()
    if status not in {"COMPLETED", "NO_RESULTS"}:
        return {
            "status": status,
            "goal": goal,
            "opportunity_type": chosen_type,
            "query": sources.get("query"),
            "source_names": sources.get("source_names") or [],
            "source_warnings": sources.get("source_warnings") or [],
            "saved_count": 0,
            "new_count": 0,
            "updated_count": 0,
            "opportunities": [],
            "workflow": [],
            "message": sources.get("message") or "Search was not completed; no opportunity was invented or saved.",
        }

    now = datetime.utcnow()
    saved_rows: list[BusinessOpportunity] = []
    new_count = 0
    updated_count = 0
    for item in sources.get("items") or []:
        title = str(item.get("title") or "").strip()[:255]
        source_url = str(item.get("source_url") or "").strip()
        if not title or not _https_url(source_url):
            continue
        source_name = str(item.get("source_name") or "Unknown public source").strip()[:120]
        summary = str(item.get("summary") or "").strip()[:6000]
        organization = str(item.get("organization") or "").strip()[:255] or None
        score, rationale = _score(goal, title, summary, organization, source_url)
        existing = db.query(BusinessOpportunity).filter(
            BusinessOpportunity.user_id == user_id,
            BusinessOpportunity.source_url == source_url,
        ).first()
        evidence = {
            "retrieval_status": "source_response_received",
            "source_item": item.get("evidence") or {},
            "research_query": sources.get("query"),
            "source_warnings": sources.get("source_warnings") or [],
            "identity_verified": False,
            "pricing_verified": False,
        }
        if existing:
            existing.title = title
            existing.organization = organization or existing.organization
            existing.summary = summary or existing.summary
            existing.source_name = source_name
            existing.source_checked_at = now
            existing.evidence = json.dumps(evidence, ensure_ascii=False, default=str)
            existing.fit_score = score
            existing.fit_rationale = rationale
            if existing.status in {"UNVERIFIED", "RESEARCHED"}:
                existing.status = "RESEARCHED"
            row = existing
            updated_count += 1
        else:
            row = BusinessOpportunity(
                user_id=user_id,
                opportunity_type=chosen_type,
                title=title,
                organization=organization,
                summary=summary,
                source_name=source_name,
                source_url=source_url,
                source_checked_at=now,
                evidence=json.dumps(evidence, ensure_ascii=False, default=str),
                status="RESEARCHED",
                fit_score=score,
                fit_rationale=rationale,
                risk_level="HIGH" if chosen_type in {"SUPPLIER", "PRODUCT", "AFFILIATE"} else "MEDIUM",
            )
            db.add(row)
            db.flush()
            new_count += 1
        saved_rows.append(row)

    saved_rows.sort(key=lambda row: (row.fit_score, row.source_checked_at or now), reverse=True)
    workflow: list[dict[str, Any]] = []
    if prepare_workflow:
        for row in saved_rows[:3]:
            workflow.append({
                "opportunity_id": row.id,
                **_prepare_workflow(db, row, user_id, offer=offer),
            })
    # Write a compact, owner-scoped Memory Core index so later missions can recall the last
    # research batch without copying sensitive contact data into memory.
    if saved_rows:
        memory_key = "business_broker:last_research:" + chosen_type.lower()
        memory_context = {
            "goal": goal[:500],
            "opportunity_type": chosen_type,
            "checked_at": now.isoformat(),
            "source_names": sources.get("source_names") or [],
            "opportunity_ids": [row.id for row in saved_rows[:25]],
            "opportunities": [
                {
                    "id": row.id,
                    "title": row.title,
                    "source_url": row.source_url,
                    "fit_score": row.fit_score,
                    "status": row.status,
                }
                for row in saved_rows[:10]
            ],
            "warning": "Search evidence does not verify publisher identity, current availability, or guaranteed profit.",
        }
        remembered = db.query(Memory).filter(
            Memory.user_id == user_id,
            Memory.key == memory_key,
        ).order_by(Memory.id.desc()).first()
        if remembered:
            remembered.value = json.dumps(memory_context, ensure_ascii=False, default=str)
        else:
            db.add(Memory(
                user_id=user_id,
                key=memory_key,
                value=json.dumps(memory_context, ensure_ascii=False, default=str),
            ))

    db.add(ActivityLog(
        user_id=user_id,
        action="BUSINESS_BROKER_RESEARCH",
        details=f"type={chosen_type}; saved={len(saved_rows)}; new={new_count}; updated={updated_count}; query_length={len(goal)}",
    ))
    db.commit()
    for row in saved_rows:
        db.refresh(row)
    final_status = "COMPLETED" if saved_rows else "NO_RESULTS"
    return {
        "status": final_status,
        "goal": goal,
        "opportunity_type": chosen_type,
        "query": sources.get("query"),
        "source_names": sources.get("source_names") or [],
        "source_warnings": sources.get("source_warnings") or [],
        "saved_count": len(saved_rows),
        "new_count": new_count,
        "updated_count": updated_count,
        "opportunities": [_serialize(row) for row in saved_rows],
        "workflow": workflow,
        "message": (
            "Public source results were stored. Publisher identity, current availability, eligibility, prices and terms remain unverified until checked at the source."
            if saved_rows else
            "The source query completed but returned no usable HTTPS records. Nothing was invented or saved."
        ),
    }


@router.get("/status")
def broker_status(current_user=Depends(get_current_user)) -> dict[str, Any]:
    from ..config import settings

    return {
        "status": "AVAILABLE",
        "owner_scoped_pipeline": True,
        "public_job_feeds": ["RemoteOK", "Remotive"],
        "business_supplier_search": "CONNECTED" if settings.searxng_url.strip() else "NOT_CONNECTED",
        "automatic_outreach": False,
        "payments_and_orders": False,
        "message": "Research can store source evidence, prepare drafts and create follow-up tasks. It does not send outreach, place orders or guarantee profit.",
    }


@router.post("/research")
async def broker_research(
    payload: BrokerResearchRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return await research_business_opportunities(
        db=db,
        user_id=current_user.id,
        goal=payload.goal,
        opportunity_type=payload.opportunity_type,
        max_results=payload.max_results,
        prepare_workflow=payload.prepare_workflow,
        offer=payload.offer,
    )


@router.get("/opportunities")
def list_opportunities(
    opportunity_type: OpportunityType | None = None,
    status: str | None = None,
    limit: int = 50,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    query = db.query(BusinessOpportunity).filter(BusinessOpportunity.user_id == current_user.id)
    if opportunity_type:
        query = query.filter(BusinessOpportunity.opportunity_type == opportunity_type)
    if status:
        normalized = status.strip().upper()
        if normalized not in ALLOWED_STATUSES:
            raise HTTPException(status_code=400, detail="Unsupported opportunity status.")
        query = query.filter(BusinessOpportunity.status == normalized)
    rows = query.order_by(BusinessOpportunity.fit_score.desc(), BusinessOpportunity.id.desc()).limit(max(1, min(limit, 100))).all()
    return [_serialize(row) for row in rows]


@router.post("/opportunities")
def create_opportunity(
    payload: BrokerOpportunityCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not _https_url(payload.source_url):
        raise HTTPException(status_code=422, detail="source_url must be an HTTPS URL. Owner-submitted entries are marked UNVERIFIED until checked.")
    row = BusinessOpportunity(
        user_id=current_user.id,
        opportunity_type=payload.opportunity_type,
        title=payload.title.strip(),
        organization=payload.organization.strip()[:255] if payload.organization else None,
        summary=payload.summary.strip(),
        source_name=payload.source_name.strip(),
        source_url=payload.source_url.strip(),
        source_checked_at=None,
        evidence=json.dumps({"retrieval_status": "owner_submitted_unverified", "identity_verified": False, "pricing_verified": False}, ensure_ascii=False),
        status="UNVERIFIED",
        risk_level="HIGH" if payload.opportunity_type in {"SUPPLIER", "PRODUCT", "AFFILIATE"} else "MEDIUM",
        currency=payload.currency.strip().upper()[:12] if payload.currency else None,
        **{field: getattr(payload, field) for field in MONEY_FIELDS if field not in {"actual_revenue", "actual_cost"}},
    )
    row.fit_score = 35
    row.fit_rationale = "Owner-submitted record; fit is provisional until matched to a specific goal and the source is checked."
    db.add(row)
    db.add(ActivityLog(user_id=current_user.id, action="BUSINESS_OPPORTUNITY_CREATED", details="owner_submitted_unverified"))
    db.commit()
    db.refresh(row)
    return _serialize(row)


@router.get("/opportunities/{opportunity_id}")
def get_opportunity(
    opportunity_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = db.query(BusinessOpportunity).filter(
        BusinessOpportunity.id == opportunity_id,
        BusinessOpportunity.user_id == current_user.id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Opportunity not found.")
    return _serialize(row)


@router.post("/opportunities/{opportunity_id}/prepare-outreach")
def prepare_opportunity_outreach(
    opportunity_id: int,
    payload: OutreachRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = db.query(BusinessOpportunity).filter(
        BusinessOpportunity.id == opportunity_id,
        BusinessOpportunity.user_id == current_user.id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Opportunity not found.")
    workflow = _prepare_workflow(db, row, current_user.id, payload.offer, payload.follow_up_days)
    db.add(ActivityLog(
        user_id=current_user.id,
        action="BUSINESS_OUTREACH_DRAFT_PREPARED",
        details=f"opportunity_id={row.id}; message_sent=false; follow_up_task_id={workflow['follow_up_task_id']}",
    ))
    db.commit()
    db.refresh(row)
    return {
        "status": "COMPLETED",
        "opportunity": _serialize(row),
        "workflow": workflow,
        "message": "Draft saved. No email, message, order or contract was sent or accepted.",
    }


@router.patch("/opportunities/{opportunity_id}")
def update_opportunity(
    opportunity_id: int,
    payload: OpportunityUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = db.query(BusinessOpportunity).filter(
        BusinessOpportunity.id == opportunity_id,
        BusinessOpportunity.user_id == current_user.id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Opportunity not found.")
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        if field in MONEY_FIELDS and value is not None and (not isfinite(float(value)) or float(value) < 0):
            raise HTTPException(status_code=422, detail=f"{field} must be a finite non-negative number.")
        if field == "currency" and value:
            value = value.strip().upper()[:12]
        setattr(row, field, value)
    db.add(ActivityLog(
        user_id=current_user.id,
        action="BUSINESS_OPPORTUNITY_UPDATED",
        details=f"opportunity_id={row.id}; fields={','.join(sorted(changes))}",
    ))
    db.commit()
    db.refresh(row)
    return _serialize(row)
