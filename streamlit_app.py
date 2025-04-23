import streamlit as st
from datetime import datetime, timedelta
import pandas as pd

# ---------- Page Configuration ----------
st.set_page_config(page_title="OutRunna", page_icon="🏃")

# ---------- UI Header ----------
st.title("OutRunna MVP")
st.markdown("""
**Two hard workouts per week (Intervals & Tempo) + one Long Run**  
As recommended by Coach Chris Bennett: focus on quality hard sessions and accumulate easy running volume on your own.
""")

# ---------- Helper Functions ----------
def format_pace(min_per_mile):
    minutes = int(min_per_mile)
    seconds = int(round((min_per_mile - minutes) * 60))
    return f"{minutes}:{seconds:02d}"

def rpe_to_pace_map(base_pace):
    return {
        "interval": f"{format_pace(base_pace - 0.3)}–{format_pace(base_pace - 0.15)} min/mile (Intervals @ RPE 9)",
        "tempo":    f"{format_pace(base_pace + 0.25)}–{format_pace(base_pace + 0.5)} min/mile (Tempo @ RPE 7)",
        "long":     f"{format_pace(base_pace + 0.75)}–{format_pace(base_pace + 1.25)} min/mile (Long @ RPE 4)"
    }

def predict_distance_time(time_str, d1, d2, exponent=1.06):
    m, s = map(int, time_str.split(':'))
    t1 = m + s/60
    return t1 * (d2 / d1)**exponent

def predict_time(time_str, trial_dist, goal_dist):
    minutes = predict_distance_time(time_str, trial_dist, goal_dist)
    return format_pace(minutes)

def compute_tt_target_range(pr_5k, wave_num,
                            base_dist=3.1, tt_dist=2,
                            improvement_rate=0.015, buffer_pct=0.02):
    baseline = predict_distance_time(pr_5k, base_dist, tt_dist)
    factor = max(0, 1 - improvement_rate * wave_num)
    target = baseline * factor
    low = target * (1 - buffer_pct)
    high = target * (1 + buffer_pct)
    return format_pace(low), format_pace(high)

# ---------- Workout Library ----------
workout_library = {
    "interval":   {"name":"Norwegian 4x4","duration":40,"rpe":9},
    "tempo":      {"name":"Tempo Run","duration":40,"rpe":7},
    "long":       {"name":"Long Run","duration":75,"rpe":4}
}

# ---------- Generate One Week (3 Workouts) ----------
def generate_week(user_profile, week_num=1):
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
def generate_wave(user_profile, start_week, base_minutes,
                  progression_rate=0.08, deload_factor=0.7):
    wave = []
    goal = user_profile["goal_distance"].lower()
    tt_dist = 2 if goal=="5k" else 3.1
    for offset in range(4):
        wk = start_week + offset
        is_deload = (offset==3)
        minutes = round(base_minutes * (deload_factor if is_deload else (1+progression_rate*offset)),1)
        # generate 3 workouts
        sessions = generate_week({**user_profile, "weekly_duration_minutes": minutes}, week_num=wk)
        if is_deload:
            # replace first session with time trial
            tt = {"day":"Day 1","workout":f"{tt_dist} mile TT","duration":20,"rpe":9,
                  "context_pace":"All-out","description":"Time trial – log result"}
            sessions[0] = tt
            entry = {"week_num":wk, "minutes":minutes, "sessions":sessions, "label":"Deload Week"}
        else:
            entry = {"week_num":wk, "minutes":minutes, "sessions":sessions}
        wave.append(entry)
    return wave

# ---------- Generate Full Plan ----------
def generate_plan(user_profile, start_date, race_date, base_minutes):
    start = datetime.strptime(start_date, "%Y-%m-%d")
    race = datetime.strptime(race_date, "%Y-%m-%d")
    total_weeks = (race - start).days // 7
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
    taper = round(peak*0.7,1)
    plan.append({"week_num":wk_cursor,"minutes":taper,"label":"Taper Week", "sessions":generate_week({**user_profile,"weekly_duration_minutes":taper}, wk_cursor)})
    wk_cursor +=1
    # Race Week
    race_sessions = [
        {"day":"Day 1","workout":"6x400m Strides","duration":20,"rpe":7,"context_pace":"10K pace","description":"Sharpen up"},
        {"day":"Day 3","workout":f"{user_profile['goal_distance'].upper()} Race","duration":25 if user_profile['goal_distance'].lower()=='5k' else 60,
         "rpe":9,"context_pace":"All-out","description":"Race day!"}
    ]
    plan.append({"week_num":wk_cursor,"minutes":round(peak*0.5,1),"label":"Race Week","sessions":race_sessions})
    return plan

# ---------- Streamlit Inputs ----------
col1, col2 = st.columns(2)
with col1:
    goal = st.selectbox('Goal Distance',['5K','10K','Half','Marathon'])
    pr = st.text_input('Your 5K PR (MM:SS)','25:00')
    try:
        init = predict_time(pr,3.1,{'5K':3.1,'10K':6.2,'Half':13.1,'Marathon':26.2}[goal])
        st.success(f"Initial Predicted {goal} Time: {init}")
    except:
        pass
with col2:
    race_date = st.date_input('Race Date',value=datetime.today().date()+timedelta(weeks=8))

# ---------- Generate & Display ----------
if st.button('Generate Plan'):
    mins,secs = map(int,pr.split(':'))
    base_pace = (mins*60+secs)/3.1/60
    user = {'goal_distance':goal,'weekly_duration_minutes':240,'base_5k_pace':base_pace}
    plan = generate_plan(user,str(datetime.today().date()),str(race_date),240)

    # Time Trials Table
    st.subheader('Time Trial Schedule & Targets')
    start = datetime.today().date()
    weeks=(race_date-start).days//7
    dates=[];w=1
    while weeks-w>=2:
        dates.append(start+timedelta(weeks=w+2));w+=4
    tt_dist = 2 if goal=='5K' else 3.1
    gdist = {'5K':3.1,'10K':6.2,'Half':13.1,'Marathon':26.2}[goal]
    for i,d in enumerate(dates):
        low,high=compute_tt_target_range(pr,i+1)
        c=st.columns(3)
        c[0].write(f"**{d}**\nTarget: {low}–{high}")
        inp=c[1].text_input('',key=f'tt{i}')
        out=''
        if inp and ':' in inp:
            out=predict_time(inp,tt_dist,gdist)
        c[2].write(f"**{out}**")

    # Training Plan
    st.subheader('Training Plan')
    for wk in plan:
        lbl=wk.get('label',f"Week {wk['week_num']}")
        if lbl=='Deload Week':
            st.markdown(f"<h3 style='color:green'>{lbl} – {wk['minutes']} min</h3>",unsafe_allow_html=True)
        else:
            st.markdown(f"### {lbl} – {wk['minutes']} min")
        for s in wk['sessions']:
            st.markdown(f"- **{s['day']}**: {s['workout']} – {s['duration']} min @ RPE {s['rpe']}")
            st.caption(f"Pace: {s['context_pace']} | {s['description']}")
