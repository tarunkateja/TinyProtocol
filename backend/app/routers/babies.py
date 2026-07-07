from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from ulid import ULID

from app.auth import CurrentUser, get_current_user
from app.models.baby import Baby, BabyIn, BabyUpdate
from app.repo import family_items, keys
from app.routers.deps import get_baby_or_404

router = APIRouter(prefix="/babies", tags=["babies"])


@router.post("", response_model=Baby, status_code=201)
def create_baby(body: BabyIn, user: CurrentUser = Depends(get_current_user)):
    baby = Baby(
        id=str(ULID()), created_at=datetime.now(timezone.utc), **body.model_dump()
    )
    family_items.put(user.family_id, keys.baby_sk(baby.id), baby.model_dump(mode="json"))
    return baby


@router.get("", response_model=list[Baby])
def list_babies(user: CurrentUser = Depends(get_current_user)):
    items = family_items.list_by_prefix(user.family_id, "BABY#")
    return sorted(
        (Baby.model_validate(i) for i in items), key=lambda b: b.created_at
    )


@router.get("/{baby_id}", response_model=Baby)
def get_baby(baby_id: str, user: CurrentUser = Depends(get_current_user)):
    return get_baby_or_404(user, baby_id)


@router.patch("/{baby_id}", response_model=Baby)
def update_baby(
    baby_id: str, body: BabyUpdate, user: CurrentUser = Depends(get_current_user)
):
    baby = get_baby_or_404(user, baby_id)
    updated = baby.model_copy(update=body.model_dump(exclude_unset=True))
    family_items.put(
        user.family_id, keys.baby_sk(baby.id), updated.model_dump(mode="json")
    )
    return updated
