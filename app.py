import streamlit as st
import google.generativeai as genai

st.title("🔍 API Debugger")

# 1. Get Key
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    st.success("✅ API Key found in secrets.")
except:
    st.error("❌ API Key NOT found in secrets.")
    st.stop()

# 2. Configure
genai.configure(api_key=api_key)

# 3. List Models
st.write("Attempting to list available models...")

try:
    models = list(genai.list_models())
    found_any = False
    for m in models:
        # Check if it supports generating content
        if 'generateContent' in m.supported_generation_methods:
            st.markdown(f"- **`{m.name}`**")
            found_any = True
            
    if not found_any:
        st.warning("⚠️ Connected to API, but no 'generateContent' models found. Check if 'Generative Language API' is enabled in GCP Console.")
    else:
        st.success("✅ Connection Successful! Use one of the names above in your main app.")

except Exception as e:
    st.error(f"❌ Connection Failed. Error details:\n\n{e}")
