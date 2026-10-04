"""
suggest.py - Progressive Overload Suggestion Engine

Rule-based logic to suggest the next workout target for an exercise.
NOTE: This is deterministic plain Python logic (NOT AI).

Progressive overload is the foundation of strength training:
- If the lifter hit 10 or more reps, they have earned the right to increase weight (+2.5 kg)
  and drop reps back down to 8 to build back up.
- Otherwise, they keep the same weight and aim for +1 extra rep.
"""

from typing import Optional


def get_suggestion(
    last_weight_kg: Optional[float],
    last_reps: Optional[int],
    last_sets: Optional[int] = None
) -> str:
    """
    Computes progressive overload recommendation based on the previous session.

    Rules:
      - If last reps >= 10:
          Suggest +2.5 kg and 8 reps.
      - Otherwise:
          Suggest same weight and +1 rep.

    Parameters:
      last_weight_kg: Weight lifted last time in kg (None for bodyweight/untracked)
      last_reps: Number of repetitions completed last time
      last_sets: Number of sets completed last time (optional, for context)

    Returns:
      A short, human-readable recommendation string.
    """
    # Progressive Overload Rule:
    # Handling when reps are known:
    if last_reps is not None:
        if last_reps >= 10:
            # Hit 10+ reps -> increase weight by 2.5 kg and reset to 8 reps
            if last_weight_kg is not None:
                new_weight = round(last_weight_kg + 2.5, 1)
                sets_info = f" ({last_sets} sets)" if last_sets else ""
                return f"+2.5 kg ({new_weight} kg) x 8 reps{sets_info}"
            else:
                sets_info = f" ({last_sets} sets)" if last_sets else ""
                return f"+2.5 kg (weighted) x 8 reps{sets_info}"
        else:
            # Under 10 reps -> hold weight steady and aim for 1 more rep
            new_reps = last_reps + 1
            weight_str = f"{last_weight_kg} kg" if last_weight_kg is not None else "bodyweight"
            sets_info = f" ({last_sets} sets)" if last_sets else ""
            return f"Same weight ({weight_str}) x {new_reps} reps (+1 rep){sets_info}"

    # Fallback if reps weren't logged last time
    if last_weight_kg is not None:
        return f"Try {last_weight_kg} kg x 8-10 reps"

    return "No previous reps recorded. Start comfortable and aim for 8-10 reps."
