"""
Last War Kill Tracker - Main Orchestrator
Runs the complete kill tracking pipeline:
1. Launch the game
2. Navigate to the kill leaderboard
3. Capture screenshots (scrolling through the list)
4. Extract kill data using Gemini Vision
5. Write data to Google Sheets
6. Optionally close the game
"""
import os
import sys
import time
import logging
import argparse
from datetime import datetime

from config import GAME_LOAD_WAIT_SECONDS
from launcher import launch_game, close_game, find_game_window, is_game_running
from capture import capture_leaderboard_with_scrolling, capture_full_screen
from analyzer import analyze_multiple_screenshots, analyze_single_screenshot
from sheets import write_kill_data, write_weekly_summary

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            f"lastwar_tracker_{datetime.now().strftime('%Y%m%d')}.log",
            encoding="utf-8"
        ),
    ],
)
logger = logging.getLogger("main")


def navigate_to_kill_leaderboard(window):
    """
    Navigate from the game's main screen to the kill leaderboard.
    Uses saved click positions from nav_config.json (created by calibrate.py).

    Navigation path: Alliance Icon → Strength Ranking → Kills Tab
    """
    import pyautogui
    import json

    nav_config_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "nav_config.json"
    )

    if not os.path.exists(nav_config_path):
        logger.error(
            "Navigation config not found! Run 'python calibrate.py' first "
            "to record button positions."
        )
        logger.info("Waiting 10s assuming you'll navigate manually...")
        time.sleep(10)
        return

    with open(nav_config_path, "r") as f:
        positions = json.load(f)

    # Step sequence with wait times
    steps = [
        ("dismiss_screen", "Dismissing initial screen...", 5),
        ("alliance_icon", "Clicking Alliance icon...", 5),
        ("strength_ranking", "Clicking Strength Ranking...", 5),
        ("kills_tab", "Clicking Kills tab...", 3),
    ]

    # First, make sure the window is focused
    try:
        window.activate()
        time.sleep(2)
    except Exception as e:
        logger.warning(f"Could not activate window: {e}")

    for step_id, description, wait_time in steps:
        if step_id not in positions:
            logger.error(f"Missing position for '{step_id}' in nav_config.json")
            continue

        pos = positions[step_id]
        x, y = pos["x"], pos["y"]
        logger.info(f"  {description} at ({x}, {y})")
        pyautogui.click(x, y)
        time.sleep(wait_time)

    logger.info("Navigation complete - should be on kill leaderboard now")
    time.sleep(2)  # Extra wait for the leaderboard to fully render



