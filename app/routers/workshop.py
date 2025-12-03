from fastapi import APIRouter, HTTPException, status, Depends
from typing import List, Dict, Any
from datetime import datetime
from firebase_admin import auth

from app.auth import AuthUser, AdminUser, verify_admin
from app.models.workshop import (
    Employee, EmployeeIn,
    Department, DepartmentIn,
    Booking, BookingIn, BookingStatusUpdate,
    Customer, CustomerIn,
    JobCard, JobCardIn,
    Invoice, InvoiceIn,
    Part, PartIn
)
from app.services.activity_service import log_activity
from beanie import PydanticObjectId
from pydantic import BaseModel

router = APIRouter(
    prefix="/workshop",
    tags=["Workshop Data"]
)

# --- Admin Models ---
class WorkshopStats(BaseModel):
    workshop_id: str
    name: str
    email: str
    total_bookings: int
    revenue: float
    pending_tasks: int

# --- Helper Function ---
async def find_document(model, doc_id, workshop_id, not_found_msg="Item not found"):
    try:
        doc = await model.get(PydanticObjectId(doc_id))
    except Exception:
        doc = None
    if not doc or doc.workshop_id != workshop_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found_msg)
    return doc

# --- ADMIN ENDPOINTS ---
@router.get("/admin/workshops", response_model=List[WorkshopStats], tags=["Admin"])
async def get_all_workshops_stats(is_admin: bool = Depends(verify_admin)):
    """
    Admin: Fetches statistics for all workshops.
    """
    # 1. Aggregate Bookings (Total & Pending)
    booking_pipeline = [
        {
            "$group": {
                "_id": "$workshop_id",
                "total": {"$sum": 1},
                "pending": {
                    "$sum": {"$cond": [{"$eq": ["$status", "pending"]}, 1, 0]}
                }
            }
        }
    ]
    booking_stats = await Booking.get_motor_collection().aggregate(booking_pipeline).to_list(None)
    booking_map = {item["_id"]: item for item in booking_stats}

    # 2. Aggregate Revenue (Paid Invoices)
    revenue_pipeline = [
        {"$match": {"status": "paid"}},
        {
            "$group": {
                "_id": "$workshop_id",
                "totalRevenue": {"$sum": "$amount"}
            }
        }
    ]
    revenue_stats = await Invoice.get_motor_collection().aggregate(revenue_pipeline).to_list(None)
    revenue_map = {item["_id"]: item["totalRevenue"] for item in revenue_stats}

    # 3. Get all unique workshop IDs from both sources
    all_workshop_ids = set(booking_map.keys()) | set(revenue_map.keys())

    results = []
    for wid in all_workshop_ids:
        if not wid: continue
        
        # Fetch user details from Firebase
        try:
            user_record = auth.get_user(wid)
            name = user_record.display_name or "Unknown Workshop"
            email = user_record.email or "No Email"
        except Exception:
            name = "Unknown ID"
            email = wid

        b_data = booking_map.get(wid, {"total": 0, "pending": 0})
        rev = revenue_map.get(wid, 0.0)

        results.append(WorkshopStats(
            workshop_id=wid,
            name=name,
            email=email,
            total_bookings=b_data["total"],
            revenue=rev,
            pending_tasks=b_data["pending"]
        ))

    return results

# --- Workshop Endpoints (Existing) ---

# --- Employees ---
@router.post("/employees", response_model=Employee, status_code=status.HTTP_201_CREATED)
async def create_employee(data: EmployeeIn, user: AuthUser):
    workshop_id = user["uid"]
    employee = Employee(**data.model_dump(), workshop_id=workshop_id)
    await employee.insert()
    await log_activity(workshop_id, f"Added employee: {employee.firstName}", "UserPlus")
    return employee

@router.get("/employees", response_model=List[Employee])
async def get_employees(user: AuthUser):
    return await Employee.find(Employee.workshop_id == user["uid"]).to_list()

