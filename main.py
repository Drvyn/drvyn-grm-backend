import uvicorn
import asyncio
import logging
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.db import init_db
from app.routers import workshop, dashboard

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Lifespan (Startup & Shutdown) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Startup: Initialize Database
    await init_db()
    
    # 2. Startup: Start Background Task
    # We store the task in a variable so we can cancel it later
    task = asyncio.create_task(keep_alive())
    
    yield # App runs here
    
    # 3. Shutdown: Clean up task
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        logger.info("Keep-alive task stopped")

# --- App Definition ---
app = FastAPI(
    title="DrvynGRM API",
    description="Backend API for the Drvyn Garage Management System",
    version="1.0.0",
    lifespan=lifespan
)

# --- CORS Middleware ---
origins = [
    "http://localhost:3000",        
    "https://grm.drvyn.in",           
    "https://www.grm.drvyn.in",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Include Routers ---
app.include_router(workshop.router)
app.include_router(dashboard.router)

# --- Root Endpoint ---
@app.get("/")
def read_root():
    return {"message": "Welcome to the DrvynGRM API"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)