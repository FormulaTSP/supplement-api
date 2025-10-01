from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Union
from dotenv import load_dotenv

load_dotenv()  # ✅ Load environment variables from .env

from app.data_model import (
    UserProfile,
    SupplementRecommendation,
    WearableMetrics,
    BloodTestResult,
    UserFeedback,
    RecommendationOutput
)
from app.supplement_engine import generate_supplement_plan, PlanningError
import uuid
import logging

app = FastAPI()

# ✅ Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace "*" with "https://your-frontend-url.com" for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root endpoint supporting GET and HEAD to avoid 405 errors on HEAD requests
@app.get("/")
@app.head("/")
def root():
    return {"message": "Welcome to the Supplement API"}

# Setup logger
logger = logging.getLogger("uvicorn.error")

# -----------------------------
# Pydantic models for API input
# -----------------------------

class FeedbackInput(BaseModel):
    mood: Optional[str] = None
    energy: Optional[str] = None
    stress: Optional[str] = None
    symptoms: Optional[List[str]] = Field(default_factory=list)
    symptom_changes: Optional[Dict[str, str]] = Field(default_factory=dict)

class UserInput(BaseModel):
    age: int
    gender: str
    symptoms: Optional[List[str]] = Field(default_factory=list)
    lifestyle: Optional[Dict[str, Union[str, bool, float]]] = Field(default_factory=dict)
    medical_history: Optional[Dict[str, Union[str, bool, float]]] = Field(default_factory=dict)
    medical_conditions: Optional[List[str]] = Field(default_factory=list)
    medications: Optional[List[str]] = Field(default_factory=list)
    goals: Optional[List[str]] = Field(default_factory=list)
    blood_tests: Optional[List[Dict[str, Union[str, float]]]] = Field(default_factory=list)
    wearable_data: Optional[Dict[str, Union[str, float]]] = None
    feedback: Optional[FeedbackInput] = None

# -----------------------------
# POST endpoint for recommendation
# -----------------------------

@app.post("/recommend", response_model=RecommendationOutput)
def recommend(user_input: UserInput):
    try:
        # Convert blood test data
        blood_tests = [
            BloodTestResult(marker=bt["marker"], value=float(bt["value"]), unit=bt["unit"])
            for bt in user_input.blood_tests or []
        ]

        # Normalize and convert wearable data
        wearable = None
        if user_input.wearable_data:
            wearable_dict = user_input.wearable_data.copy()
            level_map = {"low": 0.0, "moderate": 0.5, "high": 1.0}
            if "activity_level" in wearable_dict and isinstance(wearable_dict["activity_level"], str):
                level = wearable_dict["activity_level"].lower()
                wearable_dict["activity_level"] = level_map.get(level, 0.0)
            wearable = WearableMetrics(**wearable_dict)

        # Format lifestyle (convert all values to lowercase strings)
        lifestyle_dict = {
            k: str(v).lower() for k, v in (user_input.lifestyle or {}).items()
        }

        # Convert feedback directly (Pydantic already validated)
        feedback = user_input.feedback

        # Build user profile
        user = UserProfile(
            user_id=str(uuid.uuid4()),
            age=user_input.age,
            gender=user_input.gender,
            symptoms=user_input.symptoms,
            lifestyle=lifestyle_dict,
            medical_conditions=user_input.medical_conditions,
            medical_history=user_input.medical_history,
            medications=user_input.medications,
            goals=user_input.goals,
            wearable_data=wearable,
            blood_tests=blood_tests,
            feedback=feedback,
        )

        # Directly plan with the LLM-based engine (no clustering/rule-based pipeline)
        recommendations = generate_supplement_plan(user)
        return recommendations

    except PlanningError as e:
        # LLM failed — surface a clear error to clients
        logger.error(f"LLM planning error: {e}")
        raise HTTPException(status_code=502, detail="Supplement planning temporarily unavailable. Please try again later.")
    except Exception as e:
        logger.error(f"Error in /recommend endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error. Please check your input and try again.")

# Routers
from app.receipt_ocr import router as receipt_router
app.include_router(receipt_router)

from app.grocery_router import router as grocery_router
app.include_router(grocery_router)

from app.bloodtest_ocr import router as bloodtest_router
app.include_router(bloodtest_router)