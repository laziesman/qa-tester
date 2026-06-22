@echo off
echo Starting Chrome with remote debugging on port 9222...
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --no-first-run --no-default-browser-check
echo Chrome launched. You can now run agent-browser commands.
