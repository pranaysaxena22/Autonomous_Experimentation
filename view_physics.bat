@echo off
cd /d "%~dp0"
echo Writing the cell as a MuJoCo scene and opening it in MuJoCo's own viewer (a separate window on this computer only).
echo Illustrative: the layout's made-up numbers. Close the viewer window to finish.
".venv\Scripts\python.exe" -B -m cellpoc.physics.export
if errorlevel 1 goto :end
".venv\Scripts\python.exe" -B -m mujoco.viewer --mjcf=runs\physics\cell.xml
:end
echo.
pause
