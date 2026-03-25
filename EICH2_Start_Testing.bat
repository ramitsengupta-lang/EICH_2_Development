@echo off
cd /d "d:\Market Scopping and Research\EICH_2_Development"
call .\.venv\Scripts\activate.bat
start "EICH2 Frontend Server" python eich2_frontend_server.py
timeout /t 2 /nobreak >nul
start http://127.0.0.1:5051