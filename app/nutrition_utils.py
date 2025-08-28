# app/nutrition_utils.py

import os
import json
from openai import OpenAI

client = OpenAI()  # Picks up OPENAI_API_KEY from environment


def categorize_items_with_llm(item_list, store_name=None):
    """
    Uses GPT-4o to analyze grocery items and return structured nutrition data:
    - Clean name
    - Form (fresh/frozen/dried/etc.)
    - Estimated amount (g)
    - Category
    - Nutrients per 100g (complete list)
    """

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

    user_message = {
        "role": "user",
        "content": prompt_content
    }

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[system_message, user_message],
        temperature=0.4
    )

    try:
        parsed = json.loads(response.choices[0].message.content)
        return parsed
    except Exception as e:
        print("Error parsing response:", e)
        print("Raw response:", response.choices[0].message.content)
        return []