from fastapi import APIRouter, HTTPException, status, Query
from typing import List, Dict, Any
from datetime import date, datetime, time, timedelta
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

class ChartDataPoint(BaseModel):
    date: str
    bookings: int = 0
    completed: int = 0
    revenue: float = 0.0

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


@router.get("/dashboard-chart-data", response_model=List[ChartDataPoint])
async def get_dashboard_chart_data(
    user: AuthUser,
    days: int = 30
):
    """
    Returns daily breakdown of bookings and revenue for charts.
    """
    workshop_id = user["uid"]
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=days)
    
    # Initialize dictionary with all dates in range
    data_map: Dict[str, ChartDataPoint] = {}
    current = start_date
    while current <= end_date:
        d_str = current.isoformat()
        data_map[d_str] = ChartDataPoint(date=current.strftime("%m/%d")) # Format MM/DD for chart
        current += timedelta(days=1)

    # Aggregate Bookings per day
    booking_pipeline = [
        {
            "$match": {
                "workshop_id": workshop_id,
                "date": {"$gte": start_date.isoformat(), "$lte": end_date.isoformat()}
            }
        },
        {
            "$group": {
                "_id": "$date",
                "count": {"$sum": 1},
                "completed": {
                    "$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}
                }
            }
        }
    ]
    
    booking_results = await Booking.aggregate(booking_pipeline).to_list(None)
    for res in booking_results:
        date_key = res["_id"]
        # Handle if date format in DB matches YYYY-MM-DD
        if date_key in data_map:
            # We need to find the correct ChartDataPoint by mapping the date string back
            # Since data_map keys are YYYY-MM-DD, and _id is likely YYYY-MM-DD
            target_date = datetime.strptime(date_key, "%Y-%m-%d").strftime("%m/%d")
            # Find the item in our map values (inefficient but safe for 30 items)
            for item in data_map.values():
                if item.date == target_date:
                    item.bookings = res["count"]
                    item.completed = res["completed"]
                    break

    # Aggregate Revenue per day (Invoices)
    revenue_pipeline = [
        {
            "$match": {
                "workshop_id": workshop_id,
                "status": "paid",
                "date": {"$gte": start_date.isoformat(), "$lte": end_date.isoformat()}
            }
        },
        {
            "$group": {
                "_id": "$date",
                "total": {"$sum": "$amount"}
            }
        }
    ]

    revenue_results = await Invoice.aggregate(revenue_pipeline).to_list(None)
    for res in revenue_results:
        date_key = res["_id"]
        if date_key:
             try:
                target_date = datetime.strptime(date_key, "%Y-%m-%d").strftime("%m/%d")
                for item in data_map.values():
                    if item.date == target_date:
                        item.revenue = res["total"]
                        break
             except:
                 pass

    return list(data_map.values())


@router.get("/recent-activity", response_model=List[ActivityLog])
async def get_recent_activity(user: AuthUser):
    """
    Gets the 5 most recent activity log entries for the workshop.
    """
    workshop_id = user["uid"]
    
    activities = await ActivityLog.find(
        ActivityLog.workshop_id == workshop_id
    ).sort(-ActivityLog.created_at).limit(5).to_list()
    
    return activities
