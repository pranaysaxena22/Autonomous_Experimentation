@echo off
rem  build_video.bat -> makes the demo video runs\video\Autonomous_Formulation_Cell_demo.mp4 (about 5 minutes, with the narrator's voice):
rem  a short presentation (intro, the problem, what was built and who it helps, how it works), then the guided walkthrough.
rem  It plays the demo FULL SCREEN for about four minutes to record it: do not touch the keyboard or mouse until it closes by itself.
rem  Needs setup_voice.bat and build_replay.bat to have been run once. Everything is illustrative: a simulation with made-up values. Nothing leaves this computer.
cd /d "%~dp0"
if not exist ".venv_voice\Scripts\python.exe" (
  echo The voice tools are not set up. Double-click setup_voice.bat first.
  pause
  exit /b 1
)
if not exist "runs\replay\Autonomous_Formulation_Cell_replay.html" (
  echo The replay file is missing. Double-click build_replay.bat first.
  pause
  exit /b 1
)
".venv_voice\Scripts\python.exe" -m pip install --quiet pillow imageio-ffmpeg
".venv_voice\Scripts\python.exe" tools\make_video.py all
if errorlevel 1 (
  echo.
  echo Something went wrong (see the message above).
  pause
  exit /b 1
)
start "" explorer "runs\video"
pause
