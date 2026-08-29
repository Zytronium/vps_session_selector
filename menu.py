#!/bin/python3
"""
menu.py
-------
Tmux session manager - reads and writes session data from a single JSON file.

Contains:
  - Key input primitives   (get_key, get_key_with_shift)
  - Menu rendering         (display_menu, arrow_menu)
  - Data helpers           (read_data, save_data)
  - Session management     (sync_sessions, attach_session, new_session, delete_session)
"""

import json
import os
import subprocess
import sys
import time
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
    # Clear the screen so this menu overwrites whatever was shown before
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()

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


# Session management helpers

def get_tmux_sessions() -> list[str]:
    """Return a list of currently active tmux session names.

    Returns:
        List of session name strings, or empty list if tmux has no sessions
        or is not running.
    """
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except FileNotFoundError:
        return []


def sync_sessions(data: list) -> list:
    """Sync data.json against live tmux sessions.

    - Adds entries for tmux sessions not already tracked (using the tmux name
      as both the key and display name).
    - Removes entries whose tmux session no longer exists.

    Args:
        data: Current list of single-key dicts from data.json.

    Returns:
        Updated list.
    """
    live = set(get_tmux_sessions())
    tracked = {list(entry.keys())[0]: list(entry.values())[0] for entry in data}

    # Drop sessions that are no longer alive
    synced = {k: v for k, v in tracked.items() if k in live}

    # Add sessions that tmux knows about but we don't
    for session_name in live:
        if session_name not in synced:
            synced[session_name] = session_name

    return [{k: v} for k, v in synced.items()]


def prompt_input(prompt: str) -> str:
    """Display a prompt and read a line of input with the terminal in normal mode.

    Args:
        prompt: Text to display before the cursor.

    Returns:
        The stripped string the user typed.
    """
    print(prompt, end="", flush=True)
    return input()


# Sub-menus

def attach_session(data: list) -> None:
    """Show a list of tracked sessions and attach to the chosen one."""
    if not data:
        print("\n  No sessions available.\n")
        time.sleep(1)
        return

    display_names = [list(entry.values())[0] for entry in data]
    tmux_names    = [list(entry.keys())[0]   for entry in data]
    options = display_names + ["← Back"]

    choice = arrow_menu("Attach Session", options)

    if choice is None or choice == len(display_names):
        return  # Esc or Back

    tmux_name = tmux_names[choice]
    os.execvp("tmux", ["tmux", "attach", "-t", tmux_name])


def shell_quote(value: str) -> str:
    """Return a shell-safe single-quoted string."""
    return "'" + value.replace("'", "'\"'\"'") + "'"


def create_persistent_session(
    tmux_name: str,
    display_name: str,
    working_directory: str,
    venv_command: str,
    startup_command: str,
) -> None:
    """Create configuration and systemd startup files for a persistent tmux session."""

    config_dir = Path("/etc/tmux-persistent/config")
    start_dir = Path("/etc/tmux-persistent/start")

    config_dir.mkdir(parents=True, exist_ok=True)
    start_dir.mkdir(parents=True, exist_ok=True)

    config_file = config_dir / f"{tmux_name}.conf"
    start_script = start_dir / f"{tmux_name}.sh"

    # Configuration consumed by start-session.sh
    config_file.write_text(
        f"SESSION_NAME={shell_quote(tmux_name)}\n"
        f"WORKING_DIRECTORY={shell_quote(working_directory)}\n"
        f"START_SCRIPT={shell_quote(str(start_script))}\n",
        encoding="utf-8",
    )

    # Startup script executed inside tmux
    start_script.write_text(
        "#!/bin/bash\n"
        "set -e\n"
        "\n"
        f"cd {shell_quote(working_directory)}\n"
        "\n"
        f"{venv_command}\n"
        "\n"
        "clear\n"
        f"exec {startup_command}\n",
        encoding="utf-8",
    )

    start_script.chmod(0o755)

    # Escape the session name for use as a systemd template instance.
    result = subprocess.run(
        ["systemd-escape", "--template=tmux-persistent@.service", tmux_name],
        capture_output=True,
        text=True,
        check=True,
    )

    service_name = result.stdout.strip()

    subprocess.run(
        ["systemctl", "daemon-reload"],
        check=True,
    )

    subprocess.run(
        ["systemctl", "enable", "--now", service_name],
        check=True,
    )


