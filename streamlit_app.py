"""
Last War Kill Tracker - Streamlit Web App
Upload screenshots, analyze them with Gemini Vision, and track kills in Google Sheets.
"""
import streamlit as st
import json
import io
import pandas as pd
from datetime import datetime
from PIL import Image

import google.genai as genai
from google.genai import types
import gspread
from google.oauth2.service_account import Credentials

# --- Page Config ---
st.set_page_config(
    page_title="Last War Kill Tracker",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Custom CSS ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

    .stApp {
        font-family: 'Inter', sans-serif;
    }

    .main-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        padding: 2rem 2.5rem;
        border-radius: 16px;
        margin-bottom: 2rem;
        border: 1px solid rgba(255, 255, 255, 0.08);
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    }

    .main-header h1 {
        color: #e94560;
        font-weight: 800;
        font-size: 2.2rem;
        margin: 0;
        letter-spacing: -0.5px;
    }

    .main-header p {
        color: #a0aec0;
        font-size: 1rem;
        margin: 0.5rem 0 0 0;
    }

    .stat-card {
        background: linear-gradient(135deg, #1a1a2e, #16213e);
        padding: 1.5rem;
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        text-align: center;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
    }

    .stat-card h3 {
        color: #e94560;
        font-size: 2rem;
        font-weight: 700;
        margin: 0;
    }

    .stat-card p {
        color: #a0aec0;
        font-size: 0.85rem;
        margin: 0.3rem 0 0 0;
        text-transform: uppercase;
        letter-spacing: 1px;
    }

    .success-banner {
        background: linear-gradient(135deg, #0d4b2e, #1a6b3c);
        padding: 1rem 1.5rem;
        border-radius: 10px;
        border: 1px solid rgba(72, 187, 120, 0.3);
        color: #9ae6b4;
        font-weight: 500;
    }

    .upload-zone {
        border: 2px dashed rgba(233, 69, 96, 0.4);
        border-radius: 12px;
        padding: 2rem;
        text-align: center;
        background: rgba(233, 69, 96, 0.05);
        transition: all 0.3s ease;
    }

    div[data-testid="stFileUploader"] {
        border: 2px dashed rgba(233, 69, 96, 0.3);
        border-radius: 12px;
        padding: 1rem;
        background: rgba(233, 69, 96, 0.03);
    }

    .stDataFrame {
        border-radius: 12px;
        overflow: hidden;
    }

    div[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
    }

    div[data-testid="stSidebar"] .stMarkdown h2 {
        color: #e94560;
    }
</style>
""", unsafe_allow_html=True)


# --- Gemini Analysis (inline, no file imports needed) ---
EXTRACTION_PROMPT = """Analyze these screenshots from the game "Last War: Survival Game".
They show a leaderboard/ranking of alliance members with their kill counts.
There may be multiple screenshots from scrolling, so deduplicate by rank number.

Each row contains:
- A rank number (1, 2, 3, etc.)
- A player avatar image
- A role badge (R3, R4, R5, etc.)
- A player name
- A kill count (large number on the right)

Extract ALL unique player entries and return as a JSON array sorted by rank.
Each entry: {"rank": int, "name": "string", "kills": int}

Rules:
- Include the green highlighted row (user's own rank) only ONCE
- Read large numbers carefully
- Preserve non-Latin characters exactly
- Return ONLY the JSON array"""


def analyze_screenshots(images, api_key):
    """Analyze screenshots with Gemini Vision."""
    client = genai.Client(api_key=api_key)

    pil_images = [img if isinstance(img, Image.Image) else Image.open(img) for img in images]

    content = [EXTRACTION_PROMPT] + pil_images
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=content,
    )

    text = response.text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    data = json.loads(text)

    # Deduplicate and clean
    cleaned = []
    seen_ranks = set()
    for entry in data:
        rank = int(entry.get("rank", 0))
        name = str(entry.get("name", "")).strip()
        kills = int(entry.get("kills", 0))
        if rank > 0 and name and rank not in seen_ranks:
            cleaned.append({"rank": rank, "name": name, "kills": kills})
            seen_ranks.add(rank)

    cleaned.sort(key=lambda x: x["rank"])
    return cleaned


def write_to_sheets(kill_data, sheet_id, credentials_json, date_str=None):
    """Write kill data to Google Sheets."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    creds_dict = json.loads(credentials_json)
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(credentials)

    spreadsheet = client.open_by_key(sheet_id)

    # Get or create worksheet
    ws_name = "Kill Tracker"
    try:
        worksheet = spreadsheet.worksheet(ws_name)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=ws_name, rows=200, cols=50)

    # Load aliases
    aliases = {}
    try:
        alias_ws = spreadsheet.worksheet("Name Aliases")
        alias_values = alias_ws.get_all_values()
        for row in alias_values[1:]:
            if len(row) >= 2 and row[0] and row[1]:
                aliases[row[0].strip()] = row[1].strip()
    except gspread.WorksheetNotFound:
        pass

    all_values = worksheet.get_all_values()
    if not all_values:
        all_values = [["Rank", "Member Name"]]

    headers = all_values[0]

    if date_str in headers:
        date_col_idx = headers.index(date_str)
    else:
        date_col_idx = len(headers)
        headers.append(date_str)

    existing_members = {}
    for row_idx, row in enumerate(all_values[1:], start=1):
        if len(row) >= 2 and row[1]:
            existing_members[row[1]] = row_idx

    num_cols = len(headers)
    for i, row in enumerate(all_values):
        while len(row) < num_cols:
            all_values[i].append("")

    for entry in kill_data:
        raw_name = entry["name"]
        name = aliases.get(raw_name, raw_name)
        rank = entry["rank"]
        kills = entry["kills"]

        if name in existing_members:
            row_idx = existing_members[name]
        else:
            row_idx = len(all_values)
            all_values.append([""] * num_cols)
            existing_members[name] = row_idx

        all_values[row_idx][0] = rank
        all_values[row_idx][1] = name
        all_values[row_idx][date_col_idx] = kills

    # Convert numeric strings to int
    for i, row in enumerate(all_values):
        for j, cell in enumerate(row):
            if isinstance(cell, str) and cell.isdigit():
                all_values[i][j] = int(cell)

    def col_letter(n):
        r = ""
        while n > 0:
            n, rem = divmod(n - 1, 26)
            r = chr(65 + rem) + r
        return r

    range_str = f"A1:{col_letter(num_cols)}{len(all_values)}"
    worksheet.update(range_str, all_values, value_input_option="RAW")

    return len(kill_data)


# --- Helper: Load secrets safely ---
def get_secret(key, default=""):
    """Get a secret from Streamlit secrets, return default if not found."""
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default


def get_credentials_from_secrets():
    """Try to build credentials JSON from Streamlit secrets."""
    try:
        creds = st.secrets["google_credentials"]
        # Convert AttrDict to regular dict
        return json.dumps(dict(creds))
    except Exception:
        return None


# --- Load secrets silently ---
gemini_key = get_secret("GEMINI_API_KEY")
sheet_id = get_secret("GOOGLE_SHEET_ID")
credentials_json = get_credentials_from_secrets()


def extract_sheet_id(url_or_id: str) -> str:
    """Extract sheet ID from a full Google Sheets URL or return as-is if already an ID."""
    import re
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url_or_id)
    if match:
        return match.group(1)
    return url_or_id.strip()


with st.sidebar:
    # Only show API key / credentials fields if secrets are missing
    if not (gemini_key and credentials_json):
        st.markdown("## ⚙️ Configuration")

        if not gemini_key:
            gemini_key = st.text_input(
                "Gemini API Key",
                type="password",
                help="Get yours at aistudio.google.com/apikey",
            )

        if not credentials_json:
            credentials_file = st.file_uploader(
                "Service Account JSON",
                type=["json"],
                help="Upload your Google service account credentials file",
            )
            if credentials_file:
                credentials_json = credentials_file.read().decode("utf-8")

        st.markdown("---")

    # Sheet URL/ID is always visible so users can easily switch sheets
    st.markdown("### 📊 Google Sheet")
    sheet_input = st.text_input(
        "Sheet URL or ID",
        value=sheet_id,
        help="Paste the full Google Sheets URL or just the sheet ID",
    )
    if sheet_input:
        sheet_id = extract_sheet_id(sheet_input)

    st.markdown("### 📅 Date")
    custom_date = st.date_input(
        "Data date",
        value=datetime.now(),
        help="Override the date for this data entry",
    )


# --- Main Content ---
st.markdown("""
<div class="main-header">
    <h1>⚔️ Last War Kill Tracker</h1>
    <p>Upload leaderboard screenshots • AI-powered analysis • Automatic Google Sheets tracking</p>
</div>
""", unsafe_allow_html=True)

# --- Upload Section ---
st.markdown("### 📸 Upload Screenshots")

uploaded_files = st.file_uploader(
    "Drop your leaderboard screenshots here",
    type=["png", "jpg", "jpeg", "webp"],
    accept_multiple_files=True,
    help="Upload one or more screenshots of the kill leaderboard",
)

if uploaded_files:
    # Preview uploaded images
    st.markdown("#### Preview")
    cols = st.columns(min(len(uploaded_files), 4))
    for idx, file in enumerate(uploaded_files):
        with cols[idx % 4]:
            img = Image.open(file)
            st.image(img, caption=file.name, use_container_width=True)
            file.seek(0)  # Reset for later use

    st.markdown("---")

    # Analyze button
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        analyze_clicked = st.button(
            "🔍 Analyze Screenshots",
            use_container_width=True,
            type="primary",
            disabled=not gemini_key,
        )

    if not gemini_key:
        st.warning("⚠️ Enter your Gemini API key in the sidebar to enable analysis.")

    if analyze_clicked and gemini_key:
        with st.spinner("🤖 Analyzing screenshots with Gemini Vision..."):
            try:
                images = [Image.open(f) for f in uploaded_files]
                results = analyze_screenshots(images, gemini_key)
                st.session_state["results"] = results
            except Exception as e:
                st.error(f"❌ Analysis failed: {e}")

    # Show results
    if "results" in st.session_state and st.session_state["results"]:
        results = st.session_state["results"]

        st.markdown("---")
        st.markdown("### 📊 Extracted Data")

        # Stats cards
        col1, col2, col3 = st.columns(3)
        total_kills = sum(r["kills"] for r in results)
        with col1:
            st.markdown(f"""
            <div class="stat-card">
                <h3>{len(results)}</h3>
                <p>Members Found</p>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            st.markdown(f"""
            <div class="stat-card">
                <h3>{total_kills:,}</h3>
                <p>Total Kills</p>
            </div>
            """, unsafe_allow_html=True)
        with col3:
            avg_kills = total_kills // len(results) if results else 0
            st.markdown(f"""
            <div class="stat-card">
                <h3>{avg_kills:,}</h3>
                <p>Average Kills</p>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("")

        # Results table
        df = pd.DataFrame(results)
        df.columns = ["Rank", "Player Name", "Kills"]
        df["Kills"] = df["Kills"].apply(lambda x: f"{x:,}")

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            height=min(len(results) * 40 + 40, 600),
        )

        # Write to Sheets button
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            write_clicked = st.button(
                "📤 Write to Google Sheets",
                use_container_width=True,
                type="primary",
                disabled=not (sheet_id and credentials_json),
            )

        if not (sheet_id and credentials_json):
            st.info("💡 Configure Google Sheets in the sidebar to enable writing.")

        if write_clicked and sheet_id and credentials_json:
            with st.spinner("📤 Writing to Google Sheets..."):
                try:
                    date_str = custom_date.strftime("%Y-%m-%d")
                    count = write_to_sheets(results, sheet_id, credentials_json, date_str)
                    st.markdown(f"""
                    <div class="success-banner">
                        ✅ Successfully wrote {count} members to Google Sheets for {date_str}
                    </div>
                    """, unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"❌ Failed to write to Sheets: {e}")

        # Download as JSON
        st.markdown("")
        st.download_button(
            "💾 Download as JSON",
            data=json.dumps(results, indent=2, ensure_ascii=False),
            file_name=f"kill_data_{custom_date.strftime('%Y%m%d')}.json",
            mime="application/json",
        )

else:
    # Empty state
    st.markdown("""
    <div style="text-align: center; padding: 3rem 1rem; color: #718096;">
        <p style="font-size: 3rem;">📸</p>
        <p style="font-size: 1.1rem;">Drop your leaderboard screenshots above to get started</p>
        <p style="font-size: 0.9rem;">Supports PNG, JPG, and WebP images</p>
    </div>
    """, unsafe_allow_html=True)

# --- Footer ---
st.markdown("---")
st.markdown(
    "<p style='text-align: center; color: #4a5568; font-size: 0.8rem;'>"
    "Last War Kill Tracker • Powered by Gemini Vision AI"
    "</p>",
    unsafe_allow_html=True,
)
