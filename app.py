
import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import google.generativeai as genai
import json
from datetime import date

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="IGCSE Math Tutor", page_icon="📐", layout="wide")

# --- 1. SETUP & AUTHENTICATION ---
# Load Gemini API Key from Secrets
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except (FileNotFoundError, KeyError):
    st.error("Missing GEMINI_API_KEY in secrets.toml")
    st.stop()

# Initialize Google Sheets Connection
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. HELPER FUNCTIONS ---

def get_data():
    """Fetch all history from Google Sheets."""
    try:
        # read() returns a pandas DataFrame
        df = conn.read(worksheet="History", usecols=list(range(5)), ttl=5)
        # Ensure correct data types
        if not df.empty:
            df = df.dropna(how='all')
            df['Date'] = pd.to_datetime(df['Date']).dt.date
        return df
    except Exception:
        # Return empty structure if sheet is new/empty
        return pd.DataFrame(columns=["Date", "Name", "Topic", "Score", "Grade"])

def save_data(name, topic, score, grade):
    """Append a new quiz result to Google Sheets."""
    df = get_data()
    new_row = pd.DataFrame([{
        "Date": str(date.today()),
        "Name": name.lower().strip(),
        "Topic": topic,
        "Score": score,
        "Grade": grade
    }])
    # Combine old data with new row
    updated_df = pd.concat([df, new_row], ignore_index=True)
    # Update the sheet
    conn.update(worksheet="History", data=updated_df)

def get_gemini_questions(grade, curriculum, topic, num_questions, user_context=""):
    """Call Gemini to generate a JSON quiz."""
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    prompt = f"""
    You are an expert math tutor. Create a quiz for a Grade {grade} student following the {curriculum} curriculum.
    Topic: {topic}
    Number of questions: {num_questions}
    
    Student Context (Previous Weaknesses): {user_context}
    
    Strictly output VALID JSON in the following format (no markdown, no ```):
    [
        {{
            "question": "Question text here",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct_answer": "Option A",
            "explanation": "Brief explanation of the solution."
        }}
    ]
    """
    
    try:
        response = model.generate_content(prompt)
        # Clean response to ensure pure JSON
        text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        st.error(f"AI Generation Error: {e}")
        return []

# --- 3. UI: SIDEBAR (Login & Settings) ---
with st.sidebar:
    st.title("Settings")
    
    # User Login
    current_user = st.text_input("👤 Student Name").strip().lower()
    
    st.divider()
    
    # Quiz Settings
    st.subheader("Quiz Configuration")
    grade = st.selectbox("Grade", ["Grade 5", "Grade 6", "Grade 7", "Grade 8"], index=1)
    curriculum = st.selectbox("Curriculum", ["IGCSE", "IB MYP", "CBSE", "Common Core"])
    topic = st.text_input("Topic", "Algebra - Linear Equations")
    num_q = st.slider("Number of Questions", 1, 10, 5)
    
    # Generate Button
    start_btn = st.button("🚀 Generate New Quiz")

# --- 4. MAIN INTERFACE ---
st.title("📐 IGCSE Daily Math Practice")

if not current_user:
    st.info("👈 Please enter your Name in the sidebar to start tracking your progress.")
    st.stop()

# --- 5. ANALYTICS DASHBOARD ---
# Fetch data and filter for current user
df_all = get_data()
if not df_all.empty:
    user_history = df_all[df_all['Name'] == current_user]
else:
    user_history = pd.DataFrame()

if not user_history.empty:
    # Stats
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Quizzes", len(user_history))
    avg_score = user_history['Score'].mean()
    col2.metric("Average Score", f"{avg_score:.1f}%")
    
    # Check if practiced today
    today = date.today()
    last_practice = user_history['Date'].max()
    is_done_today = last_practice == today
    col3.metric("Status Today", "✅ Done" if is_done_today else "❌ Not yet")
    
    # Identification of Weak Areas (Simple logic: Topics with avg score < 70%)
    topic_perf = user_history.groupby('Topic')['Score'].mean()
    weak_topics = topic_perf[topic_perf < 70].index.tolist()
    
    with st.expander("📊 View Progress History"):
        st.dataframe(user_history.sort_values(by='Date', ascending=False))
        if weak_topics:
            st.warning(f"Focus Areas (Avg < 70%): {', '.join(weak_topics)}")
            user_context_str = f"Student struggles with: {', '.join(weak_topics)}"
        else:
            user_context_str = ""
else:
    st.info(f"Welcome, {current_user.title()}! Your history will appear here after your first quiz.")
    user_context_str = ""

st.divider()

# --- 6. QUIZ LOGIC ---

# Initialize Session State
if 'quiz_data' not in st.session_state:
    st.session_state['quiz_data'] = None
if 'quiz_active' not in st.session_state:
    st.session_state['quiz_active'] = False
if 'current_q_index' not in st.session_state:
    st.session_state['current_q_index'] = 0
if 'current_score' not in st.session_state:
    st.session_state['current_score'] = 0

# Trigger: Generate Quiz
if start_btn:
    with st.spinner("Gemini is crafting questions just for you..."):
        # Pass user context (weak topics) to AI
        questions = get_gemini_questions(grade, curriculum, topic, num_q, user_context_str)
        if questions:
            st.session_state['quiz_data'] = questions
            st.session_state['current_q_index'] = 0
            st.session_state['current_score'] = 0
            st.session_state['quiz_active'] = True
            st.rerun()

# Display Quiz
if st.session_state['quiz_active'] and st.session_state['quiz_data']:
    q_idx = st.session_state['current_q_index']
    quiz = st.session_state['quiz_data']
    total_q = len(quiz)
    
    # Progress Bar
    st.progress((q_idx) / total_q)
    
    if q_idx < total_q:
        question_item = quiz[q_idx]
        
        st.subheader(f"Question {q_idx + 1}")
        st.markdown(f"**{question_item['question']}**")
        
        # Answer Selection
        choice = st.radio("Select Answer:", question_item['options'], key=f"q_{q_idx}")
        
        # Check Answer Button
        if st.button("Submit Answer"):
            if choice == question_item['correct_answer']:
                st.success("✅ Correct!")
                st.session_state['current_score'] += 1
            else:
                st.error(f"❌ Incorrect. The correct answer was: {question_item['correct_answer']}")
                st.info(f"📝 Explanation: {question_item['explanation']}")
            
            # Move to next logic
            if st.button("Next Question ➡️"):
                st.session_state['current_q_index'] += 1
                st.rerun()
                
    else:
        # --- QUIZ COMPLETE ---
        final_score = (st.session_state['current_score'] / total_q) * 100
        st.balloons()
        
        st.success(f"🎉 Quiz Finished! You scored {final_score:.0f}%")
        
        if st.button("💾 Save Results"):
            with st.spinner("Saving to database..."):
                save_data(current_user, topic, final_score, grade)
            st.success("Saved! Check your history above.")
            st.session_state['quiz_active'] = False
            st.rerun()

elif not st.session_state['quiz_active']:
    st.markdown("### Ready to practice? Configure the settings on the left and click **Generate New Quiz**.")
