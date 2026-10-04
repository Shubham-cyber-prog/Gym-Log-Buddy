"""
parser.py - Workout Text Parser using Local Ollama

Converts messy plain English workout descriptions into structured JSON
using a local Ollama instance running the gemma3 model.
"""

import json
from typing import Dict, Any, List, Optional
import requests

# Model name configuration (MUST be in ONE constant)
MODEL_NAME = "gemma3"
OLLAMA_URL = "http://localhost:11434/api/generate"
REQUEST_TIMEOUT = 120  # seconds

MISSING_OLLAMA_MSG = "Start Ollama and run: ollama pull gemma3"

PROMPT_TEMPLATE = """You are a fitness data extraction assistant. Your job is to extract workout exercises from messy plain English notes and return ONLY a valid JSON object matching the exact schema below.

JSON SCHEMA:
{
  "exercises": [
    {
      "exercise": "string (standard exercise name, e.g. 'Bench Press', 'Incline Dumbbell Press')",
      "weight_kg": float or null (weight in kilograms; null if bodyweight or missing),
      "reps": int or null (repetitions per set; null if missing),
      "sets": int or null (number of sets; null if missing)
    }
  ]
}

RULES:
1. Normalize abbreviations:
   - "db" -> "Dumbbell"
   - "bb" -> "Barbell"
   - "bench" -> "Bench Press"
   - "incline db" -> "Incline Dumbbell Press"
   - "ohp" -> "Overhead Press"
   - "squat" -> "Squat"
   - "dl" / "deadlift" -> "Deadlift"
2. Syntax interpretations:
   - "4x4" means 4 sets of 4 reps (sets: 4, reps: 4).
   - "7x3" means 7 reps, 3 sets (or sets x reps).
   - "30 x 12 x 4" means 30 kg, 12 reps, 4 sets (weight: 30, reps: 12, sets: 4).
3. Weight units (CRITICAL):
   - The DEFAULT weight unit is KILOGRAMS (kg).
   - If a number has no unit specified (e.g. "leg press 120", "lunges 24"), treat it as KILOGRAMS (120.0 kg, 24.0 kg). DO NOT convert to kg unless the input explicitly says "lb", "lbs", or "pounds".
   - ONLY convert from lbs to kg if the unit "lb", "lbs", or "pounds" is explicitly written (multiply by 0.4536 and round to 1 decimal place).
   - If no weight or bodyweight (e.g., push-ups, burpees), use null.
4. Non-exercise or vague notes (CRITICAL):
   - If the input does not mention any explicit exercise, or is just casual diary commentary (e.g. "back day was brutal", "went for a run", "stretched in the morning"), return an EMPTY list: {"exercises": []}.
   - NEVER hallucinate or guess exercises if they were not explicitly named.
5. Output ONLY the JSON object. Do not wrap in markdown quotes if possible, and include no extra explanations.

FEW-SHOT EXAMPLES:

Example 1:
Input: "incline bench 50 10x3, romanian deadlift 90 8 reps 3 sets"
Output:
{
  "exercises": [
    {"exercise": "Incline Bench Press", "weight_kg": 50.0, "reps": 10, "sets": 3},
    {"exercise": "Romanian Deadlift", "weight_kg": 90.0, "reps": 8, "sets": 3}
  ]
}

Example 2:
Input: "db lateral raise 20 lbs 15 reps 4 sets, chin-ups 10 reps 3 sets"
Output:
{
  "exercises": [
    {"exercise": "Dumbbell Lateral Raise", "weight_kg": 9.1, "reps": 15, "sets": 4},
    {"exercise": "Chin-Up", "weight_kg": null, "reps": 10, "sets": 3}
  ]
}

Example 3:
Input: "took a recovery walk in the park today, slept 8 hours"
Output:
{
  "exercises": []
}

USER INPUT:
"{user_input}"
"""


