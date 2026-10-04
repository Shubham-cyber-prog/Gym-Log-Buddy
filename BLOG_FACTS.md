# Gym Log Buddy - Development and Experiment Facts

This document compiles the verified experimental facts, benchmark numbers, model failure cases, prompt leakage history, and engineering bugs encountered during the development of Gym Log Buddy. All data is taken directly from `NOTES.md`, actual script execution logs, and the repository codebase.

---

## 1. Experiment Progression and Pass Rate Table

| Stage / Run | Inferences & Scope | Pass Rate | Cold Latency (Avg) | Warm Latency (Avg) | Overall Latency (Avg) | Changes Applied (Kya Badla) |
|---|---|---|---|---|---|---|
| **1. Pehla Baseline** | 6 inputs, 1 run each (6 inferences) | **4 / 6 (66.7%)** | 21.04s (all cold) | N/A | 21.04s | Initial prompt with basic JSON schema. Model failed on unadorned units (assumed lbs) and casual conversational notes (hallucinated exercise). |
| **2. First Prompt Leakage (Few-Shots)** | 6 inputs, 3 runs each (18 inferences) | **18 / 18 (100% - Artificial)** | 22.03s | 12.01s | 15.35s | Fixed weight rules and casual notes, but prompt few-shot examples contained exact test strings (`bench 60 8x3`, `did legs today, felt good`). Score was artificially high due to direct test set contamination. |
| **3. Held-Out Evaluation (Contaminated Rules)** | 12 inputs (6 original + 6 held-out), 3 runs each (36 inferences) | **30 / 36 (83.3% - Partially Contaminated)** | 21.99s | 11.10s | 14.73s | Disjoint few-shot examples were added, but prompt `RULES` section still contained verbatim test strings. 6 runs failed (strict string mismatch on Case 4, varying reps on Case 11). |
| **4. Canonical Normalizer (Contaminated Rules)** | 12 inputs, 3 runs each (36 inferences) | **33 / 36 (91.7% - Partially Contaminated)** | 23.61s | 11.49s | 15.53s | Added `normalize_exercise_name()` for plural/singular matching. However, prompt `RULES` still had test leaks (`bench 60 8x3`, `did legs today, felt good`, etc.). |
| **5. Final Clean Run (Zero Leaks + Leakage Pytest)** | 12 inputs, 3 runs each (36 inferences) | **Headline: 15 / 18 (83.3%) on Held-Out**<br>Original: 18 / 18 (100%)<br>Combined: 33 / 36 (91.7%) | 17.85s | 9.54s | 12.31s | Removed all test substrings from `RULES`. Added automated pytest `test_prompt_template_has_no_test_leakage`. Zero leakage confirmed. |

> [!IMPORTANT]
> **Headline Metric**: The genuine benchmark score for generalisation is **15 / 18 (83.3%) across the 6 Held-Out inputs**. The original 6 inputs scored 18 / 18 (100%) because the prompt instructions were originally tuned around them.

---

## 2. Real Model Failures and Raw Outputs

### Failure 1: Unadorned Weight Converted to Pounds (`bench 60 8x3` -> 27.2 kg)
- **Raw Input**: `bench 60 8x3`
- **Model Raw Output**:
  ```
  Bench Press (27.2 kg, 8r, 3s)
  ```
  JSON: `[{"exercise": "Bench Press", "weight_kg": 27.2, "reps": 8, "sets": 3}]`
- **Expected Output**: `[{"exercise": "Bench Press", "weight_kg": 60.0, "reps": 8, "sets": 3}]`
- **Measured Latency**: 18.27s (Baseline Run)
- **Why It Happened**: The model implicitly defaulted bare numbers to pounds (imperial), multiplying 60 by 0.453592 to produce 27.2 kg instead of preserving 60.0 kg.
- **Fix**: Updated system prompt instructions to explicitly make kilograms (kg) the default for any unadorned numeric weight, and stated that conversion only triggers when `lb`, `lbs`, or `pounds` is explicitly present in the input.

---

