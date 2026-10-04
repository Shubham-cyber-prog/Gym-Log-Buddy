"""
app.py - Streamlit Web UI for Gym Log Buddy

Features:
- Parse workout notes using local Ollama (gemma3)
- Preview, edit, and confirm parsed exercises
- SQLite persistence in gym.db
- Sidebar displaying last performance and progressive overload target
- History tab with weight progression line chart
"""

import streamlit as st
import pandas as pd
from datetime import date
from typing import List, Dict, Any

import db
import parser
import suggest

# Page Configuration - Minimal plain text without emojis
st.set_page_config(
    page_title="Gym Log Buddy",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize Database
db.init_db()

# State Management
if "parsed_exercises" not in st.session_state:
    st.session_state.parsed_exercises = None
if "last_raw_text" not in st.session_state:
    st.session_state.last_raw_text = ""
if "quick_fill_text" not in st.session_state:
    st.session_state.quick_fill_text = ""
if "save_success_msg" not in st.session_state:
    st.session_state.save_success_msg = None

# Sidebar: Progressive Overload & Stats
with st.sidebar:
    st.title("Gym Log Buddy")
    st.caption("Local model: gemma3 | Database: gym.db")
    st.markdown("---")

    st.subheader("Progressive Overload Target")
    tracked_exercises = db.get_exercises()

    if tracked_exercises:
        selected_exercise = st.selectbox(
            "Select an exercise:",
            tracked_exercises,
            key="sidebar_exercise_select"
        )

        last_sess = db.get_last_session(selected_exercise)
        if last_sess:
            last_wt = last_sess.get("weight_kg")
            last_reps = last_sess.get("reps")
            last_sets = last_sess.get("sets")

            wt_display = f"{last_wt:.1f} kg" if last_wt is not None else "Bodyweight"
            reps_display = f"{last_reps} reps" if last_reps is not None else "N/A"
            sets_display = f"{last_sets} sets" if last_sets is not None else "N/A"

            st.write(f"**Last time ({last_sess['date']}):**")
            st.write(f"{wt_display} | {reps_display} | {sets_display}")

            suggestion_text = suggest.get_suggestion(last_wt, last_reps, last_sets)
            st.write("**Try today:**")
            st.write(suggestion_text)
    else:
        st.info("No workouts logged yet. Log your first workout to see progressive overload targets here.")

    st.markdown("---")
    st.subheader("Database Stats")
    all_logs = db.get_all_logs()
    st.metric("Total Entries", len(all_logs))
    st.metric("Unique Exercises", len(tracked_exercises))

# Main App Layout
st.title("Gym Log Buddy")
st.write("Enter workout notes in plain English. Local Ollama (gemma3) parses them into structured data.")

tab_log, tab_history = st.tabs(["Log Workout", "History and Progress"])

with tab_log:
    st.subheader("1. Enter Workout Notes")

    if st.session_state.get("save_success_msg"):
        st.success(st.session_state.save_success_msg)
        st.session_state.save_success_msg = None

    # Quick prompt chips
    st.write("Examples:")
    col_ex1, col_ex2, col_ex3 = st.columns(3)
    with col_ex1:
        if st.button("Example 1 (Bench, Incline, Squat)", use_container_width=True):
            st.session_state.quick_fill_text = "bench 60kg 8 reps 3 sets, incline db 22 x 10 x 3, squat 80 5x5"
    with col_ex2:
        if st.button("Example 2 (Curls in lbs, Pullups)", use_container_width=True):
            st.session_state.quick_fill_text = "db curl 30 lbs 10 reps 3 sets, pullups 4x8, bb row 50 12x3"
    with col_ex3:
        if st.button("Example 3 (Deadlift, OHP, Dips)", use_container_width=True):
            st.session_state.quick_fill_text = "deadlift 100kg 5x5, overhead press 40kg 6 reps, dips 3 sets 12 reps"

    col_input, col_date = st.columns([3, 1])
    with col_input:
        default_val = st.session_state.quick_fill_text or st.session_state.last_raw_text
        workout_text = st.text_area(
            "Workout Notes",
            value=default_val,
            placeholder="e.g. bench 60kg 8 reps 3 sets, incline db 22 x 10 x 3, squat 80 5x5",
            height=100,
            key="workout_input_area"
        )
    with col_date:
        workout_date = st.date_input("Workout Date", value=date.today(), key="workout_date_picker")

    btn_parse = st.button("Parse Workout", type="primary", use_container_width=True)

    if btn_parse:
        if not workout_text.strip():
            st.warning("Please enter workout notes first.")
        else:
            with st.spinner("Parsing with the local model. The first run can take 20-30 seconds."):
                result = parser.parse_workout(workout_text.strip())

            if not result.get("success"):
                err = result.get("error", "Parsing failed.")
                st.error(f"Error: {err}")
                if "Start Ollama" in err:
                    st.info("Start Ollama and run: ollama pull gemma3")
            else:
                exercises = result.get("exercises", [])
                if not exercises:
                    st.warning("No exercises detected. Check input.")
                else:
                    st.session_state.parsed_exercises = exercises
                    st.session_state.last_raw_text = workout_text.strip()
                    st.success(f"Extracted {len(exercises)} exercise(s).")

    # Confirmation & Review Section
    if st.session_state.parsed_exercises:
        st.markdown("---")
        st.subheader("2. Review and Confirm")
        st.info("Save karne se pehle values check karo")
        st.caption("Missing values null dikhenge. Kisi bhi cell par click karke directly edit kar sakte hain.")

        df_preview = pd.DataFrame(st.session_state.parsed_exercises)
        edited_df = st.data_editor(
            df_preview,
            num_rows="dynamic",
            use_container_width=True,
            key="preview_data_editor"
        )

        st.subheader("Projected Next Overload Targets")
        for idx, row in edited_df.iterrows():
            target_str = suggest.get_suggestion(row.get("weight_kg"), row.get("reps"), row.get("sets"))
            st.write(f"- {row.get('exercise', 'Exercise')}: {target_str}")

        col_save, col_cancel = st.columns([1, 4])
        with col_save:
            if st.button("Save Workout", type="primary", use_container_width=True):
                items_to_save = edited_df.to_dict(orient="records")
                date_str = workout_date.isoformat()
                count = db.save_workout(date_str, items_to_save, st.session_state.last_raw_text)
                st.session_state.save_success_msg = f"{count} exercise(s) saved for {date_str}."
                st.session_state.parsed_exercises = None
                st.session_state.quick_fill_text = ""
                st.rerun()
        with col_cancel:
            if st.button("Discard"):
                st.session_state.parsed_exercises = None
                st.rerun()

with tab_history:
    st.subheader("Workout History and Analytics")
    all_logs = db.get_all_logs()

    if not all_logs:
        st.info("No workout history yet. As you log workouts, your progress charts and session history will appear here.")
    else:
        df_logs = pd.DataFrame(all_logs)

        st.subheader("Weight Progression Over Time")
        exercises_list = db.get_exercises()
        if exercises_list:
            selected_chart_ex = st.selectbox("Select exercise:", exercises_list, key="chart_select")
            selected_key = db.normalize_exercise_name(selected_chart_ex)
            ex_df = df_logs[df_logs["exercise"].apply(db.normalize_exercise_name) == selected_key].copy()

            if not ex_df.empty:
                ex_df["date"] = pd.to_datetime(ex_df["date"])
                ex_df = ex_df.sort_values("date")

                col_m1, col_m2, col_m3 = st.columns(3)
                max_wt = ex_df["weight_kg"].max()
                latest_wt = ex_df.iloc[-1]["weight_kg"]
                col_m1.metric("Max Weight", f"{max_wt:.1f} kg" if pd.notnull(max_wt) else "N/A")
                col_m2.metric("Latest Weight", f"{latest_wt:.1f} kg" if pd.notnull(latest_wt) else "N/A")
                col_m3.metric("Total Sessions", len(ex_df))

                chart_data = ex_df.dropna(subset=["weight_kg"])[["date", "weight_kg"]].set_index("date")
                if not chart_data.empty:
                    st.line_chart(chart_data, y="weight_kg", use_container_width=True)
                else:
                    st.info("No weight recorded for this exercise.")

        st.subheader("All Recorded Sessions")
        st.dataframe(
            df_logs[["date", "exercise", "weight_kg", "reps", "sets", "raw_text"]],
            use_container_width=True,
            column_config={
                "date": "Date",
                "exercise": "Exercise",
                "weight_kg": st.column_config.NumberColumn("Weight (kg)", format="%.1f kg"),
                "reps": "Reps",
                "sets": "Sets",
                "raw_text": "Original Note"
            }
        )
