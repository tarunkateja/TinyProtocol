from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Emergency card / care profile (family singleton)
# --------------------------------------------------------------------------- #
class CareContact(BaseModel):
    label: str
    phone: str
    when: Optional[str] = None  # e.g. "Mon–Fri 8:00–4:30"


class PatientInfo(BaseModel):
    name: Optional[str] = None
    mrn: Optional[str] = None
    dob: Optional[str] = None
    diagnosis: Optional[str] = None


class CareProfile(BaseModel):
    patient: PatientInfo = PatientInfo()
    er_interventions: list[str] = []
    when_to_call: list[str] = []
    contacts: list[CareContact] = []
    bring_to_er: list[str] = []
    formula_ordering: list[str] = []
    notes: Optional[str] = None
    updated_at: Optional[datetime] = None


# --------------------------------------------------------------------------- #
# Clinic questions
# --------------------------------------------------------------------------- #
class ClinicNoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class ClinicNoteUpdate(BaseModel):
    text: Optional[str] = Field(None, min_length=1, max_length=500)
    done: Optional[bool] = None


class ClinicNote(BaseModel):
    id: str
    text: str
    done: bool = False
    created_by: str
    created_at: datetime


# --------------------------------------------------------------------------- #
# Lab results
# --------------------------------------------------------------------------- #
class LabResultIn(BaseModel):
    analyte: str = Field(min_length=1, max_length=60)
    value: float
    unit: str = Field(min_length=1, max_length=20)
    collected_date: date


class LabResult(LabResultIn):
    id: str
    source_doc_id: Optional[str] = None
    created_at: datetime


# --------------------------------------------------------------------------- #
# Care documents
# --------------------------------------------------------------------------- #
DocStatus = Literal["uploaded", "processing", "ready", "error"]


class ExtractedContact(BaseModel):
    label: str
    phone: str
    when: Optional[str] = None


class DocExtraction(BaseModel):
    doc_type: str = "other"  # clinic_guide | emergency_letter | lab_report | ...
    summary_points: list[str] = []
    contacts: list[ExtractedContact] = []
    key_facts: list[str] = []


class DocCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    content_type: str = Field(pattern=r"^(image/(jpeg|png|heic|webp)|application/pdf)$")
    title: Optional[str] = Field(None, max_length=120)


class Doc(BaseModel):
    id: str
    title: str
    filename: str
    content_type: str
    s3_key: str
    status: DocStatus = "uploaded"
    error: Optional[str] = None
    processing_started_at: Optional[datetime] = None
    summary: Optional[str] = None
    extracted: Optional[DocExtraction] = None
    lab_results_added: int = 0
    created_at: datetime


class DocCreated(BaseModel):
    doc: Doc
    upload_url: str
    upload_content_type: str  # echo — client must send this exact header
