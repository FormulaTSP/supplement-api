# CONTINUE.md — Project Guide

This guide helps developers quickly understand, run, and extend the project. Continue will auto-load this file into context when you work in this repository.

## 1) Project Overview
- Purpose: Backend API that analyzes user profiles, symptoms, blood tests, wearable data, and grocery receipts to generate safe, personalized supplement recommendations. Includes basic data clustering to learn protocols and a Supabase Edge Function to ingest lab results.
- Key technologies:
  - Python 3.13, FastAPI, Uvicorn
  - Google Cloud Vision (OCR)
  - OpenAI API (GPT-4o) for parsing/extraction/categorization and LLM planning
  - Supabase (Postgres + Edge Functions)
  - Docker + Render deployment
  - Node/Playwright (auxiliary receipt scraping/automation)
- High-level architecture:
  - app/api.py exposes REST endpoints. Core recommendation pipeline lives in app/supplement_engine.py and now delegates exclusively to the LLM planner in app/llm_planner.py. The output is post-processed with safety/interaction checks and explanations.
  - OCR/Extraction endpoints for receipts and blood tests, using Google Vision + optional GPT fallback.
  - Supabase Edge Function (supabase/functions/lab-mock-callback) maps incoming lab observations to database tables.

Note: The previous rule-based and clustering engines have been deprecated and removed from the live path. cluster_engine.py and related files may still exist for historical reference but are not used by the API.

## 2) Getting Started
Prerequisites
- Python 3.13
- pip, virtualenv (recommended)
- Poppler (for pdf2image). Docker image installs poppler-utils. On local:
  - macOS: brew install poppler
  - Ubuntu/Debian: sudo apt-get install poppler-utils
  - Windows: install poppler and add bin to PATH; see pdf2image docs.
- Google Cloud Vision credentials (as JSON string in env var)
- OpenAI API key
- Optional: Supabase project URL and service key
- Optional: Node 18+ (for Playwright automation scripts)

Environment variables (.env)
- OPENAI_API_KEY=...
- GOOGLE_APPLICATION_CREDENTIALS_JSON=<entire service account JSON string>
- SUPABASE_URL=...
- SUPABASE_KEY=...
- Optional for tests: TESTING=1 (bypasses some dosage upper-limit behavior in tests)

Install and run (local)
- Create venv, install deps, run server:
  - python -m venv .venv
  - source .venv/bin/activate  (Windows: .venv\\Scripts\\activate)
  - pip install -r requirements.txt
  - uvicorn app.api:app --host 0.0.0.0 --port 10000 --reload
- Basic health check:
  - GET http://localhost:10000/

Docker (local)
- docker build -t supplement-api .
- docker run -p 10000:10000 --env-file .env supplement-api

Render deployment
- Uses render.yaml and render-build.sh.
- Render start: uvicorn app.api:app --host 0.0.0.0 --port $PORT
- Expects PORT=10000 (configured in render.yaml).

Running tests
- pytest app/tests -q
- Some tests may require env vars (e.g., OPENAI_API_KEY) or network. For CI/offline, you may need to mock OpenAI/Google calls.

## 3) Project Structure
Top-level
- Dockerfile: Python 3.13-slim, installs poppler-utils and Python deps, starts uvicorn on 10000.
- requirements.txt: Python dependencies.
- render.yaml, render-build.sh, Procfile: deployment config (Render/Procfile-based).
- package.json: Node deps (dotenv, playwright) for optional automation scripts.
- deno.json, supabase/: Supabase config and Edge Function.

