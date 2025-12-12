import streamlit as st
import google.generativeai as genai
import os
import pandas as pd
import gspread
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

# 2. Optimized Google Sheets Connection (Robust Auth)
@st.cache_resource
def get_google_sheet_client():
    """Authenticates using a robust key cleaning method."""
    try:
        # Fetch the secrets dictionary
        # We use dict() to ensure we have a mutable copy
        if "gcp_service_account" not in st.secrets:
            st.error("Secrets Error: Section [gcp_service_account] not found.")
            return None
            
        creds_dict = dict(st.secrets["gcp_service_account"])
        
        # --- KEY REPAIR STATION ---
        private_key = creds_dict.get("private_key", "")
        
        # 1. Fix escaped newlines (common in TOML/JSON copies)
        if "\\n" in private_key:
            private_key = private_key.replace("\\n", "\n")
            
        # 2. Check for missing Headers (The cause of "No key detected")
        if "-----BEGIN PRIVATE KEY-----" not in private_key:
            # Try to force add them if missing
            private_key = "-----BEGIN PRIVATE KEY-----\n" + private_key + "\n-----END PRIVATE KEY-----"
            
        # 3. Apply the fix
        creds_dict["private_key"] = private_key
        # ---------------------------
        
        # Use the modern native auth method
        client = gspread.service_account_from_dict(creds_dict)
        return client
        
    except Exception as e:
        st.error(f"Authentication Error: {e}")
        st.info("Tip: Check that your 'private_key' in secrets starts with '-----BEGIN PRIVATE KEY-----' and ends with '-----END PRIVATE KEY-----'")
        return None

def save_to_google_sheet(data_row):
    """Appends a row to the sheet."""
    try:
        client = get_google_sheet_client()
        if not client:
            return False
            
        sheet_name = st.secrets.get("SHEET_NAME", "Math Practice History")
        sheet = client.open(sheet_name).sheet1
        sheet.append_row(data_row)
        return True
    except Exception as e:
        st.warning(f"⚠️ Could not save to Google Sheet. Check that the sheet name '{st.secrets.get('SHEET_NAME')}' matches exactly and is shared with the service account email.")
        return False

# --- LOGIC FUNCTIONS ---

def get_current_difficulty(q_number):
    """Determines difficulty based on question number (1-25)."""
    if q_number <= 7: return "Easy"
    elif q_number <= 15: return "Medium"
    else: return "Hard"

def get_new_question():
    """Fetches a new question based on the specific progression logic."""
    model = genai.GenerativeModel("models/gemini-2.5-flash")
    
    if st.session_state.question_count > 25:
        st.session_state.question_text = "🎉 You have completed all 25 questions! Great job."
        st.session_state.is_finished = True
        return

    topic = st.session_state.opt_topic
    grade = st.session_state.opt_grade
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
            
        st.session_state.reveal_answer = False
        st.session_state.feedback = "" 
        st.session_state.user_input = "" 
            
    except Exception as e:
        st.error(f"Error generating question: {e}")

def check_answer():
    """Grades, Updates Score, Saves to Sheet, and Auto-Advances."""
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
    If they are wrong, it is WRONG.
    
    Reply with ONLY one word: "CORRECT" or "WRONG".
    """
    
    try:
        response = judge_model.generate_content(judge_prompt)
        result_text = response.text.strip().upper()
        
        is_correct = "CORRECT" in result_text
        
        if is_correct:
            st.session_state.feedback = "✅ Correct!"
            st.session_state.score_correct += 1
        else:
            st.session_state.feedback = f"❌ Wrong. The answer was: {correct_ans}"
        
        # Save Logic
        current_q_signature = f"{st.session_state.question_count}-{question[:10]}"
        
        if st.session_state.last_logged != current_q_signature:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            status = "Correct" if is_correct else "Wrong"
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
            
            save_to_google_sheet(row_data)
            
            st.session_state.last_logged = current_q_signature
            st.session_state.reveal_answer = True 
            
    except Exception as e:
        st.error(f"Error grading: {e}")

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
        st.session_state.opt_grade = "Grade 5" 
        st.session_state.opt_topic = "Arithmetic" 
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

if not st.session_state.is_finished:
    curr_diff = get_current_difficulty(st.session_state.question_count)
    st.caption(f"Topic: {st.session_state.opt_topic} | Grade: {st.session_state.opt_grade} | Difficulty: **{curr_diff}**")

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
        st.markdown("### Explanation")
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
