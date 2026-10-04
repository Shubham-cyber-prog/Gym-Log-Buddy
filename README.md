# Gym Log Buddy

Gym Log Buddy is a local-first workout tracking application that extracts structured exercises, weights, reps, and sets from natural language workout notes.
It is built for a gym buddy who wants quick, friction-free workout logging without manual forms, accounts, or subscriptions.
It runs entirely on your local machine using an open-source language model (Gemma 3 via Ollama) for text extraction, deterministic Python rules for progressive overload recommendations, and SQLite for storage.

---

## Features

- Plain English input: Type workout notes naturally (e.g. "bench 60kg 8 reps 3 sets, incline db 22 x 10 x 3, squat 80 5x5").
- Local open-source model: Uses Gemma 3 via Ollama. No cloud APIs, no API keys, and no paid services.
- Deterministic progressive overload:
  - If last reps >= 10: suggest +2.5 kg and 8 reps
  - Otherwise: suggest same weight and +1 rep
- Dual interfaces:
  - CLI (cli.py): log, last, suggest, history commands.
  - Streamlit UI (app.py): natural text input, preview and confirmation step, sidebar overload targets, and progress chart.
- Local SQLite database.

---

## Screenshots

<!-- Placeholder section: Add screenshots here when available -->
- [Screenshot 1: Streamlit UI - Workout logging and confirmation preview]
- [Screenshot 2: Streamlit UI - Exercise history and progression line chart]
- [Screenshot 3: CLI - Logging a workout and viewing progressive overload target]

---

## Setup and Installation

### 1. Install and Start Ollama

#### Windows (PowerShell):
```powershell
# Install Ollama
irm https://ollama.com/install.ps1 | iex

# Start the Ollama server
ollama serve

# In a separate terminal, pull Gemma 3
ollama pull gemma3

# Verify Ollama is responding
curl http://localhost:11434
```

#### Ubuntu / Debian:
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Start the Ollama server
ollama serve

# In a separate terminal, pull Gemma 3
ollama pull gemma3

# Verify Ollama is responding
curl http://localhost:11434
```

---

### 2. Python Environment Setup

Requires Python 3.10+.

```bash
cd gym-log-buddy
pip install -r requirements.txt
```

---

## How to Run

### Command Line Interface (CLI)

```bash
# Log a workout (parses, shows preview, and asks confirmation before saving)
python cli.py log "bench 60kg 8 reps 3 sets, incline db 22 x 10 x 3, squat 80 5x5"

# Show last session and progressive overload target
python cli.py last "Bench Press"
python cli.py last

# Suggest target for an exercise based on last recorded session
python cli.py suggest "Bench Press"

# View workout history
python cli.py history
```

### Streamlit Web App

```bash
cd gym-log-buddy
streamlit run app.py
```
Open http://localhost:8501 in your browser.

---

## Tests

1. Automated Tests (pytest):
   - 20 automated tests executed via `pytest`:
     - `tests/test_parser_examples.py` (18 tests): Unit tests using mocked Ollama API responses and temporary in-memory/isolated SQLite databases. Covers parsing across 5 varied input formats, schema and type validation, offline Ollama error handling, progressive overload rules, canonical exercise key normalization / deduplication, and automated prompt leakage prevention (`test_prompt_template_has_no_test_leakage`).
     - `tests/test_app.py` (2 tests): Headless Streamlit application tests using `streamlit.testing.v1.AppTest`. Runs `app.py` in-memory against empty and populated temporary databases, verifying that tabs, forms, and line charts render without exceptions or NameErrors.
   - Run command: `pytest`

2. Live Verification Script (`tests/live_check.py`):
   - Evaluates 12 real workout inputs (6 original + 6 held-out) across 3 runs each (36 total inferences) directly against the live Gemma 3 model running locally on Ollama.
   - Genuine Held-Out Benchmark: 15 / 18 passed (83.3%) across the 6 held-out inputs.
   - Original Inputs: 18 / 18 passed (100%) across the 6 prompt-tuned inputs.
   - Combined Overall: 33 / 36 passed (91.7%).
   - Prompt Leakage Prevention: Both few-shot examples and prompt rules were audited to eliminate verbatim test inputs, with zero-leakage verified by automated pytest assertions.
   - Full per-run details, cold/warm latencies, and raw outputs are documented in `NOTES.md` and `BLOG_FACTS.md`.
   - Run command: `python tests/live_check.py` (Note: Run only when verifying live model output, as each full run takes ~7-10 minutes on integrated GPU).

---

## Limitations

1. Small local model accuracy: Small local language models can misparse complex phrasing, infer incorrect units, or hallucinate exercises on conversational text. A preview and confirmation step is enforced in both CLI and UI before saving data to the database.
2. Default kilograms assumption: Any unadorned number (such as "bench 60 8x3") is assumed to be kilograms. Weight conversion only triggers if imperial units ("lb", "lbs", "pounds") are explicitly typed.
3. Lack of per-set reps support: The schema stores a single `reps` integer per exercise. Pyramiding or variable per-set repetitions (e.g. "bb row 70 8,8,6") are not supported per-set; in live checks, the model misparsed this as `reps: 8, sets: 8`, scoring 0/3 passed.
4. Exercise name normalizer scope: `normalize_exercise_name()` handles basic pluralization, hyphens, and whitespace differences (e.g., matching "Pull-Ups", "Pullups", and "pull up" to canonical key "pullup"). It does not recognize semantic synonyms or acronyms (e.g., "OHP" vs "Overhead Press" remain distinct).
5. Inference latency: On machines without a dedicated discrete GPU (tested on Intel Iris Xe with 16 GB RAM), inference latency averages ~17.8s for cold runs and ~9.5s for warm runs.
6. Cloud sync storage warning: If this project directory is placed inside a cloud-synced folder such as OneDrive or Dropbox, concurrent sync operations can lock the SQLite database file (`gym.db`), causing database errors or file corruption. Run the project in a local directory outside sync folders.
7. Browser testing: Automated UI flows are verified headlessly via Streamlit's `AppTest` framework in pytest. Basic manual browser logging was verified by the user.
