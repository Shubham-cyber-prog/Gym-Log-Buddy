"""
test_app.py - Headless Streamlit App Tests using AppTest

Verifies that app.py runs without exceptions, renders both tabs
('Log Workout', 'History and Progress'), and successfully executes
the chart and sidebar code paths against a temporary isolated database.
"""

import os
import sys
import pytest
from streamlit.testing.v1 import AppTest

# Add parent dir to sys.path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import db


def test_app_renders_empty_db(tmp_path, monkeypatch):
    """
    Verifies that app.py runs cleanly without exceptions when the database is empty,
    and properly renders both main tabs.
    """
    temp_db = str(tmp_path / "empty_gym.db")
    monkeypatch.setenv("GYM_DB_PATH", temp_db)

    # Initialize empty DB
    db.init_db(temp_db)

    # Path to app.py relative to project root
    app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app.py"))
    at = AppTest.from_file(app_path, default_timeout=30)
    at.run(timeout=30)

    # Assert no unhandled exceptions occurred
    assert len(at.exception) == 0, f"App raised exceptions: {[e.value for e in at.exception]}"

    # Assert tabs render correctly
    assert len(at.tabs) == 2
    tab_labels = [t.label for t in at.tabs]
    assert "Log Workout" in tab_labels
    assert "History and Progress" in tab_labels


def test_app_renders_with_workout_history_and_charts(tmp_path, monkeypatch):
    """
    Verifies that app.py executes the history tab and line chart code paths
    without any NameError or exceptions when rows with varying exercise names
    ('Pull-Ups', 'Pullups') exist in the database.
    """
    temp_db = str(tmp_path / "populated_gym.db")
    monkeypatch.setenv("GYM_DB_PATH", temp_db)

    # Initialize and seed temporary DB with variations
    db.init_db(temp_db)
    db.save_workout(
        "2026-10-01",
        [{"exercise": "Pull-Ups", "weight_kg": None, "reps": 10, "sets": 3}],
        "pullups 3 sets 10 reps",
        temp_db
    )
    db.save_workout(
        "2026-10-02",
        [{"exercise": "Pullups", "weight_kg": 5.0, "reps": 8, "sets": 3}],
        "pullups 5kg 8 reps 3 sets",
        temp_db
    )
    db.save_workout(
        "2026-10-03",
        [{"exercise": "Bench Press", "weight_kg": 60.0, "reps": 8, "sets": 3}],
        "bench 60 8x3",
        temp_db
    )

    # Run app via Streamlit AppTest
    app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app.py"))
    at = AppTest.from_file(app_path, default_timeout=30)
    at.run(timeout=30)

    # Assert no unhandled exceptions occurred
    assert len(at.exception) == 0, f"App raised exceptions: {[e.value for e in at.exception]}"

    # Assert both tabs exist and rendered
    assert len(at.tabs) == 2
    tab_labels = [t.label for t in at.tabs]
    assert "Log Workout" in tab_labels
    assert "History and Progress" in tab_labels

    # Verify that the chart selectbox was rendered and contains deduplicated exercise
    chart_selects = [s for s in at.selectbox if s.key == "chart_select"]
    assert len(chart_selects) == 1
    # Exercise deduplication should present 'Pullups' (most recent) alongside 'Bench Press'
    chart_options = chart_selects[0].options
    assert "Pullups" in chart_options
    assert "Bench Press" in chart_options
    # Ensure 'Pull-Ups' was deduplicated into 'Pullups'
    assert "Pull-Ups" not in chart_options
