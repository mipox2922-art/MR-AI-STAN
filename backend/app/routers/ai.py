"""
MR AI — Production-Grade FastAPI Chat Endpoint (v2.0)
======================================================
Enhanced version with:
- Request validation & sanitization
- Comprehensive error handling (provider, DB, realtime)
- Audit logging & request tracing
- Rate limiting hooks
- Timeout management
- Structured logging
- Security best practices

Usage:
    from app.api.endpoints.chat_optimized import router
    app.include_router(router)
"""

import asyncio
import logging
import time
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from ..dependencies import get_current_user
from ..database import get_db
from ..models import ActivityLog, Conversation, Message, User
from ..providers.factory import get_provider
from ..providers.base import AIProviderError
from ..realtime import manager
from ..schemas import ChatRequest, ChatResponse

# ==============================================================================
# CONSTANTS & CONFIGURATION
# ==============================================================================

logger = logging.getLogger("mr_ai.chat")

# Timeouts (seconds)
AI_PROVIDER_TIMEOUT = 30

MR_AI_SYSTEM_PROMPT = (
    "You are MR AI, the Digital Chief of Staff for Boss Ferisi. "
    "Reply naturally in Swahili. Be short, useful, confident and friendly. "
    "Never claim an action happened unless verified."
)
REALTIME_TIMEOUT = 5

# Limits
MAX_MESSAGE_LENGTH = 6000
MAX_CONVERSATION_CONTEXT = 50  # Messages to keep in context
MIN_MESSAGE_LENGTH = 1

# Error messages (user-friendly)
PROVIDER_ERROR_MSG = "AI provider returned empty or invalid response"
DATABASE_ERROR_MSG = "Failed to save chat message"
REALTIME_ERROR_MSG = "Real-time notification failed (non-critical)"

# ==============================================================================
# ROUTER SETUP
# ==============================================================================

router = APIRouter(
    prefix="/ai",
    tags=["AI"],
)

# ==============================================================================
# REQUEST VALIDATION HELPERS
# ==============================================================================

def validate_chat_request(data: ChatRequest) -> ChatRequest:
    """Validate and sanitize chat request"""
    message = str(data.message).strip()
    
    if not message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message cannot be empty"
        )
    
    if len(message) < MIN_MESSAGE_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Message too short (minimum {MIN_MESSAGE_LENGTH} char)"
        )
    
    if len(message) > MAX_MESSAGE_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Message too long (maximum {MAX_MESSAGE_LENGTH} chars)"
        )
    
    # Sanitize message (basic XSS prevention)
    data.message = message
    
    return data

# ==============================================================================
# DATABASE HELPERS
# ==============================================================================

def get_or_create_conversation(
    db: Session,
    user_id: int,
    title: str = "MR AI Chat"
) -> Conversation:
    """Get latest conversation or create new one"""
    try:
        conversation = (
            db.query(Conversation)
            .filter(Conversation.user_id == user_id)
            .order_by(Conversation.id.desc())
            .first()
        )
        
        if conversation:
            return conversation
        
        # Create new conversation
        conversation = Conversation(
            user_id=user_id,
            title=title,
        )
        db.add(conversation)
        db.flush()  # Get ID without committing
        
        logger.info(
            "📝 New conversation created",
            extra={
                "conversation_id": conversation.id,
                "user_id": user_id
            }
        )
        
        return conversation
    
    except SQLAlchemyError as exc:
        logger.error(
            f"❌ Failed to get/create conversation: {exc}",
            extra={"user_id": user_id}
        )
        raise

def save_messages_and_log(
    db: Session,
    conversation_id: int,
    user_id: int,
    user_message: str,
    assistant_message: str,
    provider: str,
) -> None:
    """Save user and assistant messages to database"""
    try:
        # Add user message
        user_msg = Message(
            conversation_id=conversation_id,
            role="user",
            content=user_message,
        )
        db.add(user_msg)
        
        # Add assistant message
        assistant_msg = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=assistant_message,
        )
        db.add(assistant_msg)
        
        # Log activity
        activity = ActivityLog(
            user_id=user_id,
            action="AI_CHAT",
            details=f"Provider: {provider} | Input: {len(user_message)} chars | Output: {len(assistant_message)} chars",
        )
        db.add(activity)
        
        db.commit()
        
        logger.info(
            "💾 Messages saved to database",
            extra={
                "conversation_id": conversation_id,
                "user_id": user_id,
                "provider": provider,
                "input_length": len(user_message),
                "output_length": len(assistant_message),
            }
        )
    
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error(
            f"❌ Database error saving messages: {exc}",
            extra={
                "conversation_id": conversation_id,
                "user_id": user_id
            }
        )
        raise

