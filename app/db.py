from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.models.workshop import (
    Employee, 
    Department, 
    Booking, 
    Customer, 
    JobCard, 
    Invoice, 
    Part,
    Todo,            
    ServiceCatalog,
    Vehicle,
    Expense,
    Purchase,
    WorkshopSettings  # <-- Added
)
from app.models.activity import ActivityLog

class Settings(BaseSettings):
    MONGODB_URI: str
    DB_NAME: str
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

async def init_db():
    """
    Initializes the database connection and Beanie ODM.
    """
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    database = client[settings.DB_NAME]
    
    document_models = [
        Employee,
        Department,
        Booking,
        Customer,
        JobCard,
        Invoice,
        Part,
        ActivityLog,
        Todo,            
        ServiceCatalog,
        Expense,  
        Purchase,
        Vehicle,
        WorkshopSettings 
    ]
    
    await init_beanie(database=database, document_models=document_models)
    print(f"Successfully connected to MongoDB database: {settings.DB_NAME}")