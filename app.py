import streamlit as st
import google.generativeai as genai
import os
import pandas as pd
import gspread
from datetime import datetime
import threading  # NEW: For background saving

# --- CONFIGURATION & SETUP ---

# 1. API Key Setup
try:
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    elif "GEMINI_API_KEY" in os.environ:
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    else:
        st.error("Missing GEMINI_API_KEY! Please check your secrets.toml.")
        st.stop()
except Exception as e:
    st.error(f"Error configuring Gemini API: {e}")
    st.stop()

# 2. Optimized Google Sheets Connection
@st.cache_resource
def get_google_sheet_client():
    try:
        if "gcp_service_account" not in st.secrets:
            return None
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        client = gspread.service_account_from_dict(creds_dict)
        return client
    except Exception:
        return None

def save_to_google_sheet_background(data_row):
    """Runs in a separate thread to avoid freezing the app."""
    try:
        client = get_google_sheet_client()
        if client:
            sheet_name = st.secrets.get("SHEET_NAME", "Math Practice History")
            sheet = client.open(sheet_name).sheet1
            sheet.append_row(data_row)
    except Exception as e:
        print(f"Background save failed: {e}")

def trigger_background_save(data_row):
    """Starts the save process without making the user wait."""
    thread = threading.Thread(target=save_to_google_sheet_background, args=(data_row,))
    thread.start()

# --- LOGIC FUNCTIONS ---

def get_current_difficulty(q_number):
    if q_number <= 7: return "Easy (Foundation)"
    elif q_number <= 15: return "Medium (Crossover)"
    else: return "Hard (Higher)"

def get_curriculum_context(topic):
    """Maps the high-level topic to specific GCSE sub-skills."""
    curriculum_map = {
        "Place Value & Rounding": "multiplying and dividing by powers of 10, rounding to significant figures and decimal places, estimation.",
        "Decimals": "ordering decimals, adding and subtracting decimals, multiplying and dividing decimals by integers and other decimals.",
        "Angles & Construction": "sum of angles (360 degrees), intersecting lines, drawing lines and quadrilaterals, vertically opposite angles.",
        "Collecting Data": "conducting investigations, taking a sample, bias, questionnaires, tally charts.",
        "Fractions": "ordering fractions, adding mixed numbers, multiplying and dividing fractions, reciprocals.",
        "Shapes & Areas": "converting units for area (m2 to cm2), hectares, area of triangles/parallelograms, volume and surface area of cubes and cuboids.",
        "Percentages": "converting between fractions/decimals/percentages, finding percentage of amounts, percentage change."
    }
    return curriculum_map.get(topic, "GCSE Maths curriculum")

def get_new_question():
    model = genai.GenerativeModel("models/gemini-2.5-flash")
    
    if st.session_state.question_count > 25:
        st.session_state.question_text = "🎉 You have completed all 25 questions! Great job."
        st.session_state.is_finished = True
        return

    topic = st.session_state.opt_topic
    grade = st.session_state.opt_grade
    difficulty = get_current_difficulty(st.session_state.question_count)
    sub_topic_context = get_curriculum_context(topic)
    
    prompt = f"""
    Act as a GCSE Maths teacher creating a worksheet question similar to CorbettMaths style.
    
    Target Student: {grade}
    Topic: {topic}
    Specific Skills to Test: {sub_topic_context}
    Difficulty: {difficulty} (Question {st.session_state.question_count} of 25)
    
    Requirements:
    1. The question must be clear and direct.
    2. If it is a word problem, use British English (e.g., £ for currency, metres for distance).
    3. Ensure the numbers are clean enough to be solved without a calculator if appropriate for the topic.
    4. The question must be on tougher side.
    5. The sample questions can be taken from www.corbettmaths.com
    
    Output exactly in this format:
    [The Question Text]
    |||
    [The Final Numerical Answer or Short Phrase]
    """
    
    try:
        response = model.generate_content(prompt)
        text = response.text
        
        if "|||" in text:
            q, a = text.split("|||")
            st.session_state.question_text = q.strip()
            st.session_state.answer_text = a.strip()
        else:
            st.session_state.question_text = text
            st.session_state.answer_text = "Error parsing answer."
            
        st.session_state.reveal_answer = False
        st.session_state.feedback = "" 
        st.session_state.user_input = "" 
            
    except Exception as e:
        st.error(f"Error generating question: {e}")

