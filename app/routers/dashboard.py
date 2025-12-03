from fastapi import APIRouter, HTTPException, status, Query
from typing import List, Dict, Any
from datetime import date, datetime, time, timedelta
from app.auth import UserOrAdmin
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
    if hasattr(model_class, "get_pymongo_collection"):
        return model_class.get_pymongo_collection()
    if hasattr(model_class, "get_motor_collection"):
        return model_class.get_motor_collection()
    raise AttributeError(f"Model {model_class} does not have a collection accessor method.")

@router.get("/dashboard-stats", response_model=DashboardStats)
async def get_dashboard_stats(
    user: UserOrAdmin,
    from_date: date,
    to_date: date
):
    """
    Calculates stats. If Admin, sums all workshops. If Workshop, filters by ID.
    """
    is_admin = user["role"] == "admin"
    workshop_id = user["uid"]
    
    # Base query
    base_query = {
        "date": {
            "$gte": from_date.isoformat(),
            "$lte": to_date.isoformat()
        }
    }
    
    # Only filter by workshop_id if NOT admin
    if not is_admin:
        base_query["workshop_id"] = workshop_id

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
        # Match stage needs to respect admin/workshop scope
        match_stage = {
            "status": "paid",
            "date": {
                "$gte": from_date.isoformat(),
                "$lte": to_date.isoformat()
            }
        }
        if not is_admin:
            match_stage["workshop_id"] = workshop_id

        revenue_pipeline = [
            {"$match": match_stage},
            {"$group": {"_id": None, "totalRevenue": {"$sum": "$amount"}}}
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
    user: UserOrAdmin,
    days: int = 30
):
    """
    Returns daily breakdown of bookings and revenue for charts.
    """
    is_admin = user["role"] == "admin"
    workshop_id = user["uid"]
    
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=days)
    
    # Initialize dictionary
    data_map: Dict[str, ChartDataPoint] = {}
    current = start_date
    while current <= end_date:
        d_str = current.isoformat()
        data_map[d_str] = ChartDataPoint(date=current.strftime("%m/%d")) 
        current += timedelta(days=1)

    booking_collection = get_db_collection(Booking)
    
    # Match stage
    booking_match = {
        "date": {"$gte": start_date.isoformat(), "$lte": end_date.isoformat()}
    }
    if not is_admin:
        booking_match["workshop_id"] = workshop_id

    booking_pipeline = [
        {"$match": booking_match},
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
        if date_key in data_map:
            try:
                # Assuming date matches ISO key directly
                data_map[date_key].bookings = res["count"]
                data_map[date_key].completed = res["completed"]
            except Exception:
                pass

    invoice_collection = get_db_collection(Invoice)

    revenue_match = {
        "status": "paid",
        "date": {"$gte": start_date.isoformat(), "$lte": end_date.isoformat()}
    }
    if not is_admin:
        revenue_match["workshop_id"] = workshop_id

    revenue_pipeline = [
        {"$match": revenue_match},
        {"$group": {"_id": "$date", "total": {"$sum": "$amount"}}}
    ]

    revenue_results = await invoice_collection.aggregate(revenue_pipeline).to_list(length=None)
    
    for res in revenue_results:
        date_key = res["_id"]
        if date_key in data_map:
             data_map[date_key].revenue = res["total"]

    return list(data_map.values())


@router.get("/recent-activity", response_model=List[ActivityLog])
async def get_recent_activity(user: UserOrAdmin):
    """
    Gets the 5 most recent activity log entries.
    """
    is_admin = user["role"] == "admin"
    workshop_id = user["uid"]
    
    if is_admin:
        # Admin sees all activity
        activities = await ActivityLog.find_all().sort(-ActivityLog.created_at).limit(5).to_list()
    else:
        activities = await ActivityLog.find(
            ActivityLog.workshop_id == workshop_id
        ).sort(-ActivityLog.created_at).limit(5).to_list()
    
    return activities