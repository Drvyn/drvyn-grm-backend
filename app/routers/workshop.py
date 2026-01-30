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
    ServiceCatalog, ServiceCatalogIn,
    Expense, ExpenseIn,
    Vehicle, VehicleIn
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
    return model_class.get_motor_collection()

# --- HELPER FUNCTION: Sync Vehicle from Job Card ---
async def sync_vehicle_from_jobcard(workshop_id: str, jc_data: JobCard):
    """
    Automatically creates or updates a Vehicle record whenever a Job Card is used.
    """
    if not jc_data.carNumber:
        return # Cannot save without a Reg Number

    reg_number = jc_data.carNumber.replace(" ", "").upper()
    
    # Try to find existing vehicle
    existing_vehicle = await Vehicle.find_one(
        Vehicle.workshop_id == workshop_id,
        Vehicle.carNumber == reg_number
    )

    # Parse Make/Model if available
    make, model = "Unknown", "Unknown"
    if jc_data.makeAndModel:
        parts = jc_data.makeAndModel.split(" ", 1)
        if len(parts) > 0: make = parts[0]
        if len(parts) > 1: model = parts[1]

    vehicle_data = {
        "make": make,
        "model": model,
        "makeYear": jc_data.makeYear,
        "color": jc_data.color,
        "vinNumber": jc_data.vinNumber,
        "engineNumber": jc_data.engineNumber,
        "fuelType": jc_data.fuelType,
        "transmissionType": jc_data.transmissionType,
        "odometer": jc_data.odometer,
        "fuelLevel": jc_data.fuelIndicator,
        "customerName": jc_data.customer,
        "customerPhone": jc_data.phone,
        "updated_at": datetime.utcnow()
    }

    if existing_vehicle:
        # Update existing vehicle with latest info from this job card
        await existing_vehicle.update({"$set": vehicle_data})
    else:
        # Create new vehicle
        new_vehicle = Vehicle(
            workshop_id=workshop_id,
            carNumber=reg_number,
            **vehicle_data
        )
        await new_vehicle.insert()

# --- ADMIN ENDPOINTS ---

@router.get("/admin/workshops", response_model=List[WorkshopStats], tags=["Admin"])
async def get_all_workshops_stats(is_admin: bool = Depends(verify_admin)):
    try:
        booking_collection = get_db_collection(Booking)
        invoice_collection = get_db_collection(Invoice)

        # 1. Aggregate Bookings
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

        # 2. Aggregate Revenue
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

        all_workshop_ids = set(booking_map.keys()) | set(revenue_map.keys())

        results = []
        for wid in all_workshop_ids:
            if not wid: continue
            name = "Unknown Workshop"
            email = str(wid)
            try:
                user_record = auth.get_user(wid)
                name = user_record.display_name or "Unknown Workshop"
                email = user_record.email or str(wid)
            except Exception:
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
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/admin/workshops/{workshop_id}/jobcards", response_model=List[JobCard], tags=["Admin"])
async def get_admin_workshop_job_cards(workshop_id: str, is_admin: bool = Depends(verify_admin)):
    return await JobCard.find(JobCard.workshop_id == workshop_id).sort(-JobCard.id).to_list()

# --- WORKSHOP ENDPOINTS ---

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
    await employee.update({"$set": data.model_dump(exclude_unset=True)})
    return await Employee.get(employee.id)

