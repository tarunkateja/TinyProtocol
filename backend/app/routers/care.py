"""Emergency card (care profile), clinic questions, and lab results."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from ulid import ULID

from app.auth import CurrentUser, get_current_user
from app.models.care import (
    CareProfile,
    ClinicNote,
    ClinicNoteIn,
    ClinicNoteUpdate,
    LabResult,
    LabResultIn,
)
from app.repo import family_items, keys, users

router = APIRouter(tags=["care"])


# --------------------------------------------------------------------------- #
# Emergency card
# --------------------------------------------------------------------------- #
@router.get("/care-profile", response_model=CareProfile)
def get_care_profile(user: CurrentUser = Depends(get_current_user)):
    item = family_items.get(user.family_id, keys.CARE_PROFILE_SK)
    return CareProfile.model_validate(item) if item else CareProfile()


@router.put("/care-profile", response_model=CareProfile)
def put_care_profile(
    body: CareProfile, user: CurrentUser = Depends(get_current_user)
):
    body.updated_at = datetime.now(timezone.utc)
    family_items.put(user.family_id, keys.CARE_PROFILE_SK, body.model_dump(mode="json"))
    return body


# --------------------------------------------------------------------------- #
# Clinic questions
# --------------------------------------------------------------------------- #
@router.get("/clinic-notes", response_model=list[ClinicNote])
def list_clinic_notes(user: CurrentUser = Depends(get_current_user)):
    items = family_items.list_by_prefix(user.family_id, "CLINICNOTE#")
    notes = [ClinicNote.model_validate(i) for i in items]
    # Open questions first, newest first within each group.
    return sorted(notes, key=lambda n: (n.done, -n.created_at.timestamp()))


@router.post("/clinic-notes", response_model=ClinicNote, status_code=201)
def create_clinic_note(
    body: ClinicNoteIn, user: CurrentUser = Depends(get_current_user)
):
    profile = users.get_user(user.email)
    note = ClinicNote(
        id=str(ULID()),
        text=body.text.strip(),
        done=False,
        created_by=profile["name"] if profile else "parent",
        created_at=datetime.now(timezone.utc),
    )
    family_items.put(
        user.family_id, keys.clinic_note_sk(note.id), note.model_dump(mode="json")
    )
    return note


@router.patch("/clinic-notes/{note_id}", response_model=ClinicNote)
def update_clinic_note(
    note_id: str, body: ClinicNoteUpdate, user: CurrentUser = Depends(get_current_user)
):
    item = family_items.get(user.family_id, keys.clinic_note_sk(note_id))
    if item is None:
        raise HTTPException(404, "Note not found")
    note = ClinicNote.model_validate(
        {**item, **body.model_dump(exclude_unset=True)}
    )
    family_items.put(
        user.family_id, keys.clinic_note_sk(note_id), note.model_dump(mode="json")
    )
    return note


@router.delete("/clinic-notes/{note_id}", status_code=204)
def delete_clinic_note(note_id: str, user: CurrentUser = Depends(get_current_user)):
    if family_items.get(user.family_id, keys.clinic_note_sk(note_id)) is None:
        raise HTTPException(404, "Note not found")
    family_items.delete(user.family_id, keys.clinic_note_sk(note_id))


# --------------------------------------------------------------------------- #
# Lab results
# --------------------------------------------------------------------------- #
@router.get("/labs", response_model=list[LabResult])
def list_labs(user: CurrentUser = Depends(get_current_user)):
    items = family_items.list_by_prefix(user.family_id, "LAB#")
    labs = [LabResult.model_validate(i) for i in items]
    return sorted(labs, key=lambda x: (x.analyte, str(x.collected_date)))


@router.post("/labs", response_model=LabResult, status_code=201)
def create_lab(body: LabResultIn, user: CurrentUser = Depends(get_current_user)):
    lab = LabResult(
        id=str(ULID()),
        analyte=body.analyte.strip().lower().replace(" ", "_"),
        value=body.value,
        unit=body.unit.strip(),
        collected_date=body.collected_date,
        source_doc_id=body.source_doc_id,
        created_at=datetime.now(timezone.utc),
    )
    family_items.put(
        user.family_id,
        keys.lab_sk(str(lab.collected_date), lab.id),
        lab.model_dump(mode="json"),
    )
    return lab


@router.delete("/labs/{lab_id}", status_code=204)
def delete_lab(lab_id: str, user: CurrentUser = Depends(get_current_user)):
    # SK embeds the date, so find by suffix among the family's labs.
    items = family_items.list_by_prefix(user.family_id, "LAB#")
    match = next((i for i in items if i.get("id") == lab_id), None)
    if match is None:
        raise HTTPException(404, "Lab result not found")
    family_items.delete(user.family_id, match["SK"])
