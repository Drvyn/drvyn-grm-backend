import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.db import init_db
from app.routers import workshop, dashboard

@asynccontextmanager
async def lifespan(app: FastAPI):
    # On startup: Initialize the database connection and Beanie models
    await init_db()
    yield
    # On shutdown: (add cleanup code here if needed)

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

# --- API Routers ---
# Include all the different parts of your API
app.include_router(workshop.router)
app.include_router(dashboard.router)

# --- Root Endpoint ---
@app.get("/")
def read_root():
    return {"message": "Welcome to the DrvynGRM API"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
