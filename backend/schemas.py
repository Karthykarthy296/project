from pydantic import BaseModel
from typing import List, Optional

class UserCreate(BaseModel):
    username: str
    password: str
    role: str

class UserLogin(BaseModel):
    username: str
    password: str

class LeaveApply(BaseModel):
    employee_name: str
    date: str

class ScheduleUpdate(BaseModel):
    date: str
    shift_id: int
    old_employee_id: int
    new_employee_id: int

class EmployeeCreate(BaseModel):
    emp_id: str
    name: str
    skills: List[str]
    preferred_shift: str
    max_hours: int
    weekly_off: Optional[str] = None

class EmployeeUpdate(BaseModel):
    emp_id: Optional[str] = None
    name: Optional[str] = None
    skills: Optional[List[str]] = None
    preferred_shift: Optional[str] = None
    max_hours: Optional[int] = None
    weekly_off: Optional[str] = None
