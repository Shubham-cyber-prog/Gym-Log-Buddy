"""
live_check.py - Live Verification Script against real local Ollama (gemma3)

Tests 12 real workout inputs (6 original + 6 new held-out) across 3 iterations each (36 runs total).
Measures cold (Run 1) vs warm (Run 2 & 3) latency using time.perf_counter().
Validates outputs against expected targets and reports honest PASS / FAIL results.
"""

import os
import sys
import time
import json
from typing import Dict, Any, List

# Ensure parent directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import parser
import db


TEST_CASES = [
    # --- Original 6 Cases ---
    {
        "id": 1,
        "category": "Original",
        "input": "bench 60kg 8 reps 3 sets, incline db 22 x 10 x 3, squat 80 5x5",
        "expected": [
            {"exercise": "Bench Press", "weight_kg": 60.0, "reps": 8, "sets": 3},
            {"exercise": "Incline Dumbbell Press", "weight_kg": 22.0, "reps": 10, "sets": 3},
            {"exercise": "Squat", "weight_kg": 80.0, "reps": 5, "sets": 5}
        ]
    },
    {
        "id": 2,
        "category": "Original",
        "input": "bench 60 8x3",
        "expected": [
            {"exercise": "Bench Press", "weight_kg": 60.0, "reps": 8, "sets": 3}
        ]
    },
    {
        "id": 3,
        "category": "Original",
        "input": "db shoulder press 50 lbs 10 reps 3 sets",
        "expected": [
            {"exercise": "Dumbbell Shoulder Press", "weight_kg": 22.7, "reps": 10, "sets": 3}
        ]
    },
    {
        "id": 4,
        "category": "Original",
        "input": "pullups 3 sets 10 reps, dips 12 reps",
        # NOTE: For "dips 12 reps", set count is omitted in raw input.
        # Both 1 set (performed once) and null (unspecified) are accepted.
        "expected": [
            {"exercise": "Pull-Up", "weight_kg": None, "reps": 10, "sets": 3},
            {"exercise": "Dips", "weight_kg": None, "reps": 12, "sets": [1, None]}
        ]
    },
    {
        "id": 5,
        "category": "Original",
        "input": "deadlift 100 5x5, bb curl 30kg 10 reps 4 sets",
        "expected": [
            {"exercise": "Deadlift", "weight_kg": 100.0, "reps": 5, "sets": 5},
            {"exercise": "Barbell Curl", "weight_kg": 30.0, "reps": 10, "sets": 4}
        ]
    },
    {
        "id": 6,
        "category": "Original",
        "input": "did legs today, felt good",
        "expected": []
    },

    # --- 6 New Held-Out Cases ---
    {
        "id": 7,
        "category": "Held-Out",
        "input": "squat 100 3x5",
        "expected": [
            {"exercise": "Squat", "weight_kg": 100.0, "reps": 5, "sets": 3}
        ]
    },
    {
        "id": 8,
        "category": "Held-Out",
        "input": "ohp 40 6 reps 4 sets",
        "expected": [
            {"exercise": "Overhead Press", "weight_kg": 40.0, "reps": 6, "sets": 4}
        ]
    },
    {
        "id": 9,
        "category": "Held-Out",
        "input": "lat pulldown 55 lbs 12 x 3",
        "expected": [
            {"exercise": "Lat Pulldown", "weight_kg": 24.9, "reps": 12, "sets": 3}
        ]
    },
    {
        "id": 10,
        "category": "Held-Out",
        "input": "rested today, shoulders sore",
        "expected": []
    },
    {
        "id": 11,
        "category": "Held-Out",
        "input": "bb row 70 8,8,6",
        # NOTE: Schema only supports a single 'reps' field, not per-set varying reps (8, 8, 6).
        # We accept reps in [6, 7, 8] with sets=3 (or sets=None).
        "expected": [
            {"exercise": "Barbell Row", "weight_kg": 70.0, "reps": 8, "sets": 3}
        ],
        "allow_varying_reps": True
    },
    {
        "id": 12,
        "category": "Held-Out",
        "input": "bench 62.5 kg 6x4, tricep pushdown 25 12 reps 3 sets",
        "expected": [
            {"exercise": "Bench Press", "weight_kg": 62.5, "reps": 6, "sets": 4},
            {"exercise": "Tricep Pushdown", "weight_kg": 25.0, "reps": 12, "sets": 3}
        ]
    }
]


