@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv 가 없습니다. README.md 의 셋업 절차를 먼저 수행하세요.
    pause
    exit /b 1
)

echo ============================================
echo  EAF 대시보드 - 단일 포트 실행
echo  http://localhost:8000  (종료: Ctrl+C)
echo ============================================

rem 서버 기동 3초 후 브라우저 자동 오픈
start "" /b cmd /c "timeout /t 3 >nul && start http://localhost:8000"

.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend
