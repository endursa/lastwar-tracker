"""
Last War Kill Tracker - Screenshot Capture Module
Handles capturing screenshots of the game window, including scrolling
to capture the full leaderboard.
"""
import os
import time
import logging
from datetime import datetime

import mss
import mss.tools
import pyautogui
from PIL import Image

from config import SCREENSHOTS_DIR, SCROLL_WAIT_SECONDS

logger = logging.getLogger(__name__)


def capture_full_screen(filename=None):
    """Capture a full-screen screenshot."""
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.png"

    filepath = os.path.join(SCREENSHOTS_DIR, filename)

    with mss.mss() as sct:
        monitor = sct.monitors[1]  # Primary monitor
        screenshot = sct.grab(monitor)
        mss.tools.to_png(screenshot.rgb, screenshot.size, output=filepath)

    logger.info(f"Screenshot saved: {filepath}")
    return filepath


def capture_window(window, filename=None):
    """Capture a screenshot of a specific window."""
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.png"

    filepath = os.path.join(SCREENSHOTS_DIR, filename)

    # Get window position and size
    region = {
        "left": window.left,
        "top": window.top,
        "width": window.width,
        "height": window.height
    }

    with mss.mss() as sct:
        screenshot = sct.grab(region)
        mss.tools.to_png(screenshot.rgb, screenshot.size, output=filepath)

    logger.info(f"Window screenshot saved: {filepath}")
    return filepath


def capture_leaderboard_with_scrolling(window, num_scrolls=10, scroll_amount=-15):
    """
    Capture multiple screenshots of the leaderboard by scrolling down.
    The kill leaderboard in Last War is scrollable, so we need to:
    1. Capture the current view
    2. Scroll down
    3. Capture again
    4. Repeat until we've captured enough

    Args:
        window: The game window object
        num_scrolls: Number of times to scroll (adjust based on alliance size)
        scroll_amount: How much to scroll each time (negative = down)

    Returns:
        List of screenshot file paths
    """
    screenshots = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Focus the game window
    try:
        window.activate()
        time.sleep(1)
    except Exception as e:
        logger.warning(f"Could not activate window: {e}")

    # Move mouse to center of the game window (for scrolling)
    center_x = window.left + window.width // 2
    center_y = window.top + window.height // 2
    pyautogui.moveTo(center_x, center_y)
    time.sleep(0.5)

    # Capture initial view (top of leaderboard)
    filename = f"leaderboard_{timestamp}_page0.png"
    filepath = capture_window(window, filename)
    screenshots.append(filepath)
    logger.info(f"Captured page 0 (top of leaderboard)")

    # Scroll and capture
    for i in range(num_scrolls):
        # Scroll down
        pyautogui.scroll(scroll_amount, center_x, center_y)
        time.sleep(SCROLL_WAIT_SECONDS)

        # Capture after scrolling
        filename = f"leaderboard_{timestamp}_page{i + 1}.png"
        filepath = capture_window(window, filename)
        screenshots.append(filepath)
        logger.info(f"Captured page {i + 1} after scroll")

    logger.info(f"Captured {len(screenshots)} leaderboard screenshots total")
    return screenshots


def stitch_screenshots_vertically(image_paths, output_filename=None):
    """
    Combine multiple screenshots into one tall image for easier analysis.
    """
    if output_filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"leaderboard_combined_{timestamp}.png"

    output_path = os.path.join(SCREENSHOTS_DIR, output_filename)

    images = [Image.open(p) for p in image_paths]

    total_width = max(img.width for img in images)
    total_height = sum(img.height for img in images)

    combined = Image.new("RGB", (total_width, total_height))
    y_offset = 0
    for img in images:
        combined.paste(img, (0, y_offset))
        y_offset += img.height

    combined.save(output_path)
    logger.info(f"Combined screenshot saved: {output_path}")
    return output_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Capturing full screen screenshot...")
    path = capture_full_screen()
    print(f"Saved to: {path}")
