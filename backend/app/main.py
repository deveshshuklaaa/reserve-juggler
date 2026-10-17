from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.routers import health, treasury, transactions, simulation

# Create schema tables if not exist (ensures standalone testing works instantly)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Reserve Juggler API",
    description="Quantitative Treasury Decision Engine for HackForge 2026",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
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
app.include_router(treasury.router)
app.include_router(transactions.router)
app.include_router(simulation.router)

@app.get("/")
def root():
    return {
        "project": "Reserve Juggler",
        "description": "Uncertainty-Aware Treasury Decision Engine",
        "docs": "/docs",
        "health": "/health",
        "contract": "/contracts/openapi.yaml"
    }
