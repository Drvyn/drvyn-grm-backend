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

# --- Keep Alive Function ---
async def keep_alive():
    """
    Background task to ping the server periodically.
    """
    await asyncio.sleep(20)
    url = "https://drvyn-grm-backend.vercel.app/" 
    
    while True:
        try:
            async with httpx.AsyncClient() as client:
                # 10 second timeout to prevent hanging
                await client.get(url, timeout=10.0)
            logger.info("Keep-alive ping successful")
        except Exception as e:
            # We log the error but allow the loop to continue
            logger.error(f"Keep-alive ping failed: {e}")
        
        # Ping every 10 minutes (600 seconds)
        # Render free tier spins down after 15 minutes of inactivity.
        await asyncio.sleep(600) 

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
    # Add your render frontend domain if needed
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
    # Note: On Render, this block is usually skipped because they use the command 'uvicorn main:app' directly.
    # However, it is useful for local debugging.
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)