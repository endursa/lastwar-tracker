"""
Last War Kill Tracker - Game Launcher Module
Handles launching the Last War game and waiting for it to be ready.
"""
import subprocess
import time
import logging

import pygetwindow as gw

from config import GAME_EXE_PATH, GAME_LOAD_WAIT_SECONDS

logger = logging.getLogger(__name__)


def find_game_window():
    """Find the Last War game window."""
    keywords = ["Last War", "LastWar", "last war"]
    for window in gw.getAllWindows():
        for keyword in keywords:
            if keyword.lower() in window.title.lower():
                return window
    return None


def is_game_running():
    """Check if the game is already running."""
    return find_game_window() is not None


def launch_game():
    """
    Launch the Last War game and wait for it to load.
    Returns the game window object if found, None otherwise.
    """
    if is_game_running():
        logger.info("Game is already running.")
        window = find_game_window()
        if window:
            try:
                window.activate()
                time.sleep(2)
            except Exception as e:
                logger.warning(f"Could not activate window: {e}")
        return window

    logger.info(f"Launching game from: {GAME_EXE_PATH}")
    try:
        subprocess.Popen(
            [GAME_EXE_PATH],
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except FileNotFoundError:
        logger.error(f"Game executable not found at: {GAME_EXE_PATH}")
        return None
    except Exception as e:
        logger.error(f"Failed to launch game: {e}")
        return None

    logger.info(f"Waiting {GAME_LOAD_WAIT_SECONDS}s for game to load...")
    # Poll for the game window to appear
    start_time = time.time()
    window = None
    while time.time() - start_time < GAME_LOAD_WAIT_SECONDS:
        window = find_game_window()
        if window:
            logger.info(f"Game window found: '{window.title}'")
            break
        time.sleep(5)

    if not window:
        logger.warning("Game window not found after waiting. Proceeding anyway...")
        return None

    # Give extra time for the game content to fully render
    logger.info("Waiting additional 30s for game content to render...")
    time.sleep(30)

    try:
        window.activate()
        time.sleep(2)
    except Exception as e:
        logger.warning(f"Could not activate window: {e}")

    return window


def close_game():
    """Close the Last War game."""
    window = find_game_window()
    if window:
        try:
            window.close()
            logger.info("Game window closed.")
        except Exception as e:
            logger.warning(f"Could not close game window: {e}")
    else:
        logger.info("No game window found to close.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Launching game...")
    w = launch_game()
    if w:
        print(f"Game window: {w.title} at ({w.left}, {w.top}) size ({w.width}x{w.height})")
    else:
        print("Could not find game window.")
