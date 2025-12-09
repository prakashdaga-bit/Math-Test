import streamlit as st
import google.generativeai as genai
import os
import pandas as pd # Import pandas for the history table

# 1. Setup
try:
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    elif "GEMINI_API_KEY" in os.environ:
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    else:
        st.error("Missing API Key!")
        st.stop()
except Exception as e:
    st.error(f"Error configuring API: {e}")
    st.stop()

# 2. Logic Functions

def get_new_question():
    """Fetches a new question based on Grade, Topic, and Difficulty."""
    model = genai.GenerativeModel("models/gemini-2.5-flash")
    
    topic = st.session_state.opt_topic
    difficulty = st.session_state.opt_difficulty
    grade = st.session_state.opt_grade
    
    prompt = f"""
    Generate a unique math practice question specifically for a student in {grade}.
    The topic is {topic}.
    The difficulty level for this specific grade should be {difficulty}.
    
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
        st.session_state.hint_text = "" 
            
    except Exception as e:
        st.error(f"Error: {e}")

def get_hint():
    """Asks AI for a hint."""
    if st.session_state.hint_text:
        return

    model = genai.GenerativeModel("models/gemini-2.5-flash")
    q = st.session_state.question_text
    a = st.session_state.answer_text
    
    prompt = f"""
    The Student is stuck on this question: "{q}"
    The solution is: "{a}"
    Provide a short, helpful hint. Do NOT reveal the answer.
    """
    
    try:
        response = model.generate_content(prompt)
        st.session_state.hint_text = response.text
    except Exception as e:
        st.error(f"Error getting hint: {e}")

def check_answer():
    """Uses Gemini to grade the answer and UPDATES SCORE."""
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
    Is the student's answer correct? Reply ONLY "CORRECT" or "INCORRECT".
    """
    
    try:
        response = judge_model.generate_content(judge_prompt)
        result = response.text.strip().upper()
        
        is_correct = "CORRECT" in result
        
        if is_correct:
            st.session_state.feedback = "✅ Correct! Great job."
            st.session_state.reveal_answer = True
            # Update Score
            st.session_state.score_correct += 1
        else:
            st.session_state.feedback = "❌ Incorrect. Try again or click 'Show Answer'."
        
        # Add to History Log (if not already added for this specific attempt)
        # We use a simple check to ensure we don't log the same question twice if they click submit multiple times
        current_q_signature = f"{question[:20]}... | {user_ans}"
        if st.session_state.last_logged != current_q_signature:
            st.session_state.history_list.append({
                "Question": question,
                "Your Answer": user_ans,
                "Result": "Correct" if is_correct else "Incorrect",
                "Topic": st.session_state.opt_topic
            })
            st.session_state.last_logged = current_q_signature
            st.session_state.score_total += 1
            
    except Exception as e:
        st.error(f"Error grading: {e}")

def show_answer():
    st.session_state.reveal_answer = True

# 3. Initialization (Session State)
if 'init' not in st.session_state:
    st.session_state.init = True
    st.session_state.question_text = ""
    st.session_state.user_input = ""
    st.session_state.feedback = ""
    st.session_state.hint_text = ""
    
    # NEW: Score Tracking
    st.session_state.score_correct = 0
    st.session_state.score_total = 0
    st.session_state.history_list = []
    st.session_state.last_logged = ""
    
    # Trigger first question
    if "GEMINI_API_KEY" in st.secrets or "GEMINI_API_KEY" in os.environ:
        # We need to manually set defaults for the first run since sidebar hasn't rendered yet
        st.session_state.opt_grade = "Grade 5" 
        st.session_state.opt_topic = "Arithmetic" 
        st.session_state.opt_difficulty = "Medium"
        get_new_question()

# 4. Sidebar Configuration
with st.sidebar:
    st.header("User Profile")
    user_name = st.text_input("Enter your name:", value="Student")
    
    st.metric("Score", f"{st.session_state.score_correct} / {st.session_state.score_total}")
    
    st.divider()
    
    st.header("Settings")
    st.selectbox("Select Grade Level", [f"Grade {i}" for i in range(1, 13)] + ["College/University"], key="opt_grade", on_change=get_new_question)
    st.selectbox("Select Topic", ["Arithmetic", "Algebra", "Geometry", "Metric Conversion", "Operation on Integers", "Fractions", "Decimal Operations", "Metric Conversion"], key="opt_topic", on_change=get_new_question)
    st.selectbox("Select Difficulty", ["Easy", "Medium", "Hard"], key="opt_difficulty", on_change=get_new_question)
    
    if st.button("Reset Score"):
        st.session_state.score_correct = 0
        st.session_state.score_total = 0
        st.session_state.history_list = []
        st.rerun()

# 5. Main UI Layout
st.title(f"🎓 {user_name}'s Math Practice")
st.caption(f"Topic: {st.session_state.opt_topic} | Grade: {st.session_state.opt_grade}")

if st.session_state.question_text:
    st.markdown("### Question")
    st.info(st.session_state.question_text)

    if st.session_state.hint_text:
        st.warning(f"💡 **Hint:** {st.session_state.hint_text}")

    st.markdown("### Your Answer")
    st.text_input("Type your answer here:", key="user_input")

    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    with col1: st.button("Submit Answer", on_click=check_answer)
    with col2: st.button("Get Hint", on_click=get_hint)
    with col3: st.button("Show Answer", on_click=show_answer)
    with col4: st.button("Next Question", on_click=get_new_question)

    if st.session_state.feedback:
        if "Correct!" in st.session_state.feedback:
            st.success(st.session_state.feedback)
        else:
            st.error(st.session_state.feedback)

    if st.session_state.reveal_answer:
        st.markdown("---")
        st.markdown("### Explanation")
        st.write(st.session_state.answer_text)

# 6. Session History Table
if st.session_state.history_list:
    st.markdown("---")
    st.markdown("### 📜 Session History")
    df = pd.DataFrame(st.session_state.history_list)
    st.dataframe(df, use_container_width=True)
