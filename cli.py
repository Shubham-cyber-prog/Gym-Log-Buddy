"""
cli.py - Command Line Interface for Gym Log Buddy

Commands:
  python cli.py log ["workout text"] [--yes]
  python cli.py last [exercise]
  python cli.py suggest <exercise>
  python cli.py history [exercise]
"""

import sys
import argparse
from datetime import date
from typing import List, Dict, Any, Optional

import db
import parser
import suggest


def print_table(headers: List[str], rows: List[List[Any]]) -> None:
    """Prints a neatly aligned ASCII table."""
    if not rows:
        print("  (No data to display)")
        return

    # Calculate column widths
    str_rows = [[str(cell if cell is not None else "-") for cell in row] for row in rows]
    col_widths = [len(h) for h in headers]
    for row in str_rows:
        for i, val in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(val))

    # Formatter strings
    header_fmt = " | ".join(f"{{:<{w}}}" for w in col_widths)
    separator = "-+-".join("-" * w for w in col_widths)
    row_fmt = " | ".join(f"{{:<{w}}}" for w in col_widths)

    print(f"+-{separator}-+")
    print(f"| {header_fmt.format(*headers)} |")
    print(f"+={separator}=+")
    for row in str_rows:
        # Pad row if it has fewer columns than headers
        padded = row + ["-"] * (len(headers) - len(row))
        print(f"| {row_fmt.format(*padded[:len(headers)])} |")
    print(f"+-{separator}-+")


def handle_log(args: argparse.Namespace) -> None:
    """Handles the 'log' command to parse and record a workout."""
    raw_text = args.text
    if not raw_text:
        try:
            print("\nEnter your workout notes (e.g. 'bench 60kg 8 reps 3 sets, incline db 22 x 10 x 3'):")
            raw_text = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            return

    if not raw_text:
        print("[!] No workout text provided.")
        return

    print("\nParsing workout with local model (gemma3)...")
    result = parser.parse_workout(raw_text)

    if not result.get("success"):
        error_msg = result.get("error", "Unknown parsing error.")
        print(f"\n[X] Error: {error_msg}")
        return

    exercises = result.get("exercises", [])
    if not exercises:
        print("\n[!] No exercises could be extracted from your notes.")
        return

    # Display parsed exercises
    print("\n--- Parsed Workout Preview ---")
    headers = ["#", "Exercise", "Weight (kg)", "Reps", "Sets"]
    rows = []
    for i, ex in enumerate(exercises, 1):
        w = f"{ex['weight_kg']:.1f}" if ex.get("weight_kg") is not None else "-"
        r = str(ex.get("reps") or "-")
        s = str(ex.get("sets") or "-")
        rows.append([i, ex.get("exercise"), w, r, s])
    print_table(headers, rows)

    # Confirmation
    if not args.yes:
        try:
            confirm = input("\nSave this workout to database? [Y/n]: ").strip().lower()
            if confirm in ["n", "no"]:
                print("Workout not saved.")
                return
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            return

    today = date.today().isoformat()
    saved = db.save_workout(today, exercises, raw_text)
    print(f"\n[OK] Saved {saved} exercise(s) on {today}!")

    # Show progressive overload targets for next time
    print("\n--- Progressive Overload Targets (For Next Time) ---")
    for ex in exercises:
        target = suggest.get_suggestion(ex.get("weight_kg"), ex.get("reps"), ex.get("sets"))
        print(f"- {ex.get('exercise')}: {target}")


