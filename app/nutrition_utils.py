# app/nutrition_utils.py

import os
import json
from openai import OpenAI

client = OpenAI()  # Picks up OPENAI_API_KEY from environment


def categorize_items_with_llm(item_list, store_name=None):
    """
    Uses GPT-4o to categorize grocery items into structured food data with
    original name, cleaned name, category, and optional emoji.
    """

    system_message = {
        "role": "system",
        "content": (
            "You are a nutritionist assistant. Your task is to group scanned grocery receipt items "
            "into broad categories with clean names and optional emojis for UI display."
        )
    }

    prompt_content = (
        f"Receipt items:\n{item_list}\n\n"
        "Format your response as a JSON array, each entry with keys:\n"
        "- item: original item name from receipt\n"
        "- clean: cleaned standardized name\n"
        "- category: broad category (Protein, Dairy, Vegetables, Grains, Snacks, Beverages, Condiments)\n"
        "- emoji: optional emoji\n\n"
        "Example output:\n"
        '[{"item": "Arla Ekologisk Mjölk", "clean": "Organic Milk", "category": "Dairy", "emoji": "🥛"}, '
        '{"item": "Bananer", "clean": "Bananas", "category": "Fruit", "emoji": "🍌"}]'
    )

    if store_name:
        prompt_content = (
            f"The following items were extracted from a {store_name} receipt:\n{item_list}\n\n" + prompt_content
        )

    user_message = {
        "role": "user",
        "content": prompt_content
    }

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[system_message, user_message],
            temperature=0.3
        )
        content = response.choices[0].message.content

        # Clean the response from markdown code blocks
        if content.startswith("```"):
            content = content.strip("`\n\r ")
            if content.lower().startswith("json"):
                content = content[4:].strip()

        return json.loads(content)

    except Exception as e:
        print("[LLM] Failed to categorize items:", e)
        print("[LLM] Raw response content:", content if 'content' in locals() else 'No content')
        return []


def estimate_nutrients(categorized_items):
    """
    For each categorized food, adds nutrient estimates.
    Returns:
    - a list of per-food nutrient data
    - a dictionary of total nutrient intake
    """

    # Simplified mock nutrient database (expand as needed)
    food_nutrient_db = {
        "Tuna": {"Omega-3": 150, "Protein": 25},
        "Milk": {"Calcium": 300, "Vitamin D": 100},
        "Spinach": {"Iron": 3, "Vitamin A": 150, "Vitamin K": 400},
        "Salmon": {"Omega-3": 180, "Protein": 27},
        "Eggs": {"Choline": 250, "Protein": 6},
        "Oat Milk": {"Calcium": 350, "Fiber": 2},
        "Beef": {"Iron": 2.5, "Protein": 26},
        "Apple": {"Fiber": 4, "Vitamin C": 8}
    }

    detailed = []
    totals = {}

    for item in categorized_items:
        name = item.get("clean") or item.get("item")
        category = item.get("category", "Other")

        nutrients = food_nutrient_db.get(name, {})

        # Add to nutrient totals
        for nutrient, value in nutrients.items():
            totals[nutrient] = totals.get(nutrient, 0) + value

        detailed.append({
            "name": name,
            "category": category,
            "nutrients": nutrients
        })

    return detailed, totals