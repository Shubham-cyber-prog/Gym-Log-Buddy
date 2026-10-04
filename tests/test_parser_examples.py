"""
test_parser_examples.py - Test Suite for Gym Log Buddy

Covers:
1. Parsing of at least 5 varied / messy inputs (via mock and live if available)
   - Shorthand 8x3
   - Imperial lbs conversion to kg
   - Missing weights (bodyweight exercises)
   - Complex multi-exercise notation
   - Standard example from prompt
2. Schema and type validation rules (positive numbers, string names)
3. Offline Ollama error handling (graceful error message, zero crashes)
4. Progressive overload rules (suggest.py)
5. Database operations (db.py) with isolated SQLite
"""

import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock

# Add parent directory to path so imports work
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import parser
import db
import suggest


# ==========================================
# 1. 5 Inputs for Workout Parsing
# ==========================================

TEST_INPUT_1 = "bench 60kg 8 reps 3 sets, incline db 22 x 10 x 3, squat 80 5x5"
EXPECTED_1 = [
    {"exercise": "Bench Press", "weight_kg": 60.0, "reps": 8, "sets": 3},
    {"exercise": "Incline Dumbbell Press", "weight_kg": 22.0, "reps": 10, "sets": 3},
    {"exercise": "Squat", "weight_kg": 80.0, "reps": 5, "sets": 5},
]

TEST_INPUT_2 = "bench 60 8x3"
EXPECTED_2 = [
    {"exercise": "Bench Press", "weight_kg": 60.0, "reps": 8, "sets": 3}
]

TEST_INPUT_3 = "db shoulder press 50 lbs 10 reps 3 sets"
EXPECTED_3 = [
    {"exercise": "Dumbbell Shoulder Press", "weight_kg": 22.7, "reps": 10, "sets": 3}
]

TEST_INPUT_4 = "pullups 3 sets 10 reps, dips 12 reps"
EXPECTED_4 = [
    {"exercise": "Pull-Up", "weight_kg": None, "reps": 10, "sets": 3},
    {"exercise": "Dips", "weight_kg": None, "reps": 12, "sets": 1}
]

TEST_INPUT_5 = "deadlift 100 5x5, bb curl 30kg 10 reps 4 sets"
EXPECTED_5 = [
    {"exercise": "Deadlift", "weight_kg": 100.0, "reps": 5, "sets": 5},
    {"exercise": "Barbell Curl", "weight_kg": 30.0, "reps": 10, "sets": 4}
]


@pytest.mark.parametrize("raw_input,expected_exercises", [
    (TEST_INPUT_1, EXPECTED_1),
    (TEST_INPUT_2, EXPECTED_2),
    (TEST_INPUT_3, EXPECTED_3),
    (TEST_INPUT_4, EXPECTED_4),
    (TEST_INPUT_5, EXPECTED_5),
])
def test_parse_workout_with_mocked_ollama(raw_input, expected_exercises):
    """
    Tests end-to-end parsing flow across 5 distinct messy workout formats
    using mocked Ollama response to verify parsing pipeline deterministically.
    """
    mock_response = {"exercises": expected_exercises}
    with patch("parser.call_ollama", return_value=(True, mock_response, None, json.dumps(mock_response))):
        res = parser.parse_workout(raw_input)
        assert res["success"] is True, f"Failed on input: {raw_input}"
        assert len(res["exercises"]) == len(expected_exercises)
        for actual, exp in zip(res["exercises"], expected_exercises):
            assert actual["exercise"] == exp["exercise"]
            assert actual["weight_kg"] == exp["weight_kg"]
            assert actual["reps"] == exp["reps"]
            assert actual["sets"] == exp["sets"]


# ==========================================
# 2. Schema Validation Tests
# ==========================================

def test_validate_parsed_data_valid():
    sample = {
        "exercises": [
            {"exercise": "Bench Press", "weight_kg": 60, "reps": 8, "sets": 3},
            {"exercise": "Pull-Up", "weight_kg": None, "reps": 10, "sets": None}
        ]
    }
    is_valid, err, sanitized = parser.validate_parsed_data(sample)
    assert is_valid is True
    assert err is None
    assert len(sanitized) == 2
    assert sanitized[0]["weight_kg"] == 60.0