app/ (Python backend)
- api.py: FastAPI app, CORS, routes:
  - GET/HEAD /
  - POST /recommend → RecommendationOutput
  - POST /process-receipt → OCR + nutrition estimates
  - POST /process-bloodtest → OCR/Excel parse to structured blood tests
  - /grocery/* → CRUD to Supabase table grocery_data
- data_model.py: Dataclasses for domain model (UserProfile, BloodTestResult, WearableMetrics, SupplementRecommendation, RecommendationOutput, etc.).
- supplement_engine.py: Delegates exclusively to LLM planner (app/llm_planner.py), then runs post-processing: feedback labels, safety validation, drug interaction flags. No rule-based or clustering logic remains in the live path.
- symptom_scorer.py: Maps symptoms/lifestyle → per-nutrient need scores.
- dosage_calculator.py and supplement_utils.py: Dosage logic (DB-driven), RDA groups, upper limits, contraindications.
- safety_checks.py: Upper-limit checks, contraindications, bidirectional interactions within recs.
- drug_interaction_checker.py: Medication vs. supplement interaction flags using local JSON db (drug_supp_interactions.json).
- explanation_utils.py: Concise and structured explanations for UI.
- unit_converter.py: Blood test unit normalization helpers.
- wearable_middleware.py: Normalizes/fetches wearable data (scaffold for Apple/Oura/etc.).
- receipt_ocr.py: OCR for receipts via Google Vision, then GPT categories, basic nutrient estimation.
- bloodtest_ocr.py: OCR/Excel parsing for blood tests, returns structured JSON; uses parse_bloodtest_text (llm_utils.py) for GPT fallback.
- grocery_router.py: Supabase client + CRUD endpoints for grocery_data.
- data_storage.py: Persist/load users.json, serialization helpers for dataclasses.
- cluster_engine.py: Legacy/experimental (not used by the API anymore). Previously generated cluster protocols; can be kept for offline analysis.
- cluster_logger.py, protocol_log_utils.py: Logging and analysis of protocol changes/history.
- tests/: Extensive pytest suite covering components and endpoints.

supabase/
- config.toml: local dev config via supabase CLI.
- functions/lab-mock-callback/index.ts: Edge Function for ingesting lab results and mapping them via markers_map.

Important data/config files
- app/supplement_db.json: Nutrient metadata, RDA, ranges, upper limits, interactions, contraindications.
- app/cluster_protocols.json: Generated cluster protocols (persisted by cluster_engine).
- app/cluster_history.json, app/protocol_change_log.json: Logs maintained by cluster_logger.
- app/drug_supp_interactions.json: Local interaction map for meds vs supplements.

## 4) Development Workflow
Coding standards and conventions
- Python 3.13, type hints encouraged. Dataclasses are used for domain models.
- Keep side effects behind clear interfaces (e.g., dosage via supplement_utils, safety in safety_checks, clustering in cluster_engine).
- Do not log secrets. Some files currently print Supabase keys for debugging; remove for production.

Testing
- pytest app/tests -q
- Tests include: API integration, dosage, interactions, scoring, wearable middleware, OCR endpoints, explanations, clustering.
- For stable tests without external calls, mock OpenAI/Google Vision.

Build and deployment
- Local dev via uvicorn with --reload.
- Dockerfile is production-ready base; includes poppler-utils for pdf2image. Configure .env at runtime.
- Render deploys via render.yaml. Ensure OPENAI_API_KEY, GOOGLE_APPLICATION_CREDENTIALS_JSON, SUPABASE_URL, SUPABASE_KEY are set in Render dashboard.

Contribution guidelines
- Small PRs, include/extend unit tests.
- Document new endpoints in this file (Endpoints section) and add example requests.
- If extending supplement_db.json, also update tests to cover new nutrients and edge cases.

## 5) Key Concepts
- Planning: LLM planner (app/llm_planner.py) is the sole engine that proposes supplement plans, constrained by the local catalog (app/supplement_db.json). It returns JSON that is converted into SupplementRecommendation objects.
- Safety checks: safety_checks flags upper-limit breaches, contraindications, intra-protocol interactions. drug_interaction_checker flags med–supp interactions.
- Explanations: explanation_utils builds concise and structured explanations for UI.
- Data ingestion: receipt_ocr and bloodtest_ocr use Google Vision and optionally GPT for parsing; grocery_router stores structured grocery data to Supabase.

## 6) Common Tasks
Run the API locally
- uvicorn app.api:app --host 0.0.0.0 --port 10000 --reload

Example: POST /recommend
- Request JSON (minimal):
  {
    "age": 30,
    "gender": "female",
    "symptoms": ["fatigue", "brain fog"],
    "goals": ["better sleep"],
    "medications": ["sertraline"],
    "blood_tests": [{"marker": "Vitamin D", "value": 18, "unit": "ng/mL"}],
    "wearable_data": {"sleep_hours": 6.5, "activity_level": "moderate"}
  }
- Response: RecommendationOutput with recommendations[], confidence_score, optional cluster_id.

Process a receipt
- POST /process-receipt with file form field. Returns consumed_foods, dietary_intake, raw text.
- Requires GOOGLE_APPLICATION_CREDENTIALS_JSON and poppler installed.

Process a blood test
- POST /process-bloodtest with file (pdf/png/jpg/xlsx). Returns structured_bloodtest.parsed_text[].
- Excel parser expects a "Datum" column with dates and the rest as markers.
- If OCR text is unstructured, GPT fallback is used (requires OPENAI_API_KEY).

Persist users and clustering
- New users are added through add_user_and_recluster in app/user_update_pipeline.py, which re-fits the engine, assigns clusters, logs changes, and persists users.json.

Add a new nutrient
- Update app/supplement_db.json with name, unit, rda_by_gender_age, optimal_range, upper_limit, contraindications, interactions.
- Add/extend tests in app/tests/.

How to adjust planning behavior
- llm_planner.py controls the prompt, schema, and constraints. Adjust the system prompt or catalog filtering if you want fewer/more items, different priorities, or stricter limits.
- You can also pre-filter the catalog (e.g., by relevant categories or symptoms) to reduce token usage and shape outputs.

Use Supabase Edge Function (lab-mock-callback)
- Deployed under supabase/functions/lab-mock-callback. Expects SUPABASE_URL and SERVICE_ROLE_KEY in the Edge environment.
- Accepts POST with order_id and observations[]. Maps observations to markers_map and inserts into results/observations tables.

## 7) Troubleshooting
- pdf2image errors (No such file or directory): Ensure poppler-utils installed and on PATH. In Docker, it is pre-installed.
- Google Vision auth errors: Ensure GOOGLE_APPLICATION_CREDENTIALS_JSON is set to the full JSON string for the service account. For local files, you could switch to GOOGLE_APPLICATION_CREDENTIALS path approach if you refactor.
- OpenAI errors: Ensure OPENAI_API_KEY is present. Network issues can cause timeouts; add retries/mocking for tests. Since the LLM planner is now the only engine, API will return 502 if planning fails.
- Supabase client errors: SUPABASE_URL/SUPABASE_KEY must be set. Avoid printing secrets in logs (grocery_router.py, supabase_client.py currently print them for debugging).
- Duplicate router includes: app/api.py currently includes receipt_router and grocery_router twice; remove duplicates if you see duplicate routes or logs.
- Unit encoding artifacts: Some tests include units like "Âµg/dL". unit_converter handles "µg/dL" lowercased ("µg/dl"). If issues arise, normalize inputs or extend unit_converter.
- Port mismatch: Render sets $PORT. Locally default is 10000. Update config if needed.

## 8) References
- FastAPI: https://fastapi.tiangolo.com/
- Uvicorn: https://www.uvicorn.org/
- scikit-learn KMeans: https://scikit-learn.org/stable/modules/generated/sklearn.cluster.KMeans.html
- pdf2image + Poppler: https://github.com/Belval/pdf2image
- Google Cloud Vision: https://cloud.google.com/vision/docs
- OpenAI Python SDK: https://github.com/openai/openai-python
- Supabase JS/Python: https://supabase.com/docs
- Render deploys: https://render.com/docs

Notes to verify
- Supabase table names and schema used by grocery_router (grocery_data) and the Edge Function (results, observations, markers_map) should match your actual database.
- supplement_db.json content should be reviewed to ensure dosage logic aligns with medical guidance for your target audience.

---
Maintenance tips
- Keep secrets out of logs and version control.
- Add CI to run pytest and basic type checks.
- For heavy OCR/LLM usage, consider request quotas, retries, and caching.
