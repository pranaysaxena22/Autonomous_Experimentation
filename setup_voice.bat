@echo off
rem  setup_voice.bat -> one-time set-up of the narrator's offline neural voice (Piper). It makes its own small environment (.venv_voice) and downloads the voice files (about 120 MB each) into voice_models.
rem  This is the only step that uses the internet, and it only downloads. Nothing of yours is sent anywhere. The voice files are not part of the project and are kept out of git.
cd /d "%~dp0"
if not exist ".venv_voice\Scripts\python.exe" (
  echo Making the voice tool's own environment ...
  ".venv\Scripts\python.exe" -c "import sys,subprocess; subprocess.check_call([sys.base_prefix + '\\python.exe', '-m', 'venv', '.venv_voice'])"
  ".venv_voice\Scripts\python.exe" -m pip install --quiet piper-tts soundfile
)
if not exist "voice_models" mkdir voice_models
for %%V in (en_US-ryan-high en_US-lessac-high en_US-hfc_female-medium) do (
  if not exist "voice_models\%%V.onnx" ".venv_voice\Scripts\python.exe" -m piper.download_voices %%V --data-dir voice_models
)
echo.
echo Done. Next: build_replay.bat makes the file you can send.
pause
