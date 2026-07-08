"""One-off: seed every family's Emergency Card (CAREPROFILE) from Tara's
Lurie Children's documents (Emergency Letter, Sick Days protocol, Metabolic
Clinic Guide, IDPH formula ordering). Skips families that already have one.

Run from backend/: TABLE_NAME=TinyProtocol-dev .venv/bin/python scripts/seed_care_profile.py
"""

from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Attr

from app.config import settings
from app.models.care import CareContact, CareProfile, PatientInfo
from app.repo.client import to_item

PROFILE = CareProfile(
    patient=PatientInfo(
        name="Tara Rajani",
        mrn="3107332",
        dob="5/22/2026",
        diagnosis="Glutaric Acidemia Type 1 (GA-1)",
    ),
    er_interventions=[
        "This patient requires immediate medical attention and intervention.",
        "1. Stabilize patient, insert peripheral IV and draw STAT labs: Comprehensive Metabolic Profile (CMP).",
        "2. Immediately start D10 0.9 Normal Saline at 1.5 times maintenance rate.",
        "3. Give antipyretics for ANY illness.",
        "4. Complete rapid neurologic assessment for metabolic stroke.",
        "5. Call the operator at Lurie Children's at 312-227-4000 and have them page the geneticist on-call as soon as possible.",
        "Source: Emergency Letter, Dr. Joshua Baker, Lurie Children's (6/23/2026).",
    ],
    when_to_call=[
        "Call AS SOON AS POSSIBLE if Tara is sick: fever, vomiting, diarrhea, decreased appetite, extremely tired (lethargic), or unable to keep food, formula, or medications down.",
        "Do NOT use MyChart messaging to report illness, concerns, or symptoms.",
        "Weekdays 8:00 AM–4:30 PM: call the Genetics Office and ask for the Genetics nurse.",
        "Nights, weekends, holidays: call the Main Hospital Operator and ask to page the Geneticist on call.",
    ],
    contacts=[
        CareContact(label="Genetics Office (Genetics nurse)", phone="312-227-6120", when="Mon–Fri 8:00 AM–4:30 PM, except holidays"),
        CareContact(label="Main Hospital Operator (page on-call Geneticist)", phone="312-227-4000", when="Nights, weekends, holidays"),
        CareContact(label="Metabolic nutrition team", phone="312-227-6120", when="Business hours"),
        CareContact(label="IDPH formula orders", phone="217-557-5395", when="Business hours (closed state holidays)"),
        CareContact(label="KIDS DOC (insurance/registration updates)", phone="800-543-7362", when=None),
    ],
    bring_to_er=[
        "All of Tara's medications",
        "Tara's medical formula",
        "A copy of Tara's Emergency Letter",
    ],
    formula_ordering=[
        "Formula is covered for life by IDPH (Illinois) for screened metabolic disorders.",
        "Order by phone (217-557-5395) with Tara's name, DOB, and your phone number — match the clinic's prescription.",
        "Order when about a TWO-WEEK supply is left; it is specialized and cannot be bought in stores.",
        "Each prescription covers one month; prescriptions are valid 12 months.",
        "Tara must be seen in clinic at least once per year to keep receiving prescriptions.",
        "Ships by UPS to your address; report any move to the clinic and IDPH.",
    ],
    notes=(
        "Followed by the Edwards Family Division of Genetics & Rare Diseases, "
        "Ann & Robert H. Lurie Children's Hospital of Chicago, 225 E. Chicago Ave, Box 59, Chicago IL 60611. "
        "Sourced from clinic documents dated 2026; verify against the latest letter after each clinic visit."
    ),
    updated_at=datetime.now(timezone.utc),
)

table = boto3.resource("dynamodb").Table(settings.table_name)

resp = table.scan(FilterExpression=Attr("SK").eq("META"))
seeded = skipped = 0
for fam in resp["Items"]:
    pk = fam["PK"]
    existing = table.get_item(Key={"PK": pk, "SK": "CAREPROFILE"}).get("Item")
    if existing:
        skipped += 1
        continue
    table.put_item(
        Item=to_item({"PK": pk, "SK": "CAREPROFILE", **PROFILE.model_dump(mode="json")})
    )
    seeded += 1

print(f"care profiles seeded: {seeded}, already present (skipped): {skipped}")
