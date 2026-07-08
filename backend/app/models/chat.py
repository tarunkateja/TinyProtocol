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


class ChatReply(BaseModel):
    chat: Chat
    reply: str
