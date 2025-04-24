import streamlit as st
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

# ---------- Page Configuration ----------
st.set_page_config(page_title="OutRunna", page_icon="🏃")

# ---------- UI Header ----------
st.title("OutRunna. It's free.")
st.markdown("""
**Two hard workouts per week (Intervals & Tempo) + one Long Run**
From Coach Chris Bennett: 2 hard sessions a week, then run as many easy miles as your legs can handle.
""")

# ---------- Helper Functions ----------
def format_pace(minutes_per_mile: float) -> str:
    """Formats a pace in minutes per mile (float) into a MM:SS string."""
    minutes = int(minutes_per_mile)
    seconds = int(round((minutes_per_mile - minutes) * 60))
    return f"{minutes}:{seconds:02d}"

def rpe_to_pace_map(base_pace: float) -> Dict[str, str]:
    """Generates a dictionary mapping workout types to pace ranges based on a base 5K pace."""
    return {
        "interval": f"{format_pace(base_pace - 0.3)}–{format_pace(base_pace - 0.15)} min/mile (Intervals @ RPE 9)",
        "tempo": f"{format_pace(base_pace + 0.25)}–{format_pace(base_pace + 0.5)} min/mile (Tempo @ RPE 7)",
        "long": f"{format_pace(base_pace + 0.75)}–{format_pace(base_pace + 1.25)} min/mile (Long @ RPE 4)"
    }

def predict_distance_time(time_str: str, d1: float, d2: float, exponent: float = 1.06) -> Optional[float]:
    """
    Predicts race time for a distance d2 based on a known time for distance d1.

    Args:
        time_str (str):  Time for distance d1 (MM:SS).
        d1 (float): Distance 1 in miles.
        d2 (float): Distance 2 in miles.
        exponent (float):  The exponent used in the formula.  1.06 is a common value.
    Returns:
        Predicted time for distance d2 in minutes, or None on error.
    """
    try:
        m, s = map(int, time_str.split(':'))
        t1 = m + s / 60
        return t1 * (d2 / d1) ** exponent
    except ValueError:
        return None  # Handle invalid time string

def predict_time(time_str: str, trial_dist: float, goal_dist: float) -> str:
    """Predicts race time for the goal distance based on a trial time."""
    minutes = predict_distance_time(time_str, trial_dist, goal_dist)
    if minutes is not None:
        return format_pace(minutes)
    else:
        return "Invalid Time"

def compute_tt_target_range(pr_5k: str, wave_num: int, tt_dist: float = 2, improvement_rate: float = 0.015, buffer_pct: float = 0.02) -> tuple[str, str]:
    """Computes a target time range for a time trial, adjusting for improvement.

    Args:
        pr_5k (str): 5K PR in MM:SS format
        wave_num (int): The week number in the training wave (1, 2, 3, or 4)
        tt_dist (float): The distance of the time trial.  Defaults to 2 miles.
        improvement_rate (float):  The assumed improvement rate per week.
        buffer_pct (float):  The percentage buffer around the target time.
    """
    base_dist = 3.1  # 5K distance in miles
    baseline_tt = predict_distance_time(pr_5k, base_dist, tt_dist)  # Predict TT time from 5K PR
    if baseline_tt is not None:
        # Apply improvement factor
        factor = max(0, 1 - improvement_rate * wave_num)
        target_tt = baseline_tt * factor
        low = target_tt * (1 - buffer_pct)
        high = target_tt * (1 + buffer_pct)
        return format_pace(low), format_pace(high)
    else:
        return "Invalid PR", "Invalid PR"

def format_time_difference(seconds: int) -> str:
    """Formats a time difference in seconds into a signed MM:SS string."""
    sign = "-" if seconds < 0 else "+"
    seconds = abs(seconds)
    minutes = seconds // 60
    seconds %= 60
    return f"{sign}{minutes:02d}:{seconds:02d}"

# ---------- Workout Library ----------
workout_library: Dict[str, Dict[str, Any]] = {
    "interval": {"name": "Norwegian 4x4", "duration": 40, "rpe": 9, "structure": "4 min hard, 2 min rest x 4"},
    "tempo": {"name": "Tempo Run", "duration": 40, "rpe": 7, "structure": "20 min warm up, 20 min tempo, 5 min cool down"},
    "long": {"name": "Long Run", "duration": 75, "rpe": 4, "structure": "Easy pace, conversational"},
}

# ---------- Generate One Week (3 Workouts) ----------
def generate_week(user_profile: Dict[str, Any], week_num: int = 1) -> List[Dict[str, Any]]:
    """Generates a single week of training (3 workouts)."""
    base_pace = user_profile["base_5k_pace"]
    pace_zones = rpe_to_pace_map(base_pace)
    seq = ["interval", "tempo", "long"]
    week_plan = []
    for i, key in enumerate(seq, start=1):
        w = workout_library[key]
        week_plan.append({
            "day": f"Day {i}",
            "workout": w["name"],
            "duration": w["duration"],
            "rpe": w["rpe"],
            "context_pace": pace_zones[key],
            "description": w.get("structure", "")
        })
    return week_plan

