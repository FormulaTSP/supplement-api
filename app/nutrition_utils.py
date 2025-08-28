# app/nutrition_utils.py

import os
import json
from typing import Any, Dict, List, Tuple

# OpenAI client (graceful fallback if key not set)
try:
    from openai import OpenAI
    _openai_available = True
except Exception:  # package missing or import error
    _openai_available = False
    OpenAI = None  # type: ignore

def _get_openai_client():
    """
    Returns an OpenAI client if OPENAI_API_KEY is present and package is installed;
    otherwise returns None so we can fail gracefully.
    """
    if not _openai_available:
        return None
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        return OpenAI()  # picks up OPENAI_API_KEY from env
    except Exception:
        return None

_client = _get_openai_client()


def categorize_items_with_llm(item_list: Any, store_name: str | None = None) -> List[Dict[str, Any]]:
    """
    Uses GPT-4o to analyze grocery items and return structured nutrition data.
    Returns a JSON-like Python list of objects with:
      - name (str): cleaned food name
      - form (str): fresh, frozen, dried, cooked, etc.
      - amount_g (float|int): estimated weight in grams
      - category (str): broad category (Fruit, Vegetable, Dairy, Protein, Grain, etc.)
      - nutrients_per_100g (dict): keys like vitamins/minerals/macros (best-effort)
    """
    if _client is None:
        # No key or OpenAI package missing; return empty so callers can decide a fallback path.
        return []

    system_message = {
        "role": "system",
        "content": (
            "You are a precise nutrition assistant. For each grocery item, return a clean food name, "
            "the form (fresh, frozen, dried, cooked, etc.), the estimated amount in grams, a general category, "
            "and a detailed list of nutrients per 100g. Use real-world data. Only include fields you are confident in."
        )
    }

    prompt_content = (
        f"Receipt items:\n{json.dumps(item_list)}\n\n"
        "Return a JSON array. Each object must contain:\n"
        "- name: cleaned food name (e.g. 'Mango')\n"
        "- form: fresh, dried, frozen, cooked, etc.\n"
        "- amount_g: estimated weight in grams\n"
        "- category: broad food category (Fruit, Vegetable, Dairy, Protein, Grain, etc.)\n"
        "- nutrients_per_100g: dictionary with as many of the following as possible:\n"
        "    Vit A (µg), B1 (mg), B2 (mg), B3 (mg), B5 (mg), B6 (mg), B7 (µg), B9 (µg), B12 (µg),\n"
        "    Vit C (mg), Vit D (µg), Vit E (mg), Vit K (µg), Ca (mg), Fe (mg), Se (µg), Cu (mg),\n"
        "    Mg (mg), Zn (mg), Omega-3 (EPA/DHA), Probiotika, calories, carbs, protein, fats, fiber"
    )

    user_message = {"role": "user", "content": prompt_content}

    response = _client.chat.completions.create(  # type: ignore[union-attr]
        model="gpt-4o",
        messages=[system_message, user_message],
        temperature=0.4,
    )

    try:
        parsed = json.loads(response.choices[0].message.content)  # type: ignore[index]
        # Ensure a list is returned
        return parsed if isinstance(parsed, list) else []
    except Exception as e:
        print("Error parsing response:", e)
        try:
            print("Raw response:", response.choices[0].message.content)  # type: ignore[index]
        except Exception:
            pass
        return []


def estimate_nutrients(categorized: Any) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Compatibility stub so receipt_ocr.py can import and call this.

    Parameters
    ----------
    categorized : can be:
      - list of dicts/strings, or
      - dict with key "items" holding that list

    Returns
    -------
    (consumed_foods, dietary_intake)
      consumed_foods : list[dict] with normalized items (name, quantity, unit, optional macro placeholders)
      dietary_intake : dict with "totals" holding summed macros (zeros by default here)

    Notes
    -----
    - This stub returns zeros by default. If the upstream categorizer already put numeric fields
      on items (e.g., kcal, protein_g, carbs_g, fat_g, fiber_g, sugar_g, sodium_mg), you can uncomment
      the summation block below to aggregate them.
    - Replace this stub with your real implementation when ready.
    """

    # Normalize to a list of items
    if isinstance(categorized, dict) and "items" in categorized:
        items = categorized.get("items") or []
    else:
        items = categorized or []

    consumed: List[Dict[str, Any]] = []

    totals: Dict[str, float] = {
        "kcal": 0.0,
        "protein_g": 0.0,
        "carbs_g": 0.0,
        "fat_g": 0.0,
        "fiber_g": 0.0,
        "sugar_g": 0.0,
        "sodium_mg": 0.0,
    }

    for it in items:
        if isinstance(it, dict):
            name = it.get("name") or it.get("item") or str(it)
            qty = it.get("quantity") or 1
            unit = it.get("unit") or "item"
            kcal = float(it.get("kcal", 0) or 0)
            protein_g = float(it.get("protein_g", 0) or 0)
            carbs_g = float(it.get("carbs_g", 0) or 0)
            fat_g = float(it.get("fat_g", 0) or 0)
            fiber_g = float(it.get("fiber_g", 0) or 0)
            sugar_g = float(it.get("sugar_g", 0) or 0)
            sodium_mg = float(it.get("sodium_mg", 0) or 0)
        else:
            name = str(it)
            qty = 1
            unit = "item"
            kcal = protein_g = carbs_g = fat_g = fiber_g = sugar_g = sodium_mg = 0.0

        consumed.append(
            {
                "name": name,
                "quantity": qty,
                "unit": unit,
                "kcal": kcal,
                "protein_g": protein_g,
                "carbs_g": carbs_g,
                "fat_g": fat_g,
                "fiber_g": fiber_g,
                "sugar_g": sugar_g,
                "sodium_mg": sodium_mg,
            }
        )

        # If you want to sum any provided values right now, uncomment:
        # totals["kcal"]      += kcal
        # totals["protein_g"] += protein_g
        # totals["carbs_g"]   += carbs_g
        # totals["fat_g"]     += fat_g
        # totals["fiber_g"]   += fiber_g
        # totals["sugar_g"]   += sugar_g
        # totals["sodium_mg"] += sodium_mg

    dietary_intake: Dict[str, Any] = {"totals": totals}
    return consumed, dietary_intake