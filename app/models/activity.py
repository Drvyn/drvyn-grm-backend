from beanie import Document, Indexed
from pydantic import Field
from datetime import datetime

class ActivityLog(Document):
    workshop_id: Indexed(str)
    title: str
    icon: str  # e.g., "Clock", "FileText", "Wrench"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "activity_logs"
        # This creates a TTL (Time-To-Live) index.
        # Documents will be automatically deleted after 30 days.
        indexes = [
            [("created_at", 1), ("expireAfterSeconds", 30 * 24 * 60 * 60)]
        ]