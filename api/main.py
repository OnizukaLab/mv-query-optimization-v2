"""FastAPI application for the MV optimization web dashboard.

Run locally (loopback only; arbitrary SQL is accepted):
    uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import experiments, health, plans, results

app = FastAPI(title="MV Optimization API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(plans.router)
app.include_router(experiments.router)
app.include_router(results.router)