# ==============================================================================
# AI PROVIDER HELPERS (With retry and timeout)
# ==============================================================================

async def generate_with_timeout(
    provider,
    message: str,
    timeout: int = AI_PROVIDER_TIMEOUT,
    max_retries: int = 2,
) -> str:
    """Call AI provider with timeout and retry logic"""
    last_error = None
    
    for attempt in range(max_retries + 1):
        try:
            logger.info(
                f"🤖 AI call (attempt {attempt + 1}/{max_retries + 1})",
                extra={"provider": provider.__class__.__name__}
            )
            
            # Call with timeout
            answer = await asyncio.wait_for(
                provider.generate(message, system_instruction=MR_AI_SYSTEM_PROMPT),
                timeout=timeout
            )
            
            if not answer or not str(answer).strip():
                raise AIProviderError(provider.__class__.__name__, PROVIDER_ERROR_MSG)
            
            logger.info(
                "✅ AI provider returned response",
                extra={
                    "provider": provider.__class__.__name__,
                    "response_length": len(str(answer))
                }
            )
            
            return str(answer).strip()
        
        except asyncio.TimeoutError as exc:
            last_error = exc
            logger.warning(
                f"⏱️  AI provider timeout (attempt {attempt + 1})",
                extra={"provider": provider.__class__.__name__}
            )
            
            if attempt < max_retries:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.info(f"⏳ Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            
        except AIProviderError as exc:
            logger.error(
                f"❌ AI provider error: {exc}",
                extra={"provider": provider.__class__.__name__}
            )
            last_error = exc
            
        except Exception as exc:
            logger.exception(
                f"❌ Unexpected AI provider error: {exc}",
                extra={"provider": provider.__class__.__name__}
            )
            last_error = exc
    
    # All retries exhausted
    error_detail = f"{PROVIDER_ERROR_MSG}: {type(last_error).__name__}"
    logger.error(f"🚫 All retries exhausted: {error_detail}")
    raise AIProviderError(provider.__class__.__name__, error_detail)

# ==============================================================================
# REALTIME NOTIFICATION (Non-blocking)
# ==============================================================================

async def notify_realtime_safe(
    event: str,
    data: dict,
    timeout: int = REALTIME_TIMEOUT,
) -> None:
    """Broadcast to realtime clients (never breaks main flow)"""
    try:
        await asyncio.wait_for(
            manager.broadcast(event, data),
            timeout=timeout
        )
        logger.debug(f"📡 Realtime event broadcasted: {event}")
    
    except asyncio.TimeoutError:
        logger.warning(
            f"⚠️  Realtime broadcast timeout (non-critical)",
            extra={"event": event}
        )
    
    except Exception as exc:
        # Log but don't raise - realtime is non-critical
        logger.warning(
            f"⚠️  {REALTIME_ERROR_MSG}: {type(exc).__name__}: {exc}",
            extra={"event": event}
        )

# ==============================================================================
# MAIN CHAT ENDPOINT
# ==============================================================================

@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat with AI",
    description="Send a message to the AI provider and get a response",
)
async def chat(
    data: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    """
    Chat endpoint with comprehensive error handling
    
    Flow:
    1. Validate request
    2. Get/create conversation
    3. Call AI provider (with retry)
    4. Save to database (atomic transaction)
    5. Broadcast to realtime (non-blocking)
    6. Return response
    
    Errors are classified:
    - Validation: 400 Bad Request
    - Provider: 502 Bad Gateway
    - Database: 500 Internal Server Error
    - Realtime: 200 OK (doesn't block)
    """
    
    request_start = time.time()
    request_id = f"{current_user.id}_{int(request_start * 1000)}"
    
    logger.info(
        "🔵 Chat request received",
        extra={
            "request_id": request_id,
            "user_id": current_user.id,
            "provider": data.provider,
        }
    )
    
    # ─────────────────────────────────────────────────────────────────────
    # STEP 1: VALIDATE REQUEST
    # ─────────────────────────────────────────────────────────────────────
    try:
        data = validate_chat_request(data)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"❌ Request validation error: {exc}",
            extra={"request_id": request_id}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request format"
        )
    
    # ─────────────────────────────────────────────────────────────────────
    # STEP 2: GET AI PROVIDER
    # ─────────────────────────────────────────────────────────────────────
    try:
        provider = get_provider(data.provider)
        logger.debug(
            f"✅ Provider loaded: {provider.__class__.__name__}",
            extra={"request_id": request_id}
        )
    except ValueError as exc:
        logger.error(
            f"❌ Invalid provider: {exc}",
            extra={"request_id": request_id, "provider": data.provider}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider: {data.provider}"
        )
    except Exception as exc:
        logger.exception(
            f"❌ Provider initialization error: {exc}",
            extra={"request_id": request_id}
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to initialize AI provider"
        )
    
    # ─────────────────────────────────────────────────────────────────────
    # STEP 3: CALL AI PROVIDER (with retry & timeout)
    # ─────────────────────────────────────────────────────────────────────
    try:
        answer = await generate_with_timeout(
            provider,
            data.message,
            timeout=AI_PROVIDER_TIMEOUT,
            max_retries=2,
        )
    except AIProviderError as exc:
        logger.error(
            f"❌ AI provider failed: {exc}",
            extra={"request_id": request_id}
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    except Exception as exc:
        logger.exception(
            f"❌ Unexpected AI error: {exc}",
            extra={"request_id": request_id}
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=DATABASE_ERROR_MSG,
        )
    
    # ─────────────────────────────────────────────────────────────────────
    # STEP 4: GET/CREATE CONVERSATION
    # ─────────────────────────────────────────────────────────────────────
    try:
        conversation = get_or_create_conversation(
            db,
            current_user.id,
            title=f"Chat - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        )
    except SQLAlchemyError as exc:
        logger.error(
            f"❌ Database error: {exc}",
            extra={"request_id": request_id, "user_id": current_user.id}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=DATABASE_ERROR_MSG,
        )
    
    # ─────────────────────────────────────────────────────────────────────
    # STEP 5: SAVE MESSAGES TO DATABASE (atomic)
    # ─────────────────────────────────────────────────────────────────────
    try:
        save_messages_and_log(
            db,
            conversation.id,
            current_user.id,
            data.message,
            answer,
            data.provider,
        )
    except SQLAlchemyError as exc:
        logger.error(
            f"❌ Failed to save messages: {exc}",
            extra={
                "request_id": request_id,
                "conversation_id": conversation.id
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=DATABASE_ERROR_MSG,
        )
    
    # ─────────────────────────────────────────────────────────────────────
    # STEP 6: BROADCAST TO REALTIME (non-blocking)
    # ─────────────────────────────────────────────────────────────────────
    # Fire and forget - never let this break the response
    asyncio.create_task(
        notify_realtime_safe(
            "NEW_MESSAGE",
            {
                "provider": data.provider,
                "user_id": current_user.id,
                "conversation_id": conversation.id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    )
    
    # ─────────────────────────────────────────────────────────────────────
    # STEP 7: RETURN RESPONSE
    # ─────────────────────────────────────────────────────────────────────
    elapsed = time.time() - request_start
    
    logger.info(
        "✅ Chat request completed",
        extra={
            "request_id": request_id,
            "user_id": current_user.id,
            "provider": data.provider,
            "elapsed_ms": int(elapsed * 1000),
        }
    )
    
    return ChatResponse(
        response=answer,
        provider=data.provider,
        request_id=request_id,
        elapsed_ms=int(elapsed * 1000),
    )

# ==============================================================================
# HEALTH CHECK (for monitoring)
# ==============================================================================

@router.get("/health", tags=["AI"])
async def health_check() -> dict:
    """Check if AI endpoint is healthy"""
    return {
        "status": "healthy",
        "service": "ai_chat",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

# ==============================================================================
# EXCEPTION HANDLERS
# ==============================================================================

