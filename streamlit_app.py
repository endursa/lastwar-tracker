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

    # Always enforce proper header structure
    # Headers MUST start with "Rank", "Member Name", then date columns
    if not all_values or len(all_values[0]) < 2 or all_values[0][0] != "Rank":
        # Sheet is empty or has corrupted headers — start fresh
        existing_dates = []
        all_values = []
    else:
        # Extract existing date columns (everything after Rank and Member Name)
        existing_dates = all_values[0][2:]

    # Build proper headers
    headers = ["Rank", "Member Name"] + existing_dates
    if date_str not in headers:
        headers.append(date_str)
    date_col_idx = headers.index(date_str)
    num_cols = len(headers)

    # Build a dict of member data: name -> {col_idx: value, ...}
    member_order = []  # Preserve row order
    member_data = {}   # name -> dict of col values

    for row in all_values[1:]:
        if len(row) >= 2 and row[1]:
            name = row[1]
            if name not in member_data:
                member_order.append(name)
                member_data[name] = {}
            # Copy existing column values
            for col_idx, val in enumerate(row):
                member_data[name][col_idx] = val

    # Fuzzy matching: find existing name that closely matches
    from difflib import SequenceMatcher
    import unicodedata

    def normalize_name(name):
        """Strip accents/diacritics for comparison. Èmmå → Emma"""
        nfkd = unicodedata.normalize("NFKD", name)
        return "".join(c for c in nfkd if not unicodedata.combining(c))

    def find_matching_name(new_name, existing_names, threshold=0.85):
        """Find an existing name that matches via normalization or fuzzy match."""
        norm_new = normalize_name(new_name)
        # First: exact match on normalized names
        for existing in existing_names:
            if normalize_name(existing) == norm_new:
                return existing
        # Second: fuzzy match on original names
        best_match = None
        best_ratio = 0
        for existing in existing_names:
            ratio = SequenceMatcher(None, new_name, existing).ratio()
            if ratio >= threshold and ratio > best_ratio:
                best_match = existing
                best_ratio = ratio
        return best_match

    # Apply new kill data
    for entry in kill_data:
        raw_name = entry["name"]
        name = aliases.get(raw_name, raw_name)
        rank = entry["rank"]
        kills = entry["kills"]

        # Check for fuzzy match against existing members
        if name not in member_data:
            matched = find_matching_name(name, member_data.keys())
            if matched:
                name = matched  # Use existing canonical name

        if name not in member_data:
            member_order.append(name)
            member_data[name] = {}

        member_data[name][0] = rank           # Rank column
        member_data[name][1] = name           # Name column
        member_data[name][date_col_idx] = kills  # Kill count

    # Build the final grid from the dict
    output = [headers]
    for name in member_order:
        row = [""] * num_cols
        for col_idx, val in member_data[name].items():
            if col_idx < num_cols:
                row[col_idx] = val
        output.append(row)

    # Convert numeric strings to int for proper Sheets formatting
    for i in range(len(output)):
        for j in range(len(output[i])):
            cell = output[i][j]
            if isinstance(cell, str) and cell.isdigit():
                output[i][j] = int(cell)

    def col_letter(n):
        r = ""
        while n > 0:
            n, rem = divmod(n - 1, 26)
            r = chr(65 + rem) + r
        return r

    range_str = f"A1:{col_letter(num_cols)}{len(output)}"
    worksheet.update(range_str, output, value_input_option="RAW")

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
                    # Debug: show sample data that was written
                    st.caption("Sample data sent to Sheets:")
                    sample = [{"rank": r["rank"], "name": r["name"], "kills": r["kills"]} for r in results[:5]]
                    st.json(sample)
                except Exception as e:
                    import traceback
                    st.error(f"❌ Failed to write to Sheets: {e}")
                    st.code(traceback.format_exc())

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

# --- Comparison Section ---
st.markdown("---")
st.markdown("### 📈 Kill Comparison")

