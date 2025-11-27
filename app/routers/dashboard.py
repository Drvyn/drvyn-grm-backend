from fastapi import APIRouter, HTTPException, status, Query
from typing import List
from datetime import date, datetime, time
from app.auth import AuthUser
from app.models.workshop import Booking, Invoice
from app.models.activity import ActivityLog
from pydantic import BaseModel

router = APIRouter(
    prefix="/workshop",
    tags=["Dashboard"]
)

class DashboardStats(BaseModel):
    bookings: int
    completed: int
    revenue: float
    pending: int

@router.get("/dashboard-stats", response_model=DashboardStats)
async def get_dashboard_stats(
    user: AuthUser,
    from_date: date,
    to_date: date
):
    """
    Calculates and returns key stats for the dashboard within a date range.
    """
    workshop_id = user["uid"]
    
    # Combine date with time to create datetime objects for MongoDB query
    start_datetime = datetime.combine(from_date, time.min)
    end_datetime = datetime.combine(to_date, time.max)
    
    # Create date filter for string-based dates (YYYY-MM-DD)
    date_filter = {
        "date": {
            "$gte": from_date.isoformat(),
            "$lte": to_date.isoformat()
        }
    }

    try:
        # Get booking counts
        bookings_count = await Booking.find(
            Booking.workshop_id == workshop_id,
            date_filter
        ).count()
        
        completed_count = await Booking.find(
            Booking.workshop_id == workshop_id,
            Booking.status == "completed",
            date_filter
        ).count()
        
        pending_count = await Booking.find(
            Booking.workshop_id == workshop_id,
            Booking.status == "pending",
            date_filter
        ).count()

        # Calculate revenue from *paid* invoices in the date range
        revenue_pipeline = [
            {
                "$match": {
                    "workshop_id": workshop_id,
                    "status": "paid",
                    "date": {
                        "$gte": from_date.isoformat(),
                        "$lte": to_date.isoformat()
                    }
                }
            },
            {
                "$group": {
                    "_id": None,
                    "totalRevenue": {"$sum": "$amount"}
                }
            }
        ]
        
        revenue_result = await Invoice.aggregate(revenue_pipeline).to_list(1)
        total_revenue = revenue_result[0]["totalRevenue"] if revenue_result else 0.0

        return DashboardStats(
            bookings=bookings_count,
            completed=completed_count,
            revenue=total_revenue,
            pending=pending_count
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recent-activity", response_model=List[ActivityLog])
async def get_recent_activity(user: AuthUser):
    """
    Gets the 10 most recent activity log entries for the workshop.
    This is now fully dynamic.
    """
    workshop_id = user["uid"]
    
    activities = await ActivityLog.find(
        ActivityLog.workshop_id == workshop_id
    ).sort(-ActivityLog.created_at).limit(10).to_list()
    
    return activities