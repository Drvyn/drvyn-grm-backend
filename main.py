import uvicorn
import logging
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
    # 1. Startup: Initialize Database (Required for Beanie/MongoDB)
    try:
        await init_db()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
    
    yield # App runs here
    
    # 2. Shutdown: Logic if needed
    logger.info("Application shutting down.")

# --- App Definition ---
app = FastAPI(
    title="DrvynGRM API",
    description="Backend API for the Drvyn Garage Management System",
    version="1.0.0",
    lifespan=lifespan
)

# --- CORS Middleware ---
# Updated with your production frontend domain to prevent CORS preflight errors
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
# Both routers use the /workshop prefix as defined in their respective files
app.include_router(workshop.router) #
app.include_router(dashboard.router) #

# --- Root Endpoint ---
@app.get("/")
def read_root():
    return {"status": "online", "message": "Welcome to the DrvynGRM API"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)