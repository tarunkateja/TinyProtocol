from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

# Stored per chat; trimmed so the DynamoDB item stays far below the 400KB cap.
MAX_STORED_MESSAGES = 30
TITLE_LEN = 60


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)
    at: Optional[datetime] = None


class Chat(BaseModel):
    id: str
    baby_id: str
    title: str
    created_by: str  # user name, for "asked by Dad" in the shared list
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessage] = []


class ChatMeta(BaseModel):
    """List view — no message bodies."""

    id: str
    baby_id: str
    title: str
    created_by: str
    updated_at: datetime


class ChatMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    # "community_only" restricts the assistant to the GA-1 support-group corpus:
    # no baby logs, and no answering from the model's own knowledge.
    mode: Literal["auto", "community_only"] = "auto"


class ChatReply(BaseModel):
    chat: Chat
    reply: str
    # What the tools actually returned, built from tool output rather than from
    # the model's prose. Lets the app show the underlying data beside the answer
    # so a fabricated number is visible instead of merely unlikely.
    sources: list[dict] = []