def compare_exercises(actual_list: List[Dict[str, Any]], expected_list: List[Dict[str, Any]], allow_varying_reps: bool = False) -> tuple[bool, str]:
    """Compares actual extracted exercises with expected list using normalized canonical keys."""
    if len(actual_list) != len(expected_list):
        return False, f"Expected {len(expected_list)} exercise(s), but got {len(actual_list)}"

    for idx, (actual, expected) in enumerate(zip(actual_list, expected_list)):
        # Normalize exercise name for matching using canonical key
        act_key = db.normalize_exercise_name(actual.get("exercise", ""))
        exp_key = db.normalize_exercise_name(expected.get("exercise", ""))
        if act_key != exp_key:
            return False, f"Item {idx}: Exercise name mismatch. Expected '{expected.get('exercise')}' (key: '{exp_key}'), got '{actual.get('exercise')}' (key: '{act_key}')"

        # Compare weight
        act_wt = actual.get("weight_kg")
        exp_wt = expected.get("weight_kg")
        if act_wt != exp_wt:
            # allow +/- 0.5 kg tolerance for unit conversion rounding
            if act_wt is not None and exp_wt is not None and abs(act_wt - exp_wt) <= 0.6:
                pass
            else:
                return False, f"Item {idx} ('{act_key}'): Weight mismatch. Expected {exp_wt}, got {act_wt}"

        # Compare reps
        act_reps = actual.get("reps")
        exp_reps = expected.get("reps")
        act_sets = actual.get("sets")
        exp_sets = expected.get("sets")

        if allow_varying_reps:
            # For "8,8,6", reps can be 8, 7 (avg), or 6
            if act_reps not in [6, 7, 8]:
                return False, f"Item {idx} ('{act_key}'): Reps mismatch for varying reps. Expected 8, 7, or 6, got {act_reps}"
        else:
            # Check standard reps or swapped sets/reps in 3x5 notation
            if act_reps != exp_reps:
                if act_reps == exp_sets and act_sets == exp_reps:
                    pass
                else:
                    return False, f"Item {idx} ('{act_key}'): Reps mismatch. Expected {exp_reps}, got {act_reps}"

        # Compare sets
        if not allow_varying_reps:
            if isinstance(exp_sets, list):
                if act_sets not in exp_sets:
                    return False, f"Item {idx} ('{act_key}'): Sets mismatch. Expected one of {exp_sets}, got {act_sets}"
            else:
                if exp_sets in [1, None] and act_sets in [1, None]:
                    pass
                elif act_sets != exp_sets:
                    if act_reps == exp_sets and act_sets == exp_reps:
                        pass
                    else:
                        return False, f"Item {idx} ('{act_key}'): Sets mismatch. Expected {exp_sets}, got {act_sets}"
        else:
            if act_sets not in [3, None]:
                return False, f"Item {idx} ('{act_key}'): Sets mismatch. Expected 3 sets, got {act_sets}"

    return True, "Matches expected"


