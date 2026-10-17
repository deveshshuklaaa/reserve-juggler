from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging
from app.database import engine, Base
from app.routers import health, treasury, transactions, simulation
from app.routers import runs

# Create schema tables if not exist (ensures standalone testing works instantly)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Reserve Juggler API",
    description="Quantitative Treasury Decision Engine for HackForge 2026",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/v1/openapi.json"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root level health for standard container health checks
app.include_router(health.router)

# Domain Routers
app.include_router(runs.router, prefix="/api/v1")

# Existing dashboard clients keep working while they migrate to /api/v1.
app.include_router(treasury.router, include_in_schema=False)
app.include_router(transactions.router, include_in_schema=False)
app.include_router(simulation.router, include_in_schema=False)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={
        "error_code": "VALIDATION_ERROR",
        "message": "Request does not match the API contract.",
        "details": [{"location": list(error["loc"]), "type": error["type"]}
                    for error in exc.errors()],
    })


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    if isinstance(exc.detail, dict) and "error_code" in exc.detail:
        content = exc.detail
    else:
        content = {"error_code": f"HTTP_{exc.status_code}",
                   "message": str(exc.detail), "details": {}}
    return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    logging.getLogger(__name__).error("Unhandled API error", exc_info=exc)
    return JSONResponse(status_code=500, content={
        "error_code": "INTERNAL_ERROR", "message": "An unexpected internal error occurred.",
        "details": {},
    })

@app.get("/", include_in_schema=False)
def root():
    return {
        "project": "Reserve Juggler",
        "description": "Uncertainty-Aware Treasury Decision Engine",
        "docs": "/docs",
        "health": "/health",
        "contract": "/api/v1/openapi.json"
    }
