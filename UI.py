import os
import sys
import platform
import time
import json
import re
import threading
import pyperclip
import webview

if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
    ASSET_DIR = getattr(sys, "_MEIPASS", APP_DIR)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    ASSET_DIR = APP_DIR
HOTKEY_LOG_PATH = os.path.join(APP_DIR, "hotkey_debug.log")
CONFIG_YAML_PATH = os.path.join(APP_DIR, "config.yaml")
LEGACY_CONFIG_PATH = os.path.join(APP_DIR, "config.json")
ICON_PATH = os.path.join(ASSET_DIR, "pngwing.com.ico")

# ---------------------------------------------------------
# Configuration Options
# ---------------------------------------------------------
AUTO_PASTE = True  # If True, automatically simulates Ctrl+V to paste the snippet on Enter
AUTO_PASTE_DELAY_MS = 80  # Small grace period after the launcher hides before pasting
START_WITH_WINDOWS = True  # If True, launches this utility automatically after Windows sign-in
START_HIDDEN_ON_WINDOWS_STARTUP = True  # If True, the startup launch runs quietly in the background
HOTKEY_DEBOUNCE_SECONDS = 0.35  # Prevents duplicate AltGr/Ctrl+Alt hotkey events from double-firing
SELECTION_CAPTURE_DELAY_MS = 180  # Wait for the creator hotkey to be released before copying
SELECTION_COPY_TIMEOUT_MS = 900  # Maximum time to wait for highlighted text to reach the clipboard
SELECTION_COPY_POLL_MS = 50  # Clipboard polling interval after sending Ctrl+C
SELECTION_HOTKEY_RELEASE_TIMEOUT_MS = 1200  # Avoid copying while AltGr/Ctrl/Alt from the trigger are still held
DEFAULT_CONFIG = {
    "snippet_directory": os.path.join(os.path.expanduser("~"), "Documents", "MarkStash"),
    "hotkey_launcher": "alt gr+m",
    "hotkey_creator": "alt gr+n",
    "run_at_startup": START_WITH_WINDOWS,
    "enable_pinning": True,
    "window_width": 1000,
    "window_height": 485,
    "theme_accent": "#7c8cff",
    "theme_background": "#101116",
    "theme_panel": "#171923",
    "theme_text": "#e7eaf3",
    "setup_complete": False,
}

# Global variables to handle PyWebView references cleanly across threads
web_window = None
creator_window = None
hotkey_manager = None

# ---------------------------------------------------------
# 1. Platform & Logging Utilities
# ---------------------------------------------------------

SYSTEM = platform.system().lower()


