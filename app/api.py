from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Union
from dotenv import load_dotenv
import uuid
import logging

load_dotenv()

from app.data_model import (
    UserProfile,
    SupplementRecommendation,
    WearableMetrics,
    BloodTestResult,
    UserFeedback,
    RecommendationOutput,  # kept import; not used as response_model anymore
)
from app.supplement_engine import generate_supplement_plan, PlanningError

app = FastAPI()

# -----------------------------
# Middleware
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # replace "*" with your frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
@app.head("/")
def root():
    return {"message": "Welcome to the Supplement API"}

logger = logging.getLogger("uvicorn.error")

# -----------------------------
# Helper / nested models
# -----------------------------
class FeedbackInput(BaseModel):
    mood: Optional[str] = None
    energy: Optional[str] = None
    stress: Optional[str] = None
    symptoms: Optional[List[str]] = Field(default_factory=list)
    symptom_changes: Optional[Dict[str, str]] = Field(default_factory=dict)


class ProcessedItem(BaseModel):
    name: str
    category: Optional[str] = None


class MemberProfile(BaseModel):
    display_name: Optional[str] = None
    age_band: Optional[str] = None
    ref_group: Optional[str] = None
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    eats_household_groceries: Optional[bool] = None
    portion_weight: Optional[float] = None


class HouseholdInput(BaseModel):
    household_id: Optional[str] = None
    total_members: Optional[int] = None
    me: Optional[MemberProfile] = None
    other_members: Optional[List[MemberProfile]] = Field(default_factory=list)


# -----------------------------
# Frontend-compatible input
# -----------------------------
class FrontendUserInput(BaseModel):
    age: Optional[int] = None
    biological_sex: Optional[str] = None
    location: Optional[str] = None
    pregnancy: Optional[str] = None
    lifestyle: Optional[Dict[str, Union[str, bool, float]]] = Field(default_factory=dict)
    medical_conditions: Optional[List[str]] = Field(default_factory=list)
    health_priorities: Optional[List[str]] = Field(default_factory=list)
    household: Optional[HouseholdInput] = None
    processed_blood_data: Optional[List[ProcessedItem]] = Field(default_factory=list)
    processed_grocery_data: Optional[List[ProcessedItem]] = Field(default_factory=list)
    has_blood_test_file: Optional[bool] = False
    has_receipt_file: Optional[bool] = False


# -----------------------------
# POST /recommend endpoint
# -----------------------------
@app.post("/recommend", response_model=dict)  # <- allow extended fields without editing data_model.py
def recommend(user_input: FrontendUserInput):
    try:
        # --- Normalize gender flexibly ---
        gender_raw = (user_input.biological_sex or "unspecified").strip().lower()
        if gender_raw in ["f", "female", "woman", "girl"]:
            gender = "female"
        elif gender_raw in ["m", "male", "man", "boy"]:
            gender = "male"
        elif gender_raw in ["other", "non-binary", "nonbinary"]:
            gender = "other"
        else:
            gender = "unspecified"

        # Default age if missing
        age = user_input.age or 35

        # Merge pregnancy info into lifestyle
        lifestyle = user_input.lifestyle or {}
        if user_input.pregnancy:
            lifestyle["pregnancy"] = user_input.pregnancy.lower()

        # Split medications vs. conditions
        conditions = []
        medications = []
        for item in user_input.medical_conditions or []:
            if item.lower() in ["aspirin", "ibuprofen", "paracetamol", "acetaminophen"]:
                medications.append(item)
            else:
                conditions.append(item)

        # --- Future use: optional extended data ---
        household_data = user_input.household.dict() if user_input.household else {}
        grocery_data = [item.dict() for item in user_input.processed_grocery_data or []]
        blood_data = [item.dict() for item in user_input.processed_blood_data or []]

        logger.info(f"Received household={bool(household_data)}, "
                    f"groceries={len(grocery_data)}, blood_tests={len(blood_data)}")

        # Build internal user profile
        user = UserProfile(
            user_id=str(uuid.uuid4()),
            age=age,
            gender=gender,
            symptoms=[],
            lifestyle=lifestyle,
            medical_conditions=conditions,
            medical_history={},
            medications=medications,
            goals=user_input.health_priorities or [],
            blood_tests=[],  # you can later map blood_data here
            wearable_data=None,
            feedback=None,
        )

        # Generate full plan via LLM planner (supps + groceries + recipes + timeframe)
        out = generate_supplement_plan(user)
        return out

    except PlanningError as e:
        logger.error(f"LLM planning error: {e}")
        raise HTTPException(status_code=502,
                            detail="Supplement planning temporarily unavailable. Please try again later.")
    except Exception as e:
        logger.error(f"Error in /recommend endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500,
                            detail="Internal Server Error. Please check your input and try again.")


# -----------------------------
# Other routers
# -----------------------------
from app.receipt_ocr import router as receipt_router
app.include_router(receipt_router)

from app.grocery_router import router as grocery_router
app.include_router(grocery_router)

from app.bloodtest_ocr import router as bloodtest_router
app.include_router(bloodtest_router)