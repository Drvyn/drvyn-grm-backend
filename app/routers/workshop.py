from fastapi import APIRouter, HTTPException, status
from typing import List
from datetime import datetime

from app.auth import AuthUser
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

router = APIRouter(
    prefix="/workshop",
    tags=["Workshop Data"]
)

# --- Helper Function ---
async def find_document(model, doc_id, workshop_id, not_found_msg="Item not found"):
    """Fetches a document by its ID and workshop_id."""
    try:
        doc = await model.get(PydanticObjectId(doc_id))
    except Exception:
        doc = None
        
    if not doc or doc.workshop_id != workshop_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found_msg)
    return doc

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
    
    # Re-fetch to get updated data
    updated_employee = await Employee.get(employee.id)
    return updated_employee

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
    booking = Booking(
        **data.model_dump(), 
        workshop_id=workshop_id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
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
    
    updated_booking = await Booking.get(booking.id)
    await log_activity(user["uid"], f"Updated booking for {updated_booking.customerName}", "Edit2")
    return updated_booking

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
    
    updated_booking = await Booking.get(booking.id)
    await log_activity(user["uid"], f"Booking for {booking.customerName} set to {data.status}", "Wrench")
    return updated_booking

# --- Customers (Example from your 'customers/page.tsx') ---
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

# ... (Add PUT and DELETE for Customers as needed, following the pattern) ...

# --- Job Cards (Example from your 'bookings/[id]/page.tsx') ---
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

# ... (Add PUT, DELETE, and GET by booking_id for JobCards as needed) ...

# --- Invoices (Example from your 'invoices/page.tsx') ---
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

# ... (Add PUT and DELETE for Invoices as needed) ...

# --- Parts (Example from your 'parts/page.tsx') ---
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

# ... (Add PUT and DELETE for Parts as needed) ...