def validate_parsed_data(data: Any) -> tuple[bool, Optional[str], List[Dict[str, Any]]]:
    """
    Validates that the parsed data strictly conforms to the expected schema.
    Returns:
      (is_valid, error_message, sanitized_exercises)
    """
    if not isinstance(data, dict):
        return False, "Response must be a JSON object", []

    exercises = data.get("exercises")
    if not isinstance(exercises, list):
        return False, "Missing 'exercises' array in response", []

    sanitized = []
    for idx, item in enumerate(exercises):
        if not isinstance(item, dict):
            return False, f"Item {idx} is not an object", []

        name = item.get("exercise")
        if not name or not isinstance(name, str) or not name.strip():
            return False, f"Item {idx} is missing a valid 'exercise' name string", []

        weight = item.get("weight_kg")
        if weight is not None:
            if not isinstance(weight, (int, float)) or weight <= 0:
                return False, f"Item {idx} ('{name}') weight_kg must be positive number or null", []
            weight = round(float(weight), 1)

        reps = item.get("reps")
        if reps is not None:
            if not isinstance(reps, int) or reps <= 0:
                return False, f"Item {idx} ('{name}') reps must be positive integer or null", []

        sets = item.get("sets")
        if sets is not None:
            if not isinstance(sets, int) or sets <= 0:
                return False, f"Item {idx} ('{name}') sets must be positive integer or null", []

        # Reject items where weight, reps, and sets are all null (e.g. vague hallucinated item)
        if weight is None and reps is None and sets is None:
            continue

        sanitized.append({
            "exercise": name.strip(),
            "weight_kg": weight,
            "reps": reps,
            "sets": sets
        })

    return True, None, sanitized


def call_ollama(prompt: str) -> tuple[bool, Optional[Dict[str, Any]], Optional[str], Optional[str]]:
    """
    Calls Ollama API with format='json' and stream=False.
    Returns:
      (success, parsed_json_dict, error_message, raw_response_text)
    """
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.ConnectionError:
        return False, None, MISSING_OLLAMA_MSG, None
    except requests.exceptions.Timeout:
        return False, None, f"Ollama request timed out after {REQUEST_TIMEOUT} seconds.", None
    except requests.exceptions.RequestException as e:
        return False, None, f"Network error communicating with Ollama: {e}", None

    if response.status_code == 404:
        return False, None, MISSING_OLLAMA_MSG, None

    if response.status_code != 200:
        return False, None, f"Ollama returned HTTP error {response.status_code}: {response.text}", None

    try:
        res_json = response.json()
        raw_output = res_json.get("response", "")
        parsed = json.loads(raw_output)
        return True, parsed, None, raw_output
    except (json.JSONDecodeError, ValueError) as e:
        raw_str = res_json.get("response", "") if "res_json" in locals() else ""
        return False, None, f"Failed to decode model output as JSON: {e}", raw_str


def parse_workout(raw_text: str) -> Dict[str, Any]:
    """
    Main entry point for parsing workout text into structured exercises.
    Includes 1 retry with a stricter prompt on validation failure.
    Never crashes, always returns a dictionary:
      {"success": bool, "exercises": list, "error": Optional[str], "raw_response": Optional[str]}
    """
    if not raw_text or not raw_text.strip():
        return {
            "success": True,
            "exercises": [],
            "error": "Empty workout text provided.",
            "raw_response": None
        }

    # Attempt 1: Standard Prompt
    prompt1 = PROMPT_TEMPLATE.replace("{user_input}", raw_text.strip())
    ok, data, err, raw_output = call_ollama(prompt1)

    if not ok:
        if err == MISSING_OLLAMA_MSG:
            print(f"\n[Gym Log Buddy] {MISSING_OLLAMA_MSG}\n")
        return {
            "success": False,
            "exercises": [],
            "error": err,
            "raw_response": raw_output
        }

    is_valid, val_err, sanitized = validate_parsed_data(data)
    if is_valid:
        return {
            "success": True,
            "exercises": sanitized,
            "error": None,
            "raw_response": raw_output
        }

    # Attempt 2: Stricter retry prompt
    retry_prompt = (
        f"{prompt1}\n\n"
        f"CRITICAL FIX REQUIRED: Your previous output failed validation with error: '{val_err}'.\n"
        f"Ensure output is valid JSON matching {{\"exercises\": [{{\"exercise\": str, \"weight_kg\": float|null, \"reps\": int|null, \"sets\": int|null}}]}}."
    )
    ok2, data2, err2, raw_output2 = call_ollama(retry_prompt)
    if not ok2:
        return {
            "success": False,
            "exercises": [],
            "error": err2,
            "raw_response": raw_output2
        }

    is_valid2, val_err2, sanitized2 = validate_parsed_data(data2)
    if is_valid2:
        return {
            "success": True,
            "exercises": sanitized2,
            "error": None,
            "raw_response": raw_output2
        }

    # If still invalid after 1 retry, return clear error without crashing
    return {
        "success": False,
        "exercises": [],
        "error": f"Failed validation after retry: {val_err2}",
        "raw_response": raw_output2
    }
