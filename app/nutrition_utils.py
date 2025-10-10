# app/nutrition_utils.py

import os
import json
import re
from typing import List, Dict, Any, Tuple, Optional

from openai import OpenAI

client = OpenAI()  # Picks up OPENAI_API_KEY from environment


# ----------------------------
# Helpers
# ----------------------------

def _strip_code_fence(text: str) -> str:
    if not isinstance(text, str):
        return text
    t = text.strip()
    if t.startswith("```"):
        # remove leading ```json or ``` and trailing ```
        t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s*```$", "", t)
    return t


def _coerce_json_array(text: str) -> List[Dict[str, Any]]:
    t = _strip_code_fence(text)
    try:
        data = json.loads(t)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "items" in data and isinstance(data["items"], list):
            return data["items"]
        raise ValueError("Response is not a JSON array.")
    except Exception:
        # try to find the first valid JSON array in the text
        m = re.search(r"\[[\s\S]*\]", t)
        if m:
            return json.loads(m.group(0))
        raise


def _to_float(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _normalize_unit(u: Optional[str]) -> Optional[str]:
    if not u:
        return None
    s = str(u).strip().lower()
    mapping = {
        "g": "g",
        "gram": "g",
        "grams": "g",
        "kg": "kg",
        "kilogram": "kg",
        "kilograms": "kg",
        "ml": "ml",
        "milliliter": "ml",
        "milliliters": "ml",
        "l": "l",
        "liter": "l",
        "liters": "l",
        "cl": "cl",
        "dl": "dl",
        "oz": "oz",
        "ounce": "oz",
        "ounces": "oz",
        "lb": "lb",
        "pound": "lb",
        "pounds": "lb",
        "count": "count",
        "pcs": "count",
        "pc": "count",
        "piece": "count",
        "pieces": "count",
        "unit": "count",
    }
    return mapping.get(s, s)


def _to_grams(value: float, unit: Optional[str]) -> Optional[float]:
    unit = _normalize_unit(unit)
    if unit is None:
        return None
    if unit == "g":
        return value
    if unit == "kg":
        return value * 1000.0
    if unit == "oz":
        return value * 28.3495
    if unit == "lb":
        return value * 453.592
    # liquids measured in ml/l are NOT grams; return None to avoid mixing
    if unit in ("ml", "l", "cl", "dl"):
        return None
    if unit == "count":
        return None
    return None


def _to_milliliters(value: float, unit: Optional[str]) -> Optional[float]:
    unit = _normalize_unit(unit)
    if unit is None:
        return None
    if unit == "ml":
        return value
    if unit == "l":
        return value * 1000.0
    if unit == "cl":
        return value * 10.0
    if unit == "dl":
        return value * 100.0
    # weight-based units are NOT volume
    if unit in ("g", "kg", "oz", "lb"):
        return None
    if unit == "count":
        return None
    return None


def _infer_totals(entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Given an LLM-extracted entry, compute inferred_total_grams / inferred_total_ml when possible.
    We combine either:
      - quantity + unit (e.g., "750 ml", "1000 g")
      - package_count * package_size_value + package_size_unit (e.g., "2 x 500 g")
    """
    # normalize fields
    quantity = _to_float(entry.get("quantity"))
    unit = _normalize_unit(entry.get("unit"))
    pkg_count = _to_float(entry.get("package_count"))
    pkg_size_val = _to_float(entry.get("package_size_value"))
    pkg_size_unit = _normalize_unit(entry.get("package_size_unit"))

    total_grams: Optional[float] = None
    total_ml: Optional[float] = None

    # case 1: quantity + unit
    if quantity and unit:
        grams = _to_grams(quantity, unit)
        ml = _to_milliliters(quantity, unit)
        if grams is not None:
            total_grams = (total_grams or 0) + grams
        if ml is not None:
            total_ml = (total_ml or 0) + ml

    # case 2: package_count * package_size
    if pkg_count and pkg_size_val and pkg_size_unit:
        grams = _to_grams(pkg_count * pkg_size_val, pkg_size_unit)
        ml = _to_milliliters(pkg_count * pkg_size_val, pkg_size_unit)
        if grams is not None:
            total_grams = (total_grams or 0) + grams
        if ml is not None:
            total_ml = (total_ml or 0) + ml

    # If neither computed, leave as None
    if total_grams is not None:
        entry["inferred_total_grams"] = round(total_grams, 2)
    if total_ml is not None:
        entry["inferred_total_ml"] = round(total_ml, 2)

    # Always keep normalized units
    if unit:
        entry["unit"] = unit
    if pkg_size_unit:
        entry["package_size_unit"] = pkg_size_unit

    return entry


# ----------------------------
# LLM categorization (keeps metrics)
# ----------------------------

def categorize_items_with_llm(item_list: List[str], store_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Uses GPT-4o to categorize grocery items into structured food data with
    original name, cleaned name, category, emoji, and QUANTITY METRICS preserved.
    """
    system_message = {
        "role": "system",
        "content": (
            "You are a nutritionist assistant. Group scanned grocery receipt items into broad categories with clean names "
            "and also EXTRACT METRICS (quantities and units). Return STRICT JSON (no code fences)."
        )
    }

    # Add explicit schema with metrics
    schema_hint = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "item": {"type": "string", "description": "Original line as seen on receipt"},
                "clean": {"type": "string", "description": "Clean standardized name (e.g. 'Bananas', 'Salmon')"},
                "category": {
                    "type": "string",
                    "description": "One of: Protein, Dairy, Vegetables, Fruit, Grains, Snacks, Beverages, Condiments, Other"
                },
                "emoji": {"type": "string"},
                # metrics
                "quantity": {"type": "number", "description": "Numeric quantity if present, e.g., 750, 2"},
                "unit": {"type": "string", "description": "Unit paired with quantity, e.g., g, kg, ml, l, oz, lb, count"},
                "package_count": {"type": "number", "description": "Number of packages if a multipack, e.g., 2 in '2x 500g'"},
                "package_size_value": {"type": "number", "description": "Size per package, e.g., 500 in '2x 500g'"},
                "package_size_unit": {"type": "string", "description": "Unit for size per package, e.g., g, ml"},
                # optional direct totals if the model wants to compute them:
                "inferred_total_grams": {"type": "number"},
                "inferred_total_ml": {"type": "number"},
            },
            "required": ["item", "clean", "category"]
        }
    }

    example = (
        '[{"item":"Arla Mjölk 1L","clean":"Milk","category":"Dairy","emoji":"🥛","quantity":1,"unit":"l",'
        '"inferred_total_ml":1000},'
        '{"item":"Bananer 1.02kg","clean":"Bananas","category":"Fruit","emoji":"🍌","quantity":1.02,"unit":"kg",'
        '"inferred_total_grams":1020},'
        '{"item":"Lax 2x 200g","clean":"Salmon","category":"Protein","emoji":"🐟","package_count":2,'
        '"package_size_value":200,"package_size_unit":"g","inferred_total_grams":400}]'
    )

    prompt_header = (
        f"The following items were extracted from a {store_name} receipt:\n{item_list}\n\n"
        if store_name else
        f"Receipt items:\n{item_list}\n\n"
    )

    user_message = {
        "role": "user",
        "content": (
            prompt_header +
            "Return a JSON array. Each entry MUST include:\n"
            "- item: original item name from receipt\n"
            "- clean: cleaned standardized name\n"
            "- category: broad category (Protein, Dairy, Vegetables, Fruit, Grains, Snacks, Beverages, Condiments, Other)\n"
            "- emoji: optional\n"
            "- quantity + unit when present (e.g., '1.02' + 'kg', '750' + 'ml', '2' + 'count')\n"
            "- OR package_count + package_size_value + package_size_unit (e.g., '2' + '500' + 'g')\n"
            "- You MAY include inferred_total_grams or inferred_total_ml if you compute them.\n\n"
            f"schema: {json.dumps(schema_hint)}\n\n"
            f"example: {example}\n"
        )
    }

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[system_message, user_message],
            temperature=0.2
        )
        content = response.choices[0].message.content or "[]"
        data = _coerce_json_array(content)

        # post-process: normalize units and compute totals if missing
        out = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            entry = dict(entry)
            entry = _infer_totals(entry)
            out.append(entry)

        return out

    except Exception as e:
        print("[LLM] Failed to categorize items:", e)
        print("[LLM] Raw response content:", content if 'content' in locals() else 'No content')
        return []


# ----------------------------
# LLM-based nutrient estimation (optional)
# ----------------------------

def estimate_nutrients_with_llm(categorized_items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    """
    LLM-based nutrient estimation. Sends items + metrics (inferred_total_grams/ml etc.)
    and asks the model to return per-item nutrients and overall totals.
    Returns (detailed_list, totals_dict) with the same shape as estimate_nutrients.
    """
    system_message = {
        "role": "system",
        "content": (
            "You are a nutrition estimation assistant. Given grocery items with weights/volumes, "
            "estimate key nutrient amounts realistically using your general nutrition knowledge. "
            "Return STRICT JSON only."
        )
    }

    minimal_items = []
    for it in categorized_items:
        minimal_items.append({
            "name": it.get("clean") or it.get("item"),
            "category": it.get("category"),
            "quantity": it.get("quantity"),
            "unit": it.get("unit"),
            "package_count": it.get("package_count"),
            "package_size_value": it.get("package_size_value"),
            "package_size_unit": it.get("package_size_unit"),
            "inferred_total_grams": it.get("inferred_total_grams"),
            "inferred_total_ml": it.get("inferred_total_ml"),
        })

    schema_hint = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "category": {"type": "string"},
                        "basis_used": {"type": "string", "description": "100g or 100ml or other"},
                        "weight_grams": {"type": "number"},
                        "volume_ml": {"type": "number"},
                        "nutrients": {"type": "object", "additionalProperties": {"type": "number"}}
                    },
                    "required": ["name", "nutrients"]
                }
            },
            "totals": {"type": "object", "additionalProperties": {"type": "number"}}
        },
        "required": ["items", "totals"]
    }

    user_message = {
        "role": "user",
        "content": (
            "Given these grocery items with metrics, estimate nutrients realistically. "
            "Prefer scaling by provided grams or ml. If both are missing, make a reasonable default assumption. "
            "Focus on common nutrients (Protein, Fiber, Omega-3, Calcium, Iron, Magnesium, Vitamin D, Vitamin C, etc.). "
            "Return ONLY JSON matching the schema.\n\n"
            f"schema: {json.dumps(schema_hint)}\n\n"
            f"items: {json.dumps(minimal_items)}\n"
        )
    }

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[system_message, user_message],
            temperature=0.2,
            max_tokens=1200,
        )
        content = resp.choices[0].message.content or "{}"
        data = json.loads(_strip_code_fence(content))

        detailed = []
        for it in data.get("items", []):
            detailed.append({
                "name": it.get("name"),
                "category": it.get("category"),
                "basis_used": it.get("basis_used"),
                "weight_grams": it.get("weight_grams"),
                "volume_ml": it.get("volume_ml"),
                "nutrients": it.get("nutrients") or {}
            })
        totals = data.get("totals") or {}
        # coerce numbers just in case
        totals = {k: float(v) for k, v in totals.items() if isinstance(v, (int, float, str)) and str(v).replace('.', '', 1).isdigit()}
        return detailed, totals

    except Exception as e:
        print("[LLM] Nutrient estimation failed:", e)
        print("[LLM] Raw response content:", content if 'content' in locals() else 'No content')
        return [], {}


# ----------------------------
# Local nutrient estimation (fallback; per-100g/100ml table + scaling)
# ----------------------------

def estimate_nutrients(categorized_items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    """
    Estimate nutrients for categorized_items.

    If env USE_LLM_NUTRIENTS=1 -> use LLM-based estimator (estimate_nutrients_with_llm).
    Else -> use local per-100g/100ml table scaled by inferred grams/ml or category defaults.

    Returns:
      - detailed: list of per-food nutrient data with the weight/volume used
      - totals: dict of total nutrient intake
    """
    if os.getenv("USE_LLM_NUTRIENTS") == "1":
        return estimate_nutrients_with_llm(categorized_items)

    # Per-100g or per-100ml approximate nutrient densities (toy examples; expand as needed)
    # Keys are clean names; try to keep generic. Values include 'basis': '100g' or '100ml'.
    food_nutrient_db = {
        "Tuna": {"basis": "100g", "Omega-3": 150, "Protein": 25},
        "Milk": {"basis": "100ml", "Calcium": 120, "Vitamin D": 50, "Protein": 3.4},
        "Spinach": {"basis": "100g", "Iron": 3, "Vitamin A": 150, "Vitamin K": 400},
        "Salmon": {"basis": "100g", "Omega-3": 180, "Protein": 20},
        "Eggs": {"basis": "100g", "Choline": 294, "Protein": 13},
        "Oat Milk": {"basis": "100ml", "Calcium": 120, "Fiber": 0.8},
        "Beef": {"basis": "100g", "Iron": 2.5, "Protein": 26},
        "Apple": {"basis": "100g", "Fiber": 2.4, "Vitamin C": 4.6},
        "Bananas": {"basis": "100g", "Potassium": 358, "Fiber": 2.6, "Vitamin B6": 0.4},
        "Banana": {"basis": "100g", "Potassium": 358, "Fiber": 2.6, "Vitamin B6": 0.4},
        "Yogurt": {"basis": "100g", "Calcium": 121, "Protein": 10},
        "Greek Yogurt": {"basis": "100g", "Calcium": 110, "Protein": 10},
        "Quinoa": {"basis": "100g", "Protein": 4.4, "Magnesium": 64, "Fiber": 2.8},
        "Cucumber": {"basis": "100g", "Vitamin K": 16, "Potassium": 147},
        "Rice": {"basis": "100g", "Carbohydrate": 28},
        "Jasmine Rice": {"basis": "100g", "Carbohydrate": 28},
        "Fusilli Pasta": {"basis": "100g", "Carbohydrate": 25, "Protein": 5},
        "Oats": {"basis": "100g", "Fiber": 10, "Magnesium": 177},
        "Almonds": {"basis": "100g", "Magnesium": 268, "Vitamin E": 25.6, "Protein": 21},
    }

    # Default assumed weights/volumes if metrics missing (very rough)
    default_weight_g_by_category = {
        "Protein": 150.0,
        "Vegetables": 100.0,
        "Fruit": 120.0,
        "Grains": 75.0,
        "Snacks": 50.0,
        "Dairy": 200.0,  # might be yogurt/cheese; will switch to volume if beverage
        "Condiments": 15.0,
        "Beverages": 250.0,  # ml basis
        "Other": 100.0,
    }

    detailed: List[Dict[str, Any]] = []
    totals: Dict[str, float] = {}

    for item in categorized_items:
        clean_name = item.get("clean") or item.get("item") or "Unknown"
        category = item.get("category", "Other")

        # Look up nutrient profile
        profile = food_nutrient_db.get(clean_name)
        # Try a simpler fallback by stripping plural
        if not profile and isinstance(clean_name, str) and clean_name.endswith("s"):
            profile = food_nutrient_db.get(clean_name[:-1])

        # Decide whether to use weight or volume
        inferred_g = item.get("inferred_total_grams")
        inferred_ml = item.get("inferred_total_ml")

        basis_used = None
        amount_scalar = None

        if profile:
            basis = profile.get("basis", "100g")
            if basis == "100g":
                if inferred_g:
                    basis_used = "100g"
                    amount_scalar = float(inferred_g) / 100.0
                elif category == "Beverages" and inferred_ml:
                    basis_used = "100g"
                    # naive convert ml->g ~1:1 if density ~ water (rough fallback)
                    amount_scalar = float(inferred_ml) / 100.0
                else:
                    basis_used = "100g"
                    amount_scalar = default_weight_g_by_category.get(category, 100.0) / 100.0
            elif basis == "100ml":
                if inferred_ml:
                    basis_used = "100ml"
                    amount_scalar = float(inferred_ml) / 100.0
                else:
                    basis_used = "100ml"
                    amount_scalar = default_weight_g_by_category.get("Beverages", 250.0) / 100.0
        else:
            # Unknown food: record zero nutrients but still show chosen weight/volume for transparency
            if inferred_ml:
                basis_used = "100ml"
                amount_scalar = float(inferred_ml) / 100.0
            elif inferred_g:
                basis_used = "100g"
                amount_scalar = float(inferred_g) / 100.0
            else:
                # fallback by category: beverages as ml, others as g
                if category == "Beverages":
                    basis_used = "100ml"
                    amount_scalar = default_weight_g_by_category.get("Beverages", 250.0) / 100.0
                else:
                    basis_used = "100g"
                    amount_scalar = default_weight_g_by_category.get(category, 100.0) / 100.0

        # Accumulate nutrients
        nutrients_out: Dict[str, float] = {}
        if profile:
            for nutrient, per100 in profile.items():
                if nutrient == "basis":
                    continue
                try:
                    nutrients_out[nutrient] = round(float(per100) * float(amount_scalar), 4)
                    totals[nutrient] = totals.get(nutrient, 0.0) + nutrients_out[nutrient]
                except Exception:
                    # Skip bad values silently
                    pass

        # record in detailed list
        detailed.append({
            "name": clean_name,
            "category": category,
            "basis_used": basis_used,
            "weight_grams": float(inferred_g) if inferred_g is not None else None,
            "volume_ml": float(inferred_ml) if inferred_ml is not None else None,
            "nutrients": nutrients_out
        })

    return detailed, totals