@router.delete("/employees/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_employee(employee_id: str, user: AuthUser):
    employee = await find_document(Employee, employee_id, user["uid"], "Employee not found")
    await employee.delete()
    return None

# --- Departments ---
@router.post("/departments", response_model=Department, status_code=status.HTTP_201_CREATED)
async def create_department(data: DepartmentIn, user: AuthUser):
    workshop_id = user["uid"]
    department = Department(**data.model_dump(), workshop_id=workshop_id)
    await department.insert()
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
    return await Booking.get(booking.id)

@router.delete("/bookings/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_booking(booking_id: str, user: AuthUser):
    booking = await find_document(Booking, booking_id, user["uid"], "Booking not found")
    await booking.delete()
    return None

@router.put("/bookings/{booking_id}/status", response_model=Booking)
async def update_booking_status(booking_id: str, data: BookingStatusUpdate, user: AuthUser):
    booking = await find_document(Booking, booking_id, user["uid"], "Booking not found")
    await booking.update({"$set": {"status": data.status, "updated_at": datetime.utcnow()}})
    return await Booking.get(booking.id)

# --- Customers ---
@router.post("/customers", response_model=Customer, status_code=status.HTTP_201_CREATED)
async def create_customer(data: CustomerIn, user: AuthUser):
    workshop_id = user["uid"]
    customer = Customer(**data.model_dump(), workshop_id=workshop_id)
    await customer.insert()
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
    return None

# --- Job Cards (UPDATED WITH SYNC) ---
@router.post("/jobcards", response_model=JobCard, status_code=status.HTTP_201_CREATED)
async def create_job_card(data: JobCardIn, user: AuthUser):
    workshop_id = user["uid"]
    existing_jc = await JobCard.find_one(
        JobCard.workshop_id == workshop_id,
        JobCard.booking_id == data.booking_id
    )
    
    if existing_jc:
        update_data = data.model_dump(exclude_unset=True)
        await existing_jc.update({"$set": update_data})
        job_card = await JobCard.get(existing_jc.id)
    else:
        job_card = JobCard(**data.model_dump(), workshop_id=workshop_id)
        await job_card.insert()
        await log_activity(workshop_id, f"Job card created for {job_card.customer}", "FileText")

    # SYNC VEHICLE
    if job_card.carNumber:
        await sync_vehicle_from_jobcard(workshop_id, job_card)
        
    return job_card

@router.get("/jobcards", response_model=List[JobCard])
async def get_job_cards(user: AuthUser):
    return await JobCard.find(JobCard.workshop_id == user["uid"]).to_list()

@router.put("/jobcards/{jobcard_id}", response_model=JobCard)
async def update_job_card(jobcard_id: str, data: JobCardIn, user: AuthUser):
    job_card = await find_document(JobCard, jobcard_id, user["uid"], "Job Card not found")
    await job_card.update({"$set": data.model_dump(exclude_unset=True)})
    updated_jc = await JobCard.get(job_card.id)
    
    # SYNC VEHICLE
    if updated_jc.carNumber:
        await sync_vehicle_from_jobcard(user["uid"], updated_jc)
        
    return updated_jc

# --- Invoices ---
@router.post("/invoices", response_model=Invoice, status_code=status.HTTP_201_CREATED)
async def create_invoice(data: InvoiceIn, user: AuthUser):
    workshop_id = user["uid"]
    job_card = await find_document(JobCard, data.jobCardId, workshop_id, "Linked Job Card not found")
    parts_total = sum(p.quantity * p.price * (1 + p.taxPercent / 100) for p in job_card.spareParts)
    services_total = sum(s.cost * (1 + s.taxPercent / 100) for s in job_card.services)
    calculated_total = round(parts_total + services_total, 2)
    invoice_data = data.model_dump()
    invoice_data["amount"] = calculated_total
    invoice = Invoice(**invoice_data, workshop_id=workshop_id)
    await invoice.insert()
    await log_activity(workshop_id, f"Invoice created for {invoice.customer}: ₹{calculated_total}", "DollarSign")
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
    return None

# --- Parts ---
@router.post("/parts", response_model=Part, status_code=status.HTTP_201_CREATED)
async def create_part(data: PartIn, user: AuthUser):
    workshop_id = user["uid"]
    part = Part(**data.model_dump(), workshop_id=workshop_id)
    await part.insert()
    await log_activity(workshop_id, f"Added part: {part.name}", "Package")
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

# --- Todos ---
@router.post("/todos", response_model=Todo, status_code=status.HTTP_201_CREATED)
async def create_todo(data: TodoIn, user: AuthUser):
    workshop_id = user["uid"]
    todo = Todo(**data.model_dump(), workshop_id=workshop_id)
    await todo.insert()
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

# --- Services ---
@router.post("/services", response_model=ServiceCatalog, status_code=status.HTTP_201_CREATED)
async def create_service(data: ServiceCatalogIn, user: AuthUser):
    workshop_id = user["uid"]
    service = ServiceCatalog(**data.model_dump(), workshop_id=workshop_id)
    await service.insert()
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

# --- Expenses ---
@router.post("/expenses", response_model=Expense, status_code=status.HTTP_201_CREATED)
async def create_expense(data: ExpenseIn, user: AuthUser):
    workshop_id = user["uid"]
    expense = Expense(**data.model_dump(), workshop_id=workshop_id)
    await expense.insert()
    await log_activity(workshop_id, f"Created expense: {expense.expense_type} - {expense.supplier}", "Receipt")
    return expense

@router.get("/expenses", response_model=List[Expense])
async def get_expenses(user: AuthUser):
    return await Expense.find(Expense.workshop_id == user["uid"]).sort(-Expense.created_at).to_list()

@router.delete("/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense(expense_id: str, user: AuthUser):
    expense = await find_document(Expense, expense_id, user["uid"], "Expense not found")
    await expense.delete()
    return None

# --- Vehicles ---
@router.post("/vehicles", response_model=Vehicle, status_code=status.HTTP_201_CREATED)
async def create_vehicle(data: VehicleIn, user: AuthUser):
    workshop_id = user["uid"]
    existing = await Vehicle.find_one(Vehicle.workshop_id == workshop_id, Vehicle.carNumber == data.carNumber)
    if existing:
        await existing.update({"$set": data.model_dump(exclude_unset=True)})
        return await Vehicle.get(existing.id)
    
    vehicle = Vehicle(**data.model_dump(), workshop_id=workshop_id)
    await vehicle.insert()
    await log_activity(workshop_id, f"Added vehicle: {vehicle.carNumber}", "Car")
    return vehicle

@router.get("/vehicles", response_model=List[Vehicle])
async def get_vehicles(user: AuthUser):
    return await Vehicle.find(Vehicle.workshop_id == user["uid"]).sort(-Vehicle.created_at).to_list()

@router.delete("/vehicles/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vehicle(vehicle_id: str, user: AuthUser):
    vehicle = await find_document(Vehicle, vehicle_id, user["uid"], "Vehicle not found")
    await vehicle.delete()
    return None

@router.post("/vehicles/import-from-jobcards", status_code=status.HTTP_200_OK)
async def import_vehicles_from_jobcards(user: AuthUser):
    workshop_id = user["uid"]
    job_cards = await JobCard.find(JobCard.workshop_id == workshop_id).to_list()
    
    count = 0
    for jc in job_cards:
        if jc.carNumber:
            await sync_vehicle_from_jobcard(workshop_id, jc)
            count += 1
            
    await log_activity(workshop_id, f"Scanned {len(job_cards)} Job Cards, synced {count} vehicles", "Database")
    return {"message": "Sync complete", "processed": count}


@router.post("/purchases", response_model=Purchase, status_code=status.HTTP_201_CREATED)
async def create_purchase(data: PurchaseIn, user: AuthUser):
    workshop_id = user["uid"]
    purchase = Purchase(**data.model_dump(), workshop_id=workshop_id)
    await purchase.insert()
    await log_activity(workshop_id, f"Purchase recorded: {purchase.itemName}", "ShoppingBag")
    return purchase

@router.get("/purchases", response_model=List[Purchase])
async def get_purchases(user: AuthUser):
    return await Purchase.find(Purchase.workshop_id == user["uid"]).sort(-Purchase.created_at).to_list()