@router.put("/employees/{employee_id}", response_model=Employee)
async def update_employee(employee_id: str, data: EmployeeIn, user: AuthUser):
    employee = await find_document(Employee, employee_id, user["uid"], "Employee not found")
    update_data = data.model_dump(exclude_unset=True)
    await employee.update({"$set": update_data})
    return await Employee.get(employee.id)

@router.delete("/employees/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_employee(employee_id: str, user: AuthUser):
    employee = await find_document(Employee, employee_id, user["uid"], "Employee not found")
    await employee.delete()
    await log_activity(user["uid"], f"Removed employee: {employee.firstName}", "Trash2")
    return None

# --- Departments ---
@router.post("/departments", response_model=Department, status_code=status.HTTP_201_CREATED)
async def create_department(data: DepartmentIn, user: AuthUser):
    workshop_id = user["uid"]
    department = Department(**data.model_dump(), workshop_id=workshop_id)
    await department.insert()
    await log_activity(workshop_id, f"Created department: {department.name}", "Building")
    return department

@router.get("/departments", response_model=List[Department])
async def get_departments(user: AuthUser):
    return await Department.find(Department.workshop_id == user["uid"]).to_list()

# --- Bookings ---
@router.post("/bookings", response_model=Booking, status_code=status.HTTP_201_CREATED)
async def create_booking(data: BookingIn, user: AuthUser):
    workshop_id = user["uid"]
    booking = Booking(**data.model_dump(), workshop_id=workshop_id)
    await booking.insert()
    await log_activity(workshop_id, f"New booking for {booking.customerName}", "Clock")
    return booking

@router.get("/bookings", response_model=List[Booking])
async def get_bookings(user: AuthUser):
    return await Booking.find(Booking.workshop_id == user["uid"]).sort(-Booking.created_at).to_list()

@router.put("/bookings/{booking_id}", response_model=Booking)
async def update_booking(booking_id: str, data: BookingIn, user: AuthUser):
    booking = await find_document(Booking, booking_id, user["uid"], "Booking not found")
    update_data = data.model_dump(exclude_unset=True)
    update_data["updated_at"] = datetime.utcnow()
    await booking.update({"$set": update_data})
    updated = await Booking.get(booking.id)
    await log_activity(user["uid"], f"Updated booking for {updated.customerName}", "Edit2")
    return updated

@router.delete("/bookings/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_booking(booking_id: str, user: AuthUser):
    booking = await find_document(Booking, booking_id, user["uid"], "Booking not found")
    await booking.delete()
    await log_activity(user["uid"], f"Deleted booking for {booking.customerName}", "Trash2")
    return None

@router.put("/bookings/{booking_id}/status", response_model=Booking)
async def update_booking_status(booking_id: str, data: BookingStatusUpdate, user: AuthUser):
    booking = await find_document(Booking, booking_id, user["uid"], "Booking not found")
    await booking.update({"$set": {"status": data.status, "updated_at": datetime.utcnow()}})
    updated = await Booking.get(booking.id)
    await log_activity(user["uid"], f"Booking for {booking.customerName} set to {data.status}", "Wrench")
    return updated

# --- Customers ---
@router.post("/customers", response_model=Customer, status_code=status.HTTP_201_CREATED)
async def create_customer(data: CustomerIn, user: AuthUser):
    workshop_id = user["uid"]
    customer = Customer(**data.model_dump(), workshop_id=workshop_id)
    await customer.insert()
    await log_activity(workshop_id, f"New customer added: {customer.name}", "Users")
    return customer

@router.get("/customers", response_model=List[Customer])
async def get_customers(user: AuthUser):
    return await Customer.find(Customer.workshop_id == user["uid"]).to_list()

@router.put("/customers/{customer_id}", response_model=Customer)
async def update_customer(customer_id: str, data: CustomerIn, user: AuthUser):
    customer = await find_document(Customer, customer_id, user["uid"], "Customer not found")
    await customer.update({"$set": data.model_dump(exclude_unset=True)})
    return await Customer.get(customer.id)

@router.delete("/customers/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(customer_id: str, user: AuthUser):
    customer = await find_document(Customer, customer_id, user["uid"], "Customer not found")
    await customer.delete()
    await log_activity(user["uid"], f"Deleted customer: {customer.name}", "Trash2")
    return None

# --- Job Cards ---
@router.post("/jobcards", response_model=JobCard, status_code=status.HTTP_201_CREATED)
async def create_job_card(data: JobCardIn, user: AuthUser):
    workshop_id = user["uid"]
    job_card = JobCard(**data.model_dump(), workshop_id=workshop_id)
    await job_card.insert()
    await log_activity(workshop_id, f"Job card created for {job_card.customer}", "FileText")
    return job_card

@router.get("/jobcards", response_model=List[JobCard])
async def get_job_cards(user: AuthUser):
    return await JobCard.find(JobCard.workshop_id == user["uid"]).to_list()

@router.put("/jobcards/{jobcard_id}", response_model=JobCard)
async def update_job_card(jobcard_id: str, data: JobCardIn, user: AuthUser):
    job_card = await find_document(JobCard, jobcard_id, user["uid"], "Job Card not found")
    await job_card.update({"$set": data.model_dump(exclude_unset=True)})
    return await JobCard.get(job_card.id)

# --- Invoices ---
@router.post("/invoices", response_model=Invoice, status_code=status.HTTP_201_CREATED)
async def create_invoice(data: InvoiceIn, user: AuthUser):
    workshop_id = user["uid"]
    invoice = Invoice(**data.model_dump(), workshop_id=workshop_id)
    await invoice.insert()
    await log_activity(workshop_id, f"Invoice created for {invoice.customer}", "DollarSign")
    return invoice

@router.get("/invoices", response_model=List[Invoice])
async def get_invoices(user: AuthUser):
    return await Invoice.find(Invoice.workshop_id == user["uid"]).to_list()

@router.put("/invoices/{invoice_id}", response_model=Invoice)
async def update_invoice(invoice_id: str, data: InvoiceIn, user: AuthUser):
    invoice = await find_document(Invoice, invoice_id, user["uid"], "Invoice not found")
    await invoice.update({"$set": data.model_dump(exclude_unset=True)})
    return await Invoice.get(invoice.id)

@router.delete("/invoices/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invoice(invoice_id: str, user: AuthUser):
    invoice = await find_document(Invoice, invoice_id, user["uid"], "Invoice not found")
    await invoice.delete()
    await log_activity(user["uid"], f"Deleted invoice for {invoice.customer}", "Trash2")
    return None

# --- Parts ---
@router.post("/parts", response_model=Part, status_code=status.HTTP_201_CREATED)
async def create_part(data: PartIn, user: AuthUser):
    workshop_id = user["uid"]
    part = Part(**data.model_dump(), workshop_id=workshop_id)
    await part.insert()
    await log_activity(workshop_id, f"Added part to inventory: {part.name}", "Package")
    return part

@router.get("/parts", response_model=List[Part])
async def get_parts(user: AuthUser):
    return await Part.find(Part.workshop_id == user["uid"]).to_list()

@router.put("/parts/{part_id}", response_model=Part)
async def update_part(part_id: str, data: PartIn, user: AuthUser):
    part = await find_document(Part, part_id, user["uid"], "Part not found")
    await part.update({"$set": data.model_dump(exclude_unset=True)})
    return await Part.get(part.id)

@router.delete("/parts/{part_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_part(part_id: str, user: AuthUser):
    part = await find_document(Part, part_id, user["uid"], "Part not found")
    await part.delete()
    return None

@router.get("/admin/workshops/{workshop_id}/jobcards", response_model=List[JobCard], tags=["Admin"])
async def get_admin_workshop_job_cards(workshop_id: str, is_admin: bool = Depends(verify_admin)):
    """
    Admin: Get all job cards for a specific workshop.
    """
    return await JobCard.find(JobCard.workshop_id == workshop_id).sort(-JobCard.id).to_list()