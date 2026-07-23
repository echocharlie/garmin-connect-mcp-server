# Quickstart (no coding experience needed)

This guide gets Claude Desktop talking to your Garmin data in about 10 minutes.
You'll copy and paste a few commands into Terminal — that's it.

**You need:** a Mac or Windows PC, your Garmin Connect email + password, and the
[Claude Desktop app](https://claude.ai/download) (free account is fine).

---

## Step 1 — Get the code

1. On this project's GitHub page, click the green **Code** button → **Download ZIP**.
2. Unzip it, and move the `garmin-connect-mcp-server` folder somewhere permanent,
   like your **Documents** folder. (Don't leave it in Downloads — if you delete or
   move it later, Claude loses the connection.)

## Step 2 — Open a terminal in that folder

- **Mac:** open the **Terminal** app (press `Cmd+Space`, type "Terminal", press Enter).
- **Windows:** open **PowerShell** (press the Windows key, type "PowerShell", press Enter).

Then type `cd ` (with a space after it), drag the `garmin-connect-mcp-server` folder
from Finder/Explorer onto the terminal window, and press **Enter**.

## Step 3 — Install (one time)

Check you have Python by pasting this and pressing Enter — on **Mac**:

```bash
python3 --version
```

On **Windows** (the `python3` command doesn't exist there):

```powershell
py --version
```

If it prints `Python 3.12` or higher, you're good. If not, install Python from
[python.org/downloads](https://www.python.org/downloads/) first — on Windows, tick
**"Add python.exe to PATH"** during install, then close and reopen the terminal.

Now paste this (Mac):

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

On **Windows**, paste this instead:

```powershell
py -m venv .venv; .venv\Scripts\pip install -r requirements.txt
```

Wait for it to finish (a minute or two of scrolling text is normal).

## Step 4 — Sign in to Garmin (one time)

Mac:

```bash
.venv/bin/python login.py
```

Windows:

```powershell
.venv\Scripts\python login.py
```

Type your Garmin Connect email, then your password (**the password stays invisible
while you type — that's normal**), and an MFA code if Garmin emails you one.

When you see **"Logged in as … Tokens saved"**, you're done. Your password is not
saved anywhere — just a long-lived login token that renews itself as you use it. If
Claude ever says your Garmin login expired, redo this step.

> **If you see "Garmin is rate limiting login attempts" or "Too many login
> attempts":** Garmin is temporarily blocking logins from your internet connection.
> Wait an hour and try again (or connect to a different network, like your phone's
> hotspot).

## Step 5 — Connect Claude Desktop

First, find the folder's full path. In the same terminal, paste:

- Mac: `pwd`   — Windows: `(Get-Location).Path`

It prints something like `/Users/alex/Documents/garmin-connect-mcp-server`. Copy it —
you'll need it for either option below.

### Option A (easiest): ask Claude to do it

Open Claude — ideally **Claude Code** (in the Claude Desktop app or by typing `claude`
in this same terminal, if you have it) or Claude Desktop with file access turned on —
and paste this, putting your folder path on the last line:

```text
Please connect a local MCP server to my Claude Desktop:

1. Open my claude_desktop_config.json
   (macOS: ~/Library/Application Support/Claude/claude_desktop_config.json,
   Windows: %APPDATA%\Claude\claude_desktop_config.json).
   Create it if it doesn't exist.
2. Under "mcpServers", add an entry named "garmin" with:
   - "command": the absolute path to .venv/bin/python inside my project folder
     (on Windows: .venv\Scripts\python.exe)
   - "args": a list containing the absolute path to server.py in that folder
   Keep any existing servers in the file, and make sure the JSON stays valid.
3. If you can't edit files directly, show me exactly what the finished file
   should contain and tell me where to paste it.

My project folder is at: [PASTE YOUR FOLDER PATH HERE]
```

When Claude says it's done, go straight to **"Finish: restart Claude Desktop"** below.

### Option B (manual): edit the config file yourself

1. Open **Claude Desktop** → **Settings** → **Developer** → **Edit Config**. This
   opens a file called `claude_desktop_config.json` in a text editor.
2. Replace its contents with the block below — **but swap both
   `/YOUR/PATH/HERE` parts for the path you copied above**. (If the file already has
   other servers listed inside `"mcpServers"`, just add the `"garmin"` part alongside
   them with a comma between entries.)

   Mac:

   ```json
   {
     "mcpServers": {
       "garmin": {
         "command": "/YOUR/PATH/HERE/.venv/bin/python",
         "args": ["/YOUR/PATH/HERE/server.py"]
       }
     }
   }
   ```

   Windows (note the double backslashes and `Scripts` instead of `bin`):

   ```json
   {
     "mcpServers": {
       "garmin": {
         "command": "C:\\YOUR\\PATH\\HERE\\.venv\\Scripts\\python.exe",
         "args": ["C:\\YOUR\\PATH\\HERE\\server.py"]
       }
     }
   }
   ```

3. Save the file.

### Finish: restart Claude Desktop

**Fully quit Claude Desktop** (Mac: `Cmd+Q`; Windows: right-click the tray icon →
Quit) and open it again — it only reads the config when it starts.

## Step 6 — Try it

Ask Claude things like:

- *"How did I sleep this week?"*
- *"Show my workouts from the last month."*
- *"How's my training load and recovery looking?"*
- *"What's my weight trend this month?"*

The first time, Claude may ask permission to use the `garmin` tools — allow it.

---

## If something's not working

| Problem | Fix |
|---|---|
| Claude doesn't mention Garmin at all | The config file likely has a typo — every `{ } " ,` matters. Redo Step 5 carefully, then fully quit and reopen Claude. |
| "Garmin Connect authentication failed" | Redo Step 4. |
| Everything shows `-` or "No activities" | Your Garmin account has no synced data for that time period. Sleep/HRV/stress need a Garmin watch. |
| "Too many login attempts" / rate limiting | Wait an hour, or switch to another network, then retry Step 4. |

Nothing here can change or delete anything in your Garmin account — the connection is
read-only.