### Failure 2: Hallucinated Exercise on Conversational Text (`did legs today, felt good`)
- **Raw Input**: `did legs today, felt good`
- **Model Raw Output**:
  ```
  Squat (null kg, null reps, null sets)
  ```
  JSON: `{"exercises": [{"exercise": "Squat", "weight_kg": null, "reps": null, "sets": null}]}`
- **Expected Output**: `{"exercises": []}`
- **Measured Latency**: 17.97s (Baseline Run)
- **Why It Happened**: When presented with casual conversational text about a workout session with no exercises or numeric metrics, the model hallucinated an exercise ("Squat") with null values across weight, reps, and sets.
- **Fix**: Added an explicit prompt rule requiring an empty list `{"exercises": []}` for non-exercise text or general notes, accompanied by programmatic validation in `parser.validate_parsed_data()` to drop any parsed exercise where weight, reps, and sets are all null.

---

### Failure 3: Variable Per-Set Repetitions Parsed as Sets (`bb row 70 8,8,6` -> `sets: 8`)
- **Raw Input**: `bb row 70 8,8,6`
- **Model Raw Output**:
  ```
  Barbell Row (70.0 kg, reps: 8, sets: 8)
  ```
  JSON: `[{"exercise": "Barbell Row", "weight_kg": 70.0, "reps": 8, "sets": 8}]` across all 3 runs
- **Expected Output**: Reps: 8 (or 6, 7), Sets: 3
- **Measured Latency**: Run 1 (Cold): 16.72s, Run 2 (Warm): 8.28s, Run 3 (Warm): 8.35s
- **Pass Rate**: 0 / 3 (0%)
- **Why It Happened**: The JSON extraction schema only defines `reps: int` (uniform repetition count per exercise) and has no array structure for per-set repetitions (`8, 8, 6`). The model parsed the first `8` as reps, and misconstrued the second `8` as the set count (`sets: 8`).
- **Resolution**: Kept as an honest failure (0/3) and documented as an architectural limitation rather than loosening the test criteria.

---

## 3. Test Leakage: Two Occurrences and How They Were Caught

Leakage repository mein do baar hui:
1. **Pehli Leakage (Few-Shot Examples)**:
   Baseline errors fix karte waqt `parser.py` ke few-shot examples mein test suite ke exact strings daal diye gaye (`bench 60 8x3` aur `did legs today, felt good`). Isse 18/18 (100%) ka artificial score aaya. Yeh pehli audit mein pakda gaya.
2. **Doosri Leakage (Prompt Rules)**:
   Few-shots ko disjoint banane ke baad bhi, prompt ke `RULES` section mein test inputs ke tukde verbatim reh gaye:
   - Rule 2: `"5x5"` aur `"22 x 10 x 3"`
   - Rule 3: `"bench 60 8x3"`, `"squat 80"`, `"pullups, dips"`
   - Rule 4: `"did legs today, felt good"`
   Yeh doosri leakage code review ke dauran pakdi gayi.

### Resolution and Actual Few-Shot Examples
Dono leakages ko poori tarah khatam kiya gaya:
1. `parser.py` ke prompt mein maujood actual few-shot examples hain:
   - Example 1: `"incline bench 50 10x3, romanian deadlift 90 8 reps 3 sets"`
   - Example 2: `"db lateral raise 20 lbs 15 reps 4 sets, chin-ups 10 reps 3 sets"`
   - Example 3: `"took a recovery walk in the park today, slept 8 hours"`
2. `RULES` section ke saare examples ko completely disjoint banaya gaya (`4x4`, `7x3`, `30 x 12 x 4`, `leg press 120`, `lunges 24`, `push-ups, burpees`, `back day was brutal`).
3. Ek automated pytest test (`test_prompt_template_has_no_test_leakage`) add kiya gaya jo assert karta hai ki `live_check.py` ka koi bhi input ya uska comma-separated segment (> 10 characters) `PROMPT_TEMPLATE` mein case-insensitive match na kare.

---

## 4. Latency and Hardware Profile (Clean Run)

- **Hardware**:
  - Processor / Graphics: Intel(R) Iris(R) Xe Graphics (integrated, ~2 GB shared memory)
  - Memory: 16 GB System RAM
  - Operating System: Windows 11
  - Model: `gemma3:latest` (3.3 GB) running on local Ollama via HTTP API
