"""Launcher: `streamlit run unified_app.py` (or double-click run_app.bat). The unified app lives in cellpoc/shell; the dashboard pages it shows live in cellpoc/dashboard.

The app opens in its CLIENT view (the pages and wording meant for the people the demo is for). The full DEVELOPER view (every page, with the technical detail) is for the team: double-click run_app_developer.bat, or set CELLPOC_DEVELOPER=1.
"""
import os

from cellpoc.shell.app import main

main(developer=os.environ.get("CELLPOC_DEVELOPER") == "1")
