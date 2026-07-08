from fastapi import APIRouter, Depends, HTTPException

from app.auth import CurrentUser, get_current_user
from app.models.family import FamilyOut, FamilyRhythms, FamilyUpdate, MeOut, MemberOut, UserOut
from app.repo import families, users

router = APIRouter(tags=["family"])


def _family_out(family_id: str) -> FamilyOut:
    fam = families.get_family(family_id)
    if fam is None:
        raise HTTPException(404, "Family not found")
    members = [MemberOut.model_validate(m) for m in families.list_members(family_id)]
    return FamilyOut(
        id=fam["id"],
        name=fam.get("name"),
        timezone=fam["timezone"],
        day_start=fam.get("day_start") or "00:00",
        rhythms=FamilyRhythms.model_validate(fam.get("rhythms") or {}),
        members=members,
    )


@router.get("/me", response_model=MeOut)
def me(user: CurrentUser = Depends(get_current_user)):
    profile = users.get_user(user.email)
    if profile is None:
        raise HTTPException(404, "User not found")
    return MeOut(
        user=UserOut(
            id=profile["id"], email=profile["email"],
            name=profile["name"], family_id=profile["family_id"],
        ),
        family=_family_out(user.family_id),
    )


@router.get("/family", response_model=FamilyOut)
def get_family(user: CurrentUser = Depends(get_current_user)):
    return _family_out(user.family_id)


@router.patch("/family", response_model=FamilyOut)
def update_family(body: FamilyUpdate, user: CurrentUser = Depends(get_current_user)):
    fam = families.get_family(user.family_id)
    if fam is None:
        raise HTTPException(404, "Family not found")
    updates = body.model_dump(exclude_unset=True)
    fam = {k: v for k, v in fam.items() if k not in ("PK", "SK")}
    fam.update(updates)
    families.put_family(user.family_id, fam)
    return _family_out(user.family_id)
