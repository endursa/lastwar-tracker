"""
Last War Kill Tracker - Navigation Calibration Tool
Run this script to record the click positions for navigating to the kill leaderboard.
It will ask you to click on each button in sequence and save the coordinates.
"""
import json
import os
import time
import pyautogui

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nav_config.json")

STEPS = [
    {
        "id": "dismiss_screen",
        "description": "anywhere on the INITIAL SCREEN to dismiss it",
    },
    {
        "id": "alliance_icon",
        "description": "the ALLIANCE ICON on the main game screen",
    },
    {
        "id": "strength_ranking",
        "description": "the STRENGTH RANKING button/tab",
    },
    {
        "id": "kills_tab",
        "description": "the KILLS TAB on the ranking screen",
    },
]


def calibrate():
    print("=" * 50)
    print("  Last War - Navigation Calibration Tool")
    print("=" * 50)
    print()
    print("This tool will record the click positions for")
    print("navigating to the kill leaderboard.")
    print()
    print("INSTRUCTIONS:")
    print("  1. Make sure the game is open and visible")
    print("  2. For each step, you have 5 seconds to")
    print("     hover your mouse over the target button")
    print("  3. The position will be recorded automatically")
    print()
    input("Press Enter when the game is open and ready...")
    print()

    positions = {}

    for step in STEPS:
        print(f"Step: Click on {step['description']}")
        print("  -> Move your mouse to that button NOW...")
        print("  -> Recording position in: ", end="", flush=True)

        for i in range(5, 0, -1):
            print(f"{i}...", end="", flush=True)
            time.sleep(1)

        x, y = pyautogui.position()
        positions[step["id"]] = {"x": x, "y": y}
        print(f"\n  -> Recorded position: ({x}, {y})")
        print()

        # Actually click it to proceed to next screen
        print("  -> Clicking now and waiting for screen to load...")
        pyautogui.click(x, y)
        time.sleep(3)

    # Save positions to file
    with open(CONFIG_FILE, "w") as f:
        json.dump(positions, f, indent=2)

    print()
    print("=" * 50)
    print("  Calibration Complete!")
    print("=" * 50)
    print()
    print(f"Saved positions to: {CONFIG_FILE}")
    print()
    print("Recorded positions:")
    for step in STEPS:
        pos = positions[step["id"]]
        print(f"  {step['description']}: ({pos['x']}, {pos['y']})")
    print()
    print("You can re-run this tool anytime if the game")
    print("window position changes.")


if __name__ == "__main__":
    calibrate()
