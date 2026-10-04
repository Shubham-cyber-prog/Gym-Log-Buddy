"""
db.py - SQLite Database Interface for Gym Log Buddy

Handles storing and querying logged workouts in a local SQLite database (gym.db).
Schema:
  workouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    exercise TEXT,
    weight_kg REAL,
    reps INTEGER,
    sets INTEGER,
    raw_text TEXT
  )
"""

import os
import sqlite3
import re
from typing import List, Dict, Any, Optional

DEFAULT_DB_PATH = "gym.db"


def _get_path(db_path: str = DEFAULT_DB_PATH) -> str:
    """Returns explicit db_path or GYM_DB_PATH env var if default."""
    if db_path != DEFAULT_DB_PATH:
        return db_path
    return os.environ.get("GYM_DB_PATH", DEFAULT_DB_PATH)


def normalize_exercise_name(name: str) -> str:
    """
    Generates a canonical normalized key for exercise matching:
    - Lowercase
    - Remove all non-alphanumeric characters (spaces, hyphens, etc.)
    - Remove trailing 's' to unify plurals (e.g. 'Pull-Ups', 'Pullups', 'pull up' -> 'pullup')
      Preserves root 'ss' (e.g. 'Bench Press' -> 'benchpress').
    """
    if not name:
        return ""
    cleaned = re.sub(r'[^a-z0-9]', '', str(name).lower())
    if cleaned.endswith("es") and cleaned.endswith("sses"):
        cleaned = cleaned[:-2]
    elif cleaned.endswith("s") and not cleaned.endswith("ss"):
        cleaned = cleaned[:-1]
    return cleaned


def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Creates a database connection with row factory enabled."""
    conn = sqlite3.connect(_get_path(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Initializes the SQLite database and ensures the workouts table exists."""
    try:
        with get_connection(db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workouts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    exercise TEXT NOT NULL,
                    weight_kg REAL,
                    reps INTEGER,
                    sets INTEGER,
                    raw_text TEXT
                )
            """)
            conn.commit()
    except sqlite3.Error as e:
        print(f"[DB Error] Failed to initialize database: {e}")


def save_workout(
    date: str,
    items: List[Dict[str, Any]],
    raw_text: str,
    db_path: str = DEFAULT_DB_PATH
) -> int:
    """
    Saves a parsed workout session into the database.

    Parameters:
      date: Date string formatted as YYYY-MM-DD
      items: List of exercise dicts with keys: exercise, weight_kg, reps, sets
      raw_text: Original raw input string from user
      db_path: SQLite database file path

    Returns:
      Number of rows saved successfully.
    """
    init_db(db_path)
    if not items:
        return 0

    inserted_count = 0
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            for item in items:
                exercise = str(item.get("exercise", "")).strip()
                if not exercise:
                    continue
                weight_kg = item.get("weight_kg")
                if weight_kg is not None:
                    try:
                        weight_kg = float(weight_kg)
                    except (ValueError, TypeError):
                        weight_kg = None

                reps = item.get("reps")
                if reps is not None:
                    try:
                        reps = int(reps)
                    except (ValueError, TypeError):
                        reps = None

                sets = item.get("sets")
                if sets is not None:
                    try:
                        sets = int(sets)
                    except (ValueError, TypeError):
                        sets = None

                cursor.execute("""
                    INSERT INTO workouts (date, exercise, weight_kg, reps, sets, raw_text)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (date, exercise, weight_kg, reps, sets, raw_text))
                inserted_count += 1
            conn.commit()
    except sqlite3.Error as e:
        print(f"[DB Error] Failed to save workout: {e}")
    return inserted_count


def get_last_session(exercise: str, db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    """
    Retrieves the most recent workout entry matching the normalized exercise key.

    Returns:
      Dictionary with workout details or None if no prior session exists.
    """
    init_db(db_path)
    target_key = normalize_exercise_name(exercise)
    if not target_key:
        return None
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, date, exercise, weight_kg, reps, sets, raw_text
                FROM workouts
                ORDER BY date DESC, id DESC
            """)
            for row in cursor.fetchall():
                row_dict = dict(row)
                if normalize_exercise_name(row_dict["exercise"]) == target_key:
                    return row_dict
    except sqlite3.Error as e:
        print(f"[DB Error] Failed to query last session for '{exercise}': {e}")
    return None


def get_all_logs(db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    """
    Returns all logged workouts ordered from newest to oldest.
    """
    init_db(db_path)
    logs = []
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, date, exercise, weight_kg, reps, sets, raw_text
                FROM workouts
                ORDER BY date DESC, id DESC
            """)
            logs = [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"[DB Error] Failed to fetch workout logs: {e}")
    return logs


def get_exercises(db_path: str = DEFAULT_DB_PATH) -> List[str]:
    """
    Returns unique exercise names deduped by normalized exercise key.
    For each unique key, displays the most recent exercise name recorded.
    Sorted alphabetically for display.
    """
    init_db(db_path)
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT exercise
                FROM workouts
                ORDER BY date DESC, id DESC
            """)
            seen_keys = set()
            unique_exercises = []
            for row in cursor.fetchall():
                ex_name = row["exercise"]
                key = normalize_exercise_name(ex_name)
                if key and key not in seen_keys:
                    seen_keys.add(key)
                    unique_exercises.append(ex_name)
            unique_exercises.sort(key=lambda s: s.lower())
            return unique_exercises
    except sqlite3.Error as e:
        print(f"[DB Error] Failed to fetch exercises: {e}")
        return []

