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
from app.supplement_engine import generate_supplement_plan
from app.cluster_engine import ClusterEngine
from app.user_update_pipeline import add_user_and_recluster
from app.drug_interaction_checker import attach_interaction_flags
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

# Root endpoint
@app.get("/")
def root():
    return {"message": "Welcome to the Supplement API"}

# Setup logger
logger = logging.getLogger("uvicorn.error")

# Shared cluster engine instance
cluster_engine = ClusterEngine(n_clusters=3)
cluster_engine.fitted = False

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

        # Recluster and generate recommendations
        updated_user, updated_cluster_engine = add_user_and_recluster(user)

        # Update global cluster engine instance for subsequent requests
        global cluster_engine
        cluster_engine = updated_cluster_engine

        # Get recommendation output directly from supplement engine
        recommendations = generate_supplement_plan(updated_user, cluster_engine=updated_cluster_engine)

        # Attach drug interaction warnings
        flagged_recs = attach_interaction_flags(updated_user, recommendations.recommendations)
        recommendations.recommendations = flagged_recs

        return recommendations

    except Exception as e:
        logger.error(f"Error in /recommend endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error. Please check your input and try again.")
    
from app.receipt_ocr import router as receipt_router
app.include_router(receipt_router)

from app.grocery_router import router as grocery_router
app.include_router(grocery_router)