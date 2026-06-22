# MarkStash

<p align="left">
  <img src="markstash_badge.png" width="96" alt="MarkStash icon">
</p>

**MarkStash - By inianexe** is a Windows Markdown snippet launcher. It lets you save useful text, commands, templates, notes, screenshots, and code snippets as `.md` files, then search and paste them anywhere with a hotkey.

![MarkStash launcher screenshot](ss%20fol.png)

## Recommended Setup

MarkStash is portable, so it works best when you keep the EXE in a normal writable folder.

Recommended app folder:

```text
D:\Apps\MarkStash
```

Recommended snippet folder:

```text
D:\Markdown Project Foler (DO NOT DELETE)
```

Your final setup should look like this:

```text
D:\Apps\MarkStash\
  MarkStash.exe
  config.yaml
  hotkey_debug.log

D:\Markdown Project Foler (DO NOT DELETE)\
  CPU GPU.md
  WiFi Networks.md
  work\
    email reply.md
  assets\
    screenshot-example.png
```

Avoid storing the EXE in:

```text
C:\Program Files
C:\Program Files (x86)
C:\Windows
Temporary folders
```

Those folders can block MarkStash from writing `config.yaml`, logs, backups, and runtime files.

## Install

1. Download `MarkStash.exe`.
2. Create this folder:

```text
D:\Apps\MarkStash
```

3. Move `MarkStash.exe` into that folder.
4. Double-click `MarkStash.exe`.
5. MarkStash will create or use `config.yaml` beside the EXE.
6. Open MarkStash Settings.
7. Set your snippet folder to:

```text
D:\Markdown Project Foler (DO NOT DELETE)
```

8. Save settings.
9. Exit the old tray process if one is already running, then reopen the EXE.

## Config File

MarkStash reads `config.yaml` from the same folder as `MarkStash.exe`.

Example:

```text
D:\Apps\MarkStash\MarkStash.exe
D:\Apps\MarkStash\config.yaml
```

In this development repo, the packaged build is here:

```text
D:\Projects\Markdown\dist_creator\MarkStash.exe
D:\Projects\Markdown\dist_creator\config.yaml
```

Important config keys:

```yaml
snippet_directory: D:\Markdown Project Foler (DO NOT DELETE)
hotkey_launcher: ctrl+shift+x
hotkey_creator: ctrl+alt+v
theme_mode: dark
theme_palette: Mocha Terminal
window_width: 1000
window_height: 540
window_opacity: 1.0
spawn_near_cursor: true
always_on_top: false
show_badge: true
show_credit: true
show_resize_grip: true
shadow_size: 5
corner_radius: 0
```

After editing `config.yaml`, hide and reopen the launcher or trigger the creator again. MarkStash reloads config before opening the launcher and creator.

## Main Features

- Global launcher hotkey
- Global creator hotkey
- Create snippets from selected text
- Create empty snippets
- Screenshot snippets from clipboard images
- Markdown preview
- Filename search
- Content search
- Folder filtering
- Tag filtering
- Favorites
- Recent snippets
- Usage count tracking
- Rename snippets
- Move snippets between folders
- Safe delete into `.trash`
- Duplicate detection
- Template placeholders
- Fill-in form before paste
- Dynamic variables
- Text expander aliases
- File watcher live refresh
- Backup/export zip
- Command palette
- Light and dark themes
- Named color palettes
- Fully editable YAML styling
- Tray integration
- Startup option
- Resizable launcher
- Spawn near cursor option

## Launcher Usage

Press the launcher hotkey, usually:

```text
ctrl+shift+x
```

Then:

```text
Type search text     Filter snippets
Arrow keys           Move selection
Enter                Copy/paste selected snippet
Esc                  Hide launcher
Ctrl+N               New empty snippet
Ctrl+E               Edit/open selected snippet
F2                   Rename selected snippet
Delete               Move snippet to .trash
Ctrl+B               Backup/export snippets
Ctrl+P               Command palette
Ctrl+R               Refresh snippets
Ctrl+L               Clear search
Ctrl+O               Open snippet folder
Ctrl+Shift+S         Create screenshot snippet from clipboard image
```

![MarkStash launcher with snippets and preview](ss%20fol.png)

