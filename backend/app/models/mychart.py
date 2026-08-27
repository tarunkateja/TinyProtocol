"""MyChart (Epic patient-access FHIR) sync models.

Same philosophy as the Huckleberry sync: connect once, pull on a schedule,
land everything as review-first import rows — nothing writes into the
medical log without a parent confirming it.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

McImportKind = Literal["lab", "doc", "message"]
McImportStatus = Literal["pending", "imported", "dismissed"]


class McStatus(BaseModel):
    connected: bool
    configured: bool = True  # false until the Epic client id is set up
    patient_name: Optional[str] = None
    fhir_base: Optional[str] = None
    scopes: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    status: Optional[str] = None  # ok | auth_expired | error
    last_error: Optional[str] = None
    pending_labs: int = 0
    pending_docs: int = 0
    pending_messages: int = 0
    messages_available: Optional[bool] = None  # None = not yet known


class McConnectUrl(BaseModel):
    url: str


class McImport(BaseModel):
    item_type: Literal["MCIMPORT"] = "MCIMPORT"
    baby_id: str
    mc_key: str  # "<kind>:<fhir id>"
    kind: McImportKind
    status: McImportStatus
    # labs
    analyte: Optional[str] = None
    value: Optional[float] = None
    unit: Optional[str] = None
    value_text: Optional[str] = None  # non-numeric results, shown but not loggable
    reference_range: Optional[str] = None
    collected_date: Optional[str] = None  # YYYY-MM-DD
    # docs
    title: Optional[str] = None
    doc_date: Optional[str] = None
    content_type: Optional[str] = None  # best importable rendition (pdf preferred)
    binary_url: Optional[str] = None
    # messages
    sender: Optional[str] = None
    sent_at: Optional[str] = None
    text: Optional[str] = None
    # bookkeeping
    imported_id: Optional[str] = None  # lab id / doc id once confirmed
    created_at: datetime
    updated_at: datetime


class McLabConfirmIn(BaseModel):
    """Overrides when confirming a lab import."""

    analyte: Optional[str] = Field(None, min_length=1, max_length=60)
    unit: Optional[str] = Field(None, min_length=1, max_length=20)
    collected_date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class McSyncResult(BaseModel):
    labs_found: int = 0
    docs_found: int = 0
    messages_found: int = 0
    new_pending: int = 0
    messages_available: Optional[bool] = None