def log_event(message):
    """Writes diagnostic events to disk because background apps have no visible console."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    try:
        with open(HOTKEY_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def validate_hotkey_string(hotkey_string):
    """Raises ValueError if the keyboard library cannot parse this hotkey combo."""
    cleaned = normalize_hotkey_string(hotkey_string)
    if not cleaned:
        raise ValueError("Hotkey cannot be empty.")
    validate_hotkey_safety(cleaned)
    keyboard.parse_hotkey(cleaned)
    return cleaned


def normalize_hotkey_part(part):
    part = (part or "").strip().lower()
    aliases = {
        "control": "ctrl",
        "ctl": "ctrl",
        "win": "windows",
        "cmd": "windows",
        "meta": "windows",
        "super": "windows",
        "option": "alt",
        "altgr": "alt gr",
        "alt-gr": "alt gr",
        "escape": "esc",
        "return": "enter",
        "del": "delete",
    }
    return aliases.get(part, part)


def normalize_hotkey_string(hotkey_string):
    parts = [normalize_hotkey_part(p) for p in str(hotkey_string or "").replace("＋", "+").split("+")]
    parts = [p for p in parts if p]
    return "+".join(parts)


def validate_hotkey_safety(hotkey_string):
    """Rejects combinations that are too broad or likely to collide with Windows/app shortcuts."""
    hotkey_string = normalize_hotkey_string(hotkey_string)
    parts = [p.strip().lower() for p in hotkey_string.split("+") if p.strip()]
    modifiers = {p for p in parts if p in ("ctrl", "shift", "alt", "alt gr", "windows")}
    keys = [p for p in parts if p not in modifiers]
    reserved = {
        "ctrl+c", "ctrl+v", "ctrl+x", "ctrl+z", "ctrl+y", "ctrl+a", "ctrl+s", "ctrl+p",
        "alt+tab", "alt+f4", "ctrl+alt+delete", "ctrl+shift+esc",
        "windows+l", "windows+d", "windows+r", "windows+e",
    }
    normalized = "+".join(parts)
    if normalized in reserved:
        raise ValueError(f"'{hotkey_string}' is reserved by Windows or common apps.")
    if not keys:
        raise ValueError("Hotkey must include a non-modifier key.")
    if len(modifiers) == 0:
        raise ValueError("Hotkey must include at least one modifier.")
    if len(modifiers) == 1 and not (("alt gr" in modifiers) or keys[0].startswith("f")):
        raise ValueError("Use at least two modifiers, AltGr, or a function key to avoid accidental triggers.")
    if keys[0] in ("esc", "escape", "tab", "enter", "space", "backspace", "delete"):
        raise ValueError("Choose a letter, number, or function key instead of navigation/system keys.")


def get_hotkey_suggestions():
    return ["ctrl+shift+x", "ctrl+shift+b", "alt gr+m", "alt gr+n", "ctrl+alt+f8"]


def parse_scalar_config_value(value):
    value = value.strip()
    if not value:
        return ""
    if value[0] in ("'", '"') and value[-1:] == value[0]:
        return value[1:-1]
    lower = value.lower()
    if lower in ("true", "yes", "on"):
        return True
    if lower in ("false", "no", "off"):
        return False
    try:
        return int(value)
    except ValueError:
        return value


def read_flat_yaml_config(path):
    config = {}
    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, value = line.split(":", 1)
            config[key.strip()] = parse_scalar_config_value(value)
    return config


def format_yaml_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    text = str(value).replace('"', '\\"')
    return f'"{text}"'


def load_application_config():
    """Loads settings from config.yaml, migrating legacy config.json when present."""
    stored_config = {}
    if os.path.exists(CONFIG_YAML_PATH):
        try:
            stored_config = read_flat_yaml_config(CONFIG_YAML_PATH)
        except Exception as e:
            log_event(f"YAML config load failed; using defaults. Error={e}")
    elif os.path.exists(LEGACY_CONFIG_PATH):
        try:
            with open(LEGACY_CONFIG_PATH, "r", encoding="utf-8") as f:
                stored_config = json.load(f)
            stored_config.setdefault("setup_complete", True)
            save_application_config({**DEFAULT_CONFIG, **stored_config})
        except Exception as e:
            log_event(f"Legacy config load failed; using defaults. Error={e}")
    else:
        try:
            save_application_config(DEFAULT_CONFIG)
        except Exception as e:
            log_event(f"Config initialization failed; using defaults. Error={e}")

    config = DEFAULT_CONFIG.copy()
    if isinstance(stored_config, dict):
        config.update({
            key: stored_config[key]
            for key in DEFAULT_CONFIG
            if key in stored_config and stored_config[key] is not None and stored_config[key] != ""
        })

    for key in ("hotkey_launcher", "hotkey_creator"):
        try:
            config[key] = validate_hotkey_string(config[key])
        except Exception as e:
            log_event(f"Invalid hotkey '{config[key]}' for '{key}'; using default. Error={e}")
            config[key] = DEFAULT_CONFIG[key]

    config["window_width"] = clamp_int(config.get("window_width"), 420, 2400, 1000)
    config["window_height"] = clamp_int(config.get("window_height"), 320, 1600, 485)
    for key in ("theme_accent", "theme_background", "theme_panel", "theme_text"):
        config[key] = sanitize_hex_color(config.get(key), DEFAULT_CONFIG[key])
    config["snippet_directory"] = resolve_user_path(config.get("snippet_directory", DEFAULT_CONFIG["snippet_directory"]))

    return config


def save_application_config(config_data):
    """Writes updated configuration settings to config.yaml."""
    ordered_keys = list(DEFAULT_CONFIG.keys())
    extra_keys = [key for key in config_data if key not in ordered_keys]
    with open(CONFIG_YAML_PATH, "w", encoding="utf-8") as f:
        f.write("# MarkStash runtime configuration. Safe for developers to edit.\n")
        f.write("# Recommended hotkeys: ctrl+shift+x, ctrl+shift+b, alt gr+m, alt gr+n, ctrl+alt+f8.\n")
        for key in ordered_keys + extra_keys:
            if key in config_data:
                f.write(f"{key}: {format_yaml_value(config_data[key])}\n")
    return config_data


def clamp_int(value, min_value, max_value, fallback):
    try:
        return max(min_value, min(max_value, int(value)))
    except Exception:
        return fallback


def sanitize_hex_color(value, fallback):
    cleaned = str(value or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", cleaned):
        return cleaned.lower()
    return fallback


def resolve_user_path(path_value):
    return os.path.abspath(os.path.expandvars(os.path.expanduser(str(path_value or ""))))


def normalize_snippet_relative_path(filename):
    """Converts user input like python/math/add into a safe nested .md path."""
    raw_name = str(filename or "").strip().replace("\\", "/")
    raw_name = re.sub(r"/+", "/", raw_name).strip("/")
    if not raw_name:
        raise ValueError("Snippet name cannot be empty.")

    parts = []
    for part in raw_name.split("/"):
        clean_part = "".join(c for c in part if c.isalnum() or c in (" ", "-", "_", ".")).strip()
        clean_part = clean_part.strip(". ")
        if not clean_part or clean_part in (".", ".."):
            raise ValueError("Snippet path contains an invalid folder or filename.")
        parts.append(clean_part)

    leaf = parts[-1]
    if not leaf.lower().endswith(".md"):
        leaf += ".md"
    parts[-1] = leaf
    return os.path.join(*parts)


def ensure_path_inside_directory(base_dir, candidate_path):
    base_real = os.path.realpath(base_dir)
    candidate_real = os.path.realpath(candidate_path)
    if os.path.commonpath([base_real, candidate_real]) != base_real:
        raise ValueError("Snippet path escapes the snippet directory.")
    return candidate_real


if SYSTEM == 'linux' and os.geteuid() != 0:
    print("=" * 70, file=sys.stderr)
    print("ERROR: Root privileges required.", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    sys.exit(1)

try:
    import keyboard
except ImportError as e:
    sys.exit(1)


# ---------------------------------------------------------
# Kernel-Level Hardware Keyboard Helper for Windows
# ---------------------------------------------------------

def is_modifier_pressed(mod_name):
    """Queries kernel-level hardware state directly, bypassing virtual focus bugs."""
    if SYSTEM == "windows":
        try:
            import ctypes
            vk_map = {
                "ctrl": 0x11,      # VK_CONTROL
                "shift": 0x10,     # VK_SHIFT
                "alt": 0x12,       # VK_MENU
                "alt gr": 0x12,    # VK_MENU (handled as Ctrl+Alt combo)
                "windows": 0x5B,   # VK_LWIN
            }
            vk = vk_map.get(mod_name)
            if vk is not None:
                return (ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000) != 0
        except Exception:
            pass
            
    # Fallback to standard tracking on non-Windows platforms
    try:
        return keyboard.is_pressed(mod_name)
    except Exception:
        return False


def parse_hotkey_string(hotkey_str):
    """Parses hotkey string into modifiers and raw trigger key."""
    hotkey_str = normalize_hotkey_string(hotkey_str)
    parts = [p.strip().lower() for p in hotkey_str.split("+")]
    modifiers = []
    trigger_key = ""
    for p in parts:
        if p in ("ctrl", "shift", "alt", "alt gr", "windows"):
            modifiers.append(p)
        else:
            trigger_key = p
    return modifiers, trigger_key


def normalize_event_key(event_key):
    key = normalize_hotkey_part(event_key)
    key_aliases = {
        "page up": "pageup",
        "page down": "pagedown",
        "num enter": "enter",
    }
    return key_aliases.get(key, key)


def check_hotkey_match(event, hotkey_str):
    """Matches hardware modifier inputs against specified hotkey schema configurations."""
    if event.event_type != keyboard.KEY_DOWN:
        return False
        
    modifiers, trigger_key = parse_hotkey_string(hotkey_str)
    event_key = normalize_event_key(event.name or "")
    
    if event_key != trigger_key:
        return False
        
    all_mods = ["ctrl", "shift", "alt", "windows"]
    for mod in all_mods:
        if "alt gr" in modifiers:
            required = (mod in ("alt", "ctrl"))
        else:
            required = (mod in modifiers)
            
        if is_modifier_pressed(mod) != required:
            return False
            
    return True


def is_key_pressed_safely(key_name):
    try:
        return keyboard.is_pressed(key_name)
    except Exception:
        return False


def wait_for_hotkey_release(hotkey_str, timeout_ms=SELECTION_HOTKEY_RELEASE_TIMEOUT_MS):
    """Waits until the trigger hotkey is released before issuing Ctrl+C."""
    modifiers, trigger_key = parse_hotkey_string(hotkey_str)
    required_modifiers = set(modifiers)
    if "alt gr" in required_modifiers:
        required_modifiers.update(("ctrl", "alt"))

    deadline = time.monotonic() + (timeout_ms / 1000.0)
    while time.monotonic() < deadline:
        modifier_down = any(is_modifier_pressed(mod) for mod in required_modifiers if mod != "alt gr")
        trigger_down = is_key_pressed_safely(trigger_key) if trigger_key else False
        if not modifier_down and not trigger_down:
            return True
        time.sleep(0.025)
    return False


# ---------------------------------------------------------
# 2. Directory Watcher and File Scanning Logic
# ---------------------------------------------------------

class SnippetWatcher:
    def __init__(self, directory_path=None):
        if directory_path is None:
            directory_path = r"D:\Markdown Project Foler (DO NOT DELETE)"
            
        self.directory_path = os.path.abspath(directory_path)
        self.ensure_directory_exists()
        self.files = []
        self.scan_files()

    def ensure_directory_exists(self):
        """Creates the directory and populates sample files if empty."""
        if not os.path.exists(self.directory_path):
            try:
                os.makedirs(self.directory_path, exist_ok=True)
            except Exception as e:
                print(f"Warning: Could not create directory {self.directory_path}: {e}")
                
        if os.path.exists(self.directory_path):
            try:
                with os.scandir(self.directory_path) as entries:
                    has_files = any(entry.is_file() and entry.name.lower().endswith('.md') for entry in entries)
                
                if not has_files:
                    backticks = '`' * 3
                    samples = {
                        "welcome.md": "# Welcome to Snippets!\n\nThis is a sample markdown snippet. Select it and press Enter to copy.",
                        "python_template.md": f"{backticks}python\ndef main():\n    print(\"Hello from Antigravity!\")\n\nif __name__ == '__main__':\n    main()\n{backticks}",
                        "markdown_table.md": "| Feature | Supported |\n| --- | --- |\n| Global Hotkey | Yes |\n| Reactive Search | Yes |\n| Borderless UI | Yes |",
                        "react_hook.md": "import { useState, useEffect } from 'react';\n\nexport function useToggle(initialValue = false) {\n  const [value, setValue] = useState(initialValue);\n  const toggle = () => setValue(v => !v);\n  return [value, toggle];\n}"
                    }
                    for filename, content in samples.items():
                        file_path = os.path.join(self.directory_path, filename)
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(content)
            except Exception as e:
                print(f"Warning: Failed to populate sample snippets: {e}")

    def scan_files(self):
        """Scans the target directory and its subfolders recursively."""
        new_files = []
        if not os.path.exists(self.directory_path):
            self.files = []
            return
            
        try:
            for root, dirs, entries in os.walk(self.directory_path):
                for entry in entries:
                    if entry.lower().endswith('.md'):
                        full_path = os.path.join(root, entry)
                        rel_path = os.path.relpath(full_path, self.directory_path)
                        rel_path = rel_path.replace("\\", "/")  # Use unified forward slashes
                        new_files.append((rel_path, full_path))
            
            # Access dynamic configuration if available to respect pinning setting
            try:
                config = load_application_config()
                use_pins = config.get("enable_pinning", True)
            except Exception:
                use_pins = True

            if use_pins:
                new_files.sort(key=lambda x: (not x[0].startswith("⭐"), x[0].lower()))
            else:
                new_files.sort(key=lambda x: x[0].lower())
                
            self.files = new_files
        except Exception as e:
            print(f"Error scanning directory {self.directory_path}: {e}")
            self.files = []

    def get_absolute_path(self, filename):
        for rel_name, path in self.files:
            if rel_name == filename:
                return path
        return os.path.join(self.directory_path, filename)


# ---------------------------------------------------------
# 3. Clipboard Handling
# ---------------------------------------------------------

def copy_snippet_to_clipboard(file_path):
    """Safely reads the selected file as UTF-8 and copies its content to system clipboard."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        pyperclip.copy(content)
        return True, "Success"
    except Exception as e:
        return False, str(e)


