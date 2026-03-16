"""
Last War Kill Tracker - Google Sheets Integration Module
Handles reading and writing kill data to Google Sheets.
"""
import logging
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

from config import GOOGLE_CREDENTIALS_FILE, GOOGLE_SHEET_ID, WORKSHEET_NAME

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_client() -> gspread.Client:
    """Create and return an authenticated gspread client."""
    if not GOOGLE_SHEET_ID:
        raise ValueError(
            "GOOGLE_SHEET_ID is not set. "
            "Set it in your .env file or config.py"
        )
    credentials = Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_FILE, scopes=SCOPES
    )
    return gspread.authorize(credentials)


def get_or_create_worksheet(spreadsheet, name: str):
    """Get an existing worksheet or create a new one."""
    try:
        return spreadsheet.worksheet(name)
    except gspread.WorksheetNotFound:
        logger.info(f"Creating new worksheet: {name}")
        ws = spreadsheet.add_worksheet(title=name, rows=200, cols=50)
        # Set up header
        ws.update_cell(1, 1, "Rank")
        ws.update_cell(1, 2, "Member Name")
        return ws


def get_aliases(spreadsheet) -> dict:
    """
    Read name aliases from the 'Name Aliases' worksheet.

    The worksheet format is:
    | Old Name    | Current Name |
    |-------------|--------------|
    | MinyoungXO  | MinyoungV2   |
    | OldPlayer   | NewPlayer    |

    Returns a dict mapping old_name -> current_name.
    If the worksheet doesn't exist, it creates one with example headers.
    """
    alias_ws_name = "Name Aliases"
    try:
        alias_ws = spreadsheet.worksheet(alias_ws_name)
    except gspread.WorksheetNotFound:
        logger.info(f"Creating '{alias_ws_name}' worksheet...")
        alias_ws = spreadsheet.add_worksheet(title=alias_ws_name, rows=100, cols=2)
        alias_ws.update("A1:B1", [["Old Name", "Current Name"]])
        return {}

    all_values = alias_ws.get_all_values()
    aliases = {}
    for row in all_values[1:]:  # Skip header
        if len(row) >= 2 and row[0] and row[1]:
            aliases[row[0].strip()] = row[1].strip()

    if aliases:
        logger.info(f"Loaded {len(aliases)} name aliases")
    return aliases


def resolve_name(name: str, aliases: dict) -> str:
    """Resolve a player name through the alias mapping."""
    return aliases.get(name, name)


