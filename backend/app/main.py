import logging
import time
import uuid
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.api import auth, projects, tasks, annotation, operations, quality, datasets
from app.core.config import settings
from app.db.session import SessionLocal
from app.queue.redis_queue import health

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("argus")
app = FastAPI(title="ARGUS", version="0.1.0", description="Human oversight for agent training data")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings().cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
for router in [
    auth.router,
    projects.router,
    tasks.router,
    annotation.router,
    operations.router,
    quality.router,
    datasets.router,
]:
    app.include_router(router)


@app.middleware("http")
async def request_log(request: Request, call_next):
    request_id = str(uuid.uuid4())
    started = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_id=%s unhandled request failure", request_id)
        response = JSONResponse(
            status_code=500,
            content={
                "error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred", "request_id": request_id}
            },
        )
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        (time.monotonic() - started) * 1000,
    )
    return response


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": f"HTTP_{exc.status_code}", "message": exc.detail}},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": [{"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()],
            }
        },
    )


@app.exception_handler(IntegrityError)
async def conflict(request, exc):
    return JSONResponse(
        status_code=409,
        content={"error": {"code": "CONFLICT", "message": "This change conflicts with an existing record"}},
    )


@app.get("/health")
def healthcheck():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "healthy", "redis": health()}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unhealthy", "database": "unavailable"})
