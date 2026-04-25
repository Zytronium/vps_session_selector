#!/bin/python3
"""
menu.py
-------
Tmux session manager - reads and writes session data from a single JSON file.

Contains:
  - Key input primitives   (get_key, get_key_with_shift)
  - Menu rendering         (display_menu, arrow_menu)
  - Data helpers           (read_data, save_data)
"""

import json
import os
import sys
from pathlib import Path


# Constants

_PRIMARY_DATA_PATH = Path("/root/sessions/data.json")
SESSION_DATA_PATH = _PRIMARY_DATA_PATH if _PRIMARY_DATA_PATH.exists() else Path("./data.json")


# Data helpers

def read_data() -> dict | None:
    """Load session data from SESSION_DATA_PATH.

    Returns:
        Parsed JSON dict, or None if the file does not exist.
    """
    if not SESSION_DATA_PATH.exists():
        return None

    with SESSION_DATA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data: dict) -> None:
    """Persist session data to SESSION_DATA_PATH.

    Args:
        data: The session dict to serialise.
    """
    SESSION_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)

    with SESSION_DATA_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


# Key input

def get_key() -> str | None:
    """Block until a keypress and return a token.

    Returns:
        'up', 'down', 'enter', 'esc', a lowercase character, or None.
    """
    if os.name == "nt":
        import msvcrt
        key = msvcrt.getch()
        if key in (b"\xe0", b"\x00"):
            key = msvcrt.getch()
            if key == b"H": return "up"
            if key == b"P": return "down"
        elif key == b"\r":   return "enter"
        elif key == b"\x1b": return "esc"
        else:
            try:    return key.decode("utf-8").lower()
            except: return None

    else:
        import termios, tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                ch2 = sys.stdin.read(1)
                if ch2 == "[":
                    ch3 = sys.stdin.read(1)
                    if ch3 == "A": return "up"
                    if ch3 == "B": return "down"
                return "esc"
            if ch in ("\n", "\r"): return "enter"
            return ch.lower()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


def get_key_with_shift() -> tuple[str | None, bool]:
    """Block until a keypress and detect whether Shift was held.

    Returns:
        (token, is_shift) - token matches get_key(); is_shift is True for uppercase letters.
    """
    if os.name == "nt":
        import msvcrt
        key = msvcrt.getch()
        if key in (b"\xe0", b"\x00"):
            key = msvcrt.getch()
            if key == b"H": return "up",    False
            if key == b"P": return "down",  False
        elif key == b"\r":   return "enter", False
        elif key == b"\x1b": return "esc",   False
        else:
            try:
                char = key.decode("utf-8")
                return char.lower(), char.isupper()
            except:
                return None, False

    else:
        import termios, tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                ch2 = sys.stdin.read(1)
                if ch2 == "[":
                    ch3 = sys.stdin.read(1)
                    if ch3 == "A": return "up",    False
                    if ch3 == "B": return "down",  False
                return "esc", False
            if ch in ("\n", "\r"): return "enter", False
            return ch.lower(), ch.isupper()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    return None, False


# Menu rendering

def _menu_height(options: list[str]) -> int:
    """Number of lines the menu occupies (title + options + hint)."""
    return 1 + len(options) + 1


def display_menu(
    title: str,
    options: list[str],
    selected_index: int,
    first_draw: bool = False,
) -> None:
    """Draw (or redraw in-place) a menu without touching anything above it.

    On the first draw the lines are simply printed. On every subsequent call
    the cursor is moved up by exactly the menu height and each line is
    overwritten.

    Args:
        title:          Heading on the first line of the menu.
        options:        Sequence of option labels.
        selected_index: Index of the currently highlighted entry.
        first_draw:     Pass True the very first time to skip the cursor-up move.
    """
    out = sys.stdout

    if not first_draw:
        # Move the cursor up to the top of the menu area
        out.write(f"\033[{_menu_height(options)}A")

    # Title line
    out.write(f"\033[2K\r  {title}\n")

    # Option lines
    for i, option in enumerate(options):
        prefix = "> " if i == selected_index else "  "
        out.write(f"\033[2K\r  {prefix}{option}\n")

    # Hint line
    out.write("\033[2K\r  ↑/↓ navigate · Enter select · Esc cancel\n")

    out.flush()


def arrow_menu(title: str, options: list[str]) -> int | None:
    """Interactive in-place arrow-key menu.

    Prints the menu once, then redraws only the menu lines on each keypress.
    Everything printed above is left untouched.

    Args:
        title:   Heading displayed on the first line of the menu.
        options: Sequence of option labels.

    Returns:
        The zero-based index of the selected option, or None if Esc was pressed.
    """
    selected = 0
    display_menu(title, options, selected, first_draw=True)

    while True:
        key = get_key()

        if key == "up":
            selected = (selected - 1) % len(options)
        elif key == "down":
            selected = (selected + 1) % len(options)
        elif key == "enter":
            return selected
        elif key == "esc":
            return None

        display_menu(title, options, selected)

# Main entry point
def main():
    print("Session data path:", SESSION_DATA_PATH)
    data = read_data()
    print("Loaded:", data)

if __name__ == "__main__":
    main()
