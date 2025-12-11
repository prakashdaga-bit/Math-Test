# 2. Optimized Google Sheets Connection (Cached)
@st.cache_resource
def get_google_sheet_client():
    """Authenticates and returns the gspread client. Cached for speed."""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # 1. Convert the secrets object to a standard Python dictionary
    # We do this so we can modify the private_key without error
    creds_dict = dict(st.secrets["gcp_service_account"])
    
    # 2. THE CRITICAL FIX: Replace literal "\n" strings with actual newlines
    if "private_key" in creds_dict:
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)
