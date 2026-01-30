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
    Part, PartIn,
    Todo, TodoIn,
    ServiceCatalog, ServiceCatalogIn
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

# Helper to handle Beanie/Motor collection access differences
def get_db_collection(model_class):
    if hasattr(model_class, "get_pymongo_collection"):
        return model_class.get_pymongo_collection()
    if hasattr(model_class, "get_motor_collection"):
        return model_class.get_motor_collection()
    # Fallback/Default for older versions
    return model_class.get_motor_collection()

# --- ADMIN ENDPOINTS ---

@router.get("/admin/workshops", response_model=List[WorkshopStats], tags=["Admin"])
async def get_all_workshops_stats(is_admin: bool = Depends(verify_admin)):
    """
    Admin: Fetches statistics for all workshops.
    """
    try:
        booking_collection = get_db_collection(Booking)
        invoice_collection = get_db_collection(Invoice)

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
        booking_stats = await booking_collection.aggregate(booking_pipeline).to_list(None)
        booking_map = {item["_id"]: item for item in booking_stats if item["_id"]}

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
        revenue_stats = await invoice_collection.aggregate(revenue_pipeline).to_list(None)
        revenue_map = {item["_id"]: item["totalRevenue"] for item in revenue_stats if item["_id"]}

        # 3. Get all unique workshop IDs from both sources
        all_workshop_ids = set(booking_map.keys()) | set(revenue_map.keys())

        results = []
        for wid in all_workshop_ids:
            if not wid: continue
            
            # Fetch user details from Firebase safely
            name = "Unknown Workshop"
            email = str(wid)
            try:
                user_record = auth.get_user(wid)
                name = user_record.display_name or "Unknown Workshop"
                email = user_record.email or str(wid)
            except Exception as e:
                # Log error if needed, but continue execution
                print(f"Error fetching user {wid}: {e}")
                pass

            b_data = booking_map.get(wid, {"total": 0, "pending": 0})
            rev = revenue_map.get(wid, 0.0)

            results.append(WorkshopStats(
                workshop_id=str(wid),
                name=name,
                email=email,
                total_bookings=b_data.get("total", 0),
                revenue=rev,
                pending_tasks=b_data.get("pending", 0)
            ))

        return results
    except Exception as e:
        print(f"Admin Stats Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/admin/workshops/{workshop_id}/jobcards", response_model=List[JobCard], tags=["Admin"])
async def get_admin_workshop_job_cards(workshop_id: str, is_admin: bool = Depends(verify_admin)):
    """
    Admin: Get all job cards for a specific workshop.
    """
    return await JobCard.find(JobCard.workshop_id == workshop_id).sort(-JobCard.id).to_list()

# --- WORKSHOP ENDPOINTS (Standard) ---

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
    
    # Check if a Job Card already exists for this booking_id
    existing_jc = await JobCard.find_one(
        JobCard.workshop_id == workshop_id,
        JobCard.booking_id == data.booking_id
    )
    
    if existing_jc:
        # Update the existing Job Card with new details from the booking/form
        update_data = data.model_dump(exclude_unset=True)
        await existing_jc.update({"$set": update_data})
        return await JobCard.get(existing_jc.id)
    else:
        # Create a new one if it doesn't exist
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
    
    # 1. Fetch the linked Job Card to get the most recent parts and services
    # We use the jobCardId provided in the request data
    job_card = await find_document(JobCard, data.jobCardId, workshop_id, "Linked Job Card not found")

    # 2. Automatically calculate the total amount including taxes
    # This ensures that even if the frontend calculation varies, the DB remains the source of truth
    parts_total = sum(p.quantity * p.price * (1 + p.taxPercent / 100) for p in job_card.spareParts)
    services_total = sum(s.cost * (1 + s.taxPercent / 100) for s in job_card.services)
    calculated_total = round(parts_total + services_total, 2)

    # 3. Create the invoice with the calculated amount
    # We override the 'amount' field from the input data with our calculated total
    invoice_data = data.model_dump()
    invoice_data["amount"] = calculated_total
    
    invoice = Invoice(**invoice_data, workshop_id=workshop_id)
    await invoice.insert()
    
    # 4. Log the activity for the dashboard
    await log_activity(workshop_id, f"Invoice created for {invoice.customer}: ₹{calculated_total}", "DollarSign")
    
    return invoice

@router.get("/invoices", response_model=List[Invoice])
async def get_invoices(user: AuthUser):
    # Returns all invoices for the specific workshop to populate the dashboard/list
    return await Invoice.find(Invoice.workshop_id == user["uid"]).to_list()

@router.put("/invoices/{invoice_id}", response_model=Invoice)
async def update_invoice(invoice_id: str, data: InvoiceIn, user: AuthUser):
    # Ensure the invoice exists and belongs to the user before updating
    invoice = await find_document(Invoice, invoice_id, user["uid"], "Invoice not found")
    
    # Update logic: we allow updating notes or status, but total amount is usually tied to items
    await invoice.update({"$set": data.model_dump(exclude_unset=True)})
    return await Invoice.get(invoice.id)

@router.delete("/invoices/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invoice(invoice_id: str, user: AuthUser):
    # Standard deletion with activity logging
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


@router.post("/todos", response_model=Todo, status_code=status.HTTP_201_CREATED)
async def create_todo(data: TodoIn, user: AuthUser):
    workshop_id = user["uid"]
    todo = Todo(**data.model_dump(), workshop_id=workshop_id)
    await todo.insert()
    await log_activity(workshop_id, f"Created task: {todo.title}", "CheckSquare")
    return todo

@router.get("/todos", response_model=List[Todo])
async def get_todos(user: AuthUser):
    return await Todo.find(Todo.workshop_id == user["uid"]).sort(-Todo.created_at).to_list()

@router.put("/todos/{todo_id}", response_model=Todo)
async def update_todo(todo_id: str, data: TodoIn, user: AuthUser):
    todo = await find_document(Todo, todo_id, user["uid"], "Task not found")
    await todo.update({"$set": data.model_dump(exclude_unset=True)})
    return await Todo.get(todo.id)

@router.delete("/todos/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_todo(todo_id: str, user: AuthUser):
    todo = await find_document(Todo, todo_id, user["uid"], "Task not found")
    await todo.delete()
    return None

# --- Service Catalog Routes ---

@router.post("/services", response_model=ServiceCatalog, status_code=status.HTTP_201_CREATED)
async def create_service(data: ServiceCatalogIn, user: AuthUser):
    workshop_id = user["uid"]
    service = ServiceCatalog(**data.model_dump(), workshop_id=workshop_id)
    await service.insert()
    await log_activity(workshop_id, f"Created service: {service.name}", "Layers")
    return service

@router.get("/services", response_model=List[ServiceCatalog])
async def get_services(user: AuthUser):
    return await ServiceCatalog.find(ServiceCatalog.workshop_id == user["uid"]).to_list()

@router.put("/services/{service_id}", response_model=ServiceCatalog)
async def update_service(service_id: str, data: ServiceCatalogIn, user: AuthUser):
    service = await find_document(ServiceCatalog, service_id, user["uid"], "Service not found")
    await service.update({"$set": data.model_dump(exclude_unset=True)})
    return await ServiceCatalog.get(service.id)

@router.delete("/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(service_id: str, user: AuthUser):
    service = await find_document(ServiceCatalog, service_id, user["uid"], "Service not found")
    await service.delete()
    return None