"""FastAPI 应用入口 - 国画临摹 AI 教练"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import init_db
from .routes import artworks, assets, courses, submissions
from .schemas import HealthResponse

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(artworks.router)
app.include_router(assets.router)
app.include_router(courses.router)
app.include_router(submissions.router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse()



@app.get("/")
def root():
    return {
        "name": "国画临摹AI教练",
        "version": "0.1.0",
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
        "api": {
            "artworks": "/api/v1/artworks/",
            "assets": "/api/v1/assets/",
            "courses": "/api/v1/courses/generate",
            "submissions": "/api/v1/submissions/",
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