# ---------- Generate 4-Week Wave ----------
def generate_wave(user_profile: Dict[str, Any], start_week: int, base_minutes: float, progression_rate: float = 0.08, deload_factor: float = 0.7) -> List[Dict[str, Any]]:
    """Generates a 4-week training wave."""
    wave = []
    goal = user_profile["goal_distance"].lower()
    tt_dist = 2 if goal == "5k" else 3.1
    for offset in range(4):
        wk = start_week + offset
        is_deload = (offset == 3)
        minutes = round(base_minutes * (deload_factor if is_deload else (1 + progression_rate * offset)), 1)
        # generate 3 workouts
        sessions = generate_week({**user_profile, "weekly_duration_minutes": minutes}, week_num=wk)
        if is_deload:
            # replace first session with time trial
            tt = {"day": "Day 1", "workout": f"{tt_dist} mile TT", "duration": 20, "rpe": 9,
                  "context_pace": "All-out", "description": "Time trial – log result"}
            sessions[0] = tt
            entry = {"week_num": wk, "minutes": minutes, "sessions": sessions, "label": "Deload Week"}
        else:
            entry = {"week_num": wk, "minutes": minutes, "sessions": sessions}
        wave.append(entry)
    return wave

# ---------- Generate Full Plan ----------
def generate_plan(user_profile: Dict[str, Any], start_date: str, race_date: str, base_minutes: float) -> Optional[List[Dict[str, Any]]]:
    """Generates a full training plan from start date to race date."""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    race = datetime.strptime(race_date, "%Y-%m-%d")
    total_weeks = (race - start).days // 7
    if total_weeks <= 0:
        st.error("Race date must be at least one week after start date.")
        return None

    plan = []
    wk_cursor = 1
    peak = base_minutes
    while total_weeks - wk_cursor >= 2:
        wave = generate_wave(user_profile, wk_cursor, base_minutes)
        plan += wave
        base_minutes = wave[-2]["minutes"]
        peak = max(peak, base_minutes)
        wk_cursor += 4
    # Taper
    taper = round(peak * 0.7, 1)
    plan.append({"week_num": wk_cursor, "minutes": taper, "label": "Taper Week",
                 "sessions": generate_week({**user_profile, "weekly_duration_minutes": taper}, wk_cursor)})
    wk_cursor += 1
    # Race Week
    race_sessions = [
        {"day": "Day 1", "workout": "6x400m Strides", "duration": 20, "rpe": 7, "context_pace": "10K pace",
         "description": "Sharpen up"},
        {"day": "Day 3", "workout": f"{user_profile['goal_distance'].upper()} Race",
         "duration": 25 if user_profile['goal_distance'].lower() == '5k' else 60,
         "rpe": 9, "context_pace": "All-out", "description": "Race day!"}
    ]
    plan.append({"week_num": wk_cursor, "minutes": round(peak * 0.5, 1), "label": "Race Week", "sessions": race_sessions})
    return plan

def update_plan_with_new_pr(plan: List[Dict[str, Any]], new_pr: str, goal_distance: str) -> List[Dict[str, Any]]:
    """
    Updates the plan with new paces based on a new 5K PR.  This function iterates through the plan,
    and updates the context_pace for each session.

    Args:
        plan (list): The existing training plan.
        new_pr (str): The new 5K PR in MM:SS format.
        goal_distance(str): the goal distance

    Returns:
        list: The updated training plan.
    """
    try:
        mins, secs = map(int, new_pr.split(':'))
        new_base_pace = (mins * 60 + secs) / 3.1 / 60  # Calculate new base pace
    except ValueError:
        st.error("Invalid 5K PR format. Please use MM:SS")
        return plan # Return original plan if new_pr is invalid

    new_user_profile = {'goal_distance': goal_distance, 'weekly_duration_minutes': 240, 'base_5k_pace': new_base_pace}
    new_pace_zones = rpe_to_pace_map(new_base_pace)

    for week in plan:
        if 'sessions' in week:  # Ensure the week has sessions
            for session in week['sessions']:
                if session['workout'] != f"{'2' if goal_distance.lower() == '5k' else '3.1'} mile TT":
                    #update the context pace, but not for the time trial session itself.
                    session['context_pace'] = new_pace_zones.get(session['workout'].lower(), "N/A")
    return plan

