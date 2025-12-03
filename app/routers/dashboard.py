from fastapi import APIRouter, HTTPException, status, Query
from typing import List, Dict, Any
from datetime import date, datetime, time, timedelta
from app.auth import UserOrAdmin
from app.models.workshop import Booking, Invoice, JobCard
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

class ReportStats(BaseModel):
    revenue_data: List[Dict[str, Any]]
    service_breakdown: List[Dict[str, Any]]
    customer_growth: List[Dict[str, Any]]
    performance: Dict[str, Any]
    top_customers: List[Dict[str, Any]]

# --- Helper to handle version differences ---
def get_db_collection(model_class):
    if hasattr(model_class, "get_pymongo_collection"):
        return model_class.get_pymongo_collection()
    if hasattr(model_class, "get_motor_collection"):
        return model_class.get_motor_collection()
    raise AttributeError(f"Model {model_class} does not have a collection accessor method.")

# ... [Existing get_dashboard_stats and get_dashboard_chart_data endpoints remain here unchanged] ...
@router.get("/dashboard-stats", response_model=DashboardStats)
async def get_dashboard_stats(user: UserOrAdmin, from_date: date, to_date: date):
    is_admin = user["role"] == "admin"
    workshop_id = user["uid"]
    base_query = {"date": {"$gte": from_date.isoformat(), "$lte": to_date.isoformat()}}
    if not is_admin: base_query["workshop_id"] = workshop_id

    booking_collection = get_db_collection(Booking)
    invoice_collection = get_db_collection(Invoice)

    bookings_count = await booking_collection.count_documents(base_query)
    
    completed_query = base_query.copy()
    completed_query["status"] = "completed"
    completed_count = await booking_collection.count_documents(completed_query)
    
    pending_query = base_query.copy()
    pending_query["status"] = "pending"
    pending_count = await booking_collection.count_documents(pending_query)

    match_stage = {"status": "paid", "date": {"$gte": from_date.isoformat(), "$lte": to_date.isoformat()}}
    if not is_admin: match_stage["workshop_id"] = workshop_id

    revenue_pipeline = [{"$match": match_stage}, {"$group": {"_id": None, "totalRevenue": {"$sum": "$amount"}}}]
    revenue_result = await invoice_collection.aggregate(revenue_pipeline).to_list(length=1)
    total_revenue = revenue_result[0]["totalRevenue"] if revenue_result else 0.0

    return DashboardStats(bookings=bookings_count, completed=completed_count, revenue=total_revenue, pending=pending_count)

@router.get("/dashboard-chart-data", response_model=List[ChartDataPoint])
async def get_dashboard_chart_data(user: UserOrAdmin, days: int = 30):
    is_admin = user["role"] == "admin"
    workshop_id = user["uid"]
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=days)
    data_map = {}
    current = start_date
    while current <= end_date:
        data_map[current.isoformat()] = ChartDataPoint(date=current.strftime("%m/%d"))
        current += timedelta(days=1)

    booking_collection = get_db_collection(Booking)
    match_q = {"date": {"$gte": start_date.isoformat(), "$lte": end_date.isoformat()}}
    if not is_admin: match_q["workshop_id"] = workshop_id
    
    b_res = await booking_collection.aggregate([
        {"$match": match_q},
        {"$group": {"_id": "$date", "count": {"$sum": 1}, "completed": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}}}}
    ]).to_list(None)
    for r in b_res:
        if r["_id"] in data_map:
            data_map[r["_id"]].bookings = r["count"]
            data_map[r["_id"]].completed = r["completed"]

    invoice_collection = get_db_collection(Invoice)
    inv_match = {"status": "paid", "date": {"$gte": start_date.isoformat(), "$lte": end_date.isoformat()}}
    if not is_admin: inv_match["workshop_id"] = workshop_id
    
    i_res = await invoice_collection.aggregate([
        {"$match": inv_match},
        {"$group": {"_id": "$date", "total": {"$sum": "$amount"}}}
    ]).to_list(None)
    for r in i_res:
        if r["_id"] in data_map:
            data_map[r["_id"]].revenue = r["total"]
            
    return list(data_map.values())

