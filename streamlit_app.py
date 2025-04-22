import streamlit as st
from datetime import datetime, timedelta
import pandas as pd

# ---------- Page Configuration ----------
st.set_page_config(page_title="OutRunna", page_icon="🏃")

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
    Return a mapping from RPE to formatted pace ranges using MM:SS.
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


def predict_distance_time(time_str, d1, d2, exponent=1.06):
    """
    Use Riegel formula to predict time at distance d2 from time at distance d1.
    Returns time in minutes (float).
    """
    m, s = map(int, time_str.split(':'))
    t1 = m + s / 60
    return t1 * (d2 / d1) ** exponent


def predict_time(time_str, trial_dist, goal_dist):
    """
    Convert predicted time in minutes to MM:SS for display.
    """
    minutes = predict_distance_time(time_str, trial_dist, goal_dist)
    return format_pace(minutes)


def compute_tt_target_range(pr_5k, wave_num,
                            base_dist=3.1, tt_dist=2,
                            improvement_rate=0.015, buffer_pct=0.02):
    """
    Calculate target time trial range (low, high) for a given wave.
    Returns two strings (MM:SS) for lower and upper bounds.
    """
    baseline = predict_distance_time(pr_5k, base_dist, tt_dist)
    factor = max(0, 1 - improvement_rate * wave_num)
    target = baseline * factor
    low = target * (1 - buffer_pct)
    high = target * (1 + buffer_pct)
    return format_pace(low), format_pace(high)

# Improvement per wave for final prediction
enhancement_rate = 0.015

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
    base_pace = user_profile["base_5k_pace"]
    pace_zones = rpe_to_pace_map(base_pace)

    # Map names to templates
    templates = {w['name']: w.copy() for w in workout_library}

    # Determine structure
    if days == 3:
        first = "Tempo Run" if week_num % 2 == 1 else "Norwegian 4x4"
        sequence = [first, "Easy Run", "Long Run"]
    else:
        sequence = ["Long Run", "Easy Run", "Norwegian 4x4", "Tempo Run"] + ["Easy Run"] * (days - 4)

    week_plan = []
    hard_counts = {"Tempo Run": 0, "Norwegian 4x4": 0}
    for idx, name in enumerate(sequence):
        if name in hard_counts:
            if hard_counts[name] >= 1:
                name = "Easy Run"
            else:
                hard_counts[name] += 1
        w = templates[name]
        # Pace info
        pz = pace_zones[w['rpe']]
        detail = w.get('structure', f"{w['duration']} min @ RPE {w['rpe']}")
        week_plan.append({
            'day': f"Day {idx+1}",
            'workout': w['name'],
            'duration': w['duration'],
            'rpe': w['rpe'],
            'context_pace': pz,
            'description': detail
        })
    return week_plan

# ---------- Generate 4-Week Wave ----------
def generate_wave(user_profile, start_week, base_minutes, progression_rate=0.08, deload_factor=0.7):
    wave = []
    goal = user_profile["goal_distance"].lower()
    tt_dist = 2 if goal == '5k' else 3.1

    for offset in range(4):
        week_num = start_week + offset
        is_deload = (offset == 3)
        volume = round(base_minutes * (deload_factor if is_deload else (1 + progression_rate * offset)), 1)
        sessions = generate_rpe_week({**user_profile, 'weekly_duration_minutes': volume}, workout_library, week_num)
        if is_deload:
            # Insert time trial
            tt = {
                'day': 'Day 1',
                'workout': f"{tt_dist} {'miles' if tt_dist==2 else 'K'} Time Trial",
                'duration': 20 if tt_dist == 2 else 25,
                'rpe': 9,
                'context_pace': 'All-out (goal pace)',
                'description': 'Time trial – log result'
            }
            # Replace first hard session
            for i, sess in enumerate(sessions):
                if sess['rpe'] in [7, 9]:
                    sessions[i] = tt
                    break
            entry = {'week_num': week_num, 'minutes': volume, 'sessions': sessions, 'label': 'Deload Week'}
        else:
            entry = {'week_num': week_num, 'minutes': volume, 'sessions': sessions}
        wave.append(entry)
    return wave