def test_validate_parsed_data_invalid_types():
    # Negative weight
    bad_sample_1 = {"exercises": [{"exercise": "Squat", "weight_kg": -20, "reps": 5, "sets": 5}]}
    is_valid, err, _ = parser.validate_parsed_data(bad_sample_1)
    assert is_valid is False
    assert "positive number" in err

    # Zero reps
    bad_sample_2 = {"exercises": [{"exercise": "Squat", "weight_kg": 80, "reps": 0, "sets": 5}]}
    is_valid, err, _ = parser.validate_parsed_data(bad_sample_2)
    assert is_valid is False
    assert "reps must be positive" in err

    # Missing exercise name
    bad_sample_3 = {"exercises": [{"exercise": "", "weight_kg": 80, "reps": 5, "sets": 5}]}
    is_valid, err, _ = parser.validate_parsed_data(bad_sample_3)
    assert is_valid is False
    assert "missing a valid 'exercise' name" in err


def test_empty_input_handling():
    res = parser.parse_workout("")
    assert res["success"] is True
    assert res["exercises"] == []


# ==========================================
# 3. Ollama Error & Offline Handling
# ==========================================

def test_ollama_offline_behavior():
    """
    Verifies that when Ollama is unreachable, parser returns the exact required message:
    'Start Ollama and run: ollama pull gemma3' and never crashes.
    """
    with patch("requests.post", side_effect=parser.requests.exceptions.ConnectionError):
        res = parser.parse_workout("bench 60kg 8 reps 3 sets")
        assert res["success"] is False
        assert res["error"] == "Start Ollama and run: ollama pull gemma3"
        assert res["exercises"] == []


def test_ollama_404_missing_model():
    """Verifies that missing model / 404 returns start instructions."""
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    with patch("requests.post", return_value=mock_resp):
        res = parser.parse_workout("bench 60kg 8 reps 3 sets")
        assert res["success"] is False
        assert res["error"] == "Start Ollama and run: ollama pull gemma3"


# ==========================================
# 4. Progressive Overload Rules (suggest.py)
# ==========================================

def test_progressive_overload_high_reps():
    """When reps >= 10, suggest +2.5 kg and 8 reps."""
    sug = suggest.get_suggestion(last_weight_kg=60.0, last_reps=10, last_sets=3)
    assert "+2.5 kg (62.5 kg) x 8 reps" in sug


def test_progressive_overload_higher_reps():
    """When reps > 10 (e.g. 12), suggest +2.5 kg and 8 reps."""
    sug = suggest.get_suggestion(last_weight_kg=22.0, last_reps=12, last_sets=3)
    assert "+2.5 kg (24.5 kg) x 8 reps" in sug


def test_progressive_overload_sub_ten_reps():
    """When reps < 10 (e.g. 8), suggest same weight and +1 rep."""
    sug = suggest.get_suggestion(last_weight_kg=60.0, last_reps=8, last_sets=3)
    assert "Same weight (60.0 kg) x 9 reps (+1 rep)" in sug


def test_progressive_overload_bodyweight():
    """Bodyweight exercises with reps >= 10 suggest adding weight."""
    sug = suggest.get_suggestion(last_weight_kg=None, last_reps=12, last_sets=3)
    assert "+2.5 kg (weighted) x 8 reps" in sug

    # Under 10 reps
    sug_sub = suggest.get_suggestion(last_weight_kg=None, last_reps=7, last_sets=3)
    assert "Same weight (bodyweight) x 8 reps (+1 rep)" in sug_sub


# ==========================================
# 5. Database Operations (db.py)
# ==========================================

def test_db_operations(tmp_path):
    test_db_path = str(tmp_path / "test_gym.db")

    # 1. Initialize
    db.init_db(test_db_path)

    # 2. Save workout
    sample_items = [
        {"exercise": "Bench Press", "weight_kg": 60.0, "reps": 8, "sets": 3},
        {"exercise": "Squat", "weight_kg": 80.0, "reps": 5, "sets": 5}
    ]
    saved_count = db.save_workout("2026-10-01", sample_items, "bench 60 8x3, squat 80 5x5", test_db_path)
    assert saved_count == 2

    # 3. Query last session
    bench_last = db.get_last_session("Bench Press", test_db_path)
    assert bench_last is not None
    assert bench_last["exercise"] == "Bench Press"
    assert bench_last["weight_kg"] == 60.0
    assert bench_last["reps"] == 8

    # Case insensitive lookup
    bench_lower = db.get_last_session("bench press", test_db_path)
    assert bench_lower is not None
    assert bench_lower["weight_kg"] == 60.0

    # 4. Save second session on later date
    second_items = [
        {"exercise": "Bench Press", "weight_kg": 62.5, "reps": 8, "sets": 3}
    ]
    db.save_workout("2026-10-03", second_items, "bench 62.5 8x3", test_db_path)

    # Last session should now be the new one
    bench_updated = db.get_last_session("Bench Press", test_db_path)
    assert bench_updated["date"] == "2026-10-03"
    assert bench_updated["weight_kg"] == 62.5

    # 5. Get all logs
    all_logs = db.get_all_logs(test_db_path)
    assert len(all_logs) == 3

    # 6. Get unique exercises
    exercises = db.get_exercises(test_db_path)
    assert sorted(exercises) == ["Bench Press", "Squat"]


