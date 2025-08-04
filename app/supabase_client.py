import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()  # Load .env variables before using them

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

print("SUPABASE_URL:", SUPABASE_URL)  # Debug print to check loading
print("SUPABASE_KEY:", SUPABASE_KEY)  # Debug print to check loading (hide in prod!)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)