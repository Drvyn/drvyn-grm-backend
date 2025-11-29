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

# --- Helper to handle version differences between Local and Render ---
def get_db_collection(model_class):
    """
    Returns the underlying Motor collection, handling differences between 
    Beanie versions (get_motor_collection vs get_pymongo_collection).
    """
    if hasattr(model_class, "get_pymongo_collection"):
        return model_class.get_pymongo_collection()
    if hasattr(model_class, "get_motor_collection"):
        return model_class.get_motor_collection()
    raise AttributeError(f"Model {model_class} does not have a collection accessor method.")

@router.get("/dashboard-stats", response_model=DashboardStats)
async def get_dashboard_stats(
    user: AuthUser,
    from_date: date,
    to_date: date
):
    """
    Calculates and returns key stats for the dashboard within a date range.
    Uses direct DB driver to ensure compatibility and accuracy.
    """
    workshop_id = user["uid"]
    
    # Base query for the date range and workshop
    base_query = {
        "workshop_id": workshop_id,
        "date": {
            "$gte": from_date.isoformat(),
            "$lte": to_date.isoformat()
        }
    }

    try:
        booking_collection = get_db_collection(Booking)
        invoice_collection = get_db_collection(Invoice)

        # 1. Total Bookings
        bookings_count = await booking_collection.count_documents(base_query)
        
        # 2. Completed Jobs
        completed_query = base_query.copy()
        completed_query["status"] = "completed"
        completed_count = await booking_collection.count_documents(completed_query)
        
        # 3. Pending Tasks
        pending_query = base_query.copy()
        pending_query["status"] = "pending"
        pending_count = await booking_collection.count_documents(pending_query)

        # 4. Revenue (from paid invoices)
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
        
        revenue_result = await invoice_collection.aggregate(revenue_pipeline).to_list(length=1)
        total_revenue = revenue_result[0]["totalRevenue"] if revenue_result else 0.0

        return DashboardStats(
            bookings=bookings_count,
            completed=completed_count,
            revenue=total_revenue,
            pending=pending_count
        )

    except Exception as e:
        print(f"Dashboard Stats Error: {e}") 
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
        data_map[d_str] = ChartDataPoint(date=current.strftime("%m/%d")) 
        current += timedelta(days=1)

    # Use helper to support both local and render environments
    booking_collection = get_db_collection(Booking)
    
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
    
    booking_results = await booking_collection.aggregate(booking_pipeline).to_list(length=None)
    
    for res in booking_results:
        date_key = res["_id"]
        # Handle if date format in DB matches YYYY-MM-DD
        if date_key in data_map:
            try:
                target_date = datetime.strptime(date_key, "%Y-%m-%d").strftime("%m/%d")
                for item in data_map.values():
                    if item.date == target_date:
                        item.bookings = res["count"]
                        item.completed = res["completed"]
                        break
            except ValueError:
                pass

    # Use helper for invoices
    invoice_collection = get_db_collection(Invoice)

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

    revenue_results = await invoice_collection.aggregate(revenue_pipeline).to_list(length=None)
    
    for res in revenue_results:
        date_key = res["_id"]
        if date_key:
             try:
                target_date = datetime.strptime(date_key, "%Y-%m-%d").strftime("%m/%d")
                for item in data_map.values():
                    if item.date == target_date:
                        item.revenue = res["total"]
                        break
             except ValueError:
                 pass

    return list(data_map.values())


@router.get("/recent-activity", response_model=List[ActivityLog])
async def get_recent_activity(user: AuthUser):
    """
    Gets the 5 most recent activity log entries for the workshop.
    """
    workshop_id = user["uid"]
    
    # Simple queries usually work fine with Beanie's find(), but we can leave this as is
    # unless it also proves problematic. It uses simple boolean logic so usually safe.
    activities = await ActivityLog.find(
        ActivityLog.workshop_id == workshop_id
    ).sort(-ActivityLog.created_at).limit(5).to_list()
    
    return activities