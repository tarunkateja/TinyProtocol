from typing import Literal

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from app.auth import CurrentUser, get_current_user
from app.repo import families, users
from app.routers.deps import get_baby_or_404
from app.services import assistant

router = APIRouter(tags=["assistant"])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatIn(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=60)

    @model_validator(mode="after")
    def _last_is_user(self) -> "ChatIn":
        if self.messages[-1].role != "user":
            raise ValueError("The last message must be from the user")
        return self


class ChatOut(BaseModel):
    reply: str


@router.post("/babies/{baby_id}/assistant/chat", response_model=ChatOut)
def assistant_chat(
    baby_id: str, body: ChatIn, user: CurrentUser = Depends(get_current_user)
):
    if not assistant.is_configured():
        raise HTTPException(
            503, "The assistant isn't set up yet (missing Anthropic API key)"
        )
    baby = get_baby_or_404(user, baby_id)
    fam = families.get_family(user.family_id)
    profile = users.get_user(user.email)
    parent_name = profile["name"] if profile else "a parent"

    try:
        reply = assistant.chat(
            baby,
            fam["timezone"] if fam else "UTC",
            parent_name,
            [m.model_dump() for m in body.messages],
        )
    except anthropic.APIStatusError as e:
        raise HTTPException(502, f"Assistant is unavailable right now ({e.status_code})")
    except anthropic.APIConnectionError:
        raise HTTPException(502, "Assistant is unavailable right now (network)")
    return ChatOut(reply=reply)
