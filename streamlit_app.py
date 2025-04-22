import streamlit as st
st.set_page_config(page_title="OutRunna", page_icon="🏃")
from datetime import datetime, timedelta
import pandas as pd

# ---------- Helper Functions ----------
def format_pace(min_per_mile):
    """
    Convert a pace in decimal minutes per mile to MM:SS string format.
    """
    minutes = int(min_per_mile)
    seconds = int(round((min_per_mile - minutes) * 60))
    return f"{minutes}:{seconds:02d}"


def rpe_to_pace_map(base_pace):
    """Return mapping from RPE to pace ranges in MM:SS."""
    return {
        3: f"{format_pace(base_pace + 3)}–{format_pace(base_pace + 4)} min/mile (Recovery)",
        4: f"{format_pace(base_pace + 2)}–{format_pace(base_pace + 2.5)} min/mile (Easy)",
        5: f"{format_pace(base_pace + 1.5)}–{format_pace(base_pace + 2)} min/mile (Steady)",
        6: f"{format_pace(base_pace + 0.75)}–{format_pace(base_pace + 1.25)} min/mile (Marathon Pace)",
        7: f"{format_pace(base_pace + 0.25)}–{format_pace(base_pace + 0.5)} min/mile (Tempo)",
        8: f"{format_pace(base_pace - 0.1)}–{format_pace(base_pace + 0.1)} min/mile (10K)",
        9: f"{format_pace(base_pace - 0.3)}–{format_pace(base_pace - 0.15)} min/mile (5K)",
    }


def predict_distance_time(time_str, d1, d2, exponent=1.06):
    """
    Convert a time string MM:SS at distance d1 to predicted time at distance d2 via Riegel.
    Returns minutes (float).
    """
    m, s = map(int, time_str.split(':'))
    t1 = m + s/60
    return t1 * (d2 / d1)**exponent


def compute_tt_target_range(pr_5k, wave_num,
                            base_dist=3.1, tt_dist=2,
                            improvement_rate=0.015, buffer_pct=0.02):
    """
    Calculate target TT range for given wave based on initial 5K PR.
    Returns (low_str, high_str).
    """
    baseline = predict_distance_time(pr_5k, base_dist, tt_dist)
    factor = max(0, 1 - improvement_rate * wave_num)
    target = baseline * factor
    low = target * (1 - buffer_pct)
    high = target * (1 + buffer_pct)
    def fmt(x):
        m = int(x)
        sec = int(round((x - m) * 60))
        return f"{m}:{sec:02d}"
    return fmt(low), fmt(high)

# ---------- Workout Library ----------
workout_library = [
    {"name": "Easy Run",      "duration": 45, "rpe": 3},
    {"name": "Tempo Run",     "duration": 40, "rpe": 7},
    {"name": "Long Run",      "duration": 75, "rpe": 4},
    {"name": "Norwegian 4x4", "structure": "4x4 min intervals @ RPE 9 with 3 min rest", "duration": 40, "rpe": 9}
]

# ---------- Generate One Week ----------
def generate_rpe_week(user_profile, workout_library, week_num=1):
    days = user_profile["days_per_week"]
    total_minutes = user_profile["weekly_duration_minutes"]

    base_5k_pace = user_profile["base_5k_pace"]
    pace_zones = rpe_to_pace_map(base_5k_pace)

    workout_types = {
        "easy": next(w for w in workout_library if w["name"] == "Easy Run"),
        "tempo": next(w for w in workout_library if w["name"] == "Tempo Run"),
        "long": next(w for w in workout_library if w["name"] == "Long Run"),
        "interval": next(w for w in workout_library if w["name"] == "Norwegian 4x4")
    }

    if days == 3:
        first = "tempo" if week_num % 2 == 1 else "interval"
        structure = [first, "easy", "long"]
    else:
        structure = ["long", "easy", "interval", "tempo"] + ["easy"] * (days - 4)

    week_plan = []
    hard_counts = {"tempo": 0, "interval": 0}

    for i, key in enumerate(structure):
        if key in hard_counts:
            if hard_counts[key] >= 1:
                key = "easy"
            else:
                hard_counts[key] += 1
        w = workout_types[key].copy()
        pace_info = pace_zones.get(w["rpe"], "N/A")
        detail = w.get("structure", f"{w['duration']} min @ RPE {w['rpe']}")
        week_plan.append({
            "day": f"Day {i+1}",
            "workout": w["name"],
            "duration": w["duration"],
            "rpe": w["rpe"],
            "context_pace": pace_info,
            "description": detail
        })

    return week_plan

# ---------- Generate 4-Week Wave ----------
def generate_wave(user_profile, start_week_num, base_minutes, progression_rate=0.08, deload_factor=0.7):
    wave = []
    goal = user_profile["goal_distance"].lower()
    time_trial_dist = "2 miles" if goal == "5k" else "5K"

    for offset in range(4):
        week_num = start_week_num + offset
        is_deload = (offset == 3)
        minutes = round(base_minutes * (deload_factor if is_deload else (1 + progression_rate * offset)), 1)

        week_sessions = generate_rpe_week(
            {**user_profile, "weekly_duration_minutes": minutes},
            workout_library,
            week_num
        )
        if is_deload:
            tt = {
                "day": "Day 1",
                "workout": f"{time_trial_dist} Time Trial",
                "duration": 20 if goal == "5k" else 25,
                "rpe": 9,
                "context_pace": "All-out (goal pace)",
                "description": "Time trial—log result to update paces"
            }
            for j, sess in enumerate(week_sessions):
                if sess["rpe"] in [7, 9]:
                    week_sessions[j] = tt
                    break
            entry = {"week_num": week_num, "minutes": minutes, "sessions": week_sessions, "label": "Deload Week"}
        else:
            entry = {"week_num": week_num, "minutes": minutes, "sessions": week_sessions}
        wave.append(entry)

    return wave

