# MarkStash

<img src="pngwing.com.ico" width="48" alt="MarkStash icon">

MarkStash is a Windows Markdown snippet launcher. It lets you keep a folder of `.md` snippets, search them with a global hotkey, preview the contents, paste snippets into the active app, and create new snippets from selected text.

![MarkStash launcher showing a saved Pokemon snippet](ss%20fol.png)

## What MarkStash Creates

MarkStash is a portable app. It stores its runtime files next to `MarkStash.exe`, so the folder that contains the exe must be writable.

After the first launch, MarkStash may create these files beside the exe:

```text
config.yaml
hotkey_debug.log
startup_crash.log
```

- `config.yaml` stores settings such as hotkeys, startup behavior, always-on-top, window size, and your snippet folder.
- `hotkey_debug.log` records hotkey startup and reload events.
- `startup_crash.log` is only created if the app crashes during startup.

## Install From Releases

1. Go to the GitHub Releases page for MarkStash.
2. Download the latest `MarkStash.exe`.
3. Create a normal writable folder for the app, for example:

   ```text
   D:\Apps\MarkStash
   ```

4. Copy `MarkStash.exe` into that folder.
5. Do not put the exe inside:

   ```text
   C:\Program Files
   C:\Program Files (x86)
   C:\Windows
   ```

   Those folders are protected by Windows. MarkStash needs permission to create `config.yaml` and log files next to the exe, so a normal folder on `D:` or inside your user folder is safer.

6. Double-click `MarkStash.exe` once.
7. Wait a few seconds. MarkStash should create `config.yaml` and `hotkey_debug.log` next to the exe.

## First Launch Checklist

After opening the exe for the first time:

1. Open MarkStash with the launcher hotkey.
2. Click the Settings button.
3. Change the snippet save location to the folder where you want your Markdown files to live.
4. Change the hotkeys from `AltGr` shortcuts to `Ctrl + Shift` shortcuts.
5. Save settings.
6. Close and reopen MarkStash if the hotkeys do not immediately respond.

## Choose a Snippet Folder

Your snippet folder is where MarkStash reads and writes Markdown files.

Recommended examples:

```text
D:\Markdown Snippets
D:\Notes\Snippets
C:\Users\YourName\Documents\MarkStash
```

Avoid:

```text
C:\Program Files
C:\Windows
Temporary folders
Cloud folders that are still syncing
```

Rules for the snippet folder:

- Pick a folder you control and can write to.
- Keep the folder in a stable location. If you move it, update the path in Settings.
- MarkStash can create missing folders inside the selected snippet folder when you save nested snippets.
- Existing `.md` files in the folder can be searched by MarkStash.
- Non-Markdown files are not the main target; keep snippets as `.md` files.

## Folder Creation and Nested Snippets

When creating a snippet, the name field can include folders.

Example:

```text
pokemon/about
```

MarkStash saves that as:

```text
pokemon/about.md
```

inside your selected snippet folder.

For example, if your snippet folder is:

```text
D:\Markdown Project Folder
```

and you create:

```text
pokemon/about
```

the final file becomes:

```text
D:\Markdown Project Folder\pokemon\about.md
```

![MarkStash creator saving a nested Pokemon snippet](ss%20creator.png)

Snippet naming rules:

- You can type a simple name such as `email reply`.
- You can type a nested path such as `work/email/reply`.
- You do not need to add `.md`; MarkStash adds it automatically.
- Avoid empty names.
- Avoid names that are only dots, such as `.` or `..`.
- Use normal letters, numbers, spaces, hyphens, underscores, and dots.
- Do not try to escape outside the selected snippet folder; MarkStash blocks unsafe paths.
- If a file with the same name already exists, MarkStash will not overwrite it.

## Recommended Hotkeys

Some builds or configs may start with `AltGr` hotkeys such as:

```text
alt gr+m
alt gr+n
```

You should change them in Settings to `Ctrl + Shift` shortcuts, for example:

```text
ctrl+shift+x
ctrl+shift+b
```

Why:

- `AltGr` behaves differently on different keyboard layouts.
- Some laptops and international keyboards treat `AltGr` as `Ctrl + Alt`.
- `Ctrl + Shift` shortcuts are usually more predictable on Windows.

Hotkey rules:

- Use at least one modifier key.
- Safer examples are `ctrl+shift+x`, `ctrl+shift+b`, and `ctrl+alt+f8`.
- Avoid reserved Windows shortcuts such as `alt+tab`, `alt+f4`, `ctrl+alt+delete`, `ctrl+shift+esc`, `windows+r`, and `windows+l`.
- Avoid common editing shortcuts such as `ctrl+c`, `ctrl+v`, `ctrl+x`, `ctrl+z`, `ctrl+a`, and `ctrl+s`.
- If a hotkey does not work, choose another combination and save settings again.

## Basic Usage

- Press the launcher hotkey to show or hide MarkStash.
- Search by snippet name, tag, or folder.
- Use arrow keys to select a result.
- Press Enter to copy and paste the selected snippet.
- Press Escape to dismiss the launcher.
- Press the creator hotkey to create a new snippet from selected text.
- Use Settings to change hotkeys, snippet folder, startup behavior, theme colors, and window size.

## Creating a Snippet From Selected Text

1. Highlight text in a browser, editor, PDF, or another app.
2. Press the creator hotkey.
3. Enter a snippet name.
4. Use `/` in the name if you want MarkStash to create folders.
5. Click Save.

Example:

```text
figma/button-states
```

creates:

```text
figma\button-states.md
```

## Run at Startup

If Run at Startup is enabled, MarkStash creates a Startup entry for your Windows user account.

On Windows sign-in:

1. MarkStash starts in the background.
2. The launcher window stays hidden.
3. Press the launcher hotkey to show it.

If you move `MarkStash.exe` to a different folder, open the app once from the new folder so it can refresh the Startup entry.

## Always on Top

The release build can keep MarkStash above other windows when it opens. This is controlled by:

```yaml
always_on_top: true
```

in `config.yaml`.

Set it to `false` if you do not want the launcher to stay above other windows.

## Troubleshooting

If MarkStash opens as a blank window:

1. Make sure you are using the latest release exe.
2. Make sure the exe is in a writable folder.
3. Close MarkStash from Task Manager.
4. Open `MarkStash.exe` again.

If hotkeys do not work:

1. Open `config.yaml` and check `hotkey_launcher` and `hotkey_creator`.
2. Prefer `ctrl+shift+x` and `ctrl+shift+b`.
3. Check `hotkey_debug.log` next to the exe.
4. Close any existing MarkStash process from Task Manager.
5. Open `MarkStash.exe` again.

If the app does not start:

1. Check whether `startup_crash.log` exists next to the exe.
2. Move the exe to a normal writable folder such as `D:\Apps\MarkStash`.
3. Do not run it from `C:\Program Files`.
4. Restart Windows if an old background copy is stuck.

## Important Rules to Tell Users

- Download `MarkStash.exe` from Releases.
- Copy it to a writable folder such as `D:\Apps\MarkStash`.
- Do not place it in `Program Files`.
- Double-click the exe once before changing settings.
- Let it create `config.yaml` and logs next to the exe.
- Open Settings and choose the folder where snippets should be saved.
- Use nested names like `folder/snippet-name` to create folders automatically.
- Change `AltGr` hotkeys to `Ctrl + Shift` hotkeys.
- If Run at Startup is enabled, launch the app once after moving the exe so the Startup entry points to the correct folder.
