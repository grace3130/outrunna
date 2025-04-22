import streamlit as st
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
    """
    Return a mapping from RPE to formatted pace ranges using MM:SS format.
    """
    return {
        3: f"{format_pace(base_pace + 3)}–{format_pace(base_pace + 4)} min/mile (Recovery)",
        4: f"{format_pace(base_pace + 2)}–{format_pace(base_pace + 2.5)} min/mile (Easy)",
        5: f"{format_pace(base_pace + 1.5)}–{format_pace(base_pace + 2)} min/mile (Steady)",
        6: f"{format_pace(base_pace + 0.75)}–{format_pace(base_pace + 1.25)} min/mile (Marathon Pace)",
        7: f"{format_pace(base_pace + 0.25)}–{format_pace(base_pace + 0.5)} min/mile (Tempo)",
        8: f"{format_pace(base_pace - 0.1)}–{format_pace(base_pace + 0.1)} min/mile (10K)",
        9: f"{format_pace(base_pace - 0.3)}–{format_pace(base_pace - 0.15)} min/mile (5K)",
    }

# ---------- Workout Library ----------
workout_library = [
    {"name": "Easy Run",      "duration": 45, "rpe": 3},
    {"name": "Tempo Run",     "duration": 40, "rpe": 7},
    {"name": "Long Run",      "duration": 75, "rpe": 4},
    {"name": "Norwegian 4x4", "structure": "4x4 min intervals @ RPE 9 with 3 min rest", "duration": 40, "rpe": 9}
]

# ---------- Generate One Week of Workouts ----------
def generate_rpe_week(user_profile, workout_library, week_num=1):
    days = user_profile["days_per_week"]
    total_minutes = user_profile["weekly_duration_minutes"]
    minutes_per_day = total_minutes // days

    base_5k_pace = user_profile["base_5k_pace"]
    pace_zones = rpe_to_pace_map(base_5k_pace)

    # Map types to workout templates
    workout_types = {
        "easy": next(w for w in workout_library if w["name"] == "Easy Run"),
        "tempo": next(w for w in workout_library if w["name"] == "Tempo Run"),
        "long": next(w for w in workout_library if w["name"] == "Long Run"),
        "interval": next(w for w in workout_library if w["name"] == "Norwegian 4x4")
    }

    # Structure based on days/week
    if days == 3:
        first = "tempo" if week_num % 2 == 1 else "interval"
        structure = [first, "easy", "long"]
    else:
        structure = ["long", "easy", "interval", "tempo"] + ["easy"] * (days - 4)

    week_plan = []
    hard_counts = {"tempo": 0, "interval": 0}

    for i, key in enumerate(structure):
        # Prevent duplicate hard sessions
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
def generate_wave(user_profile, start_week, base_minutes, progression=0.08, deload=0.7):
    wave = []
    goal = user_profile["goal_distance"].lower()
    tt_dist = 2 if goal == "5k" else 3.1

    for offset in range(4):
        week_num = start_week + offset
        is_deload = (offset == 3)
        minutes = round(base_minutes * (deload if is_deload else (1 + progression * offset)), 1)

        week = generate_rpe_week(
            {**user_profile, "weekly_duration_minutes": minutes},
            workout_library,
            week_num
        )

        if is_deload:
            tt = {
                "day": "Day 1",
                "workout": f"{tt_dist if tt_dist==2 else '5K'} Time Trial",
                "duration": 20 if tt_dist == 2 else 25,
                "rpe": 9,
                "context_pace": "All-out (goal pace)",
                "description": "Time trial—log result to update paces"
            }
            for j, sess in enumerate(week):
                if sess["rpe"] in [7, 9]:
                    week[j] = tt
                    break
        wave.append({"week": week_num, "minutes": minutes, "sessions": week})
    return wave

# ---------- Full Plan Until Race ----------
def generate_plan(user_profile, start_date, race_date, base_minutes):
    start = datetime.strptime(start_date, "%Y-%m-%d")
    race = datetime.strptime(race_date, "%Y-%m-%d")
    weeks = (race - start).days // 7

    plan = []
    week_cursor = 1
    peak = base_minutes

    while weeks - week_cursor >= 2:
        wv = generate_wave(user_profile, week_cursor, base_minutes)
        plan.extend(wv)
        base_minutes = wv[-2]["minutes"]
        peak = max(peak, base_minutes)
        week_cursor += 4

    # Taper
    taper_min = round(peak * 0.7, 1)
    tw = generate_rpe_week({**user_profile, "weekly_duration_minutes": taper_min}, workout_library)
    plan.append({"week": week_cursor, "minutes": taper_min, "label": "Taper Week", "sessions": tw})
    week_cursor += 1

    # Race Week
    race_wk = [
        {"day": "Day 1", "workout": "6x400m Strides", "duration": 20, "rpe": 9, "context_pace": "10K pace", "description": "Sharpen up"},
        {"day": "Day 3", "workout": f"{user_profile['goal_distance']} Race", "duration": 25 if user_profile['goal_distance']=="5K" else 60, "rpe": 9, "context_pace": "All-out", "description": "Race day!"}
    ]
    plan.append({"week": week_cursor, "minutes": round(peak*0.5,1), "label": "Race Week", "sessions": race_wk})
    return plan

# ---------- Prediction ----------
def predict_time(trial_str, trial_dist, goal_dist):
    m, s = map(int, trial_str.split(':'))
    t1 = m + s/60
    t2 = t1 * (goal_dist / trial_dist) ** 1.06
    mm = int(t2)
    ss = int((t2 - mm)*60)
    return f"{mm}:{ss:02d}"

# ---------- Streamlit UI ----------
st.title("OutRunna MVP")
col1, col2 = st.columns(2)
with col1:
    goal_dist = st.selectbox("Goal Distance", ["5K","10K","Half","Marathon"])
    pr = st.text_input("5K PR (MM:SS)","25:00")
with col2:
    days = st.slider("Days/Week",3,6,4)
    rd = st.date_input("Race Date",datetime.today()+timedelta(weeks=8))

if st.button("Generate Plan"):
    mins, secs = map(int, pr.split(':'))
    base_pace = (mins*60+secs)/3.1/60
    user = {"goal_distance":goal_dist,"days_per_week":days,"weekly_duration_minutes":240,"base_5k_pace":base_pace}
    plan = generate_plan(user,str(datetime.today().date()),str(rd),240)

    st.subheader("Race Prediction")
    tt = st.text_input("Time Trial (MM:SS)","")
    tdist = 2 if goal_dist=="5K" else 3.1
    gdist = {"5K":3.1,"10K":6.2,"Half":13.1,"Marathon":26.2}[goal_dist]
    if tt and ':' in tt:
        st.success(f"Predicted {goal_dist} Time: {predict_time(tt,tdist,gdist)}")

    st.subheader("Training Plan")
    for wk in plan:
        label = wk.get('label',f"Week {wk['week']}")
        st.markdown(f"### {label} – {wk['minutes']} min")
        for s in wk['sessions']:
            st.markdown(f"- **{s['day']}**: {s['workout']} – {s['duration']} min @ RPE {s['rpe']}")
            st.caption(f"Pace: {s.get('context_pace','N/A')} | {s.get('description','')}")
