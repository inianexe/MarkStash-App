import os
import sys
import signal
import platform
import time
import json
import re
import threading
import tkinter as tk
from tkinter import messagebox, filedialog
import pyperclip

APP_DIR = os.path.dirname(os.path.abspath(__file__))
HOTKEY_LOG_PATH = os.path.join(APP_DIR, "hotkey_debug.log")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

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
DEFAULT_CONFIG = {
    "snippet_directory": r"D:\Markdown Project Foler (DO NOT DELETE)",
    "hotkey_launcher": "ctrl+shift+x",
    "hotkey_creator": "ctrl+shift+v",
    "run_at_startup": START_WITH_WINDOWS,
}

# ---------------------------------------------------------
# 1. Platform & Dependency Checks
# ---------------------------------------------------------

SYSTEM = platform.system().lower()

# Prevent the Windows console host from interpreting synthetic Ctrl+C
# keystrokes (used to copy highlighted text) as a process-kill signal.
if SYSTEM == "windows":
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleCtrlHandler(None, True)
    except Exception:
        pass


def log_event(message):
    """Writes diagnostic events to disk because pythonw.exe has no visible console."""
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
    cleaned = (hotkey_string or "").strip().lower()
    if not cleaned:
        raise ValueError("Hotkey cannot be empty.")
    keyboard.parse_hotkey(cleaned)
    return cleaned


def load_application_config():
    """Loads settings from config.json or initializes defaults if file is missing."""
    if not os.path.exists(CONFIG_PATH):
        try:
            save_application_config(DEFAULT_CONFIG)
        except Exception as e:
            log_event(f"Failed to write default config.json. Error={e}")
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            stored_config = json.load(f)
    except Exception as e:
        log_event(f"Config load failed; using defaults. Error={e}")
        return DEFAULT_CONFIG.copy()

    config = DEFAULT_CONFIG.copy()
    if isinstance(stored_config, dict):
        config.update({
            key: stored_config[key]
            for key in DEFAULT_CONFIG
            if key in stored_config and stored_config[key] is not None
        })

    for key in ("hotkey_launcher", "hotkey_creator"):
        try:
            config[key] = validate_hotkey_string(config[key])
        except Exception as e:
            log_event(f"Invalid hotkey '{config[key]}' for '{key}'; using default. Error={e}")
            config[key] = DEFAULT_CONFIG[key]

    return config