# ==========================================
# 6. Exercise Name Normalization & Deduplication Tests
# ==========================================

def test_normalize_exercise_name():
    """
    Verifies that normalize_exercise_name creates a canonical key:
    - 'Pull-Ups', 'Pullups', 'pull up', and 'pullup' produce the exact same key.
    - 'Bench Press' and 'Incline Bench Press' remain separate.
    - Plurals like 'Dips' vs 'dip', 'Squats' vs 'squat' match.
    """
    pullup_keys = [
        db.normalize_exercise_name("Pull-Ups"),
        db.normalize_exercise_name("Pullups"),
        db.normalize_exercise_name("pull up"),
        db.normalize_exercise_name("pullup")
    ]
    assert all(k == "pullup" for k in pullup_keys), f"Pullup keys differ: {pullup_keys}"

    bench_key = db.normalize_exercise_name("Bench Press")
    incline_key = db.normalize_exercise_name("Incline Bench Press")
    assert bench_key != incline_key
    assert bench_key == "benchpress"
    assert incline_key == "inclinebenchpress"

    assert db.normalize_exercise_name("Dips") == db.normalize_exercise_name("dip") == "dip"
    assert db.normalize_exercise_name("Squats") == db.normalize_exercise_name("squat") == "squat"


def test_db_exercise_normalization_and_deduplication(tmp_path):
    """
    Verifies that db.get_last_session matches variations of an exercise name,
    and db.get_exercises deduplicates them while displaying the most recent name.
    """
    test_db_path = str(tmp_path / "test_norm_gym.db")
    db.init_db(test_db_path)

    # 1. Log as 'Pull-Ups' on Day 1
    db.save_workout(
        "2026-10-01",
        [{"exercise": "Pull-Ups", "weight_kg": None, "reps": 8, "sets": 3}],
        "pullups 8 reps 3 sets",
        test_db_path
    )

    # Lookup using 'pull up' should match
    session1 = db.get_last_session("pull up", test_db_path)
    assert session1 is not None
    assert session1["exercise"] == "Pull-Ups"
    assert session1["reps"] == 8

    # 2. Log as 'Pullups' on Day 2
    db.save_workout(
        "2026-10-02",
        [{"exercise": "Pullups", "weight_kg": None, "reps": 10, "sets": 3}],
        "pullups 10 reps 3 sets",
        test_db_path
    )

    # Lookup using 'Pull-Ups' should return the Day 2 session
    session2 = db.get_last_session("Pull-Ups", test_db_path)
    assert session2 is not None
    assert session2["date"] == "2026-10-02"
    assert session2["reps"] == 10
    assert session2["exercise"] == "Pullups"

    # get_exercises should deduplicate and return only the most recent display name
    unique_exercises = db.get_exercises(test_db_path)
    assert unique_exercises == ["Pullups"]


# ==========================================
# 7. Prompt Leakage Prevention Tests
# ==========================================

def test_prompt_template_has_no_test_leakage():
    """
    Verifies that parser.PROMPT_TEMPLATE contains zero test inputs from live_check.py:
    Neither the full input string nor any comma-delimited segment > 10 characters
    is present in PROMPT_TEMPLATE (case-insensitive check).
    """
    from tests.live_check import TEST_CASES

    template_lower = parser.PROMPT_TEMPLATE.lower()

    for tc in TEST_CASES:
        raw_input = tc["input"].strip()
        # 1. Full input check
        assert raw_input.lower() not in template_lower, (
            f"Test leakage detected! Full input '{raw_input}' found in PROMPT_TEMPLATE."
        )

        # 2. Comma-separated parts (> 10 characters)
        parts = [p.strip() for p in raw_input.split(",") if len(p.strip()) > 10]
        for part in parts:
            assert part.lower() not in template_lower, (
                f"Test leakage detected! Segment '{part}' from '{raw_input}' found in PROMPT_TEMPLATE."
            )


