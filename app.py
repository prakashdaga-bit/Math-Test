import streamlit as st
import google.generativeai as genai
import os

# 1. Setup
# We look for GEMINI_API_KEY in secrets first, then environment variables
try:
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    elif "GEMINI_API_KEY" in os.environ:
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    else:
        st.error("Missing API Key! Please set GEMINI_API_KEY in your .streamlit/secrets.toml file or environment.")
        st.stop()
except Exception as e:
    st.error(f"Error configuring API: {e}")
    st.stop()

# 2. Logic Functions

def get_new_question():
    """Fetches a new question and resets all states."""
    model = genai.GenerativeModel("models/gemini-2.5-flash")
    
    topic = st.session_state.opt_topic
    difficulty = st.session_state.opt_difficulty
    
    prompt = f"""
    Generate a unique, {difficulty}-level math practice question specifically about {topic}.
    
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
    You are a helpful tutor.
    The Student is stuck on this question: "{q}"
    The solution is: "{a}"
    
    Provide a short, helpful hint that guides them towards the right strategy.
    Do NOT reveal the final answer.
    """
    
    try:
        response = model.generate_content(prompt)
        st.session_state.hint_text = response.text
    except Exception as e:
        st.error(f"Error getting hint: {e}")

def check_answer():
    """Uses Gemini to grade the answer."""
    user_ans = st.session_state.user_input
    correct_ans = st.session_state.answer_text
    question = st.session_state.question_text
    
    if not user_ans:
        st.session_state.feedback = "Please enter an answer first."
        return

    judge_model = genai.GenerativeModel("models/gemini-2.5-flash")
    judge_prompt = f"""
    You are a math teacher.
    Question: {question}
    Correct Answer: {correct_ans}
    Student Answer: {user_ans}
    
    Is the student's answer correct? 
    Reply with ONLY the word "CORRECT" or "INCORRECT".
    """
    
    try:
        response = judge_model.generate_content(judge_prompt)
        result = response.text.strip().upper()
        
        if "CORRECT" in result:
            st.session_state.feedback = "✅ Correct! Great job."
            st.session_state.reveal_answer = True 
        else:
            st.session_state.feedback = "❌ Incorrect. Try again or click 'Show Answer'."
            
    except Exception as e:
        st.error(f"Error grading: {e}")

def show_answer():
    st.session_state.reveal_answer = True

# 3. Sidebar Configuration
with st.sidebar:
    st.header("Settings")
    
    st.selectbox(
        "Select Topic",
        ["Arithmetic", "Algebra", "Geometry", "Trigonometry", "Calculus", "Statistics", "Linear Algebra"],
        key="opt_topic",
        on_change=get_new_question
    )
    
    st.selectbox(
        "Select Difficulty",
        ["Beginner", "Intermediate", "Advanced"],
        key="opt_difficulty",
        on_change=get_new_question
    )

    st.markdown("---")
    st.write("Each time you change a setting, a new question is generated automatically.")

# 4. Initialization
if 'question_text' not in st.session_state:
    st.session_state.user_input = ""
    st.session_state.feedback = ""
    st.session_state.hint_text = ""
    # Only run if we haven't stopped execution due to missing key
    get_new_question()

# 5. Main UI Layout
st.title("Math Practice Generator")
st.caption(f"Topic: {st.session_state.opt_topic} | Level: {st.session_state.opt_difficulty}")

if 'question_text' in st.session_state:
    st.markdown("### Question")
    st.info(st.session_state.question_text)

    # Hint Display
    if st.session_state.hint_text:
        st.warning(f"💡 **Hint:** {st.session_state.hint_text}")

    # Input Section
    st.markdown("### Your Answer")
    st.text_input("Type your answer here:", key="user_input")

    # Button Layout
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])

    with col1:
        st.button("Submit Answer", on_click=check_answer)

    with col2:
        st.button("Get Hint", on_click=get_hint)

    with col3:
        st.button("Show Answer", on_click=show_answer)

    with col4:
        st.button("Next Question", on_click=get_new_question)

    # Feedback Display
    if st.session_state.feedback:
        if "Correct!" in st.session_state.feedback:
            st.success(st.session_state.feedback)
        else:
            st.error(st.session_state.feedback)

    # Answer Display
    if st.session_state.reveal_answer:
        st.markdown("---")
        st.markdown("### Explanation")
        st.write(st.session_state.answer_text)