def save_application_config(config_data):
    """Writes updated configuration settings to config.json."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=4)
    return config_data


if SYSTEM == 'linux' and os.geteuid() != 0:
    print("=" * 70, file=sys.stderr)
    print("ERROR: Root privileges required.", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    sys.exit(1)

try:
    import keyboard
except ImportError as e:
    sys.exit(1)

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    pystray = None
    Image = None
    ImageDraw = None


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
                # MSB (Most Significant Bit) is set if the physical key is down
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
    parts = [p.strip().lower() for p in hotkey_str.split("+")]
    modifiers = []
    trigger_key = ""
    for p in parts:
        if p in ("ctrl", "shift", "alt", "alt gr", "windows"):
            modifiers.append(p)
        else:
            trigger_key = p
    return modifiers, trigger_key


def check_hotkey_match(event, hotkey_str):
    """Matches hardware modifier inputs against specified hotkey schema configurations."""
    if event.event_type != keyboard.KEY_DOWN:
        return False
        
    modifiers, trigger_key = parse_hotkey_string(hotkey_str)
    event_key = (event.name or "").lower()
    
    if event_key != trigger_key:
        return False
        
    all_mods = ["ctrl", "shift", "alt", "windows"]
    for mod in all_mods:
        if "alt gr" in modifiers:
            # alt gr represents simultaneous ctrl + alt trigger state
            required = (mod in ("alt", "ctrl"))
        else:
            required = (mod in modifiers)
            
        if is_modifier_pressed(mod) != required:
            return False
            
    return True


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
        """Scans the target directory using os.scandir for optimal speed."""
        new_files = []
        if not os.path.exists(self.directory_path):
            self.files = []
            return
            
        try:
            with os.scandir(self.directory_path) as entries:
                for entry in entries:
                    if entry.is_file() and entry.name.lower().endswith('.md'):
                        new_files.append((entry.name, entry.path))
            new_files.sort(key=lambda x: x[0].lower())
            self.files = new_files
        except Exception as e:
            print(f"Error scanning directory {self.directory_path}: {e}")
            self.files = []

    def get_filtered_filenames(self, query):
        """Filters the files instantly using a sequential fuzzy matching regex engine."""
        if not query:
            return [name for name, _ in self.files]
        
        query_chars = [re.escape(char) for char in query.strip()]
        fuzzy_pattern = ".*?".join(query_chars)
        
        try:
            regex = re.compile(fuzzy_pattern, re.IGNORECASE)
        except re.error:
            return []

        matched_names = [name for name, _ in self.files if regex.search(name)]
        return sorted(matched_names, key=len)

    def get_absolute_path(self, filename):
        for name, path in self.files:
            if name == filename:
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
# 4. Custom Borderless Input Dialog for Snippet Creation
# ---------------------------------------------------------

class SnippetCreateDialog(tk.Toplevel):
    def __init__(self, parent, callback):
        super().__init__(parent)
        self.callback = callback
        
        self.overrideredirect(True)
        self.attributes('-topmost', True)
        
        self.bg_color = "#181825"
        self.input_bg = "#313244"
        self.accent_active = "#cba6f7"
        self.text_fg = "#cdd6f4"
        self.text_muted = "#a1a1aa"
        
        self.configure(
            bg=self.bg_color, 
            highlightbackground=self.accent_active, 
            highlightcolor=self.accent_active, 
            highlightthickness=1
        )
        
        self.width = 360
        self.height = 120
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width - self.width) // 2
        y = (screen_height - self.height) // 2
        self.geometry(f"{self.width}x{self.height}+{x}+{y}")
        
        container = tk.Frame(self, bg=self.bg_color, padx=15, pady=15)
        container.pack(fill=tk.BOTH, expand=True)
        
        self.label = tk.Label(
            container, 
            text="NAME THIS SNIPPET:", 
            fg=self.text_muted, 
            bg=self.bg_color, 
            font=("Segoe UI", 9, "bold")
        )
        self.label.pack(anchor="w", pady=(0, 6))
        
        entry_frame = tk.Frame(
            container, 
            bg=self.input_bg, 
            highlightbackground="#45475a", 
            highlightcolor=self.accent_active, 
            highlightthickness=1
        )
        entry_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.entry_var = tk.StringVar()
        self.entry = tk.Entry(
            entry_frame,
            textvariable=self.entry_var,
            bg=self.input_bg,
            fg=self.text_fg,
            insertbackground=self.text_fg,
            font=("Segoe UI", 12),
            bd=0,
            highlightthickness=0
        )
        self.entry.pack(fill=tk.X, padx=10, pady=6)
        
        self.entry.focus_force()
        self.entry.bind("<Return>", self.on_confirm)
        self.entry.bind("<Escape>", lambda e: self.destroy())
        self.bind("<FocusOut>", self.on_focus_lost)

    def on_confirm(self, event=None):
        name = self.entry_var.get().strip()
        if name:
            self.callback(name)
        self.destroy()

    def on_focus_lost(self, event):
        if not self.focus_get():
            self.destroy()


# ---------------------------------------------------------
# Settings Engine Dashboard with Custom Key Capture Hook
# ---------------------------------------------------------

class SettingsDashboard(tk.Toplevel):
    def __init__(self, parent, config, callback):
        super().__init__(parent)
        self.callback = callback
        self.config_data = config

        self.overrideredirect(True)
        self.attributes('-topmost', True)

        self.bg_color = "#181825"
        self.input_bg = "#313244"
        self.accent_active = "#cba6f7"
        self.text_fg = "#cdd6f4"
        self.text_muted = "#a1a1aa"
        self.error_fg = "#f38ba8"

        self.configure(
            bg=self.bg_color,
            highlightbackground=self.accent_active,
            highlightcolor=self.accent_active,
            highlightthickness=1
        )

        self.width = 480
        self.height = 320
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width - self.width) // 2
        y = (screen_height - self.height) // 2
        self.geometry(f"{self.width}x{self.height}+{x}+{y}")

        container = tk.Frame(self, bg=self.bg_color, padx=16, pady=16)
        container.pack(fill=tk.BOTH, expand=True)

        title = tk.Label(
            container,
            text="SETTINGS ENGINE (PRESS COMBINATION TO RECORD)",
            fg=self.text_muted,
            bg=self.bg_color,
            font=("Segoe UI", 8, "bold")
        )
        title.pack(anchor="w", pady=(0, 10))

        self.launcher_var = tk.StringVar(value=config["hotkey_launcher"])
        self.creator_var = tk.StringVar(value=config["hotkey_creator"])
        self.directory_var = tk.StringVar(value=config["snippet_directory"])

        self.launcher_entry = self.create_entry(container, "OPEN / HIDE HOTKEY", self.launcher_var)
        self.creator_entry = self.create_entry(container, "CREATE SNIPPET HOTKEY", self.creator_var)
        self.directory_entry = self.create_directory_entry(container, "SNIPPET FOLDER", self.directory_var)

        self.error_label = tk.Label(
            container,
            text="",
            fg=self.error_fg,
            bg=self.bg_color,
            font=("Segoe UI", 9),
            wraplength=self.width - 32,
            justify="left"
        )
        self.error_label.pack(anchor="w", pady=(2, 8))

        button_row = tk.Frame(container, bg=self.bg_color)
        button_row.pack(fill=tk.X)

        save_button = tk.Button(
            button_row,
            text="Save",
            command=self.on_save,
            bg=self.accent_active,
            fg="#11111b",
            activebackground="#b4befe",
            activeforeground="#11111b",
            font=("Segoe UI", 10, "bold"),
            bd=0,
            padx=12,
            pady=6
        )
        save_button.pack(side=tk.RIGHT)

        cancel_button = tk.Button(
            button_row,
            text="Cancel",
            command=self.destroy,
            bg=self.input_bg,
            fg=self.text_fg,
            activebackground="#45475a",
            activeforeground=self.text_fg,
            font=("Segoe UI", 10),
            bd=0,
            padx=12,
            pady=6
        )
        cancel_button.pack(side=tk.RIGHT, padx=(0, 8))

        self.bind("<Escape>", lambda e: self.destroy())
        self.launcher_entry.focus_force()

    def create_entry(self, container, label_text, variable):
        label = tk.Label(
            container,
            text=label_text,
            fg=self.text_muted,
            bg=self.bg_color,
            font=("Segoe UI", 8, "bold")
        )
        label.pack(anchor="w")

        entry_frame = tk.Frame(
            container,
            bg=self.input_bg,
            highlightbackground="#45475a",
            highlightcolor=self.accent_active,
            highlightthickness=1
        )
        entry_frame.pack(fill=tk.X, pady=(4, 9))

        entry = tk.Entry(
            entry_frame,
            textvariable=variable,
            bg=self.input_bg,
            fg=self.text_fg,
            insertbackground=self.text_fg,
            font=("Segoe UI", 11),
            bd=0,
            highlightthickness=0
        )
        entry.pack(fill=tk.X, padx=10, pady=6)
        
        # Key event listener bindings to capture hardware keysym events directly
        entry.bind("<KeyPress>", lambda e: self.record_hardware_keystroke(e, variable))
        entry.bind("<KeyRelease>", lambda e: "break")
        
        # Aesthetic focus tracking colors
        entry.bind("<FocusIn>", lambda e: entry_frame.configure(highlightbackground=self.accent_active))
        entry.bind("<FocusOut>", lambda e: entry_frame.configure(highlightbackground="#45475a"))
        
        return entry

    def record_hardware_keystroke(self, event, variable):
        """Captures hardware keystrokes and formats them directly to compatible lower-case sequences."""
        if event.keysym in ("Tab", "Escape"):
            return None
            
        if event.keysym in ("BackSpace", "Delete"):
            variable.set("")
            return "break"
            
        modifiers = []
        state_flags = event.state
        
        # Enforce cross-platform modifier masks mapping sequence
        if state_flags & 0x0004:
            modifiers.append("ctrl")
        if state_flags & 0x0001:
            modifiers.append("shift")
        if state_flags & 0x20000 or state_flags & 0x0008:
            modifiers.append("alt")
        if state_flags & 0x0040:
            modifiers.append("windows")

        key_name = event.keysym.lower()
        mapping_dictionary = {
            "control_l": "ctrl", "control_r": "ctrl",
            "alt_l": "alt", "alt_r": "alt gr",
            "shift_l": "shift", "shift_r": "shift",
            "win_l": "windows", "win_r": "windows",
            "meta_l": "windows", "meta_r": "windows",
            "space": "space"
        }
        
        if key_name in mapping_dictionary:
            final_str = mapping_dictionary[key_name]
        else:
            if "ctrl" in key_name or "alt" in key_name or "shift" in key_name or "win" in key_name:
                return "break"
            
            # Map symbol keystroke differences
            symbol_mapping = {
                "comma": ",", "period": ".", "slash": "/", "backslash": "\\",
                "semicolon": ";", "apostrophe": "'", "bracketleft": "[",
                "bracketright": "]", "minus": "-", "equal": "=", "grave": "`"
            }
            mapped_key = symbol_mapping.get(key_name, key_name)
            
            # Form clean sequential array
            unique_mods = []
            for modifier in modifiers:
                if modifier not in unique_mods:
                    unique_mods.append(modifier)
            if mapped_key not in unique_mods:
                unique_mods.append(mapped_key)
                
            final_str = "+".join(unique_mods)
            
        variable.set(final_str)
        return "break"

    def create_directory_entry(self, container, label_text, variable):
        label = tk.Label(
            container,
            text=label_text,
            fg=self.text_muted,
            bg=self.bg_color,
            font=("Segoe UI", 8, "bold")
        )
        label.pack(anchor="w")

        row = tk.Frame(container, bg=self.bg_color)
        row.pack(fill=tk.X, pady=(4, 9))

        entry_frame = tk.Frame(
            row,
            bg=self.input_bg,
            highlightbackground="#45475a",
            highlightcolor=self.accent_active,
            highlightthickness=1
        )
        entry_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        entry = tk.Entry(
            entry_frame,
            textvariable=variable,
            bg=self.input_bg,
            fg=self.text_fg,
            insertbackground=self.text_fg,
            font=("Segoe UI", 11),
            bd=0,
            highlightthickness=0
        )
        entry.pack(fill=tk.X, padx=10, pady=6)
        entry.bind("<Return>", lambda e: self.on_save())

        browse_button = tk.Button(
            row,
            text="Browse",
            command=lambda: self.browse_directory(variable),
            bg=self.input_bg,
            fg=self.text_fg,
            activebackground="#45475a",
            activeforeground=self.text_fg,
            font=("Segoe UI", 9),
            bd=0,
            padx=10,
            pady=6
        )
        browse_button.pack(side=tk.LEFT, padx=(8, 0))

        return entry

    def browse_directory(self, variable):
        self.attributes('-topmost', False)
        selected = filedialog.askdirectory(initialdir=variable.get() or APP_DIR, parent=self)
        self.attributes('-topmost', True)
        if selected:
            variable.set(os.path.normpath(selected))

    def on_save(self):
        try:
            launcher_hotkey = validate_hotkey_string(self.launcher_var.get())
            creator_hotkey = validate_hotkey_string(self.creator_var.get())
        except Exception as e:
            self.error_label.configure(text=str(e))
            return

        if launcher_hotkey == creator_hotkey:
            self.error_label.configure(text="Open/Hide and Create Snippet hotkeys must be different.")
            return

        directory = self.directory_var.get().strip()
        if not directory:
            self.error_label.configure(text="Snippet folder cannot be empty.")
            return

        new_config = {
            "hotkey_launcher": launcher_hotkey,
            "hotkey_creator": creator_hotkey,
            "snippet_directory": os.path.abspath(directory),
            "run_at_startup": bool(self.config_data.get("run_at_startup", START_WITH_WINDOWS)),
        }

        try:
            save_application_config(new_config)
        except Exception as e:
            self.error_label.configure(text=f"Failed to save config.json: {e}")
            return

        self.callback(new_config)
        self.destroy()


# ---------------------------------------------------------
# 5. Minimalist & Borderless Launcher Main UI
# ---------------------------------------------------------

class BorderlessSnippetLauncher:
    def __init__(self, root, watcher, config):
        self.root = root
        self.watcher = watcher
        self.config = config
        self.hotkey_manager = HotkeyManager()
        
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        
        # Expanded geometry for horizontal dual-pane layout
        self.width = 1000
        self.height = 420
        self.root.geometry(f"{self.width}x{self.height}")
        self.center_window_top_third()
        
        self.bg_color = "#181825"        
        self.input_bg = "#313244"        
        self.accent_active = "#cba6f7"   
        self.accent_idle = "#45475a"     
        self.text_fg = "#cdd6f4"         
        self.text_muted = "#a1a1aa"      
        self.text_highlight = "#11111b"  
        
        self.root.configure(bg=self.bg_color, highlightbackground=self.accent_active, highlightcolor=self.accent_active, highlightthickness=1)
        
        self.is_visible = True
        self.app_has_focus = True  # Track active window focus states
        self.animating = False
        self.after_hide_callbacks = []
        self.last_toggle_hotkey_time = 0.0
        self.last_creator_hotkey_time = 0.0
        self.tray_controller = None
        
        self.container = tk.Frame(self.root, bg=self.bg_color, padx=15, pady=15)
        self.container.pack(fill=tk.BOTH, expand=True)
        
        # Left Pane Isolation Column Frame
        self.left_pane = tk.Frame(self.container, bg=self.bg_color, width=450)
        self.left_pane.pack_propagate(False) # Prevent size shrink-wrapping to contents
        self.left_pane.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 10))
        
        self.search_frame = tk.Frame(
            self.left_pane, 
            bg=self.input_bg, 
            highlightbackground=self.accent_idle, 
            highlightcolor=self.accent_active, 
            highlightthickness=1
        )
        self.search_frame.pack(fill=tk.X, pady=(0, 12))
        
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self.on_search_changed)
        
        self.search_entry = tk.Entry(
            self.search_frame,
            textvariable=self.search_var,
            bg=self.input_bg,
            fg=self.text_fg,
            insertbackground=self.text_fg, 
            font=("Segoe UI", 14),
            bd=0,
            highlightthickness=0
        )
        self.search_entry.pack(fill=tk.X, padx=12, pady=10)

        self.toolbar = tk.Frame(self.left_pane, bg=self.bg_color)
        self.toolbar.pack(fill=tk.X, pady=(0, 10))

        self.hotkey_label = tk.Label(
            self.toolbar,
            text=self.format_hotkey_label(),
            fg=self.text_muted,
            bg=self.bg_color,
            font=("Segoe UI", 9)
        )
        self.hotkey_label.pack(side=tk.LEFT)

        self.settings_button = tk.Button(
            self.toolbar,
            text="Settings",
            command=self.open_settings,
            bg=self.input_bg,
            fg=self.text_fg,
            activebackground="#45475a",
            activeforeground=self.text_fg,
            font=("Segoe UI", 9),
            bd=0,
            padx=10,
            pady=4
        )
        self.settings_button.pack(side=tk.RIGHT)
        
        self.file_listbox = tk.Listbox(
            self.left_pane,
            bg=self.bg_color,
            fg=self.text_fg,
            selectbackground=self.accent_active,
            selectforeground=self.text_highlight,
            font=("Segoe UI", 12),
            bd=0,
            highlightthickness=0,
            activestyle="none"
        )
        self.file_listbox.pack(fill=tk.BOTH, expand=True)
        
        # Right Pane Layout Panel (Markdown Live View Panel Frame)
        self.right_pane = tk.Frame(self.container, bg="#11111b")
        self.right_pane.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        self.preview_text = tk.Text(
            self.right_pane, bg="#1e1e2e", fg=self.text_fg,
            font=("Consolas", 11), wrap=tk.WORD, bd=0, highlightthickness=0
        )
        self.preview_text.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        
        # Style syntax matching tags
        self.preview_text.tag_config("md_header", foreground=self.accent_active, font=("Consolas", 13, "bold"))
        self.preview_text.tag_config("md_code", foreground="#a6e3a1", background="#313244")
        self.preview_text.tag_config("md_bullet", foreground="#f38ba8", font=("Consolas", 11, "bold"))
        self.preview_text.config(state=tk.DISABLED)

        self.credit_label = tk.Label(
            self.root,
            text="Made By - inian.exe",
            fg=self.text_muted,
            bg="#11111b",
            font=("Segoe UI", 8)
        )
        self.credit_label.place(relx=1.0, rely=1.0, anchor=tk.SE, x=-18, y=-10)
        
        self.bind_events()
        self.update_listbox()
        self.root.after(100, self.focus_search)

    def open_settings(self):
        SettingsDashboard(self.root, self.config, self.apply_config_changes)

    def open_launcher_from_tray(self):
        if self.animating:
            return
        self.watcher.scan_files()
        self.update_listbox()
        if self.is_visible:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes('-topmost', True)
            self.root.attributes('-alpha', 1.0)
            self.focus_search()
        else:
            self.show_window_animated()

    def open_settings_from_tray(self):
        if not self.is_visible and not self.animating:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes('-topmost', True)
            self.root.attributes('-alpha', 1.0)
            self.is_visible = True
            self.app_has_focus = True
        self.open_settings()

    def is_run_at_startup_enabled(self):
        return bool(self.config.get("run_at_startup", START_WITH_WINDOWS))

    def set_run_at_startup(self, enabled):
        self.config["run_at_startup"] = bool(enabled)
        try:
            save_application_config(self.config)
            sync_windows_startup_registration(self.config["run_at_startup"])
            log_event(f"Run at Startup set to: {self.config['run_at_startup']}")
        except Exception as e:
            log_event(f"Failed to update Run at Startup: {e}")
            messagebox.showerror("Startup Error", f"Could not update Windows startup registration:\n\n{e}")
        if self.tray_controller:
            self.tray_controller.refresh_menu()

    def format_hotkey_label(self):
        return f"Open: {self.config['hotkey_launcher']}    Create: {self.config['hotkey_creator']}"

    def apply_config_changes(self, new_config):
        self.config = new_config

        # Unconditionally register updated hotkey tracking definitions inside mapping manager
        try:
            self.hotkey_manager.rebind("launcher", new_config["hotkey_launcher"], self.safe_toggle)
        except Exception as e:
            log_event(f"Failed to rebind launcher hotkey: {e}")
            messagebox.showerror("Hotkey Error", f"Could not register launcher hotkey '{new_config['hotkey_launcher']}':\n\n{e}")

        try:
            self.hotkey_manager.rebind("creator", new_config["hotkey_creator"], self.safe_trigger_creator)
        except Exception as e:
            log_event(f"Failed to rebind creator hotkey: {e}")
            messagebox.showerror("Hotkey Error", f"Could not register creator hotkey '{new_config['hotkey_creator']}':\n\n{e}")

        try:
            self.watcher = SnippetWatcher(new_config["snippet_directory"])
            self.update_listbox()
            log_event(f"Snippet directory synced to: {new_config['snippet_directory']}")
        except Exception as e:
            log_event(f"Failed to switch snippet directory: {e}")
            messagebox.showerror("Folder Error", f"Could not sync snippet directory:\n\n{e}")

        self.hotkey_label.configure(text=self.format_hotkey_label())
        
        # Re-initialize native UI triggers with fresh configurations
        self.bind_events()

    def center_window_top_third(self):
        self.root.update_idletasks()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - self.width) // 2
        y = (screen_height - self.height) // 3 
        self.root.geometry(f"+{x}+{y}")

    def parse_hotkey_for_tkinter(self, raw_hotkey_str):
        """Converts raw keyboard-library modifiers cleanly to Tkinter-compatible syntax bindings."""
        parts = raw_hotkey_str.split("+")
        tk_mods = []
        key = ""
        for p in parts:
            p = p.strip().lower()
            if p == "ctrl":
                tk_mods.append("Control")
            elif p in ("alt", "alt gr"):
                tk_mods.append("Alt")
            elif p == "shift":
                tk_mods.append("Shift")
            elif p == "windows":
                tk_mods.append("Meta")
            else:
                key = p
        
        if key == "space":
            key = "space"
        elif len(key) == 1:
            key = key.lower()
            
        if tk_mods:
            return f"<{'-'.join(tk_mods)}-{key}>"
        return f"<{key}>"

    def bind_events(self):
        self.root.bind("<Escape>", lambda e: self.hide_window_animated())
        
        self.search_entry.bind("<Return>", self.on_enter_pressed)
        self.file_listbox.bind("<Double-Button-1>", self.on_enter_pressed)
        
        self.search_entry.bind("<Down>", self.move_selection_down)
        self.search_entry.bind("<Up>", self.move_selection_up)
        
        # Intercept and manage real-time active layout focus structures
        self.root.bind("<FocusIn>", self.on_focus_in)
        self.root.bind("<FocusOut>", self.on_focus_out)
        
        # Intercept listbox trace selection lines to refresh content pane dynamically
        self.file_listbox.bind("<<ListboxSelect>>", self.refresh_markdown_preview)
        
        # --- LOCAL FOCUS CLOSURE BINDING ENGINE ---
        raw_key = self.config["hotkey_launcher"].lower()
        tk_event_str = self.parse_hotkey_for_tkinter(raw_key)
        
        try:
            self.root.bind(tk_event_str, lambda e: self.force_dismiss_from_focused_ui())
            self.search_entry.bind(tk_event_str, lambda e: self.force_dismiss_from_focused_ui())
            
            # Windows AltGr fallback (registers physically as Control+Alt)
            if "alt gr" in raw_key:
                fallback_str = tk_event_str.replace("<Alt-", "<Control-Alt-")
                self.root.bind(fallback_str, lambda e: self.force_dismiss_from_focused_ui())
                self.search_entry.bind(fallback_str, lambda e: self.force_dismiss_from_focused_ui())
        except Exception as err:
            print(f"[UI Binding Warning] Failed to register local layout toggle: {err}")

    def force_dismiss_from_focused_ui(self, event=None):
        """Forcibly dismisses panel when toggle combinations map inside focused layers."""
        if self.animating:
            return "break"
        self.hide_window_animated()
        return "break"

    def focus_search(self):
        self.search_entry.focus_force()

    def on_focus_in(self, event):
        if event.widget == self.root:
            self.app_has_focus = True
            self.focus_search()

    def on_focus_out(self, event):
        if event.widget == self.root:
            # Check if active focus actually left the application window entirely
            if not self.root.focus_get():
                self.app_has_focus = False

    def on_search_changed(self, *args):
        self.update_listbox()

    def update_listbox(self):
        """Filters list of files matching search criteria instantly."""
        query = self.search_var.get()
        filtered_names = self.watcher.get_filtered_filenames(query)
        
        self.file_listbox.delete(0, tk.END)
        for name in filtered_names:
            self.file_listbox.insert(tk.END, name)
            
        if self.file_listbox.size() > 0:
            self.file_listbox.selection_set(0)
            self.file_listbox.activate(0)
            self.refresh_markdown_preview()
        else:
            self.preview_text.config(state=tk.NORMAL)
            self.preview_text.delete("1.0", tk.END)
            self.preview_text.config(state=tk.DISABLED)

    def refresh_markdown_preview(self, event=None):
        """Reads the highlighted snippet file buffer and paints content to the preview text widget layout."""
        current_sel = self.file_listbox.curselection()
        if not current_sel:
            return
            
        filename = self.file_listbox.get(current_sel[0])
        file_path = self.watcher.get_absolute_path(filename)
        
        if not os.path.exists(file_path):
            return
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception:
            return

        self.preview_text.config(state=tk.NORMAL)
        self.preview_text.delete("1.0", tk.END)
        
        for line in lines:
            if line.startswith("#"):
                self.preview_text.insert(tk.END, line, "md_header")
            elif line.strip().startswith("`") or line.startswith("    ") or line.startswith("\t"):
                self.preview_text.insert(tk.END, line, "md_code")
            elif line.strip().startswith(("*", "-", "+")) or (line.strip() and line.strip()[0].isdigit() and line.strip().split('.')[0].isdigit()):
                self.preview_text.insert(tk.END, line, "md_bullet")
            else:
                self.preview_text.insert(tk.END, line)
                
        self.preview_text.config(state=tk.DISABLED)

    # ---------------------------------------------------------
    # Listbox Keyboard Navigation Handlers
    # ---------------------------------------------------------

    def move_selection_down(self, event):
        if self.file_listbox.size() == 0:
            return "break"
        
        current_sel = self.file_listbox.curselection()
        if not current_sel:
            next_idx = 0
        else:
            next_idx = current_sel[0] + 1
            if next_idx >= self.file_listbox.size():
                next_idx = 0 
                
        self.file_listbox.selection_clear(0, tk.END)
        self.file_listbox.selection_set(next_idx)
        self.file_listbox.activate(next_idx)
        self.file_listbox.see(next_idx)
        self.refresh_markdown_preview()
        return "break"

    def move_selection_up(self, event):
        if self.file_listbox.size() == 0:
            return "break"
            
        current_sel = self.file_listbox.curselection()
        if not current_sel:
            next_idx = self.file_listbox.size() - 1
        else:
            next_idx = current_sel[0] - 1
            if next_idx < 0:
                next_idx = self.file_listbox.size() - 1 
                
        self.file_listbox.selection_clear(0, tk.END)
        self.file_listbox.selection_set(next_idx)
        self.file_listbox.activate(next_idx)
        self.file_listbox.see(next_idx)
        self.refresh_markdown_preview()
        return "break"

    # ---------------------------------------------------------
    # Copy & Visibility Actions
    # ---------------------------------------------------------

    def on_enter_pressed(self, event=None):
        current_sel = self.file_listbox.curselection()
        if not current_sel:
            if self.file_listbox.size() > 0:
                self.file_listbox.selection_set(0)
                current_sel = (0,)
            else:
                return "break"
                
        idx = current_sel[0]
        filename = self.file_listbox.get(idx)
        
        file_path = self.watcher.get_absolute_path(filename)
        success, msg = copy_snippet_to_clipboard(file_path)
        
        if success:
            print(f"[Copied] {filename} copied to clipboard.")
            if AUTO_PASTE:
                self.hide_window_animated(after_hidden=self.auto_paste_clipboard)
            else:
                self.hide_window_animated()
        else:
            print(f"[Error] Failed to copy {filename}: {msg}", file=sys.stderr)
            self.root.configure(highlightbackground="#f38ba8")
            self.root.after(500, lambda: self.root.configure(highlightbackground=self.accent_active))
        return "break"

    def auto_paste_clipboard(self):
        """Waits briefly for focus to return, then pastes the copied snippet."""
        def do_paste():
            success, msg = paste_clipboard_into_active_window()
            if success:
                print("[Pasted] Snippet pasted into active window.")
            else:
                print(f"[Paste Error] Failed to paste snippet: {msg}", file=sys.stderr)

        self.root.after(AUTO_PASTE_DELAY_MS, do_paste)

    # ---------------------------------------------------------
    # On-the-Fly Snippet Creator Logic (Ctrl + Alt + N)
    # ---------------------------------------------------------

    def safe_trigger_creator(self):
        log_event("Creator hotkey callback received.")
        if not self.should_accept_hotkey("creator"):
            log_event("Creator hotkey ignored by debounce.")
            return
        self.root.after(0, self.capture_selection_for_snippet)

    def capture_selection_for_snippet(self):
        previous_clipboard = pyperclip.paste()
        sentinel = "__ANTIGRAVITY_SNIPPET_EMPTY_SELECTION__"

        self.root.after(
            SELECTION_CAPTURE_DELAY_MS,
            lambda: self.copy_selection_then_prompt(previous_clipboard, sentinel, 0)
        )

    def copy_selection_then_prompt(self, previous_clipboard, sentinel, elapsed_ms,
                                     last_seen=None, stable_count=0):
        """Polls clipboard after Ctrl+C with stabilization to avoid grabbing
        transient data (e.g. a browser URL) before the real text arrives."""
        STABLE_POLLS_REQUIRED = 2  # clipboard must be unchanged for this many consecutive polls
        try:
            if elapsed_ms == 0:
                pyperclip.copy(sentinel)
                # Temporarily ignore SIGINT so the synthetic Ctrl+C
                # doesn't kill our own process on non-Windows platforms.
                prev_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
                try:
                    # Release any modifier keys still held from the creator
                    # hotkey press so the OS sees a clean Ctrl+C, not
                    # Ctrl+Shift+C (which opens DevTools in browsers).
                    for mod in ("shift", "ctrl", "alt"):
                        try:
                            keyboard.release(mod)
                        except Exception:
                            pass
                    time.sleep(0.03)  # brief settle time for the OS input queue
                    keyboard.press_and_release("ctrl+c")
                finally:
                    signal.signal(signal.SIGINT, prev_handler)

            copied_text = pyperclip.paste()

            if copied_text != sentinel:
                # Clipboard has changed — but is it stable yet?
                if copied_text == last_seen:
                    new_stable = stable_count + 1
                else:
                    new_stable = 1

                if new_stable >= STABLE_POLLS_REQUIRED:
                    # Content hasn't changed between polls — accept it
                    self.prompt_create_snippet(copied_text, previous_clipboard)
                    return

                # Not yet stable; keep polling
                if elapsed_ms < SELECTION_COPY_TIMEOUT_MS:
                    self.root.after(
                        SELECTION_COPY_POLL_MS,
                        lambda: self.copy_selection_then_prompt(
                            previous_clipboard,
                            sentinel,
                            elapsed_ms + SELECTION_COPY_POLL_MS,
                            last_seen=copied_text,
                            stable_count=new_stable
                        )
                    )
                    return

            if elapsed_ms < SELECTION_COPY_TIMEOUT_MS:
                self.root.after(
                    SELECTION_COPY_POLL_MS,
                    lambda: self.copy_selection_then_prompt(
                        previous_clipboard,
                        sentinel,
                        elapsed_ms + SELECTION_COPY_POLL_MS,
                        last_seen=copied_text,
                        stable_count=0
                    )
                )
                return

            pyperclip.copy(previous_clipboard)
            print("[Creator Error] No highlighted text was copied.", file=sys.stderr)
            if self.is_visible:
                self.root.configure(highlightbackground="#f38ba8")
                self.root.after(500, lambda: self.root.configure(highlightbackground=self.accent_active))
        except Exception as e:
            pyperclip.copy(previous_clipboard)
            print(f"[Creator Error] Failed to copy highlighted text: {e}", file=sys.stderr)

    def prompt_create_snippet(self, copied_text, previous_clipboard=None):
        if not copied_text or not copied_text.strip():
            if previous_clipboard is not None:
                pyperclip.copy(previous_clipboard)
            print("[Creator Error] Highlighted selection is empty or contains non-text data.", file=sys.stderr)
            if self.is_visible:
                self.root.configure(highlightbackground="#f38ba8")
                self.root.after(500, lambda: self.root.configure(highlightbackground=self.accent_active))
            return

        def handle_snippet_name(name):
            clean_name = "".join([c for c in name if c.isalnum() or c in (" ", "-", "_")]).strip()
            if not clean_name:
                return
            
            filename = f"{clean_name}.md" if not clean_name.lower().endswith(".md") else clean_name
            file_path = os.path.join(self.watcher.directory_path, filename)
            
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(copied_text)
                print(f"[Created] Snippet '{filename}' successfully saved.")
                
                self.watcher.scan_files()
                self.update_listbox()
            except Exception as e:
                print(f"[Creator Error] Failed to write snippet: {e}", file=sys.stderr)

        SnippetCreateDialog(self.root, handle_snippet_name)

    # ---------------------------------------------------------
    # Thread-Safe Toggle Logic & Animations
    # ---------------------------------------------------------

    def safe_toggle(self):
        log_event("Toggle hotkey callback received.")
        if not self.should_accept_hotkey("toggle"):
            log_event("Toggle hotkey ignored by debounce.")
            return
            
        self.root.after(0, self.toggle_visibility)

    def should_accept_hotkey(self, action):
        now = time.monotonic()
        if action == "toggle":
            if now - self.last_toggle_hotkey_time < HOTKEY_DEBOUNCE_SECONDS:
                return False
            self.last_toggle_hotkey_time = now
            return True

        if action == "creator":
            if now - self.last_creator_hotkey_time < HOTKEY_DEBOUNCE_SECONDS:
                return False
            self.last_creator_hotkey_time = now
            return True

        return True

    def toggle_visibility(self):
        if self.animating:
            return
            
        if self.is_visible:
            self.hide_window_animated()
        else:
            self.watcher.scan_files()
            self.update_listbox()
            self.show_window_animated()

    def show_window_animated(self):
        self.animating = True
        self.root.deiconify()
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', 1.0)
        self.focus_search()
        self.is_visible = True
        self.app_has_focus = True
        self.fade_in(0.0)

    def hide_window_animated(self, after_hidden=None):
        self.animating = True
        if after_hidden:
            self.after_hide_callbacks.append(after_hidden)
        self.fade_out(1.0)

    def fade_in(self, alpha):
        if alpha <= 1.0:
            self.root.attributes('-alpha', alpha)
            self.root.after(12, lambda: self.fade_in(alpha + 0.15))
        else:
            self.root.attributes('-alpha', 1.0)
            self.animating = False

    def fade_out(self, alpha):
        if alpha >= 0.0:
            self.root.attributes('-alpha', alpha)
            self.root.after(12, lambda: self.fade_out(alpha - 0.15))
        else:
            self.root.attributes('-alpha', 0.0)
            self.root.withdraw()
            self.is_visible = False
            self.app_has_focus = False
            self.animating = False
            callbacks = self.after_hide_callbacks
            self.after_hide_callbacks = []
            for callback in callbacks:
                callback()

    def on_closing(self):
        if self.tray_controller:
            self.tray_controller.stop()
        try:
            self.hotkey_manager.unbind_all()
        except Exception:
            pass
        self.root.destroy()


# ---------------------------------------------------------
# Robust Hardware-Level Hotkey Binding Manager
# ---------------------------------------------------------

class HotkeyManager:
    def __init__(self):
        self.bound = {}
        self.callbacks = {}
        self._global_listener_hook = None

    def bind(self, role, hotkey_string, callback):
        self.bound[role] = hotkey_string.strip().lower()
        self.callbacks[role] = callback
        log_event(f"Registered physical hotkey match tracker for '{role}': {hotkey_string}")
        
        # Instantiate a single, clean global input hooks monitor
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


def start_keyboard_listener(app):
    try:
        app.hotkey_manager.bind("launcher", app.config["hotkey_launcher"], app.safe_toggle)
        app.hotkey_manager.bind("creator", app.config["hotkey_creator"], app.safe_trigger_creator)
        log_event("Hardware-linked keyboard hook is waiting for triggers.")
    except Exception as e:
        log_event(f"Listener error: {e}")
        if SYSTEM != 'darwin':
            app.root.after(0, lambda: messagebox.showerror(
                "Hotkey Listener Error",
                f"A permission or system error occurred with the keyboard listener:\n\n{e}"
            ))


# ---------------------------------------------------------
# 7. Windows Startup Registration
# ---------------------------------------------------------

def get_background_python_executable():
    executable = sys.executable
    if SYSTEM == "windows" and os.path.basename(executable).lower() == "python.exe":
        pythonw = os.path.join(os.path.dirname(executable), "pythonw.exe")
        if os.path.exists(pythonw):
            return pythonw
    return executable


def get_windows_startup_file():
    if SYSTEM != "windows":
        return None

    startup_dir = os.path.join(
        os.environ.get("APPDATA", ""),
        "Microsoft",
        "Windows",
        "Start Menu",
        "Programs",
        "Startup"
    )
    if not startup_dir.strip() or not os.path.isdir(startup_dir):
        return None

    return os.path.join(startup_dir, "Antigravity Markdown Snippet Launcher.bat")


def sync_windows_startup_registration(enabled=None):
    if SYSTEM != "windows":
        return

    if enabled is None:
        enabled = START_WITH_WINDOWS

    startup_file = get_windows_startup_file()
    if not startup_file:
        print("[Startup] Could not locate the Windows Startup folder.", file=sys.stderr)
        return

    if not enabled:
        if os.path.exists(startup_file):
            try:
                os.remove(startup_file)
                print("[Startup] Windows startup entry removed.")
            except Exception as e:
                print(f"[Startup Error] Failed to remove startup entry: {e}", file=sys.stderr)
        return

    script_path = os.path.abspath(__file__)
    python_executable = get_background_python_executable()
    startup_args = " --startup" if START_HIDDEN_ON_WINDOWS_STARTUP else ""
    startup_contents = (
        "@echo off\n"
        f'start "" "{python_executable}" "{script_path}"{startup_args}\n'
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
# 8. System Tray Integration
# ---------------------------------------------------------

class SystemTrayController:
    def __init__(self, app):
        self.app = app
        self.icon = None
        self.thread = None
        self.is_stopping = False

    def start(self):
        if pystray is None:
            log_event("System tray unavailable. Install pystray and Pillow to enable it.")
            return

        self.icon = pystray.Icon(
            "antigravity_markdown_launcher",
            self.create_icon_image(),
            "Antigravity Markdown Snippet Launcher",
            self.create_menu()
        )
        self.thread = threading.Thread(target=self.run_icon, name="SystemTrayIcon", daemon=True)
        self.thread.start()
        log_event("System tray icon started.")

    def run_icon(self):
        try:
            self.icon.run()
        except Exception as e:
            log_event(f"System tray icon stopped unexpectedly: {e}")

    def create_menu(self):
        return pystray.Menu(
            pystray.MenuItem("Open Launcher", self.open_launcher),
            pystray.MenuItem("Settings", self.open_settings),
            pystray.MenuItem(
                "Run at Startup",
                self.toggle_run_at_startup,
                checked=lambda item: self.app.is_run_at_startup_enabled()
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self.exit_application),
        )

    def create_icon_image(self):
        image = Image.new("RGBA", (64, 64), (24, 24, 37, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((8, 8, 56, 56), radius=12, fill=(24, 24, 37, 255), outline=(203, 166, 247, 255), width=3)
        draw.rectangle((20, 22, 44, 27), fill=(205, 214, 244, 255))
        draw.rectangle((20, 33, 38, 38), fill=(166, 227, 161, 255))
        draw.rectangle((20, 44, 48, 49), fill=(245, 194, 231, 255))
        return image

    def schedule_on_ui_thread(self, callback):
        try:
            self.app.root.after(0, callback)
        except Exception as e:
            log_event(f"Failed to schedule tray action: {e}")

    def open_launcher(self, icon=None, item=None):
        self.schedule_on_ui_thread(self.app.open_launcher_from_tray)

    def open_settings(self, icon=None, item=None):
        self.schedule_on_ui_thread(self.app.open_settings_from_tray)

    def toggle_run_at_startup(self, icon=None, item=None):
        enabled = not self.app.is_run_at_startup_enabled()
        self.schedule_on_ui_thread(lambda: self.app.set_run_at_startup(enabled))

    def exit_application(self, icon=None, item=None):
        self.schedule_on_ui_thread(self.app.on_closing)

    def refresh_menu(self):
        if self.icon:
            try:
                self.icon.update_menu()
            except Exception as e:
                log_event(f"Failed to refresh tray menu: {e}")

    def stop(self):
        if self.is_stopping:
            return
        self.is_stopping = True
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass


# ---------------------------------------------------------
# 9. Main Entry Point
# ---------------------------------------------------------

def main():
    print("Starting Antigravity Markdown Snippet Launcher...")
    config = load_application_config()
    print(f"Snippet directory: {config['snippet_directory']}")
    print(f"Launcher Hotkey configured: {config['hotkey_launcher']}")
    print(f"Creator Hotkey configured: {config['hotkey_creator']}")

    sync_windows_startup_registration(config.get("run_at_startup", START_WITH_WINDOWS))
    
    watcher = SnippetWatcher(config["snippet_directory"])
    root = tk.Tk()
    app = BorderlessSnippetLauncher(root, watcher, config)

    # Initial boot allocation
    if "--startup" in sys.argv and START_HIDDEN_ON_WINDOWS_STARTUP:
        root.attributes('-alpha', 0.0)
        root.withdraw()
        app.is_visible = False
        app.animating = False
    
    start_keyboard_listener(app)
    app.tray_controller = SystemTrayController(app)
    app.tray_controller.start()
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\nExiting application...")
        try:
            app.hotkey_manager.unbind_all()
        except Exception:
            pass


if __name__ == '__main__':
    main()