# ---------- Generate Full Plan Until Race ----------
def generate_plan(user_profile, start_date, race_date, base_minutes):
    start = datetime.strptime(start_date, "%Y-%m-%d")
    race = datetime.strptime(race_date, "%Y-%m-%d")
    total_weeks = (race - start).days // 7

    plan = []
    week_cursor = 1
    peak_vol = base_minutes
    while total_weeks - week_cursor >= 2:
        wv = generate_wave(user_profile, week_cursor, base_minutes)
        plan.extend(wv)
        base_minutes = wv[-2]['minutes']
        peak_vol = max(peak_vol, base_minutes)
        week_cursor += 4

    # Taper Week
    taper_vol = round(peak_vol * 0.7, 1)
    taper_sessions = generate_rpe_week({**user_profile, 'weekly_duration_minutes': taper_vol}, workout_library, week_cursor)
    plan.append({'week_num': week_cursor, 'minutes': taper_vol, 'label': 'Taper Week', 'sessions': taper_sessions})
    week_cursor += 1

    # Race Week
    strides = {'day': 'Day 1', 'workout': 'Taper Strides – 6x400m', 'duration': 20, 'rpe': 9, 'context_pace': '10K pace', 'description': 'Sharpen up'}
    race_day = {'day': 'Day 3', 'workout': f"{user_profile['goal_distance'].upper()} Race", 'duration': 25 if user_profile['goal_distance'].lower()=='5k' else 60, 'rpe': 9, 'context_pace': 'All-out', 'description': 'Race day!'}
    plan.append({'week_num': week_cursor, 'minutes': round(peak_vol * 0.5, 1), 'label': 'Race Week', 'sessions': [strides, race_day]})

    return plan

# ---------- Streamlit UI ----------
st.title("OutRunna MVP")
col1, col2 = st.columns(2)
with col1:
    goal = st.selectbox('Goal Distance', ['5K', '10K', 'Half', 'Marathon'])
    pr = st.text_input('Your 5K PR (MM:SS)', '25:00')
    try:
        init_pred = predict_time(pr, 3.1, {'5K':3.1,'10K':6.2,'Half':13.1,'Marathon':26.2}[goal])
        st.success(f"Initial Predicted {goal} Time: {init_pred}")
        # Final prediction based on plan length
        race_dt = st.session_state.get('race_date') if 'race_date' in st.session_state else datetime.today().date() + timedelta(weeks=8)
        weeks = (race_dt - datetime.today().date()).days // 7
        waves = weeks // 4
        base = predict_distance_time(pr, 3.1, {'5K':3.1,'10K':6.2,'Half':13.1,'Marathon':26.2}[goal])
        final = format_pace(base * max(0, 1 - enhancement_rate * waves))
        st.success(f"Final Predicted {goal} Time: {final}")
    except:
        pass
with col2:
    days = st.slider('Days/Week', 3, 6, 4)
    race_date = st.date_input('Race Date', value=datetime.today().date() + timedelta(weeks=8))

if st.button('Generate Plan'):
    mins, secs = map(int, pr.split(':'))
    base_pace = (mins * 60 + secs) / 3.1 / 60
    user = {'goal_distance': goal.lower(), 'days_per_week': days, 'weekly_duration_minutes': 240, 'base_5k_pace': base_pace}
    plan = generate_plan(user, str(datetime.today().date()), str(race_date), 240)

    # Time Trial Schedule & Predictions
    st.subheader('📅 Time Trial Schedule & Race Predictions')
    start = datetime.today().date()
    total_weeks = (race_date - start).days // 7
    tt_dates = []
    w = 1
    while total_weeks - w >= 2:
        tt_dates.append(start + timedelta(weeks=w+2))
        w += 4

    tt_dist = 2 if goal=='5k' else 3.1
    goal_mi = {'5k':3.1,'10k':6.2,'half':13.1,'marathon':26.2}[goal.lower()]

    for i, d in enumerate(tt_dates):
        low, high = compute_tt_target_range(pr, i+1)
        cols = st.columns(3)
        cols[0].write(f"**{d}**\nTarget: {low}–{high}")
        inp = cols[1].text_input('', key=f'tt_{i}')
        out = ''
        if inp and ':' in inp:
            out = predict_time(inp, tt_dist, goal_mi)
        cols[2].write(f"**{out}**")

    # Display Training Plan
    st.subheader('🏃 Training Plan')
    for wk in plan:
        label = wk.get('label', f"Week {wk['week_num']}")
        if label == 'Deload Week':
            st.markdown(f"<h3 style='color:green'>{label} – {wk['minutes']} min</h3>", unsafe_allow_html=True)
        else:
            st.markdown(f"### {label} – {wk['minutes']} min")
        for sess in wk['sessions']:
            st.markdown(f"- **{sess['day']}**: {sess['workout']} – {sess['duration']} min @ RPE {sess['rpe']}")
            st.caption(f"Pace: {sess['context_pace']} | {sess['description']}")
