"""
Last War Kill Tracker - Screenshot Analyzer Module
Uses Google Gemini Vision API to extract member kill data from screenshots.
"""
import json
import logging
from typing import Optional

import google.genai as genai
from google.genai import types
from PIL import Image

from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

# Prompt for Gemini to extract kill data from screenshots
EXTRACTION_PROMPT = """Analyze this screenshot from the game "Last War: Survival Game". 
It shows a leaderboard/ranking of alliance members with their kill counts.

Each row contains:
- A rank number (1, 2, 3, etc.)
- A player avatar image
- A role badge (R3, R4, R5, etc.)
- A player name
- A kill count (large number on the right)

Extract ALL visible player entries and return them as a JSON array. 
Each entry should have:
- "rank": the rank number (integer)
- "name": the player's name (string, preserve exact spelling including special characters)
- "kills": the kill count (integer, no commas)

IMPORTANT:
- Include EVERY visible row, including the green highlighted row at the bottom (that's the user's own rank).
- Read the numbers carefully - they are large numbers with many digits.
- If a name contains non-Latin characters (Korean, Chinese, etc.), include them exactly.
- Return ONLY the JSON array, no other text.

Example output format:
[
  {"rank": 1, "name": "PlayerOne", "kills": 35167068},
  {"rank": 2, "name": "PlayerTwo", "kills": 34974574}
]"""

MULTI_SCREENSHOT_PROMPT = """Analyze these screenshots from the game "Last War: Survival Game".
They show different portions of a scrollable leaderboard/ranking of alliance members with their kill counts.
The screenshots were taken in sequence by scrolling down, so there may be overlapping entries between screenshots.

Each row contains:
- A rank number (1, 2, 3, etc.)
- A player avatar image
- A role badge (R3, R4, R5, etc.)
- A player name
- A kill count (large number on the right)

Extract ALL unique player entries across all screenshots and return them as a JSON array.
DEDUPLICATE entries that appear in multiple screenshots (use the rank number to identify duplicates).
Each entry should have:
- "rank": the rank number (integer)
- "name": the player's name (string, preserve exact spelling including special characters)
- "kills": the kill count (integer, no commas)

IMPORTANT:
- Include EVERY visible row from all screenshots.
- The green highlighted row at the bottom of each screenshot is the user's own rank - include it only ONCE.
- Read the numbers carefully - they are large numbers with many digits.
- If a name contains non-Latin characters (Korean, Chinese, etc.), include them exactly.
- Sort the output by rank number ascending.
- Return ONLY the JSON array, no other text.

Example output format:
[
  {"rank": 1, "name": "PlayerOne", "kills": 35167068},
  {"rank": 2, "name": "PlayerTwo", "kills": 34974574}
]"""


def get_client():
    """Create and return a Gemini API client."""
    if not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY is not set. "
            "Set it in your .env file or config.py"
        )
    return genai.Client(api_key=GEMINI_API_KEY)


def analyze_single_screenshot(image_path: str) -> list[dict]:
    """
    Analyze a single screenshot and extract kill data.

    Args:
        image_path: Path to the screenshot file

    Returns:
        List of dicts with 'rank', 'name', 'kills' keys
    """
    client = get_client()
    image = Image.open(image_path)

    logger.info(f"Analyzing screenshot: {image_path}")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[EXTRACTION_PROMPT, image],
    )

    return _parse_response(response.text)


def analyze_multiple_screenshots(image_paths: list[str]) -> list[dict]:
    """
    Analyze multiple screenshots and extract deduplicated kill data.

    Args:
        image_paths: List of paths to screenshot files

    Returns:
        Sorted list of dicts with 'rank', 'name', 'kills' keys
    """
    if len(image_paths) == 1:
        return analyze_single_screenshot(image_paths[0])

    client = get_client()
    images = [Image.open(p) for p in image_paths]

    logger.info(f"Analyzing {len(images)} screenshots together...")
    content = [MULTI_SCREENSHOT_PROMPT] + images
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=content,
    )

    return _parse_response(response.text)


def _parse_response(response_text: str) -> list[dict]:
    """Parse the Gemini response text into structured data."""
    # Clean up the response - remove markdown code fences if present
    text = response_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Gemini response as JSON: {e}")
        logger.error(f"Raw response: {response_text}")
        return []

    # Validate and clean the data
    cleaned = []
    seen_ranks = set()
    for entry in data:
        try:
            rank = int(entry.get("rank", 0))
            name = str(entry.get("name", "")).strip()
            kills = int(entry.get("kills", 0))

            if rank > 0 and name and rank not in seen_ranks:
                cleaned.append({
                    "rank": rank,
                    "name": name,
                    "kills": kills
                })
                seen_ranks.add(rank)
        except (ValueError, TypeError) as e:
            logger.warning(f"Skipping invalid entry: {entry} ({e})")

    # Sort by rank
    cleaned.sort(key=lambda x: x["rank"])
    logger.info(f"Extracted {len(cleaned)} member entries")
    return cleaned


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print("Usage: python analyzer.py <screenshot1.png> [screenshot2.png ...]")
        sys.exit(1)

    paths = sys.argv[1:]
    if len(paths) == 1:
        results = analyze_single_screenshot(paths[0])
    else:
        results = analyze_multiple_screenshots(paths)

    print(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nTotal members found: {len(results)}")
