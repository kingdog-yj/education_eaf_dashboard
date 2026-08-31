from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import discussion, heats, kpi, live, meta
from app.config import get_settings

app = FastAPI(title="EAF 공정 분석 대시보드 & Discussion API")

# 개발용: Vite dev 서버 허용. 배포 시에는 아래 정적 서빙으로 단일 포트 운용 가능.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(heats.router)
app.include_router(kpi.router)
app.include_router(live.router)
app.include_router(discussion.router)
app.include_router(meta.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# -- 프론트 정적 서빙 (frontend/dist 존재 시에만) ----------------------------
# dist가 없으면 아무것도 마운트하지 않으므로 API 전용으로 정상 기동한다.
# 경로는 config(frontend_dist_dir) 경유 — 하드코딩 금지.

_DIST_DIR: Path = get_settings().frontend_dist_dir
_INDEX_HTML: Path = _DIST_DIR / "index.html"

if _DIST_DIR.is_dir():
    _assets_dir = _DIST_DIR / "assets"
    if _assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        """SPA fallback: dist 내 실제 파일이면 그 파일, 아니면 index.html.

        /api/* 는 fallback 대상이 아니다 (미정의 API 경로는 404 JSON 유지).
        """
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(404, "Not Found")
        if full_path:
            candidate = (_DIST_DIR / full_path).resolve()
            # 경로 탈출 방지: 반드시 dist 하위여야 한다
            if candidate.is_file() and candidate.is_relative_to(_DIST_DIR.resolve()):
                return FileResponse(candidate)
        if _INDEX_HTML.is_file():
            return FileResponse(_INDEX_HTML)
        raise HTTPException(404, "Not Found")
