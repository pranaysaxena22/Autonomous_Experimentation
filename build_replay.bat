@echo off
rem  build_replay.bat -> makes ONE file you can send to people: runs\replay\Autonomous_Formulation_Cell_replay.html
rem  It plays the guided demo by itself, with the narrator's voice, in any browser (Chrome or Edge), with no program running and no internet. Takes a few minutes.
rem  Optional: build_replay.bat en_US-lessac-high (or en_US-hfc_female-medium) uses another voice; the default is en_US-ryan-high.
rem  Everything in it is illustrative: a simulation with made-up values.
cd /d "%~dp0"
set VOICE=%1
if "%VOICE%"=="" set VOICE=en_US-ryan-high
echo Step 1 of 3: recording a simulated run (about two minutes) ...
".venv\Scripts\python.exe" -B -m tools.make_replay collect
if errorlevel 1 goto failed
if exist ".venv_voice\Scripts\python.exe" (
  echo Step 2 of 3: recording the narrator's voice (%VOICE%) ...
  ".venv_voice\Scripts\python.exe" tools\make_voice.py clips %VOICE%
  if errorlevel 1 goto failed
) else (
  echo Step 2 of 3 skipped: the narrator's voice is not set up. Double-click setup_voice.bat first for a clear voice.
)
echo Step 3 of 3: putting it together ...
".venv\Scripts\python.exe" -B -m tools.make_replay assemble
if errorlevel 1 goto failed
echo.
echo Your file is in the folder that opens now. Send that one file: it opens by double-click in Chrome or Edge.
start "" explorer "runs\replay"
pause
exit /b 0
:failed
echo.
echo Something went wrong (see the message above).
pause
exit /b 1