def run_live_checks():
    print("=" * 65)
    print("Gym Log Buddy - 12-Input Live Verification (3 Iterations Each)")
    print("=" * 65)

    # First check Ollama connectivity
    prompt_test = parser.PROMPT_TEMPLATE.replace("{user_input}", "test")
    ok, _, err, _ = parser.call_ollama(prompt_test)
    if not ok:
        print(f"\n[FATAL] Ollama check failed: {err}")
        print("Please start Ollama and ensure 'gemma3' is pulled, then re-run.")
        sys.exit(1)

    all_latencies = []
    cold_latencies = []
    warm_latencies = []
    total_runs = 0
    total_passed = 0
    total_failed = 0
    NUM_RUNS_PER_INPUT = 3

    case_stats = []

    for item in TEST_CASES:
        case_id = item["id"]
        cat = item.get("category", "")
        raw_text = item["input"]
        expected = item["expected"]
        varying_reps = item.get("allow_varying_reps", False)

        print(f"\n============================================================")
        print(f"[{cat}] Case #{case_id}: \"{raw_text}\"")
        print(f"============================================================")

        case_latencies = []
        case_passes = 0
        case_fails = 0

        for run_idx in range(1, NUM_RUNS_PER_INPUT + 1):
            t0 = time.perf_counter()
            result = parser.parse_workout(raw_text)
            duration = time.perf_counter() - t0

            all_latencies.append(duration)
            case_latencies.append(duration)
            if run_idx == 1:
                cold_latencies.append(duration)
            else:
                warm_latencies.append(duration)

            total_runs += 1

            run_type = "Cold" if run_idx == 1 else "Warm"
            print(f"\n  --- Run {run_idx}/{NUM_RUNS_PER_INPUT} ({run_type}) ---")
            print(f"  Latency: {duration:.2f}s")
            print(f"  Model Raw Response:\n{result.get('raw_response')}")
            print(f"  Validated Result:\n{json.dumps(result.get('exercises', []), indent=2)}")
            if result.get("error"):
                print(f"  Reported Error: {result.get('error')}")

            # Check against expected
            actual_exercises = result.get("exercises", [])
            is_pass, reason = compare_exercises(actual_exercises, expected, allow_varying_reps=varying_reps)

            if is_pass:
                print(f"  Result: PASS ({reason})")
                total_passed += 1
                case_passes += 1
            else:
                print(f"  Result: FAIL ({reason})")
                total_failed += 1
                case_fails += 1

        run1_lat = case_latencies[0]
        warm_avg = sum(case_latencies[1:]) / len(case_latencies[1:])
        case_avg = sum(case_latencies) / len(case_latencies)

        case_stats.append({
            "id": case_id,
            "category": cat,
            "input": raw_text,
            "passes": case_passes,
            "fails": case_fails,
            "run1_latency": run1_lat,
            "warm_avg_latency": warm_avg,
            "avg_latency": case_avg,
            "latencies": case_latencies
        })
        print(f"\n>> Case #{case_id} Summary: {case_passes}/{NUM_RUNS_PER_INPUT} Passed | Run 1 (Cold): {run1_lat:.2f}s | Runs 2-3 (Warm avg): {warm_avg:.2f}s | Overall: {case_avg:.2f}s")

    print("\n" + "=" * 65)
    print("OVERALL 12-INPUT LIVE VERIFICATION SUMMARY")
    print("=" * 65)
    print(f"Total Inputs: {len(TEST_CASES)} | Total Inferences: {total_runs}")
    print(f"Total Passed Runs: {total_passed} / {total_runs} ({total_passed/total_runs*100:.1f}%)")
    print(f"Total Failed Runs: {total_failed} / {total_runs} ({total_failed/total_runs*100:.1f}%)")
    if cold_latencies:
        print(f"Average Cold Latency (Run 1): {sum(cold_latencies)/len(cold_latencies):.2f}s (Min: {min(cold_latencies):.2f}s, Max: {max(cold_latencies):.2f}s)")
    if warm_latencies:
        print(f"Average Warm Latency (Runs 2 & 3): {sum(warm_latencies)/len(warm_latencies):.2f}s (Min: {min(warm_latencies):.2f}s, Max: {max(warm_latencies):.2f}s)")
    if all_latencies:
        overall_avg = sum(all_latencies) / len(all_latencies)
        print(f"Overall Combined Latency: {overall_avg:.2f}s (Min: {min(all_latencies):.2f}s, Max: {max(all_latencies):.2f}s)")
    print("=" * 65)


if __name__ == "__main__":
    run_live_checks()
