# main.py
import pandas as pd
from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Union, Literal
from pydantic import BaseModel, Field
import asyncio
import uuid

# --- In-Memory Data Store ---
try:
    # Load NAMASTE codes
    df_namaste = pd.read_csv("namaste_codes.csv", engine='python')
    NAMASTE_DATA = df_namaste.to_dict('records')
    print(f"NAMASTE CSV successfully ingested. {len(NAMASTE_DATA)} records loaded.")

    # Load Patient list
    df_patients = pd.read_csv("patients.csv")
    PATIENT_DATA = df_patients.to_dict('records')
    print(f"Patient CSV successfully ingested. {len(PATIENT_DATA)} records loaded.")

except FileNotFoundError as e:
    print(f"FATAL ERROR: {e.filename} not found. The application cannot start.")
    NAMASTE_DATA = []
    PATIENT_DATA = []


# --- FastAPI App Initialization ---
app = FastAPI(
    title="Ayush EMR Integration Service (In-Memory)",
    description="API to integrate NAMASTE and ICD-11. Data is loaded from CSV.",
)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Static Files and Templates ---
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- Mock ABHA-linked OAuth 2.0 Security ---
async def check_auth(request: Request):
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization scheme")
    return True

# --- Pydantic Models for FHIR Validation ---
class HumanName(BaseModel):
    text: str

class FhirReference(BaseModel):
    reference: str

class CodeableConcept(BaseModel):
    coding: List[Dict[str, Any]]
    text: str

class Patient(BaseModel):
    resourceType: Literal["Patient"]
    name: List[HumanName]
    birthDate: str | None = None

class Practitioner(BaseModel):
    resourceType: Literal["Practitioner"]
    name: List[HumanName]

class Condition(BaseModel):
    resourceType: Literal["Condition"]
    subject: FhirReference
    code: CodeableConcept
    asserter: FhirReference | None = None

AnyResource = Union[Patient, Condition, Practitioner]

class BundleEntry(BaseModel):
    fullUrl: str
    resource: AnyResource = Field(..., discriminator='resourceType')
    request: dict

class FhirBundle(BaseModel):
    resourceType: Literal["Bundle"]
    id: str
    type: str
    entry: List[BundleEntry]

# --- API Endpoints ---
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root(request: Request):
    return templates.TemplateResponse("index"
    ".html", {"request": request})

@app.get("/api/lookup")
async def lookup_namaste_code(q: str):
    if not q or not NAMASTE_DATA:
        return []
    query_lower = q.lower()
    results = [
        record for record in NAMASTE_DATA
        if query_lower in str(record.get('namaste_display', '')).lower()
        or query_lower in str(record.get('icd11_display', '')).lower()
    ]
    return results[:15]

@app.get("/api/patients")
async def search_patients(q: str):
    if not q or not PATIENT_DATA:
        return []
    query_lower = q.lower()
    results = [
        patient for patient in PATIENT_DATA
        if query_lower in str(patient.get('patient_name', '')).lower()
        or query_lower in str(patient.get('dob', '')).lower()
    ]
    return results[:10]


@app.post("/fhir/Bundle", status_code=status.HTTP_200_OK)
async def submit_fhir_bundle(bundle: FhirBundle, authorized: bool = Depends(check_auth)):
    print('--- Received FHIR Bundle for Processing ---')
    print(f"Bundle ID: {bundle.id}")
    print(f"Total Entries: {len(bundle.entry)}")

    outcome = {
        "resourceType": "OperationOutcome",
        "issue": [{
            "severity": "information",
            "code": "informational",
            "details": { "text": "FHIR Bundle received and validated successfully." }
        }]
    }
    return JSONResponse(content=outcome, status_code=status.HTTP_200_OK)
