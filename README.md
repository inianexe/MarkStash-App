# MarkStash

MarkStash is a Windows snippet launcher for saving, searching, and pasting Markdown snippets with global hotkeys.

## Install From Releases

1. Download the latest `MarkStash.exe` from the GitHub Releases page.
2. Copy `MarkStash.exe` into a normal folder, for example:

   ```text
   D:\Apps\MarkStash
   ```

   Do not put it inside `C:\Program Files`. Windows can restrict app-created files there, which may stop MarkStash from creating its config and log files.

3. Double-click `MarkStash.exe` once.
4. On first launch, MarkStash creates files next to the exe, including:

   ```text
   config.yaml
   hotkey_debug.log
   ```

5. Open MarkStash, go to Settings, and change the snippet save location to the folder where you want your Markdown files to be stored.
6. In Settings, change the hotkeys from `AltGr` combinations to safer shortcuts such as:

   ```text
   ctrl+shift+x
   ctrl+shift+b
   ```

   `AltGr` can behave differently across keyboards and languages, so `Ctrl + Shift` hotkeys are recommended.

## Usage

- Use the launcher hotkey to show or hide MarkStash.
- Use the creator hotkey to create a new snippet from selected text.
- Change hotkeys, startup behavior, and snippet folder location from Settings inside the app.

## Startup

If Run at Startup is enabled, MarkStash adds a Startup entry for your Windows user account. On sign-in, it starts hidden in the background until you press the launcher hotkey.

## Troubleshooting

If MarkStash does not open:

1. Make sure the exe is in a writable folder, not `C:\Program Files`.
2. Check `hotkey_debug.log` next to the exe.
3. If `startup_crash.log` exists next to the exe, open it to see the startup error.
4. Close any existing MarkStash process from Task Manager, then open `MarkStash.exe` again.