if sheet_id and credentials_json:
    compare_clicked = st.button("🔄 Load comparison from Google Sheets", use_container_width=True)

    if compare_clicked:
        with st.spinner("📊 Loading data from Google Sheets..."):
            try:
                creds_dict = json.loads(credentials_json)
                creds = Credentials.from_service_account_info(creds_dict, scopes=[
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive",
                ])
                gc = gspread.authorize(creds)
                spreadsheet = gc.open_by_key(sheet_id)
                ws = spreadsheet.worksheet("Kill Tracker")
                all_data = ws.get_all_values()

                if not all_data or len(all_data[0]) < 4:
                    st.warning("⚠️ Need at least 2 date columns to compare. Upload more data first.")
                else:
                    headers = all_data[0]
                    # Date columns start at index 2 (after Rank, Member Name)
                    date_cols = headers[2:]

                    if len(date_cols) < 2:
                        st.warning("⚠️ Need at least 2 date columns to compare.")
                    else:
                        # Use the two newest dates
                        newest_date = date_cols[-1]
                        prev_date = date_cols[-2]
                        newest_idx = headers.index(newest_date)
                        prev_idx = headers.index(prev_date)

                        st.info(f"📅 Comparing **{prev_date}** → **{newest_date}**")

                        comparison = []
                        for row in all_data[1:]:
                            if len(row) > max(newest_idx, prev_idx) and row[1]:
                                name = row[1]
                                try:
                                    new_kills = int(str(row[newest_idx]).replace(",", "")) if row[newest_idx] else 0
                                    old_kills = int(str(row[prev_idx]).replace(",", "")) if row[prev_idx] else 0
                                except ValueError:
                                    continue

                                if old_kills > 0 and new_kills > 0:
                                    delta = new_kills - old_kills
                                    pct = round((delta / old_kills) * 100, 2) if old_kills > 0 else 0
                                    comparison.append({
                                        "Player": name,
                                        "Previous": old_kills,
                                        "Current": new_kills,
                                        "Delta": delta,
                                        "% Change": pct,
                                    })

                        if comparison:
                            # Sort by % Change descending
                            comparison.sort(key=lambda x: x["% Change"], reverse=True)

                            # Stat cards
                            col1, col2, col3 = st.columns(3)
                            top = comparison[0]
                            avg_pct = round(sum(c["% Change"] for c in comparison) / len(comparison), 2)
                            total_delta = sum(c["Delta"] for c in comparison)

                            with col1:
                                st.markdown(f"""
                                <div class="stat-card">
                                    <h3>{top["Player"]}</h3>
                                    <p>Top Improver ({top["% Change"]}%)</p>
                                </div>
                                """, unsafe_allow_html=True)
                            with col2:
                                st.markdown(f"""
                                <div class="stat-card">
                                    <h3>{avg_pct}%</h3>
                                    <p>Average Improvement</p>
                                </div>
                                """, unsafe_allow_html=True)
                            with col3:
                                st.markdown(f"""
                                <div class="stat-card">
                                    <h3>+{total_delta:,}</h3>
                                    <p>Total Kill Increase</p>
                                </div>
                                """, unsafe_allow_html=True)

                            st.markdown("")

                            # Build display table
                            df_compare = pd.DataFrame(comparison)
                            df_compare.index = range(1, len(df_compare) + 1)
                            df_compare["Previous"] = df_compare["Previous"].apply(lambda x: f"{x:,}")
                            df_compare["Current"] = df_compare["Current"].apply(lambda x: f"{x:,}")
                            df_compare["Delta"] = df_compare["Delta"].apply(lambda x: f"+{x:,}" if x >= 0 else f"{x:,}")
                            df_compare["% Change"] = df_compare["% Change"].apply(lambda x: f"+{x}%" if x >= 0 else f"{x}%")

                            st.dataframe(
                                df_compare,
                                use_container_width=True,
                                height=min(len(comparison) * 40 + 40, 600),
                            )
                        else:
                            st.warning("⚠️ No comparable data found between the two dates.")

            except Exception as e:
                import traceback
                st.error(f"❌ Failed to load comparison: {e}")
                st.code(traceback.format_exc())
else:
    st.info("💡 Configure Google Sheets to view kill comparisons.")

# --- Footer ---
st.markdown("---")
st.markdown(
    "<p style='text-align: center; color: #4a5568; font-size: 0.8rem;'>"
    "Last War Kill Tracker • Powered by Gemini Vision AI"
    "</p>",
    unsafe_allow_html=True,
)
