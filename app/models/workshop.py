from beanie import Document, Indexed, PydanticObjectId
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

# --- Sub-models ---

class InvoiceItem(BaseModel):
    description: str
    quantity: int
    unitPrice: float

class SparePartItem(BaseModel):
    id: str
    name: str
    quantity: int
    price: float
    taxPercent: float

class ServiceItem(BaseModel):
    id: str
    description: str
    cost: float
    taxPercent: float

# --- Main Document Models ---

class Employee(Document):
    id: PydanticObjectId = Field(default_factory=PydanticObjectId, alias="_id")
    workshop_id: Indexed(str)
    designation: str
    firstName: str
    lastName: Optional[str] = None
    phone: str
    email: Optional[str] = None
    address: Optional[str] = None
    joiningDate: Optional[datetime] = None
    exitDate: Optional[datetime] = None
    salary: Optional[str] = None
    bankDetails: Optional[str] = None
    
    class Settings:
        name = "employees"

class Department(Document):
    id: PydanticObjectId = Field(default_factory=PydanticObjectId, alias="_id")
    workshop_id: Indexed(str)
    name: str
    
    class Settings:
        name = "departments"

class Booking(Document):
    id: PydanticObjectId = Field(default_factory=PydanticObjectId, alias="_id")
    workshop_id: Indexed(str)
    customerType: str
    customerName: str
    phone: str
    email: Optional[str] = None
    address: Optional[str] = None
    taxNumber: Optional[str] = None
    drivingLicenseNumber: Optional[str] = None
    drivingLicenseExpiry: Optional[datetime] = None
    businessType: str
    subType: str
    carNumber: str
    makeAndModel: str
    fuelType: str
    transmissionType: Optional[str] = None
    engineNumber: Optional[str] = None
    vinNumber: Optional[str] = None
    variant: Optional[str] = None
    makeYear: Optional[str] = None
    color: Optional[str] = None
    runningPerDay: Optional[str] = None
    insuranceDetails: Optional[str] = None
    serviceAdvisor: str
    bookingType: str
    department: str
    customerRemark: Optional[str] = None
    odometer: str
    fuelIndicator: int
    status: str
    date: Optional[str] = None
    time: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "bookings"

class Customer(Document):
    id: PydanticObjectId = Field(default_factory=PydanticObjectId, alias="_id")
    workshop_id: Indexed(str)
    name: str
    email: str
    phone: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipCode: Optional[str] = None
    notes: Optional[str] = None
    
    class Settings:
        name = "customers"

class JobCard(Document):
    id: PydanticObjectId = Field(default_factory=PydanticObjectId, alias="_id")
    workshop_id: Indexed(str)
    booking_id: Indexed(str)
    customer: str
    phone: Optional[str] = None
    email: Optional[str] = None
    vehicle: str
    service: str
    date: str
    time: str
    # Updated Fields
    workers: List[str] = []
    spareParts: List[SparePartItem] = []
    services: List[ServiceItem] = []
    issues: List[str] = []
    photos: List[str] = []
    signature: Optional[str] = None
    notes: Optional[str] = None
    
    class Settings:
        name = "job_cards"

class Invoice(Document):
    id: PydanticObjectId = Field(default_factory=PydanticObjectId, alias="_id")
    workshop_id: Indexed(str)
    jobCardId: str
    customer: str
    amount: float
    items: List[InvoiceItem] = []
    date: str
    dueDate: str
    status: str
    notes: Optional[str] = None
    
    class Settings:
        name = "invoices"

class Part(Document):
    id: PydanticObjectId = Field(default_factory=PydanticObjectId, alias="_id")
    workshop_id: Indexed(str)
    name: str
    partNumber: str
    category: str
    quantity: int
    minStock: int
    unitCost: float
    supplier: Optional[str] = None
    notes: Optional[str] = None
    
    class Settings:
        name = "parts"

# --- Input Models ---

class EmployeeIn(BaseModel):
    designation: str
    firstName: str
    lastName: Optional[str] = None
    phone: str
    email: Optional[str] = None
    address: Optional[str] = None
    joiningDate: Optional[datetime] = None
    exitDate: Optional[datetime] = None
    salary: Optional[str] = None
    bankDetails: Optional[str] = None

class DepartmentIn(BaseModel):
    name: str

class BookingIn(BaseModel):
    customerType: str
    customerName: str
    phone: str
    email: Optional[str] = None
    address: Optional[str] = None
    taxNumber: Optional[str] = None
    drivingLicenseNumber: Optional[str] = None
    drivingLicenseExpiry: Optional[datetime] = None
    businessType: str
    subType: str
    carNumber: str
    makeAndModel: str
    fuelType: str
    transmissionType: Optional[str] = None
    engineNumber: Optional[str] = None
    vinNumber: Optional[str] = None
    variant: Optional[str] = None
    makeYear: Optional[str] = None
    color: Optional[str] = None
    runningPerDay: Optional[str] = None
    insuranceDetails: Optional[str] = None
    serviceAdvisor: str
    bookingType: str
    department: str
    customerRemark: Optional[str] = None
    odometer: str
    fuelIndicator: int
    status: str
    date: Optional[str] = None
    time: Optional[str] = None
    
class BookingStatusUpdate(BaseModel):
    status: str

class CustomerIn(BaseModel):
    name: str
    email: str
    phone: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipCode: Optional[str] = None
    notes: Optional[str] = None

class JobCardIn(BaseModel):
    booking_id: str
    customer: str
    phone: Optional[str] = None
    email: Optional[str] = None
    vehicle: str
    service: str
    date: str
    time: str
    workers: List[str] = []
    spareParts: List[SparePartItem] = []
    services: List[ServiceItem] = []
    issues: List[str] = []
    photos: List[str] = []
    signature: Optional[str] = None
    notes: Optional[str] = None
    assignedMechanic: Optional[str] = None

class InvoiceIn(BaseModel):
    jobCardId: str
    customer: str
    amount: float
    items: List[InvoiceItem] = []
    date: str
    dueDate: str
    status: str
    notes: Optional[str] = None

class PartIn(BaseModel):
    name: str
    partNumber: str
    category: str
    quantity: int
    minStock: int
    unitCost: float
    supplier: Optional[str] = None
    notes: Optional[str] = None