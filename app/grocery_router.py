# app/grocery_router.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from supabase import create_client
import os
from dotenv import load_dotenv

# Load .env file at the very beginning
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

print(f"SUPABASE_URL: {SUPABASE_URL}")
print(f"SUPABASE_KEY: {'set' if SUPABASE_KEY else 'NOT set!'}")  # Just to check if key is loaded

# Now create the supabase client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

router = APIRouter(prefix="/grocery", tags=["grocery"])

class GroceryDataCreate(BaseModel):
    user_id: str
    store_name: Optional[str]
    receipt_data: Optional[Dict[str, Any]]
    products: Optional[List[Dict[str, Any]]]
    household_size: Optional[int]
    eats_at_home: Optional[bool]

class GroceryDataUpdate(BaseModel):
    store_name: Optional[str]
    receipt_data: Optional[Dict[str, Any]]
    products: Optional[List[Dict[str, Any]]]
    household_size: Optional[int]
    eats_at_home: Optional[bool]

@router.post("/", status_code=201)
def create_grocery_data(data: GroceryDataCreate):
    response = supabase.table("grocery_data").insert(data.dict()).execute()
    if response.error:
        raise HTTPException(status_code=400, detail=response.error.message)
    return response.data

@router.get("/{grocery_id}")
def read_grocery_data(grocery_id: str):
    response = supabase.table("grocery_data").select("*").eq("id", grocery_id).single().execute()
    if response.error or response.data is None:
        raise HTTPException(status_code=404, detail="Grocery data not found")
    return response.data

@router.patch("/{grocery_id}")
def update_grocery_data(grocery_id: str, data: GroceryDataUpdate):
    response = supabase.table("grocery_data").update(data.dict(exclude_unset=True)).eq("id", grocery_id).execute()
    if response.error:
        raise HTTPException(status_code=400, detail=response.error.message)
    return response.data

@router.delete("/{grocery_id}", status_code=204)
def delete_grocery_data(grocery_id: str):
    response = supabase.table("grocery_data").delete().eq("id", grocery_id).execute()
    if response.error:
        raise HTTPException(status_code=400, detail=response.error.message)
    return {"detail": "Deleted"}