def new_session(data: list) -> list:
    """Prompt for a persistent tmux session and create it.

    Args:
        data: Current session list.

    Returns:
        Updated session list with the new entry appended.
    """

    print()

    tmux_name = prompt_input("  Tmux session name   : ").strip()
    display_name = prompt_input("  Display name        : ").strip()
    working_directory = prompt_input("  Working directory   : ").strip()
    venv_command = prompt_input("  Venv activation     : ").strip()
    startup_command = prompt_input("  Startup command     : ").strip()

    if not tmux_name:
        print("\n  Aborted - session name cannot be empty.\n")
        time.sleep(1.2)
        return data

    if not display_name:
        display_name = tmux_name

    if not working_directory:
        print("\n  Aborted - working directory cannot be empty.\n")
        time.sleep(1.2)
        return data

    if not startup_command:
        print("\n  Aborted - startup command cannot be empty.\n")
        time.sleep(1.2)
        return data

    if tmux_name in get_tmux_sessions():
        print(f"\n  Aborted - tmux session '{tmux_name}' already exists.\n")
        time.sleep(1.2)
        return data

    try:
        create_persistent_session(
            tmux_name=tmux_name,
            display_name=display_name,
            working_directory=working_directory,
            venv_command=venv_command,
            startup_command=startup_command,
        )
    except subprocess.CalledProcessError as e:
        print(f"\n  Could not create systemd service: {e}\n")
        time.sleep(2)
        return data

    data.append({tmux_name: display_name})
    save_data(data)

    print(f"\n  Created persistent session '{display_name}'.")
    print("  It will automatically restart after a reboot or crash.\n")
    time.sleep(2)

    return data


def delete_session(data: list) -> list:
    """Permanently delete a persistent tmux session.

    Stops and disables its systemd service, kills the tmux session,
    removes its persistent configuration/startup files, and removes
    the session from data.json.
    """
    if not data:
        print("\n  No sessions to delete.\n")
        time.sleep(1)
        return data

    display_names = [list(entry.values())[0] for entry in data]
    tmux_names    = [list(entry.keys())[0]   for entry in data]
    options = display_names + ["← Back"]

    choice = arrow_menu("Delete Session", options)

    if choice is None or choice == len(display_names):
        return data  # Esc or Back

    tmux_name    = tmux_names[choice]
    display_name = display_names[choice]

    try:
        # Determine the systemd service name using the same escaping
        # mechanism used when creating the service.
        result = subprocess.run(
            [
                "systemd-escape",
                "--template=tmux-persistent@.service",
                tmux_name,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        service_name = result.stdout.strip()

        # Stop and disable the persistent service first. This prevents
        # systemd from recreating the tmux session after we kill it.
        subprocess.run(
            ["systemctl", "disable", "--now", service_name],
            check=True,
        )

        # Kill the tmux session if it still exists.
        subprocess.run(
            ["tmux", "kill-session", "-t", tmux_name],
            capture_output=True,
            text=True,
        )

        # Remove the generated persistence files.
        config_file = Path("/etc/tmux-persistent/config") / f"{tmux_name}.conf"
        start_script = Path("/etc/tmux-persistent/start") / f"{tmux_name}.sh"

        config_file.unlink(missing_ok=True)
        start_script.unlink(missing_ok=True)

        print(f"\n  Deleted persistent session '{display_name}'.\n")

    except subprocess.CalledProcessError as e:
        print(
            f"\n  Could not delete '{display_name}': "
            f"{e.stderr.strip() if e.stderr else e}\n"
        )
        time.sleep(2)
        return data

    time.sleep(1)

    updated = [e for e in data if list(e.keys())[0] != tmux_name]
    save_data(updated)
    return updated


# Main entry point

def main():
    data = read_data() or []
    data = sync_sessions(data)
    save_data(data)

    main_options = ["Attach Session", "New Session", "Delete Session", "Exit"]

    while True:
        choice = arrow_menu("Tmux Session Manager", main_options)

        if choice is None or choice == 3:   # Esc or Exit
            print("\n  Goodbye.\n")
            sys.exit(0)

        elif choice == 0:  # Attach Session
            attach_session(data)

        elif choice == 1:  # New Session
            data = new_session(data)

        elif choice == 2:  # Delete Session
            data = delete_session(data)

        # Re-sync after returning from any sub-menu (attach replaces the
        # process, so we only get here from new/delete or if attach failed)
        data = sync_sessions(data)
        save_data(data)


if __name__ == "__main__":
    main()

# LOGIC FLOW:
# - Update data.json by running tmux list-sessions and adding sessions not in dat.json and deleting sessions not listed in output
# - Display menu; options:
#   - "Attach Session"
#   - "New Session"
#   - "Delete Session"
#   - "Exit"
# - on "Attach Session":
#   - List sessions from data.json (use display name)
#   - On select, run `tmux attach -t <tmux session name>`
#   - On selecting "Exit", go back to main menu
# - on "New Session":
#   - Ask for session name and display name
#   - Save to data.json
#   - Display message "Press Ctrl + B, then D to detach." for 2 seconds
#   - run `tmux new -s <tmux session name>`
#   - On selecting "Exit", go back to main menu
# - on "Delete Session":
#   - List sessions from data.json
#   - On select, run `tmux kill-session -t <tmux session name>`
# - on "Exit"
#   - Exit app