- **Measured Latency Numbers (Clean Run - 36 Inferences)**:
  - **Held-Out 6 Inputs**:
    - Cold Latency (Run 1): Average 17.44s
    - Warm Latency (Runs 2 & 3): Average 8.78s
    - Overall Held-Out Average: 11.66s
  - **Original 6 Inputs**:
    - Cold Latency (Run 1): Average 18.26s
    - Warm Latency (Runs 2 & 3): Average 10.31s
    - Overall Original Average: 12.96s
  - **Combined Overall (12 Inputs)**:
    - Average Cold Latency: 17.85s (Min: 11.97s, Max: 24.52s)
    - Average Warm Latency: 9.54s (Min: 3.30s, Max: 16.99s)
    - Overall Combined Average: 12.31s (Min: 3.30s, Max: 24.52s)
- **Warm Run Speedup Cause**:
  - Status: **NOT VERIFIED / unverified**.
  - Warm inferences consistently run ~2x faster than cold runs across all inputs. However, whether this speedup is caused by Ollama's memory-mapped model weights, KV context cache reuse, OS buffer cache, or GPU shader caching was not internally profiled or measured.

---

## 5. Vocabulary and Syntax Observations

1. **Abbreviation Mapping Vocabulary vs Held-Out Status (Case #8)**:
   Rule 1 contains `"ohp" -> "Overhead Press"` and `"incline db" -> "Incline Dumbbell Press"`. This is intentional domain vocabulary mapping that improves app utility. However, because the abbreviation `"ohp"` is mapped in the system prompt, Case #8 (`ohp 40 6 reps 4 sets`) is technically not 100% held-out in terms of exercise vocabulary, though its numeric payload is held-out.
2. **Syntax Disambiguation (`NxM` notation)**:
   Rule 2 defines `"7x3" means 7 reps, 3 sets (or sets x reps)`. The flexible parenthetical allows the model latitude. In clean evaluation:
   - Case #7 (`squat 100 3x5`): Model produced `reps: 5, sets: 3` across all 3 runs.
   - Case #12 (`bench 62.5 kg 6x4`): Model produced `reps: 6, sets: 4` across all 3 runs.
   For production with a specific gym friend, aligning on a single strict convention (e.g. always `reps x sets` or always `sets x reps`) and stating it unambiguously in the prompt will eliminate potential edge-case confusion.

---

## 6. Agent-Introduced Bugs and Pytest Gap

### The Bug: `selected_chart_ex` NameError in `app.py`
During the implementation of exercise name canonicalization and the Streamlit progress line chart in `app.py`, `selected_chart_ex` was created inside a conditional branch:
```python
if exercises_list:
    selected_chart_ex = st.selectbox("Select exercise:", exercises_list, key="chart_select")
    selected_key = db.normalize_exercise_name(selected_chart_ex)
```
In earlier iterations or refactorings of the history view, `selected_chart_ex` could be referenced outside or before the conditional check, causing a potential runtime exception:
`NameError: name 'selected_chart_ex' is not defined`.

### Why Pytest Originally Failed to Catch It
The original test suite in `tests/test_parser_examples.py` only tested backend logic:
- `parser.py` (mocked Ollama HTTP calls)
- `db.py` (SQLite queries)
- `suggest.py` (progressive overload math)

None of the tests imported or executed `app.py`. Because Streamlit applications are scripts that typically execute top-to-bottom on each interaction, standard pytest unit tests completely bypassed `app.py`. A syntax error or NameError inside `app.py` would pass `pytest` with 100% green status while failing immediately for an actual user.

### How It Was Caught and Fixed
The blind spot was addressed by writing `tests/test_app.py` using Streamlit's official headless testing tool (`from streamlit.testing.v1 import AppTest`):
1. `test_app_renders_empty_db`: Simulates a clean start with an empty database, ensuring no unhandled exceptions or NameErrors occur when no exercise history exists.
2. `test_app_renders_with_workout_history_and_charts`: Seeds a temporary database with exercise name variations (`Pull-Ups`, `Pullups`, `Bench Press`), verifies tab rendering, and verifies that the chart selectbox renders deduplicated options without error.
