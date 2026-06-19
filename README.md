# MarkStash

MarkStash is a small Windows markdown snippet launcher. It stays in your tray, opens with a global hotkey, lets you search your `.md` files, and pastes the selected snippet into whatever app you are using.

It is built for people who reuse commands, notes, prompts, code blocks, support replies, templates, or setup instructions every day.

## Features

- Global launcher hotkey for fast snippet search.
- Creator hotkey for turning highlighted text into a new snippet.
- Markdown preview with headings, lists, inline code, and code blocks.
- Folder-based tags for organizing snippets.
- Nested snippet folders, for example `python/math/add` becomes `python/math/add.md`.
- Tray menu with show, hide, new snippet, startup toggle, snippet folder, and exit.
- Optional Windows startup launch.
- Safe hotkey validation to avoid common system shortcuts.
- Custom snippet folder location.
- Custom app size through settings or the drag resize handle.
- Custom theme colors through settings or `config.yaml`.
- Packaged `.exe` build support with PyInstaller.

## Quick Start For Users

1. Download the latest MarkStash release zip or folder.
2. Extract it somewhere permanent, for example:

   ```text
   C:\Users\<you>\Apps\MarkStash
   ```

3. Run:

   ```text
   MarkStash.exe
   ```

4. On first launch, choose:
   - Your snippet folder
   - Launcher hotkey
   - Creator hotkey
   - Startup preference
   - Theme colors if you want to customize them

5. Save settings. After that, MarkStash will open normally and will not show first-run setup every time.

## Default Shortcuts

| Action | Default shortcut |
| --- | --- |
| Open or hide launcher | `ctrl+shift+x` |
| Create snippet from selected text | `ctrl+shift+b` |
| Paste selected snippet from launcher | `Enter` |
| Close launcher or modal | `Esc` |
| Move selection in launcher | `ArrowUp` / `ArrowDown` |

You can change these in Settings or directly in `config.yaml`.

Recommended safe hotkeys:

```text
ctrl+shift+x
ctrl+shift+b
alt gr+m
alt gr+n
ctrl+alt+f8
```

Avoid common shortcuts like `ctrl+c`, `ctrl+v`, `alt+tab`, `alt+f4`, `win+r`, and `ctrl+shift+esc`.

## How To Use

### Open The Launcher

Press the launcher hotkey. Search by snippet name, folder name, tag, or snippet content. Press `Enter` to copy and paste the selected snippet into the active app.

### Create A Snippet From Selected Text

1. Highlight text in any app or browser.
2. Press the creator hotkey.
3. Enter a snippet name.
4. Click Save.

MarkStash preserves your existing clipboard after capturing the highlighted text.

### Organize Snippets With Folders

Tags are based only on real folders.

Examples:

| Name entered | File created |
| --- | --- |
| `git/status` | `git/status.md` |
| `python/newfile` | `python/newfile.md` |
| `python/math/add` | `python/math/add.md` |

Root snippets like `todo.md` do not get fake tags. Only snippets inside folders show folder tags.

## Configuration

MarkStash reads `config.yaml` from the same folder as the app.

Example:

```yaml
snippet_directory: "%USERPROFILE%\\Documents\\MarkStash"
hotkey_launcher: "ctrl+shift+x"
hotkey_creator: "ctrl+shift+b"
run_at_startup: true
enable_pinning: true
window_width: 1000
window_height: 485
theme_accent: "#7c8cff"
theme_background: "#101116"
theme_panel: "#171923"
theme_text: "#e7eaf3"
setup_complete: false
```

Notes:

- `snippet_directory` supports environment variables like `%USERPROFILE%`.
- Theme colors must be six-digit hex colors.
- If a hotkey is unsafe or invalid, MarkStash falls back to a safe default.
- `setup_complete: false` shows first-run setup. After setup is seen, the app updates it to `true`.

## Build From Source

### Requirements

- Windows 10 or newer
- Python 3.11+
- Node.js 18+
- npm

### Install And Run In Development

```powershell
npm install
python -m pip install -r requirements.txt
npm run build
python UI.py
```

### Build The Windows `.exe`

The release script installs requirements, builds the React UI, runs PyInstaller, and copies the final files into `release\MarkStash`.

```powershell
npm run package:windows
```

Or run the script directly:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_release.ps1
```

The output folder contains only:

```text
MarkStash.exe
config.yaml
```

## Project Structure

```text
UI.py                    Python app shell, tray, hotkeys, config, snippets
src/                     React frontend
scripts/build_release.ps1 Windows packaging script
MarkStash.spec           PyInstaller build config
config.yaml              User/developer runtime config
requirements.txt         Python dependencies
package.json             Frontend dependencies and scripts
pngwing.com.ico          App icon
```

## Troubleshooting

### The launcher does not open with my hotkey

Open Settings or edit `config.yaml`, choose a safer hotkey, then restart MarkStash. Some combinations are reserved by Windows or other apps.

### Startup does not work

Use the tray menu and enable `Run at Startup`. If Windows blocks access to the Startup folder, run MarkStash once as your normal user and try again.

### The creator popup captured the wrong text

Make sure the text is highlighted before pressing the creator hotkey. MarkStash waits for the hotkey keys to release, copies the selected text, and restores your clipboard.

### My snippets are not appearing

Check `snippet_directory` in Settings or `config.yaml`. MarkStash scans `.md` files recursively inside that folder.

### The app is too large or too small

Use the bottom-right resize handle or edit:

```yaml
window_width: 1000
window_height: 485
```

## Attribution

See `ATTRIBUTIONS.md` for third-party attribution notes.