## Creator Usage

Highlight text in any app, then press the creator hotkey:

```text
ctrl+alt+v
```

The creator popup opens with:

- Snippet name box
- Live selected text preview
- Character/word/line count
- Folder-aware naming
- Duplicate warning
- Open after save option
- Copy path option

You can create folders by typing a path:

```text
work/email/reply
```

This creates:

```text
D:\Markdown Project Foler (DO NOT DELETE)\work\email\reply.md
```

![MarkStash creator popup](ss%20creator.png)

## Screenshot Snippets

1. Take a screenshot with any Windows screenshot tool.
2. Copy the screenshot to clipboard.
3. Open MarkStash.
4. Press `Ctrl+Shift+S`.
5. Name the screenshot snippet.

MarkStash saves:

```text
assets\your-image.png
your-snippet.md
```

The Markdown file embeds the image.

## Tags And Folders

Use Markdown frontmatter at the top of a snippet:

```markdown
---
tags: [powershell, work]
aliases: [;cpu]
---

Get-CimInstance Win32_Processor
```

`tags` appear in the tag filter.

Folders appear in the folder filter.

Aliases are used by text expander mode.

## Text Expander

Add an alias in frontmatter:

```markdown
---
aliases: [;sig]
---

Regards,
inian.exe
```

When MarkStash is running, typing:

```text
;sig
```

can expand into the snippet content.

## Template Placeholders

Snippets can contain placeholders:

```text
Hello {name}, your meeting is on {date}.
```

Built-in dynamic variables:

```text
{date}
{time}
{datetime}
{username}
{clipboard}
```

Custom placeholders like `{name}` show a prompt before paste.

## Themes And Palettes

Open Settings and choose:

```text
THEME: dark / light
COLOR PALETTE: named palette
```

Dark palettes:

```text
Mocha Terminal
Emerald Console
Royal Berry
Nord Pine
Plum Dusk
Deep Harbor
Indigo Neon
Graphite Mint
```

Light palettes:

```text
Rose Milk
Cotton Candy
Lemon Sky
Aqua Citrus
Soft Linen
Matcha Glass
Peach Memo
Sage Paper
```

Choose `Custom YAML` if you want to manually edit exact colors in `config.yaml`.

The selected theme affects both:

- Launcher
- Creator popup

## Backup

Press:

```text
Ctrl+B
```

MarkStash creates a zip backup beside the app folder. The backup includes snippets and config.

## Safe Delete

Deleting a snippet does not permanently remove it. MarkStash moves it into:

```text
.trash
```

inside your snippet folder.

## Build From Source

From the project folder:

```powershell
python -m PyInstaller --clean --noconfirm --distpath dist_creator MarkStash.spec
```

Output:

```text
dist_creator\MarkStash.exe
```

The build is configured to:

- Use the app `.ico`
- Include `pngwing.com.ico` as the executable icon
- Include the badge PNG
- Disable UPX compression
- Extract beside the EXE instead of relying only on `%TEMP%`

## Troubleshooting

If config changes do not work:

1. Make sure you edited the `config.yaml` beside the EXE you launched.
2. Exit MarkStash from the tray.
3. Reopen the correct `MarkStash.exe`.
4. Open Settings and Save once.

If colors only affect the launcher:

1. Use the latest rebuilt EXE.
2. Exit any older tray process.
3. Reopen MarkStash.

If hotkeys do not work:

1. Avoid Windows reserved shortcuts.
2. Use `ctrl+shift+x` for launcher.
3. Use `ctrl+alt+v` or `ctrl+shift+b` for creator.
4. Check `hotkey_debug.log`.

If the EXE shows a decompression error:

1. Clear space on `C:\`.
2. Clear `%TEMP%`.
3. Keep MarkStash on `D:\Apps\MarkStash`.
4. Use the latest EXE built without UPX.

If MarkStash opens from the wrong folder:

1. Search for old `MarkStash.exe` copies.
2. Delete or ignore old builds.
3. Keep one main copy in:

```text
D:\Apps\MarkStash
```

## Suggested Final Release Files

For a clean release, include:

```text
MarkStash.exe
config.yaml
README.md
```

The user can then create or choose their own snippet folder on `D:\`.
