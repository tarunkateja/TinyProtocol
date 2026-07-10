from datetime import datetime, time, timezone

from fastapi import APIRouter, Depends
from ulid import ULID

from app.auth import CurrentUser, get_current_user
from app.models.baby import Baby, BabyIn, BabyUpdate
from app.repo import families, family_items, keys
from app.routers.deps import get_baby_or_404
from app.services import target_history

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
    updated = Baby.model_validate(
        {**baby.model_dump(), **body.model_dump(exclude_unset=True)}
    )
    if body.targets is not None and updated.targets != baby.targets:
        fam = families.get_family(user.family_id) or {}
        target_history.record_change(
            user.family_id,
            baby.id,
            old=baby.targets,
            new=updated.targets,
            tz_name=fam.get("timezone", "UTC"),
            day_start=time.fromisoformat(fam.get("day_start") or "00:00"),
        )
    family_items.put(
        user.family_id, keys.baby_sk(baby.id), updated.model_dump(mode="json")
    )
    return updated