def write_kill_data(kill_data: list[dict], date_str: str = None):
    """
    Write kill data to Google Sheets.

    The sheet format is:
    | Rank | Member Name | 2026-03-16 | 2026-03-17 | ... |
    |------|-------------|------------|------------|-----|
    | 1    | Ercimus     | 35167068   | ...        |     |
    | 2    | DispelMyth  | 34974574   | ...        |     |

    Each day adds a new column. Member rows are matched by name.
    Applies name aliases before matching to handle player renames.
    Uses a single batch update to avoid API rate limits.

    Args:
        kill_data: List of dicts with 'rank', 'name', 'kills' keys
        date_str: Date string for the column header (default: today)
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    client = get_client()
    spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)
    worksheet = get_or_create_worksheet(spreadsheet, WORKSHEET_NAME)

    # Load name aliases
    aliases = get_aliases(spreadsheet)

    # Get all current data from the sheet
    all_values = worksheet.get_all_values()

    if not all_values:
        # Empty sheet - set up headers
        all_values = [["Rank", "Member Name"]]

    headers = all_values[0]

    # Check if today's date column already exists
    if date_str in headers:
        date_col_idx = headers.index(date_str)
        logger.info(f"Column for {date_str} already exists at column {date_col_idx + 1}")
    else:
        # Add new date column
        date_col_idx = len(headers)
        headers.append(date_str)
        logger.info(f"Adding new column for {date_str} at column {date_col_idx + 1}")

    # Build a map of existing member names to row indices (0-indexed in all_values)
    existing_members = {}
    for row_idx, row in enumerate(all_values[1:], start=1):  # Skip header
        if len(row) >= 2 and row[1]:
            existing_members[row[1]] = row_idx

    # Ensure all rows have enough columns
    num_cols = len(headers)
    for i, row in enumerate(all_values):
        while len(row) < num_cols:
            all_values[i].append("")

    # Update or add each member
    for entry in kill_data:
        raw_name = entry["name"]
        name = resolve_name(raw_name, aliases)  # Map to canonical name
        if name != raw_name:
            logger.info(f"  Alias applied: '{raw_name}' → '{name}'")
        rank = entry["rank"]
        kills = entry["kills"]

        if name in existing_members:
            row_idx = existing_members[name]
        else:
            # Add new row
            row_idx = len(all_values)
            all_values.append([""] * num_cols)
            existing_members[name] = row_idx

        # Set rank, name (canonical), and kill count
        all_values[row_idx][0] = rank
        all_values[row_idx][1] = name
        all_values[row_idx][date_col_idx] = kills

    # Convert any numeric strings back to integers so Sheets formats them as numbers
    for i, row in enumerate(all_values):
        for j, cell in enumerate(row):
            if isinstance(cell, str) and cell.isdigit():
                all_values[i][j] = int(cell)

    # Write everything in a single batch update with RAW input to preserve number types
    range_str = f"A1:{_col_letter(num_cols)}{len(all_values)}"
    worksheet.update(range_str, all_values, value_input_option="RAW")

    logger.info(f"Updated {len(kill_data)} members for {date_str} (single batch write)")
    return len(kill_data)


def _col_letter(col_num: int) -> str:
    """Convert a column number (1-indexed) to a column letter (A, B, ..., Z, AA, ...)."""
    result = ""
    while col_num > 0:
        col_num, remainder = divmod(col_num - 1, 26)
        result = chr(65 + remainder) + result
    return result


def read_latest_data() -> dict:
    """Read the latest kill data from the sheet. Returns dict of name -> kills."""
    client = get_client()
    spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)
    worksheet = get_or_create_worksheet(spreadsheet, WORKSHEET_NAME)

    all_values = worksheet.get_all_values()
    if len(all_values) < 2:
        return {}

    headers = all_values[0]
    if len(headers) < 3:
        return {}

    # Last date column
    last_col_idx = len(headers) - 1
    result = {}
    for row in all_values[1:]:
        if len(row) >= 2 and row[1]:
            name = row[1]
            kills = int(row[last_col_idx]) if len(row) > last_col_idx and row[last_col_idx] else 0
            result[name] = kills

    return result


def write_weekly_summary():
    """
    Generate a weekly summary on the 'Weekly Summary' worksheet.
    Compares the latest data column with the one from ~7 days ago.
    Shows: Member Name, Kills (Start), Kills (End), Delta, % Increase.
    Sorted by highest percentage increase.
    """
    client = get_client()
    spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)
    worksheet = get_or_create_worksheet(spreadsheet, WORKSHEET_NAME)

    all_values = worksheet.get_all_values()
    if len(all_values) < 2:
        logger.warning("Not enough data for weekly summary")
        return

    headers = all_values[0]
    # Find date columns (skip Rank and Member Name)
    date_cols = [(i, h) for i, h in enumerate(headers) if i >= 2 and h]

    if len(date_cols) < 2:
        logger.warning("Need at least 2 days of data for a weekly summary")
        return

    # Use the latest column and find the oldest column within ~7 days
    latest_col_idx, latest_date = date_cols[-1]

    # Find the column closest to 7 days ago
    from datetime import timedelta
    try:
        latest_dt = datetime.strptime(latest_date, "%Y-%m-%d")
    except ValueError:
        logger.error(f"Cannot parse date: {latest_date}")
        return

    target_dt = latest_dt - timedelta(days=7)
    best_col_idx = date_cols[0][0]  # Default to oldest
    best_date = date_cols[0][1]
    best_diff = float("inf")

    for col_idx, date_str in date_cols[:-1]:  # Exclude latest
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            diff = abs((dt - target_dt).days)
            if diff < best_diff:
                best_diff = diff
                best_col_idx = col_idx
                best_date = date_str
        except ValueError:
            continue

    logger.info(f"Weekly summary: comparing {best_date} → {latest_date}")

    # Build summary data
    summary_rows = []
    for row in all_values[1:]:
        if len(row) < 2 or not row[1]:
            continue

        name = row[1]
        try:
            kills_start = int(row[best_col_idx]) if len(row) > best_col_idx and row[best_col_idx] else 0
            kills_end = int(row[latest_col_idx]) if len(row) > latest_col_idx and row[latest_col_idx] else 0
        except (ValueError, TypeError):
            continue

        delta = kills_end - kills_start
        pct_increase = (delta / kills_start * 100) if kills_start > 0 else 0

        summary_rows.append({
            "name": name,
            "kills_start": kills_start,
            "kills_end": kills_end,
            "delta": delta,
            "pct_increase": round(pct_increase, 2),
        })

    # Sort by percentage increase (highest first)
    summary_rows.sort(key=lambda x: x["pct_increase"], reverse=True)

    # Build the summary sheet
    week_label = f"Week {best_date} → {latest_date}"
    summary_ws_name = "Weekly Summary"

    try:
        summary_ws = spreadsheet.worksheet(summary_ws_name)
    except gspread.WorksheetNotFound:
        summary_ws = spreadsheet.add_worksheet(title=summary_ws_name, rows=200, cols=20)

    # Build the data grid
    summary_data = [
        [week_label, "", "", "", ""],
        ["Rank", "Member Name", f"Kills ({best_date})", f"Kills ({latest_date})", "Kills Gained", "% Increase"],
    ]

    for i, entry in enumerate(summary_rows, start=1):
        summary_data.append([
            i,
            entry["name"],
            entry["kills_start"],
            entry["kills_end"],
            entry["delta"],
            entry["pct_increase"],
        ])

    # Write in a single batch
    range_str = f"A1:{_col_letter(6)}{len(summary_data)}"
    summary_ws.clear()
    summary_ws.update(range_str, summary_data, value_input_option="RAW")

    logger.info(f"Weekly summary written: {len(summary_rows)} members, period: {week_label}")
    return summary_rows


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Test with sample data
    sample_data = [
        {"rank": 1, "name": "Ercimus", "kills": 35167068},
        {"rank": 2, "name": "DispelTheMyth", "kills": 34974574},
        {"rank": 3, "name": "MATHIS", "kills": 22963426},
    ]

    print("Writing sample data to Google Sheets...")
    count = write_kill_data(sample_data)
    print(f"Updated {count} members")

