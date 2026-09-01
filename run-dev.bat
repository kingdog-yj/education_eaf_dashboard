@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv 가 없습니다. README.md 의 셋업 절차를 먼저 수행하세요.
    pause
    exit /b 1
)
if not exist "frontend\node_modules" (
    echo [ERROR] frontend\node_modules 가 없습니다. cd frontend ^&^& npm install 을 먼저 수행하세요.
    pause
    exit /b 1
)

echo ============================================
echo  EAF 대시보드 - 개발 모드 (핫리로드)
echo  백엔드  http://localhost:8000
echo  프론트  http://localhost:5173  (여기로 접속)
echo  종료: 열린 두 창을 각각 닫거나 Ctrl+C
echo ============================================

start "EAF Backend (8000)" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --reload --app-dir backend"
start "EAF Frontend (5173)" cmd /k "cd frontend && npm run dev"

rem 기동 대기 후 브라우저 자동 오픈
timeout /t 5 >nul
start http://localhost:5173
