import streamlit as st
import google.generativeai as genai
import os
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

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

# 2. Optimized Google Sheets Connection (Cached)
# This @st.cache_resource decorator makes the connection 100x faster
@st.cache_resource
def get_google_sheet_client():
    """Authenticates and returns the gspread client. Cached for speed."""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # Convert Streamlit secrets to a normal dict so we can modify it
    creds_dict = dict(st.secrets["gcp_service_account"])
    
    # CRITICAL FIX: Handle newline characters in private_key
    # This fixes the "No key could be detected" error
    if "private_key" in creds_dict:
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

def save_to_google_sheet(data_row):
    """Appends a row to the sheet using the cached client."""
    try:
        client = get_google_sheet_client()
        # Fallback to a default name if not in secrets
        sheet_name = st.secrets.get("SHEET_NAME", "Math Practice History")
        sheet = client.open(sheet_name).sheet1
        sheet.append_row(data_row)
        return True
    except Exception as e:
        st.warning(f"⚠️ Could not save to Google Sheet: {e}")
        return False

# --- LOGIC FUNCTIONS ---

def get_current_difficulty(q_number):
    """Determines difficulty based on question number (1-25)."""
    # Q1-7: Easy
    if q_number <= 7:
        return "Easy"
    # Q8-15: Medium (Next 8)
    elif q_number <= 15:
        return "Medium"
    # Q16-25: Hard (Final 10)
    else:
        return "Hard"

def get_new_question():
    """Fetches a new question based on the specific progression logic."""
    model = genai.GenerativeModel("models/gemini-2.5-flash")
    
    # Check if session is over
    if st.session_state.question_count > 25:
        st.session_state.question_text = "🎉 You have completed all 25 questions! Great job."
        st.session_state.is_finished = True
        return

    topic = st.session_state.opt_topic
    grade = st.session_state.opt_grade
    
    # Automate Difficulty
    difficulty = get_current_difficulty(st.session_state.question_count)
    
    prompt = f"""
    Generate a unique math practice question specifically for a student in {grade}.
    The topic is {topic}.
    The difficulty level is {difficulty} (Question {st.session_state.question_count} of 25).
    
    Output exactly in this format:
    [The Question Text]
    |||
    [The Step-by-step Answer]
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
            
        # Reset UI states
        st.session_state.reveal_answer = False
        st.session_state.feedback = "" 
        st.session_state.user_input = "" 
            
    except Exception as e:
        st.error(f"Error generating question: {e}")

def check_answer():
    """Grades the answer, Updates Score, Saves to Sheet, and Auto-Advances."""
    user_ans = st.session_state.user_input
    correct_ans = st.session_state.answer_text
    question = st.session_state.question_text
    
    if not user_ans:
        st.session_state.feedback = "Please enter an answer first."
        return

    judge_model = genai.GenerativeModel("models/gemini-2.5-flash")
    
    judge_prompt = f"""
    Question: {question}
    Correct Answer: {correct_ans}
    Student Answer: {user_ans}
    
    Compare the Student Answer to the Correct Answer.
    If they are mathematically equivalent (e.g., 0.5 and 1/2), it is CORRECT.
    If they are wrong, it is INCORRECT.
    
    Reply with ONLY one word: "CORRECT" or "INCORRECT".
    """
    
    try:
        response = judge_model.generate_content(judge_prompt)
        result_text = response.text.strip().upper()
        
        # LOGIC FIX: Explicitly check for INCORRECT first to avoid partial matching errors
        if "INCORRECT" in result_text:
            is_correct = False
        elif "CORRECT" in result_text:
            is_correct = True
        else:
            is_correct = False 
        
        if is_correct:
            st.session_state.feedback = "✅ Correct!"
            st.session_state.score_correct += 1
        else:
            st.session_state.feedback = f"❌ Incorrect. The answer was: {correct_ans}"
        
        # Save Logic (Prevents double saving)
        current_q_signature = f"{st.session_state.question_count}-{question[:10]}"
        
        if st.session_state.last_logged != current_q_signature:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            status = "Correct" if is_correct else "Incorrect"
            difficulty = get_current_difficulty(st.session_state.question_count)
            
            # Save Local
            st.session_state.history_list.append({
                "Q#": st.session_state.question_count,
                "Topic": st.session_state.opt_topic,
                "Difficulty": difficulty,
                "Result": status
            })
            
            # Save Cloud
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
            
            # Save to sheet in background
            save_to_google_sheet(row_data)
            
            st.session_state.last_logged = current_q_signature
            st.session_state.reveal_answer = True 
            
    except Exception as e:
        st.error(f"Error grading: {e}")

def next_question_handler():
    """Increments counter and loads next Q."""
    st.session_state.question_count += 1
    get_new_question()

# --- INITIALIZATION ---
if 'init' not in st.session_state:
    st.session_state.init = True
    st.session_state.question_text = ""
    st.session_state.user_input = ""
    st.session_state.feedback = ""
    st.session_state.is_finished = False
    
    # Score & Progression
    st.session_state.score_correct = 0
    st.session_state.question_count = 1 
    st.session_state.history_list = []
    st.session_state.last_logged = ""
    
    # Defaults
    if "GEMINI_API_KEY" in st.secrets or "GEMINI_API_KEY" in os.environ:
        st.session_state.opt_grade = "Grade 5" 
        st.session_state.opt_topic = "Arithmetic" 
        get_new_question()

# --- SIDEBAR ---
with st.sidebar:
    st.header("User Profile")
    st.text_input("Enter your name:", value="Student", key="user_name_input")
    
    # Progress Bar Logic
    progress = min(st.session_state.question_count / 25, 1.0)
    st.progress(progress)
    st.write(f"Question: {min(st.session_state.question_count, 25)} / 25")
    st.metric("Score", f"{st.session_state.score_correct}")
    
    st.divider()
    st.header("Settings")
    st.selectbox("Select Grade Level", [f"Grade {i}" for i in range(1, 13)] + ["College/University"], key="opt_grade", on_change=get_new_question)
    
    topics_list = ["Arithmetic", "Algebra", "Geometry", "Metric Conversion", "Operations on Integers", "Decimal Operations", "Fraction"]
    st.selectbox("Select Topic", topics_list, key="opt_topic", on_change=get_new_question)
    
    if st.button("Restart Session"):
        st.session_state.score_correct = 0
        st.session_state.question_count = 1
        st.session_state.history_list = []
        st.session_state.is_finished = False
        get_new_question()
        st.rerun()

# --- MAIN UI ---
st.title(f"🎓 {st.session_state.user_name_input}'s Math Test")

# Difficulty Label
if not st.session_state.is_finished:
    curr_diff = get_current_difficulty(st.session_state.question_count)
    st.caption(f"Topic: {st.session_state.opt_topic} | Grade: {st.session_state.opt_grade} | Difficulty: **{curr_diff}**")

    st.markdown("### Question")
    st.info(st.session_state.question_text)

    st.markdown("### Your Answer")
    st.text_input("Type your answer here:", key="user_input")

    col1, col2 = st.columns([1, 1])
    
    # Hint button removed as requested
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
        st.markdown("### Explanation")
        st.write(st.session_state.answer_text)

else:
    st.success("🎉 You have finished the practice session!")
    st.balloons()
    st.write
