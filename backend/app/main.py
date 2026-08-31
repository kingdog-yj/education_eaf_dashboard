from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import discussion, heats, kpi, live, meta

app = FastAPI(title="EAF 공정 분석 대시보드 & Discussion API")

# 개발용: Vite dev 서버 허용. 사내 서버 배포 시 정적 서빙 또는 도메인 제한으로 교체.
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
