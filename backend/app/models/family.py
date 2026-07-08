from datetime import datetime, time
from typing import Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.baby import BabyIn


def _validate_tz(tz: str) -> str:
    try:
        ZoneInfo(tz)
    except Exception:
        raise ValueError(f"Unknown IANA timezone: {tz!r}")
    return tz


def _validate_day_start(v: str) -> str:
    try:
        time.fromisoformat(v)
    except ValueError:
        raise ValueError("day_start must be HH:MM, e.g. 08:00")
    return v


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = Field(min_length=1)
    family_name: Optional[str] = None
    timezone: str = "America/New_York"
    # Optionally create the baby in the same call — one screen at signup.
    baby: Optional[BabyIn] = None

    _tz = field_validator("timezone")(_validate_tz)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class JoinIn(BaseModel):
    """Second parent joining an existing family with an invite code."""

    email: EmailStr
    password: str = Field(min_length=8)
    name: str = Field(min_length=1)
    invite_code: str = Field(min_length=1)


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    family_id: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class MemberOut(BaseModel):
    email: str
    name: str
    role: str = "parent"


class RhythmConfig(BaseModel):
    enabled: bool = False
    interval_hours: float = Field(2.5, gt=0, le=48)


class FamilyRhythms(BaseModel):
    """Shared reminder rhythms — both parents see the same next-feed/next-dose
    times; each phone schedules its own local notification from these."""

    feed: RhythmConfig = RhythmConfig()
    med: RhythmConfig = RhythmConfig(interval_hours=8)


class FamilyOut(BaseModel):
    id: str
    name: Optional[str] = None
    timezone: str
    # Local wall-clock time the family's "day" starts (daily totals bucket).
    day_start: str = "00:00"
    rhythms: FamilyRhythms = FamilyRhythms()
    members: list[MemberOut] = []


class FamilyUpdate(BaseModel):
    name: Optional[str] = None
    timezone: Optional[str] = None
    day_start: Optional[str] = None
    rhythms: Optional[FamilyRhythms] = None

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: Optional[str]) -> Optional[str]:
        return _validate_tz(v) if v is not None else None

    @field_validator("day_start")
    @classmethod
    def _ds(cls, v: Optional[str]) -> Optional[str]:
        return _validate_day_start(v) if v is not None else None


class InviteOut(BaseModel):
    code: str
    expires_at: datetime


class MeOut(BaseModel):
    user: UserOut
    family: FamilyOut
