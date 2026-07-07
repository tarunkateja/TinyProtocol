import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from ulid import ULID

from app import auth
from app.auth import CurrentUser, get_current_user
from app.models.baby import Baby
from app.models.family import InviteOut, JoinIn, LoginIn, RegisterIn, TokenOut, UserOut
from app.models.food import Food, MedPreset
from app.repo import families, family_items, keys, users
from app.services.seed import DEFAULT_FOODS, DEFAULT_MED_PRESETS

router = APIRouter(prefix="/auth", tags=["auth"])

# No ambiguous chars (0/O, 1/I/L) — these get read out loud between parents.
_INVITE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _token_response(user_id: str, email: str, name: str, family_id: str) -> TokenOut:
    return TokenOut(
        access_token=auth.create_token(user_id, email, family_id),
        user=UserOut(id=user_id, email=email, name=name, family_id=family_id),
    )


def _seed_family(family_id: str) -> None:
    now = _utcnow()
    for food_in in DEFAULT_FOODS:
        food = Food(id=str(ULID()), created_at=now, **food_in.model_dump())
        family_items.put(family_id, keys.food_sk(food.id), food.model_dump(mode="json"))
    for preset_in in DEFAULT_MED_PRESETS:
        preset = MedPreset(id=str(ULID()), created_at=now, **preset_in.model_dump())
        family_items.put(
            family_id, keys.med_preset_sk(preset.id), preset.model_dump(mode="json")
        )


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn):
    email = keys.norm_email(body.email)
    family_id, user_id = str(ULID()), str(ULID())

    families.create_family(family_id, body.family_name, body.timezone)
    try:
        users.create_user(
            email=email, name=body.name,
            password_hash=auth.hash_password(body.password),
            family_id=family_id, user_id=user_id,
        )
    except users.EmailExistsError:
        raise HTTPException(409, "An account with this email already exists")
    families.add_member(family_id, email, body.name)
    _seed_family(family_id)

    if body.baby is not None:
        baby = Baby(id=str(ULID()), created_at=_utcnow(), **body.baby.model_dump())
        family_items.put(family_id, keys.baby_sk(baby.id), baby.model_dump(mode="json"))

    return _token_response(user_id, email, body.name, family_id)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn):
    user = users.get_user(body.email)
    if user is None or not auth.verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Incorrect email or password")
    return _token_response(user["id"], user["email"], user["name"], user["family_id"])


@router.post("/join", response_model=TokenOut, status_code=201)
def join(body: JoinIn):
    invite = families.find_invite(body.invite_code.strip().upper())
    if invite is None:
        raise HTTPException(400, "Invalid or expired invite code")
    family_id = invite["family_id"]

    email = keys.norm_email(body.email)
    user_id = str(ULID())
    try:
        users.create_user(
            email=email, name=body.name,
            password_hash=auth.hash_password(body.password),
            family_id=family_id, user_id=user_id,
        )
    except users.EmailExistsError:
        raise HTTPException(409, "An account with this email already exists")
    families.add_member(family_id, email, body.name)
    families.delete_invite(family_id, invite["code"])

    return _token_response(user_id, email, body.name, family_id)


@router.post("/invites", response_model=InviteOut, status_code=201)
def create_invite(user: CurrentUser = Depends(get_current_user)):
    code = "".join(secrets.choice(_INVITE_ALPHABET) for _ in range(8))
    expires_epoch = families.create_invite(user.family_id, code, user.user_id)
    return InviteOut(
        code=code, expires_at=datetime.fromtimestamp(expires_epoch, tz=timezone.utc)
    )