# ---------- Full Plan Until Race ----------
def generate_plan(user_profile, start_date, race_date, base_minutes):
    start = datetime.strptime(start_date, "%Y-%m-%d")
    race = datetime.strptime(race_date, "%Y-%m-%d")
    total_weeks = (race - start).days // 7

    plan = []
    current_week = 1
    peak_minutes = base_minutes

    while total_weeks - current_week >= 2:
        wave = generate_wave(user_profile, current_week, base_minutes)
        plan.extend(wave)
        base_minutes = wave[-2]["minutes"]
        peak_minutes = max(peak_minutes, base_minutes)
        current_week += 4

    taper_minutes = round(peak_minutes * 0.7, 1)
    taper_sessions = generate_rpe_week({**user_profile, "weekly_duration_minutes": taper_minutes}, workout_library)
    plan.append({"week_num": current_week, "minutes": taper_minutes, "label": "Taper Week", "sessions": taper_sessions})
    current_week += 1

    strides = {"day": "Day 1", "workout": "6x400m Strides", "duration": 20, "rpe": 9, "context_pace": "10K pace", "description": "Sharpen up"}
    race_workout = {"day": "Day 3", "workout": f"{user_profile['goal_distance'].upper()} Race", "duration": 25 if user_profile["goal_distance"].lower() == "5k" else 60, "rpe": 9, "context_pace": "All-out (race effort)", "description": "Race day!"}
    plan.append({"week_num": current_week, "minutes": round(peak_minutes * 0.5, 1), "label": "Race Week", "sessions": [strides, race_workout]})

    return plan

# ---------- Prediction Function ----------
def predict_time(time_str, trial_dist, goal_dist):
    m, s = map(int, time_str.split(':'))
    t1 = m + s/60
    t2 = t1 * (goal_dist / trial_dist) ** 1.06
    mm = int(t2)
    ss = int((t2 - mm) * 60)
    return f"{mm}:{ss:02d}"

# ---------- Streamlit UI ----------
st.title("OutRunna MVP")

col1, col2 = st.columns(2)
with col1:
    goal_dist = st.selectbox("Goal Distance", ["5K","10K","Half","Marathon"])
    pr = st.text_input("Your 5K PR (MM:SS)", "25:00")
    try:
        init_pred = predict_time(pr, 3.1, {"5K":3.1,"10K":6.2,"Half":13.1,"Marathon":26.2}[goal_dist])
        st.success(f"Initial Predicted {goal_dist} Time: {init_pred}")
    except:
        pass
with col2:
    days = st.slider("Days/Week", 3, 6, 4)
    race_date = st.date_input("Race Date", value=datetime.today() + timedelta(weeks=8))

if st.button("Generate Plan"):
    mins, secs = map(int, pr.split(':'))
    base_pace = (mins * 60 + secs) / 3.1 / 60
    user_profile = {"goal_distance": goal_dist, "days_per_week": days, "weekly_duration_minutes": 240, "base_5k_pace": base_pace}
    plan = generate_plan(user_profile, str(datetime.today().date()), str(race_date), 240)

    st.subheader("📅 Time Trial Schedule & Race Predictions")
    start = datetime.today().date()
    total_weeks = (race_date - start).days // 7
    tt_dates = []
    week_cursor = 1
    while total_weeks - week_cursor >= 2:
        tt_week = week_cursor + 3
        tt_dates.append(start + timedelta(weeks=tt_week-1))
        week_cursor += 4

    tt_dist = 2 if goal_dist == "5K" else 3.1
    goal_mi = {"5K":3.1,"10K":6.2,"Half":13.1,"Marathon":26.2}[goal_dist]

    for idx, tt_date in enumerate(tt_dates):
        low, high = compute_tt_target_range(pr, idx+1)
        row = st.columns(3)
        row[0].write(f"**{tt_date}**\nTarget: {low}–{high}")
        tt_input = row[1].text_input("Enter TT (MM:SS)", "", key=f"tt_{idx}")
        pred = ""
        if tt_input and ':' in tt_input:
            pred = predict_time(tt_input, tt_dist, goal_mi)
        row[2].write(f"**{pred}**")

    st.subheader("🏃 Training Plan")
    for wk in plan:
        label = wk.get("label", f"Week {wk['week_num']}")
        if label == "Deload Week":
            st.markdown(f"<h3 style='color:green'>{label} – {wk['minutes']} min</h3>", unsafe_allow_html=True)
        else:
            st.markdown(f"### {label} – {wk['minutes']} min")
        for sess in wk["sessions"]:
            st.markdown(f"- **{sess['day']}**: {sess['workout']} – {sess['duration']} min @ RPE {sess['rpe']}")
            st.caption(f"Pace: {sess.get('context_pace','N/A')} | {sess.get('description','')}")
