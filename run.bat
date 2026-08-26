@echo off
cd /d "%~dp0"
echo Installing deps (first run may take a minute)...
python -m pip install -q -r requirements.txt
echo Starting idea-bot...
python -m bot.main
pause