def run_tracker(
    skip_launch: bool = False,
    skip_navigate: bool = False,
    num_scrolls: int = 6,
    close_after: bool = True,
    test_mode: bool = False,
):
    """
    Run the full kill tracking pipeline.

    Args:
        skip_launch: If True, assume the game is already running
        skip_navigate: If True, assume we're already on the leaderboard
        num_scrolls: Number of scroll captures to take
        close_after: If True, close the game after capturing
        test_mode: If True, only capture and analyze, don't write to Sheets
    """
    logger.info("=" * 60)
    logger.info("Last War Kill Tracker - Starting run")
    logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # Step 1: Launch or find the game
    window = None
    if not skip_launch:
        logger.info("Step 1: Launching game...")
        window = launch_game()
        if not window:
            logger.error("Failed to find game window. Trying full screen capture...")
    else:
        logger.info("Step 1: Skipping launch, looking for existing game window...")
        window = find_game_window()
        if not window:
            logger.warning("Game window not found. Will capture full screen.")

    # Step 2: Navigate to the kill leaderboard
    if not skip_navigate and window:
        logger.info("Step 2: Navigating to kill leaderboard...")
        navigate_to_kill_leaderboard(window)
    else:
        logger.info("Step 2: Skipping navigation (assuming leaderboard is visible)")

    # Step 3: Capture screenshots
    logger.info("Step 3: Capturing leaderboard screenshots...")
    if window:
        screenshots = capture_leaderboard_with_scrolling(
            window, num_scrolls=num_scrolls
        )
    else:
        # Fallback: single full-screen capture
        path = capture_full_screen()
        screenshots = [path]

    logger.info(f"Captured {len(screenshots)} screenshots")

    # Step 4: Analyze screenshots
    logger.info("Step 4: Analyzing screenshots with Gemini Vision...")
    kill_data = analyze_multiple_screenshots(screenshots)

    if not kill_data:
        logger.error("No kill data extracted! Check screenshots and API key.")
        return False

    logger.info(f"Extracted {len(kill_data)} members:")
    for entry in kill_data:
        logger.info(
            f"  #{entry['rank']:>3} {entry['name']:<25} {entry['kills']:>12,}"
        )

    # Step 5: Write to Google Sheets
    if not test_mode:
        logger.info("Step 5: Writing data to Google Sheets...")
        try:
            count = write_kill_data(kill_data)
            logger.info(f"Successfully wrote {count} entries to Google Sheets")
        except Exception as e:
            logger.error(f"Failed to write to Google Sheets: {e}")
            # Save data locally as backup
            backup_file = f"backup_kills_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            import json
            with open(backup_file, "w", encoding="utf-8") as f:
                json.dump(kill_data, f, ensure_ascii=False, indent=2)
            logger.info(f"Backup saved to: {backup_file}")
    else:
        logger.info("Step 5: Test mode - skipping Google Sheets write")

    # Step 6: Close the game (optional)
    if close_after and not skip_launch:
        logger.info("Step 6: Closing game...")
        close_game()
    else:
        logger.info("Step 6: Leaving game running")

    logger.info("=" * 60)
    logger.info("Kill tracking run complete!")
    logger.info("=" * 60)
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Last War Kill Tracker - Track alliance member kills"
    )
    parser.add_argument(
        "--skip-launch", action="store_true",
        help="Skip launching the game (assume it's already running)"
    )
    parser.add_argument(
        "--skip-navigate", action="store_true",
        help="Skip navigation (assume leaderboard is already visible)"
    )
    parser.add_argument(
        "--scrolls", type=int, default=6,
        help="Number of scroll captures (default: 6)"
    )
    parser.add_argument(
        "--keep-open", action="store_true",
        help="Don't close the game after capturing"
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Test mode - capture and analyze only, don't write to Sheets"
    )
    parser.add_argument(
        "--analyze-only", nargs="+", metavar="IMAGE",
        help="Skip capture, analyze existing screenshot files"
    )
    parser.add_argument(
        "--weekly-summary", action="store_true",
        help="Generate weekly summary (compare kills over past 7 days)"
    )

    args = parser.parse_args()

    # Special mode: analyze existing screenshots
    if args.analyze_only:
        import glob
        # Expand glob patterns (Windows doesn't auto-expand wildcards)
        image_files = []
        for pattern in args.analyze_only:
            expanded = glob.glob(pattern)
            if expanded:
                image_files.extend(expanded)
            else:
                image_files.append(pattern)  # Use as-is if no glob match

        if not image_files:
            logger.error("No image files found!")
            return

        logger.info(f"Analyze-only mode: processing {len(image_files)} screenshots")
        kill_data = analyze_multiple_screenshots(image_files)
        if kill_data:
            import json
            print(json.dumps(kill_data, indent=2, ensure_ascii=False))
            print(f"\nTotal members: {len(kill_data)}")
            if not args.test:
                write_kill_data(kill_data)
                print("Data written to Google Sheets!")
        return

    # Weekly summary only mode
    if args.weekly_summary and args.skip_launch:
        logger.info("Generating weekly summary from existing data...")
        write_weekly_summary()
        print("Weekly summary written to Google Sheets!")
        return

    # Normal mode: full pipeline
    success = run_tracker(
        skip_launch=args.skip_launch,
        skip_navigate=args.skip_navigate,
        num_scrolls=args.scrolls,
        close_after=not args.keep_open,
        test_mode=args.test,
    )

    # Generate weekly summary if requested
    if args.weekly_summary and success:
        logger.info("Generating weekly summary...")
        write_weekly_summary()
        logger.info("Weekly summary written to Google Sheets!")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