# ---------- Streamlit Inputs ----------
def running_plan_app():
    col1, col2 = st.columns(2)
    with col1:
        goal = st.selectbox('Goal Distance', ['5K', '10K', 'Half', 'Marathon'])
        pr = st.text_input('Your 5K PR (MM:SS)', '25:00')
        try:
            init = predict_time(pr, 3.1, {'5K': 3.1, '10K': 6.2, 'Half': 13.1, 'Marathon': 26.2}[goal])
            st.success(f"Initial Predicted {goal} Time: {init}")
        except ValueError:
            st.error("Invalid 5K PR format. Please use MM:SS")

    with col2:
        race_date = st.date_input('Race Date', value=datetime.today().date() + timedelta(weeks=8))

    # ---------- Generate & Display ----------
    # When user clicks "Generate Plan", store the plan in session_state
    if st.button('Generate Plan'):
        # compute base pace
        try:
            mins, secs = map(int, pr.split(':'))
            base_pace = (mins * 60 + secs) / 3.1 / 60
            user = {
                'goal_distance': goal.lower(),
                'weekly_duration_minutes': 240,
                'base_5k_pace': base_pace
            }
            # generate and store plan
            st.session_state['plan'] = generate_plan(user, str(datetime.today().date()), str(race_date), 240)
            st.session_state['pr'] = pr
            st.session_state['tt_inputs'] = {} # Initialize a dict to store TT inputs.  Key is tt date, value is input
            st.session_state['tt_targets'] = {} # Store the calculated TT targets, so they don't change. Key is tt date, value is target
        except ValueError:
            st.error("Invalid 5K PR format. Please use MM:SS")

    # If a plan exists in session_state, always render it (and TT table)
    if 'plan' in st.session_state:
        plan = st.session_state['plan']
        orig_pr = st.session_state['pr']
        goal_distance = goal # make sure goal_distance is defined.

        if plan is not None:
            # Time Trial Schedule & Predictions
            st.subheader('📅 Time Trial Schedule & Targets')
            start = datetime.today().date()
            race_date = race_date
            total_weeks = (race_date - start).days // 7
            tt_dates = []
            w = 1
            while total_weeks - w >= 2:
                tt_dates.append(start + timedelta(weeks=w + 2))
                w += 4

            tt_dist = 2 if goal.upper() == '5K' else 3.1
            goal_mi = {'5K': 3.1, '10K': 6.2, 'Half': 13.1, 'Marathon': 26.2}[goal]

            if tt_dates:
                for i, d in enumerate(tt_dates):
                    # Calculate and store targets if they don't exist
                    if d not in st.session_state['tt_targets']:
                        low, high = compute_tt_target_range(orig_pr, i + 1, tt_dist=tt_dist)
                        st.session_state['tt_targets'][d] = (low, high)  # Store the targets
                    else:
                        low, high = st.session_state['tt_targets'][d] #retrieve

                    cols = st.columns(4)
                    cols[0].write(f"**{d}**\nTarget: {low}–{high}")
                    key = f'tt_{i}'
                    inp = cols[1].text_input('', key=key)
                    # keep last input in session_state
                    if key in st.session_state.get('tt_inputs', {}):
                        inp = st.session_state['tt_inputs'][key]
                    # compute delta PR only when input provided
                    out = ''
                    new_pr_display = ''
                    if inp and ':' in inp:
                        # store latest TT input
                        st.session_state['tt_inputs'] = st.session_state.get('tt_inputs', {})
                        st.session_state['tt_inputs'][key] = inp

                        try:
                            new5k_min = predict_distance_time(inp, tt_dist, 3.1)
                            if new5k_min is not None:
                                new5k_sec = int(round(new5k_min * 60))
                                orig_m, orig_s = map(int, orig_pr.split(':'))
                                orig_sec = orig_m * 60 + orig_s
                                diff = new5k_sec - orig_sec
                                out = format_time_difference(diff)
                                new_pr_display = format_pace(new5k_min)
                                # Update plan with new PR
                                st.session_state['plan'] = update_plan_with_new_pr(st.session_state['plan'], format_pace(new5k_min), goal_distance)
                                st.session_state['pr'] = format_pace(new5k_min)
                                plan = st.session_state['plan']
                            else:
                                out = "Invalid TT format"
                        except ValueError:
                            out = "Invalid TT format"
                    cols[2].write(f"**{out}**")
                    cols[3].write(f"New 5k PR: **{new_pr_display}**")

            # Training Plan Display
            st.subheader('🏃 Training Plan')
            for wk in plan:
                label = wk.get('label', f"Week {wk['week_num']}")
                if label == 'Deload Week':
                    st.markdown(f"<h3 style='color:green'>{label} – {wk['minutes']} min</h3>", unsafe_allow_html=True)
                else:
                    st.markdown(f"### {label} – {wk['minutes']} min")
                if 'sessions' in wk:
                    for s in wk['sessions']:
                        st.markdown(f"- **{s['day']}**: {s['workout']} – {s['duration']} min @ RPE {s['rpe']}")
                        st.caption(f"Pace: {s['context_pace']} | {s['description']}")
if __name__ == "__main__":
    running_plan_app()
