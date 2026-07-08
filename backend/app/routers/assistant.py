from datetime import datetime, time, timezone

import openai
from fastapi import APIRouter, Depends, HTTPException
from ulid import ULID

from app.auth import CurrentUser, get_current_user
from app.models.chat import (
    MAX_STORED_MESSAGES,
    TITLE_LEN,
    Chat,
    ChatMessage,
    ChatMessageIn,
    ChatMeta,
    ChatReply,
)
from app.repo import families, family_items, keys, users
from app.routers.deps import get_baby_or_404
from app.services import assistant

router = APIRouter(tags=["assistant"])


def _require_configured() -> None:
    if not assistant.is_configured():
        raise HTTPException(
            503, "The assistant isn't set up yet (missing OpenAI API key)"
        )


def _load_chat(user: CurrentUser, chat_id: str) -> Chat:
    item = family_items.get(user.family_id, keys.chat_sk(chat_id))
    if item is None:
        raise HTTPException(404, "Chat not found")
    return Chat.model_validate(item)


def _save_chat(user: CurrentUser, chat: Chat) -> None:
    family_items.put(
        user.family_id, keys.chat_sk(chat.id), chat.model_dump(mode="json")
    )


def _run_reply(user: CurrentUser, chat: Chat, content: str) -> ChatReply:
    baby = get_baby_or_404(user, chat.baby_id)
    fam = families.get_family(user.family_id)
    profile = users.get_user(user.email)
    parent_name = profile["name"] if profile else "a parent"

    now = datetime.now(timezone.utc)
    chat.messages.append(ChatMessage(role="user", content=content, at=now))
    history = [{"role": m.role, "content": m.content} for m in chat.messages]

    day_start = time.fromisoformat((fam or {}).get("day_start") or "00:00")
    try:
        reply = assistant.chat(
            baby, fam["timezone"] if fam else "UTC", parent_name, history,
            day_start=day_start, family_id=user.family_id,
        )
    except openai.APIStatusError as e:
        raise HTTPException(502, f"Assistant is unavailable right now ({e.status_code})")
    except openai.APIConnectionError:
        raise HTTPException(502, "Assistant is unavailable right now (network)")

    chat.messages.append(
        ChatMessage(role="assistant", content=reply or "…", at=datetime.now(timezone.utc))
    )
    chat.messages = chat.messages[-MAX_STORED_MESSAGES:]
    chat.updated_at = datetime.now(timezone.utc)
    _save_chat(user, chat)
    return ChatReply(chat=chat, reply=reply)


@router.get("/assistant/chats", response_model=list[ChatMeta])
def list_chats(user: CurrentUser = Depends(get_current_user)):
    items = family_items.list_by_prefix(user.family_id, "CHAT#")
    metas = [ChatMeta.model_validate(i) for i in items]
    return sorted(metas, key=lambda c: c.updated_at, reverse=True)


@router.get("/assistant/chats/{chat_id}", response_model=Chat)
def get_chat(chat_id: str, user: CurrentUser = Depends(get_current_user)):
    return _load_chat(user, chat_id)


@router.delete("/assistant/chats/{chat_id}", status_code=204)
def delete_chat(chat_id: str, user: CurrentUser = Depends(get_current_user)):
    _load_chat(user, chat_id)
    family_items.delete(user.family_id, keys.chat_sk(chat_id))


@router.post(
    "/babies/{baby_id}/assistant/chats", response_model=ChatReply, status_code=201
)
def create_chat(
    baby_id: str, body: ChatMessageIn, user: CurrentUser = Depends(get_current_user)
):
    """Start a new shared chat with a first question."""
    _require_configured()
    get_baby_or_404(user, baby_id)
    profile = users.get_user(user.email)
    now = datetime.now(timezone.utc)
    title = body.content.strip().replace("\n", " ")
    chat = Chat(
        id=str(ULID()),
        baby_id=baby_id,
        title=title[:TITLE_LEN] + ("…" if len(title) > TITLE_LEN else ""),
        created_by=profile["name"] if profile else "parent",
        created_at=now,
        updated_at=now,
        messages=[],
    )
    return _run_reply(user, chat, body.content)


@router.post("/assistant/chats/{chat_id}/messages", response_model=ChatReply)
def send_message(
    chat_id: str, body: ChatMessageIn, user: CurrentUser = Depends(get_current_user)
):
    _require_configured()
    chat = _load_chat(user, chat_id)
    return _run_reply(user, chat, body.content)
