# One-paste setup prompt

Setting this up with an AI assistant? Copy the entire block below and paste it into
**Claude Cowork** or **Claude Code** on the computer where you use Claude Desktop.
It automates everything in [QUICKSTART.md](QUICKSTART.md) except the one step only
you can do: typing your Garmin password.

```text
I want to set up the Garmin Connect MCP server for Claude Desktop on this computer.
It's a small read-only tool that lets Claude see my Garmin fitness data. Please do
everything for me step by step, and tell me clearly whenever you need something only
I can do. I'm not technical — explain things in plain words, briefly.

1. CHECK THE BASICS. Detect my operating system. Check whether Python 3.12+ is
   available ("python3 --version" on Mac, "py --version" on Windows). If it's
   missing, install it for me if you can (winget on Windows, Homebrew on Mac if
   present); otherwise walk me through the python.org installer — on Windows remind
   me to tick "Add python.exe to PATH" — then re-check.

2. GET THE CODE. Download the public repository
   https://github.com/echocharlie/garmin-connect-mcp-server
   (git clone if git is available, otherwise download and unzip
   https://github.com/echocharlie/garmin-connect-mcp-server/archive/refs/heads/main.zip).
   Put the folder somewhere permanent like my Documents folder — not Downloads —
   and tell me the full path you chose.

3. INSTALL IT. Inside that folder, create a virtual environment and install the
   dependencies:
   - Mac:     python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   - Windows: py -m venv .venv     then  .venv\Scripts\pip install -r requirements.txt
   Then verify the install actually worked before moving on.

4. GARMIN SIGN-IN — THIS PART IS MINE. Never ask me for my Garmin password and never
   type it yourself; the login script refuses to run outside a real terminal anyway.
   Open a terminal in the project folder (or tell me exactly how), then have ME run:
   - Mac:     .venv/bin/python login.py
   - Windows: .venv\Scripts\python login.py
   I'll type my Garmin email, password, and MFA code myself. Wait until I confirm I
   saw "Logged in as ... Tokens saved." If I see "Too many login attempts" or
   anything about rate limiting, tell me to wait an hour or switch to another
   network (like a phone hotspot), and we'll resume from this step.

5. CONNECT CLAUDE DESKTOP. Edit my claude_desktop_config.json
   (macOS: ~/Library/Application Support/Claude/claude_desktop_config.json,
   Windows: %APPDATA%\Claude\claude_desktop_config.json). Create it if it doesn't
   exist. Under "mcpServers", add an entry named "garmin" with:
   - "command": the absolute path to .venv/bin/python inside the project folder
     (on Windows: .venv\Scripts\python.exe)
   - "args": a list containing the absolute path to server.py in that folder
   Keep any existing servers in the file, make sure the JSON stays valid, and show
   me the finished file.

6. FINISH AND PROVE IT WORKS. Tell me to fully quit Claude Desktop (Cmd+Q on Mac;
   quit it from the tray icon on Windows) and open it again — it only reads the
   config at launch. Then have me test it by asking Claude Desktop:
   "What were my Garmin workouts this month?" and confirm the garmin tools respond.
   If a tool replies with an authentication error, we redo step 4.

Rules: if anything fails, show me the exact error, explain it in one sentence, and
fix it before moving on. Don't skip steps, don't ask me to edit files by hand unless
you truly can't, and don't declare the job done until the step-6 test works.
```

Why step 4 is manual: your Garmin password should never pass through an AI assistant
or appear in a chat transcript. The login script stores only OAuth tokens (at
`~/.garminconnect`) and refuses to run without an interactive terminal, precisely so
this step can't be automated.