def paste_clipboard_into_active_window():
    """Simulates the standard paste shortcut in the active application."""
    try:
        keyboard.press_and_release("ctrl+v")
        return True, "Success"
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------
# 4. JavaScript to Python Communication Pipeline
# ---------------------------------------------------------

class WebLauncherAPI:
    """Provides a thread-safe data bridge between your React JS and the local OS."""
    def __init__(self, watcher, config):
        self.watcher = watcher
        self.config = config

    def get_all_snippets(self):
        """Called by React to pull the full scanned array of Markdown files."""
        self.watcher.scan_files()
        return [name for name, _ in self.watcher.files]

    def read_snippet_preview(self, filename):
        """Called by React to extract raw Markdown contents for syntax previewing."""
        file_path = self.watcher.get_absolute_path(filename)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f"Error loading file content: {str(e)}"

    def execute_paste_sequence(self, filename):
        """Called by React when a template is selected via Enter/Click to auto-paste."""
        file_path = self.watcher.get_absolute_path(filename)
        success, _ = copy_snippet_to_clipboard(file_path)
        if success:
            global web_window
            if web_window:
                web_window.hide()
                
            if AUTO_PASTE:
                time.sleep(AUTO_PASTE_DELAY_MS / 1000.0)
                paste_clipboard_into_active_window()
        return success

    def create_snippet(self, filename, content):
        """Saves a new snippet file directly to the local snippets directory."""
        try:
            relative_path = normalize_snippet_relative_path(filename)
            file_path = ensure_path_inside_directory(
                self.watcher.directory_path,
                os.path.join(self.watcher.directory_path, relative_path)
            )
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            if os.path.exists(file_path):
                return {"success": False, "error": "A snippet with that name already exists."}
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            self.watcher.scan_files()
            if web_window:
                try:
                    web_window.evaluate_js("if (window.reloadSnippets) window.reloadSnippets();")
                except Exception:
                    pass
            return {"success": True, "filename": os.path.relpath(file_path, self.watcher.directory_path).replace("\\", "/")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def toggle_pin_status(self, filename):
        """Prepends/Removes star marker on disk file to change search prioritization."""
        old_path = self.watcher.get_absolute_path(filename)
        # Strip folders relative matching path if any nested
        base_dir = os.path.dirname(old_path)
        base_name = os.path.basename(old_path)

        if base_name.startswith("⭐ "):
            new_basename = base_name.replace("⭐ ", "", 1)
        else:
            new_basename = f"⭐ {base_name}"
            
        new_path = os.path.join(base_dir, new_basename)
        try:
            os.rename(old_path, new_path)
            self.watcher.scan_files()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_config(self):
        """Exposes local configuration parameters directly to React settings page."""
        config = self.config.copy()
        config["startup_registered"] = is_windows_startup_registered()
        config["hotkey_suggestions"] = get_hotkey_suggestions()
        return config

    def mark_setup_seen(self):
        """Marks first-run setup as seen so it does not reopen on every launch."""
        self.config["setup_complete"] = True
        save_application_config(self.config)
        return {"success": True}

    def save_config(self, new_config_data):
        """Merges, validates, and saves configuration changes from React inputs."""
        updated_config = self.config.copy()
        updated_config.update(new_config_data)
        
        try:
            for key in ("hotkey_launcher", "hotkey_creator"):
                updated_config[key] = validate_hotkey_string(updated_config[key])

            updated_config["window_width"] = clamp_int(updated_config.get("window_width"), 420, 2400, 1000)
            updated_config["window_height"] = clamp_int(updated_config.get("window_height"), 320, 1600, 485)
            for key in ("theme_accent", "theme_background", "theme_panel", "theme_text"):
                updated_config[key] = sanitize_hex_color(updated_config.get(key), DEFAULT_CONFIG[key])
            updated_config["snippet_directory"] = resolve_user_path(updated_config.get("snippet_directory", DEFAULT_CONFIG["snippet_directory"]))

            save_application_config(updated_config)
            self.config = updated_config
            # Shift snippet folders dynamically
            self.watcher.directory_path = os.path.abspath(updated_config["snippet_directory"])
            self.watcher.ensure_directory_exists()
            self.watcher.scan_files()
            sync_windows_startup_registration(updated_config.get("run_at_startup", START_WITH_WINDOWS))
            
            # Rebind background hooks
            rebind_app_hotkeys(updated_config)
            if web_window and hasattr(web_window, "resize"):
                web_window.resize(updated_config["window_width"], updated_config["window_height"])
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def resize_window(self, width, height):
        """Resizes the launcher window from the React drag handle."""
        global web_window
        new_width = clamp_int(width, 420, 2400, self.config.get("window_width", 1000))
        new_height = clamp_int(height, 320, 1600, self.config.get("window_height", 485))
        self.config["window_width"] = new_width
        self.config["window_height"] = new_height
        save_application_config(self.config)
        if web_window and hasattr(web_window, "resize"):
            web_window.resize(new_width, new_height)
        return {"success": True, "width": new_width, "height": new_height}

    def browse_directory(self):
        """Triggers local Windows Explorer folder picker to dynamically select directories."""
        global web_window
        if web_window:
            result = web_window.create_file_dialog(webview.FOLDER_DIALOG)
            if result:
                folder_path = os.path.normpath(result[0])
                return folder_path
        return ""

    def hide_panel(self):
        """Closes or hides the web interface panel view on command."""
        global web_window
        if web_window:
            web_window.hide()

    def hide_creator_panel(self):
        """Hides the creator-only popup window."""
        global creator_window
        if creator_window:
            creator_window.hide()


# ---------------------------------------------------------
# 5. Robust Hardware-Level Hotkey Binding Manager
# ---------------------------------------------------------

class HotkeyManager:
    def __init__(self):
        self.bound = {}
        self.callbacks = {}
        self._global_listener_hook = None

    def bind(self, role, hotkey_string, callback):
        hotkey_string = validate_hotkey_string(hotkey_string)
        self.bound[role] = hotkey_string
        self.callbacks[role] = callback
        log_event(f"Registered physical hotkey match tracker for '{role}': {hotkey_string}")
        
        if self._global_listener_hook is None:
            self._global_listener_hook = keyboard.hook(self._global_hook_callback)

    def unbind(self, role):
        hotkey_string = self.bound.pop(role, None)
        self.callbacks.pop(role, None)
        if hotkey_string:
            log_event(f"Unregistered physical hotkey match tracker for '{role}': {hotkey_string}")

    def rebind(self, role, new_hotkey_string, callback):
        self.unbind(role)
        self.bind(role, new_hotkey_string, callback)

    def unbind_all(self):
        self.bound.clear()
        self.callbacks.clear()

    def _global_hook_callback(self, event):
        """Processes raw OS input streams, matching against direct hardware states."""
        for role, hotkey_str in list(self.bound.items()):
            if check_hotkey_match(event, hotkey_str):
                callback = self.callbacks.get(role)
                if callback:
                    callback()


def start_keyboard_listener(config, toggle_cb, creator_cb):
    global hotkey_manager
    hotkey_manager = HotkeyManager()
    try:
        hotkey_manager.bind("launcher", config["hotkey_launcher"], toggle_cb)
        hotkey_manager.bind("creator", config["hotkey_creator"], creator_cb)
        log_event("Hardware-linked keyboard hook is waiting for triggers.")
    except Exception as e:
        log_event(f"Listener error: {e}")


def rebind_app_hotkeys(new_config):
    global hotkey_manager
    if hotkey_manager:
        try:
            hotkey_manager.rebind("launcher", new_config["hotkey_launcher"], safe_toggle_launcher)
            hotkey_manager.rebind("creator", new_config["hotkey_creator"], safe_trigger_creator)
        except Exception as e:
            log_event(f"Failed to rebind hotkeys: {e}")


# ---------------------------------------------------------
# 6. Global Web Interface Transitions & Creator Actions
# ---------------------------------------------------------

last_toggle_time = 0.0
last_creator_time = 0.0
last_config_mtime = 0.0


def get_config_mtime():
    try:
        return os.path.getmtime(CONFIG_YAML_PATH)
    except Exception:
        return 0.0


def start_config_change_watcher(api_bridge):
    def watch_loop():
        global last_config_mtime
        last_config_mtime = get_config_mtime()
        while True:
            time.sleep(2.0)
            current_mtime = get_config_mtime()
            if current_mtime and current_mtime != last_config_mtime:
                last_config_mtime = current_mtime
                try:
                    new_config = load_application_config()
                    api_bridge.config = new_config
                    api_bridge.watcher.directory_path = os.path.abspath(new_config["snippet_directory"])
                    api_bridge.watcher.ensure_directory_exists()
                    api_bridge.watcher.scan_files()
                    rebind_app_hotkeys(new_config)
                    log_event(
                        "Reloaded config.yaml. "
                        f"Launcher={new_config['hotkey_launcher']} Creator={new_config['hotkey_creator']}"
                    )
                    if web_window:
                        web_window.evaluate_js("if (window.reloadSnippets) window.reloadSnippets();")
                except Exception as e:
                    log_event(f"Failed to reload config.yaml: {e}")

    threading.Thread(target=watch_loop, daemon=True).start()

def safe_toggle_launcher():
    """Toggles interface visibility under debounce guards."""
    global last_toggle_time, web_window
    now = time.monotonic()
    if now - last_toggle_time < HOTKEY_DEBOUNCE_SECONDS:
        return
    last_toggle_time = now
    
    if web_window:
        # Check native visible states safely
        if not hasattr(safe_toggle_launcher, "is_visible"):
            safe_toggle_launcher.is_visible = True
            
        if safe_toggle_launcher.is_visible:
            web_window.hide()
            safe_toggle_launcher.is_visible = False
        else:
            web_window.show()
            safe_toggle_launcher.is_visible = True


def safe_trigger_creator():
    """Triggers custom foreground capturing sequences on background hotkey call."""
    global last_creator_time
    now = time.monotonic()
    if now - last_creator_time < HOTKEY_DEBOUNCE_SECONDS:
        return
    last_creator_time = now
    
    threading.Thread(target=capture_active_text_sequence, daemon=True).start()


def looks_like_browser_location_capture(captured_text, previous_clipboard):
    text = str(captured_text or "").strip()
    previous = str(previous_clipboard or "").strip()
    if not text:
        return False
    if text == previous:
        return False
    if "\n" in text:
        return False
    return bool(re.fullmatch(r"https?://[^\s]+", text))


def capture_active_text_sequence():
    """Polls system clipboard to capture text highlights asynchronously."""
    previous_clipboard = pyperclip.paste()
    sentinel = "__ANTIGRAVITY_SNIPPET_EMPTY_SELECTION__"
    captured_text = ""

    try:
        creator_hotkey = load_application_config().get("hotkey_creator", DEFAULT_CONFIG["hotkey_creator"])
    except Exception:
        creator_hotkey = DEFAULT_CONFIG["hotkey_creator"]

    released = wait_for_hotkey_release(creator_hotkey)
    if not released:
        log_event("Creator capture continued before hotkey release timeout.")

    def copy_selection_once():
        try:
            pyperclip.copy(sentinel)
        except Exception:
            pass

        time.sleep(SELECTION_CAPTURE_DELAY_MS / 1000.0)
        try:
            keyboard.press_and_release("ctrl+c")
        except Exception:
            return ""

        start_time = time.monotonic()
        while time.monotonic() - start_time < (SELECTION_COPY_TIMEOUT_MS / 1000.0):
            try:
                current_clipboard = pyperclip.paste()
                if current_clipboard != sentinel:
                    return current_clipboard
            except Exception:
                pass
            time.sleep(SELECTION_COPY_POLL_MS / 1000.0)
        return ""

    captured_text = copy_selection_once()
    if looks_like_browser_location_capture(captured_text, previous_clipboard):
        log_event("Creator capture received a URL-like clipboard value; retrying selected-text copy.")
        time.sleep(0.2)
        retry_text = copy_selection_once()
        if retry_text:
            captured_text = retry_text

    # Revert user's standard clipboard data safely
    try:
        pyperclip.copy(previous_clipboard)
    except Exception:
        pass

    global creator_window
    if creator_window:
        creator_window.show()
        creator_window.evaluate_js(
            f"if (window.onSnippetCaptured) window.onSnippetCaptured({json.dumps(captured_text or '')});"
        )

    if not captured_text or not captured_text.strip():
        log_event("Creator capture failed: Selection empty or clipboard timeout.")


# ---------------------------------------------------------
# 7. Background System Tray Management
# ---------------------------------------------------------

class SystemTrayController:
    """Manages background launcher process inside Windows taskbar notification zones."""
    def __init__(self, config):
        self.config = config
        self.icon = None

    def start(self):
        threading.Thread(target=self._run_tray, daemon=True).start()

    def _run_tray(self):
        try:
            import pystray
            from PIL import Image, ImageDraw
        except ImportError:
            return

        # Prefer the product icon, then fall back to a generated tray glyph.
        try:
            if os.path.exists(ICON_PATH):
                image = Image.open(ICON_PATH)
            else:
                image = Image.new('RGBA', (64, 64), color=(0, 0, 0, 0))
                draw = ImageDraw.Draw(image)
                draw.rounded_rectangle([8, 8, 56, 56], radius=16, fill=(203, 166, 247, 255))
                draw.rectangle([24, 20, 40, 44], fill=(24, 24, 37, 255))
        except Exception:
            image = Image.new('RGB', (64, 64), color='#cba6f7')

        menu = pystray.Menu(
            pystray.MenuItem("Show Launcher", self._show_launcher),
            pystray.MenuItem("New Snippet", self._show_creator),
            pystray.MenuItem("Run at Startup", self._toggle_startup, checked=lambda item: is_windows_startup_registered()),
            pystray.MenuItem("Open Snippet Folder", self._open_snippet_folder),
            pystray.MenuItem("Hide Launcher", self._hide_launcher),
            pystray.MenuItem("Exit", self._exit_app)
        )

        self.icon = pystray.Icon(
            "AntigravityLauncher",
            image,
            "MarkStash",
            menu
        )
        self.icon.run()

    def _show_launcher(self, icon=None, item=None):
        global web_window
        if web_window:
            web_window.show()
            safe_toggle_launcher.is_visible = True

    def _hide_launcher(self, icon=None, item=None):
        global web_window
        if web_window:
            web_window.hide()
            safe_toggle_launcher.is_visible = False

    def _show_creator(self, icon=None, item=None):
        global creator_window
        if creator_window:
            creator_window.show()
            creator_window.evaluate_js("if (window.onSnippetCaptured) window.onSnippetCaptured('');")

    def _toggle_startup(self, icon=None, item=None):
        self.config["run_at_startup"] = not is_windows_startup_registered()
        sync_windows_startup_registration(self.config["run_at_startup"])
        save_application_config(self.config)
        if self.icon:
            self.icon.update_menu()

    def _open_snippet_folder(self, icon=None, item=None):
        folder = self.config.get("snippet_directory") or DEFAULT_CONFIG["snippet_directory"]
        os.makedirs(folder, exist_ok=True)
        if SYSTEM == "windows":
            try:
                os.startfile(folder)
            except Exception as e:
                log_event(f"Failed to open snippet folder: {e}")

    def _exit_app(self, icon=None, item=None):
        global web_window, creator_window, hotkey_manager
        if self.icon:
            self.icon.stop()
        if hotkey_manager:
            hotkey_manager.unbind_all()
        if creator_window:
            creator_window.destroy()
        if web_window:
            web_window.destroy()
        os._exit(0)


# ---------------------------------------------------------
# 8. Windows Startup Registration
# ---------------------------------------------------------

def get_background_python_executable():
    executable = sys.executable
    if SYSTEM == "windows" and os.path.basename(executable).lower() == "python.exe":
        pythonw = os.path.join(os.path.dirname(executable), "pythonw.exe")
        if os.path.exists(pythonw):
            return pythonw
    return executable


def get_startup_file_path():
    if SYSTEM != "windows":
        return ""
    startup_dir = os.path.join(
        os.environ.get("APPDATA", ""),
        "Microsoft",
        "Windows",
        "Start Menu",
        "Programs",
        "Startup"
    )
    if not startup_dir.strip() or not os.path.isdir(startup_dir):
        return ""
    return os.path.join(startup_dir, "MarkStash.bat")


def get_startup_launch_command():
    startup_args = " --startup" if START_HIDDEN_ON_WINDOWS_STARTUP else ""
    if getattr(sys, "frozen", False):
        executable = sys.executable
        return f'start "" "{executable}"{startup_args}\n'
    script_path = os.path.abspath(__file__)
    python_executable = get_background_python_executable()
    return f'start "" "{python_executable}" "{script_path}"{startup_args}\n'


def is_windows_startup_registered():
    startup_file = get_startup_file_path()
    return bool(startup_file and os.path.exists(startup_file))


def sync_windows_startup_registration(run_at_startup):
    if SYSTEM != "windows":
        return
    startup_file = get_startup_file_path()
    if not startup_file:
        print("[Startup] Could not locate the Windows Startup folder.", file=sys.stderr)
        return

    if not run_at_startup:
        if os.path.exists(startup_file):
            try:
                os.remove(startup_file)
                print("[Startup] Windows startup entry removed.")
            except Exception as e:
                print(f"[Startup Error] Failed to remove startup entry: {e}", file=sys.stderr)
        return

    startup_contents = (
        "@echo off\n"
        f"{get_startup_launch_command()}"
    )

    try:
        existing_contents = ""
        if os.path.exists(startup_file):
            with open(startup_file, "r", encoding="utf-8") as f:
                existing_contents = f.read()

        if existing_contents != startup_contents:
            with open(startup_file, "w", encoding="utf-8") as f:
                f.write(startup_contents)
            print(f"[Startup] Windows startup entry enabled: {startup_file}")
    except Exception as e:
        print(f"[Startup Error] Failed to enable startup entry: {e}", file=sys.stderr)


# ---------------------------------------------------------
# 9. Main Entry Point
# ---------------------------------------------------------

def main():
    global web_window, creator_window
    print("Starting Antigravity Markdown Snippet Launcher (Web Interface)...")
    config = load_application_config()
    print(f"Snippet directory: {config['snippet_directory']}")
    print(f"Launcher Hotkey configured: {config['hotkey_launcher']}")
    print(f"Creator Hotkey configured: {config['hotkey_creator']}")

    sync_windows_startup_registration(config.get("run_at_startup", START_WITH_WINDOWS))
    
    watcher = SnippetWatcher(config["snippet_directory"])
    api_bridge = WebLauncherAPI(watcher, config)

    # Point to the compiled frontend production static dist bundle
    ui_entry_path = os.path.join(ASSET_DIR, "dist", "index.html")

    # Launch structural framework
    web_window = webview.create_window(
        title="MarkStash Launcher",
        url=ui_entry_path,
        js_api=api_bridge,
        width=config["window_width"],
        height=config["window_height"],
        frameless=True,             # Strips traditional legacy OS borders and headers
        easy_drag=True,             # Lets user drag window naturally anywhere on canvas backplates
        background_color="#181825"  # Catppuccin Mocha blend
    )

    creator_window = webview.create_window(
        title="New MarkStash Snippet",
        url=f"{ui_entry_path}?mode=creator",
        js_api=api_bridge,
        width=560,
        height=360,
        frameless=True,
        easy_drag=True,
        hidden=True,
        background_color="#181825"
    )

    # Handle automatic silent startup view state
    if "--startup" in sys.argv and START_HIDDEN_ON_WINDOWS_STARTUP:
        web_window.hide()
        safe_toggle_launcher.is_visible = False
    else:
        safe_toggle_launcher.is_visible = True

    # Mount background keyboard hook listeners
    start_keyboard_listener(config, safe_toggle_launcher, safe_trigger_creator)
    start_config_change_watcher(api_bridge)

    # Launch System Tray zone icons
    tray = SystemTrayController(config)
    tray.start()
    
    try:
        webview.start()  # Blocks main program thread
    except KeyboardInterrupt:
        print("\nExiting application...")
        if hotkey_manager:
            hotkey_manager.unbind_all()


if __name__ == '__main__':
    main()