@router.get("/recent-activity", response_model=List[ActivityLog])
async def get_recent_activity(user: UserOrAdmin):
    is_admin = user["role"] == "admin"
    if is_admin:
        return await ActivityLog.find_all().sort(-ActivityLog.created_at).limit(5).to_list()
    return await ActivityLog.find(ActivityLog.workshop_id == user["uid"]).sort(-ActivityLog.created_at).limit(5).to_list()

# --- NEW REPORT ENDPOINT ---
@router.get("/reports", response_model=ReportStats)
async def get_reports_data(user: UserOrAdmin):
    """
    Aggregates real data for the Reports page.
    """
    is_admin = user["role"] == "admin"
    workshop_id = user["uid"]
    
    # 1. Revenue (Monthly) - Last 6 months
    invoice_collection = get_db_collection(Invoice)
    revenue_match = {"status": "paid"}
    if not is_admin: revenue_match["workshop_id"] = workshop_id
    
    revenue_pipeline = [
        {"$match": revenue_match},
        {
            "$group": {
                "_id": {"$substr": ["$date", 0, 7]}, # YYYY-MM
                "total": {"$sum": "$amount"}
            }
        },
        {"$sort": {"_id": 1}}
    ]
    rev_results = await invoice_collection.aggregate(revenue_pipeline).to_list(None)
    
    # Fill in last 6 months
    revenue_data = []
    today = datetime.today()
    for i in range(5, -1, -1):
        d = today - timedelta(days=i*30)
        month_key = d.strftime("%Y-%m")
        month_label = d.strftime("%b")
        
        found = next((r for r in rev_results if r["_id"] == month_key), None)
        revenue_data.append({
            "month": month_label,
            "revenue": found["total"] if found else 0,
            "target": 0 # Remove or mock if needed
        })

    # 2. Service Breakdown
    booking_collection = get_db_collection(Booking)
    match_booking = {} if is_admin else {"workshop_id": workshop_id}
    
    service_pipeline = [
        {"$match": match_booking},
        {"$group": {"_id": "$bookingType", "value": {"$sum": 1}}}
    ]
    service_results = await booking_collection.aggregate(service_pipeline).to_list(None)
    service_breakdown = [{"name": s["_id"] or "Unknown", "value": s["value"]} for s in service_results]

    # 3. Customer Growth (New customers per month)
    # Group by customer name, find first booking date
    growth_pipeline = [
        {"$match": match_booking},
        {"$group": {"_id": "$customerName", "first_seen": {"$min": "$date"}}},
        {
            "$group": {
                "_id": {"$substr": ["$first_seen", 0, 7]}, # YYYY-MM
                "newCustomers": {"$sum": 1}
            }
        },
        {"$sort": {"_id": 1}}
    ]
    growth_raw = await booking_collection.aggregate(growth_pipeline).to_list(None)
    
    customer_growth = []
    for i in range(5, -1, -1):
        d = today - timedelta(days=i*30)
        month_key = d.strftime("%Y-%m")
        month_label = d.strftime("%b")
        
        found = next((g for g in growth_raw if g["_id"] == month_key), None)
        customer_growth.append({
            "month": month_label,
            "newCustomers": found["newCustomers"] if found else 0
        })

    # 4. Top Customers
    top_cx_pipeline = [
        {"$match": revenue_match},
        {"$group": {"_id": "$customer", "spent": {"$sum": "$amount"}, "bookings": {"$sum": 1}}},
        {"$sort": {"spent": -1}},
        {"$limit": 5}
    ]
    top_cx_res = await invoice_collection.aggregate(top_cx_pipeline).to_list(None)
    top_customers = [{"name": c["_id"], "spent": c["spent"], "bookings": c["bookings"]} for c in top_cx_res]

    # 5. Performance
    total_bookings = await booking_collection.count_documents(match_booking)
    completed_bookings = await booking_collection.count_documents({**match_booking, "status": "completed"})
    completion_rate = (completed_bookings / total_bookings * 100) if total_bookings > 0 else 0
    
    total_rev = sum(d["revenue"] for d in revenue_data)
    avg_job_value = (total_rev / total_bookings) if total_bookings > 0 else 0

    return ReportStats(
        revenue_data=revenue_data,
        service_breakdown=service_breakdown,
        customer_growth=customer_growth,
        top_customers=top_customers,
        performance={
            "completion_rate": round(completion_rate, 1),
            "avg_job_value": round(avg_job_value, 0)
        }
    )