def handle_last(args: argparse.Namespace) -> None:
    """Handles the 'last' command to show previous session details."""
    exercise_name = args.exercise
    if exercise_name:
        session = db.get_last_session(exercise_name)
        if not session:
            print(f"\nNo previous logs found for '{exercise_name}'.")
            return
        headers = ["Date", "Exercise", "Weight (kg)", "Reps", "Sets"]
        w = f"{session['weight_kg']:.1f}" if session.get("weight_kg") is not None else "-"
        r = str(session.get("reps") or "-")
        s = str(session.get("sets") or "-")
        print(f"\nLast session for '{exercise_name}':")
        print_table(headers, [[session["date"], session["exercise"], w, r, s]])

        # Show next suggestion
        suggestion = suggest.get_suggestion(session.get("weight_kg"), session.get("reps"), session.get("sets"))
        print(f"\nNext Target: {suggestion}")
    else:
        # Show last session for all tracked exercises
        exercises = db.get_exercises()
        if not exercises:
            print("\nNo workouts recorded yet. Use 'python cli.py log' to log your first session!")
            return

        headers = ["Exercise", "Last Date", "Weight (kg)", "Reps", "Sets", "Next Suggestion"]
        rows = []
        for name in exercises:
            s = db.get_last_session(name)
            if s:
                w = f"{s['weight_kg']:.1f}" if s.get("weight_kg") is not None else "-"
                r = str(s.get("reps") or "-")
                sets = str(s.get("sets") or "-")
                sug = suggest.get_suggestion(s.get("weight_kg"), s.get("reps"), s.get("sets"))
                rows.append([s["exercise"], s["date"], w, r, sets, sug])
        print("\n--- Most Recent Sessions Per Exercise ---")
        print_table(headers, rows)


def handle_suggest(args: argparse.Namespace) -> None:
    """Handles the 'suggest' command for an exercise."""
    name = args.exercise
    session = db.get_last_session(name)
    if not session:
        print(f"\nNo workout history found for '{name}'.")
        print("Progressive Overload Rule: Aim for 8-10 reps. Once you hit 10+ reps, increase by 2.5 kg.")
        return

    w = f"{session['weight_kg']:.1f} kg" if session.get("weight_kg") is not None else "bodyweight"
    r = f"{session.get('reps')} reps" if session.get("reps") is not None else "- reps"
    s = f"{session.get('sets')} sets" if session.get("sets") is not None else "- sets"

    print(f"\nExercise: {session['exercise']}")
    print(f"Last Logged ({session['date']}): {w} x {r} ({s})")
    target = suggest.get_suggestion(session.get("weight_kg"), session.get("reps"), session.get("sets"))
    print(f"Suggested Target: {target}")


def handle_history(args: argparse.Namespace) -> None:
    """Handles the 'history' command to list recorded workouts."""
    logs = db.get_all_logs()
    if args.exercise:
        logs = [entry for entry in logs if args.exercise.lower() in entry["exercise"].lower()]

    if not logs:
        print("\nNo workout logs found.")
        return

    headers = ["Date", "Exercise", "Weight (kg)", "Reps", "Sets", "Raw Notes"]
    rows = []
    for entry in logs:
        w = f"{entry['weight_kg']:.1f}" if entry.get("weight_kg") is not None else "-"
        r = str(entry.get("reps") or "-")
        s = str(entry.get("sets") or "-")
        raw = entry.get("raw_text", "")
        # Truncate raw notes if long
        if len(raw) > 35:
            raw = raw[:32] + "..."
        rows.append([entry["date"], entry["exercise"], w, r, s, raw])

    print("\n--- Workout History ---")
    print_table(headers, rows)


def main():
    arg_parser = argparse.ArgumentParser(
        prog="gym-log-buddy",
        description="Gym Log Buddy - Open-Source Local AI Workout Logger"
    )
    subparsers = arg_parser.add_subparsers(dest="command", help="Available commands")

    # Command: log
    log_parser = subparsers.add_parser("log", help="Parse and log a workout session")
    log_parser.add_argument("text", nargs="?", default=None, help="Workout text in messy English")
    log_parser.add_argument("-y", "--yes", action="store_true", help="Auto-confirm save without interactive prompt")

    # Command: last
    last_parser = subparsers.add_parser("last", help="Show the most recent workout session")
    last_parser.add_argument("exercise", nargs="?", default=None, help="Optional exercise name")

    # Command: suggest
    suggest_parser = subparsers.add_parser("suggest", help="Get progressive overload suggestion for an exercise")
    suggest_parser.add_argument("exercise", help="Exercise name")

    # Command: history
    history_parser = subparsers.add_parser("history", help="Show workout log history")
    history_parser.add_argument("exercise", nargs="?", default=None, help="Filter by exercise name")

    args = arg_parser.parse_args()

    if args.command == "log":
        handle_log(args)
    elif args.command == "last":
        handle_last(args)
    elif args.command == "suggest":
        handle_suggest(args)
    elif args.command == "history":
        handle_history(args)
    else:
        arg_parser.print_help()


if __name__ == "__main__":
    main()