def check_answer():
    user_ans = st.session_state.user_input
    correct_ans = st.session_state.answer_text
    question = st.session_state.question_text
    
    if not user_ans:
        st.session_state.feedback = "Please enter an answer first."
        return

    # Quick local check for exact matches to speed up simple answers
    if user_ans.strip() == correct_ans.strip():
        is_correct = True
    else:
        # Fallback to AI Judge for varied formats (e.g. 1/2 vs 0.5)
        try:
            judge_model = genai.GenerativeModel("models/gemini-2.5-flash")
            judge_prompt = f"""
            Question: {question}
            Correct Answer: {correct_ans}
            Student Answer: {user_ans}
            
            Compare the Student Answer to the Correct Answer.
            Ignore minor formatting differences (e.g. £10 vs 10 pounds, 0.5 vs 1/2).
            Reply with ONLY one word: "CORRECT" or "INCORRECT".
            """
            response = judge_model.generate_content(judge_prompt)
            is_correct = "CORRECT" in response.text.strip().upper()
        except:
            is_correct = False

    if is_correct:
        st.session_state.feedback = "✅ Correct!"
        st.session_state.score_correct += 1
    else:
        st.session_state.feedback = f"❌ Incorrect. The answer was: {correct_ans}"
    
    # Save Logic
    current_q_signature = f"{st.session_state.question_count}-{question[:10]}"
    
    if st.session_state.last_logged != current_q_signature:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = "Correct" if is_correct else "Incorrect"
        difficulty = get_current_difficulty(st.session_state.question_count)
        
        st.session_state.history_list.append({
            "Q#": st.session_state.question_count,
            "Topic": st.session_state.opt_topic,
            "Difficulty": difficulty,
            "Result": status
        })
        
        row_data = [
            timestamp,
            st.session_state.user_name_input,
            st.session_state.opt_grade,
            st.session_state.opt_topic,
            difficulty,
            question,
            user_ans,
            status
        ]
        
        # KEY SPEED FIX: Fire and forget (Background Thread)
        trigger_background_save(row_data)
        
        st.session_state.last_logged = current_q_signature
        st.session_state.reveal_answer = True 

def next_question_handler():
    st.session_state.question_count += 1
    get_new_question()

# --- INITIALIZATION ---
if 'init' not in st.session_state:
    st.session_state.init = True
    st.session_state.question_text = ""
    st.session_state.user_input = ""
    st.session_state.feedback = ""
    st.session_state.is_finished = False
    st.session_state.score_correct = 0
    st.session_state.question_count = 1 
    st.session_state.history_list = []
    st.session_state.last_logged = ""
    
    if "GEMINI_API_KEY" in st.secrets or "GEMINI_API_KEY" in os.environ:
        st.session_state.opt_grade = "Year 7 (KS3)" 
        st.session_state.opt_topic = "Place Value & Rounding" 
        get_new_question()

# --- SIDEBAR ---
with st.sidebar:
    st.header("User Profile")
    st.text_input("Enter your name:", value="Student", key="user_name_input")
    
    progress = min(st.session_state.question_count / 25, 1.0)
    st.progress(progress)
    st.write(f"Question: {min(st.session_state.question_count, 25)} / 25")
    st.metric("Score", f"{st.session_state.score_correct}")
    
    st.divider()
    st.header("Settings")
    
    # Updated Grade Levels to UK System
    st.selectbox("Select Year Group", ["Year 7 (KS3)", "Year 8 (KS3)", "Year 9 (KS3)", "Year 10 (GCSE)", "Year 11 (GCSE)"], key="opt_grade", on_change=get_new_question)
    
    # Updated Topics based on your Feedback
    topics_list = [
        "Place Value & Rounding",
        "Decimals",
        "Angles & Construction",
        "Collecting Data",
        "Fractions",
        "Shapes & Areas",
        "Percentages"
    ]
    st.selectbox("Select Topic", topics_list, key="opt_topic", on_change=get_new_question)
    
    if st.button("Restart Session"):
        st.session_state.score_correct = 0
        st.session_state.question_count = 1
        st.session_state.history_list = []
        st.session_state.is_finished = False
        get_new_question()
        st.rerun()

# --- MAIN UI ---
st.title(f"🎓 {st.session_state.user_name_input}'s GCSE Maths Prep")

if not st.session_state.is_finished:
    curr_diff = get_current_difficulty(st.session_state.question_count)
    st.caption(f"Topic: {st.session_state.opt_topic} | Year: {st.session_state.opt_grade} | Level: **{curr_diff}**")

    st.markdown("### Question")
    st.info(st.session_state.question_text)

    st.markdown("### Your Answer")
    st.text_input("Type your answer here:", key="user_input")

    col1, col2 = st.columns([1, 1])
    
    with col1: 
        st.button("Submit Answer", on_click=check_answer)
    with col2: 
        st.button("Next Question", on_click=next_question_handler)

    if st.session_state.feedback:
        if "Correct!" in st.session_state.feedback:
            st.success(st.session_state.feedback)
        else:
            st.error(st.session_state.feedback)

    if st.session_state.reveal_answer:
        st.markdown("---")
        st.markdown("### Correct Answer")
        st.write(st.session_state.answer_text)

else:
    st.success("🎉 You have finished the practice session!")
    st.balloons()
    st.write(f"Final Score: {st.session_state.score_correct} / 25")

if st.session_state.history_list:
    st.markdown("---")
    st.markdown("### 📜 Session History")
    df = pd.DataFrame(st.session_state.history_list)
    st.dataframe(df, use_container_width=True)
