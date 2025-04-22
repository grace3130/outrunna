import streamlit as st
from datetime import datetime, timedelta
import pandas as pd

# ---------- Helper Functions ----------
def rpe_to_pace_map(base_pace):
    return {
        3: f"{round(base_pace + 3, 2)}–{round(base_pace + 4, 2)} min/mile (Recovery)",
        4: f"{round(base_pace + 2, 2)}–{round(base_pace + 2.5, 2)} min/mile (Easy)",
        5: f"{round(base_pace + 1.5, 2)}–{round(base_pace + 2, 2)} min/mile (Steady)",
        6: f"{round(base_pace + 0.75, 2)}–{round(base_pace + 1.25, 2)} min/mile (Marathon Pace)",
        7: f"{round(base_pace + 0.25, 2)}–{round(base_pace + 0.5, 2)} min/mile (Tempo)",
        8: f"{round(base_pace - 0.1, 2)}–{round(base_pace + 0.1, 2)} min/mile (10K)",
        9: f"{round(base_pace - 0.3, 2)}–{round(base_pace - 0.15, 2)} min/mile (5K)",
    }

workout_library = [
    {"name": "Easy Run", "duration": 45, "rpe": 4},
    {"name": "Tempo Run", "duration": 40, "rpe": 7},
    {"name": "Long Run", "duration": 75, "rpe": 6},
    {"name": "Norwegian 4x4", "structure": "4x4 min intervals @ RPE 8 with 3 min rest", "duration": 40, "rpe": 8}
]

def generate_rpe_week(user_profile, workout_library):
    total_minutes = user_profile["weekly_duration_minutes"]
    days = user_profile["days_per_week"]
    minutes_per_day = total_minutes // days

    base_5k_pace = user_profile["base_5k_pace"]
    pace_zones = rpe_to_pace_map(base_5k_pace)

    selected_workouts = []
    used_names = set()

    for _ in range(days):
        valid = [w for w in workout_library if w["name"] not in used_names]
        if not valid:
            valid = workout_library
        workout = min(valid, key=lambda w: abs(w["duration"] - minutes_per_day))
        used_names.add(workout["name"])
        selected_workouts.append(workout)

    week_plan = []
    for i, w in enumerate(selected_workouts, 1):
        pace_info = pace_zones.get(w["rpe"], "N/A")
        detail = w.get("structure", f"{w['duration']} min @ RPE {w['rpe']}")
        week_plan.append({
            "day": f"Day {i}",
            "workout": w["name"],
            "duration": w["duration"],
            "rpe": w["rpe"],
            "context_pace": pace_info,
            "description": detail
        })

    return week_plan

def generate_wave(user_profile, start_week_num, base_minutes, progression_rate=0.08, deload_factor=0.7):
    wave = []
    goal = user_profile["goal_distance"].lower()
    time_trial_dist = "2 miles" if goal == "5k" else "5K"

    for week_offset in range(4):
        week_num = start_week_num + week_offset
        is_deload = (week_offset == 3)

        if is_deload:
            week_minutes = round(base_minutes * deload_factor, 1)
        else:
            week_minutes = round(base_minutes * (1 + progression_rate * week_offset), 1)

        week_workouts = generate_rpe_week({**user_profile, "weekly_duration_minutes": week_minutes}, workout_library)

        if is_deload:
            time_trial_workout = {
                "day": "Day 1",
                "workout": f"{time_trial_dist} Time Trial",
                "duration": 20 if goal == "5k" else 25,
                "rpe": 8,
                "context_pace": "All-out but steady (goal pace)",
                "description": "Time trial effort – log your result for pace updates."
            }
            replaced = False
            for i, w in enumerate(week_workouts):
                if w["rpe"] in [7, 8]:
                    week_workouts[i] = time_trial_workout
                    replaced = True
                    break
            if not replaced:
                week_workouts[0] = time_trial_workout

        wave.append({
            "week_num": week_num,
            "total_minutes": week_minutes,
            "workouts": week_workouts
        })

    return wave

def generate_plan_until_race(user_profile, start_date, race_date, base_minutes):
    start = datetime.strptime(start_date, "%Y-%m-%d")
    race = datetime.strptime(race_date, "%Y-%m-%d")
    total_weeks = (race - start).days // 7

    plan = []
    current_week = 1
    peak_minutes = base_minutes

    while total_weeks - current_week >= 2:
        wave = generate_wave(user_profile, current_week, base_minutes)
        plan.extend(wave)
        base_minutes = wave[-2]["total_minutes"]
        peak_minutes = max(peak_minutes, base_minutes)
        current_week += 4

    taper_minutes = round(peak_minutes * 0.7, 1)
    taper_week = generate_rpe_week({**user_profile, "weekly_duration_minutes": taper_minutes}, workout_library)

    plan.append({
        "week_num": current_week,
        "total_minutes": taper_minutes,
        "label": "Taper Week",
        "workouts": taper_week
    })
    current_week += 1

    race_workout = {
        "day": "Day 3",
        "workout": f"{user_profile['goal_distance'].upper()} Race",
        "duration": 25 if user_profile["goal_distance"].lower() == "5k" else 60,
        "rpe": 9,
        "context_pace": "All-out (race effort)",
        "description": "Race day – give it your best and log your result!"
    }

    strides = {
        "day": "Day 1",
        "workout": "Taper Strides – 6x400m",
        "duration": 20,
        "rpe": 7,
        "context_pace": "10K pace",
        "description": "6x400m at 10K pace with full recovery. Sharpen up."
    }

    plan.append({
        "week_num": current_week,
        "total_minutes": round(peak_minutes * 0.5, 1),
        "label": "Race Week",
        "workouts": [strides, race_workout]
    })

    return plan

# ---------- Streamlit UI ----------
st.title("OutRunna - RPE Based Training Plan Generator")

col1, col2 = st.columns(2)
with col1:
    goal_distance = st.selectbox("Goal Distance", ["5K", "10K", "Half", "Marathon"])
    five_k_pr = st.text_input("Your 5K PR (MM:SS)", "25:00")
with col2:
    days_per_week = st.slider("Training Days per Week", 3, 6, 4)
    race_date = st.date_input("Race Date", value=datetime.today() + timedelta(weeks=8))

if st.button("Generate Plan"):
    minutes = int(five_k_pr.split(":")[0]) * 60 + int(five_k_pr.split(":")[1])
    pace = minutes / 3.1  # in seconds per mile
    base_5k_pace = pace / 60  # convert to min/mile

    user_profile = {
        "goal_distance": goal_distance,
        "days_per_week": days_per_week,
        "weekly_duration_minutes": 240,
        "base_5k_pace": base_5k_pace
    }

    plan = generate_plan_until_race(user_profile, str(datetime.today().date()), str(race_date), 240)

    st.subheader("Your Training Plan")
    for week in plan:
        label = week.get("label", f"Week {week['week_num']}")
        st.markdown(f"### {label} – {week['total_minutes']} min")
        for w in week["workouts"]:
            st.markdown(f"- **{w['day']}**: {w['workout']} – {w['duration']} min @ RPE {w['rpe']}  ")
            st.caption(f"Pace: {w['context_pace']} | {w['description']}")
