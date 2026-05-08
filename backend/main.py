from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from database import engine, SessionLocal, Base, User, Employee, Shift, Schedule, Leave
import schemas, auth, ai_scheduler
import shutil
import os
import datetime

Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.get("/")
def read_root():
    return {"message": "Shift Management AI API is running", "status": "online"}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(token: str = Depends(auth.oauth2_scheme), db: Session = Depends(get_db)):
    payload = auth.decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.query(User).filter(User.username == payload["username"]).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user

def require_role(roles: list):
    def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
        return current_user
    return role_checker

@app.post("/login")
def login(user: schemas.UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == user.username).first()
    if not db_user or not auth.verify_password(user.password, db_user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect credentials")
    access_token = auth.create_access_token(data={"sub": db_user.username, "role": db_user.role})
    return {"access_token": access_token, "token_type": "bearer", "role": db_user.role}

@app.post("/create-user")
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db), current_user: User = Depends(require_role(["admin"]))):
    existing = db.query(User).filter(User.username == user.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already registered")
    hashed_pwd = auth.get_password_hash(user.password)
    new_user = User(username=user.username, password_hash=hashed_pwd, role=user.role)
    db.add(new_user)
    db.commit()
    return {"msg": f"User {user.username} created successfully"}

@app.get("/users")
def get_users(db: Session = Depends(get_db), current_user: User = Depends(require_role(["admin"]))):
    users = db.query(User).all()
    return [{"id": u.id, "username": u.username, "role": u.role} for u in users]

@app.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_role(["admin"]))):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"msg": "User deleted successfully"}

@app.get("/employees")
def get_employees(db: Session = Depends(get_db), current_user: User = Depends(require_role(["manager", "admin", "supervisor"]))):
    emps = db.query(Employee).all()
    return emps

@app.post("/employees")
def create_employee(emp: schemas.EmployeeCreate, db: Session = Depends(get_db), current_user: User = Depends(require_role(["manager", "admin"]))):
    existing = db.query(Employee).filter(Employee.emp_id == emp.emp_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Employee ID already exists")
    new_emp = Employee(
        emp_id=emp.emp_id,
        name=emp.name,
        skills=emp.skills,
        preferred_shift=emp.preferred_shift,
        max_hours=emp.max_hours,
        weekly_off=emp.weekly_off
    )
    db.add(new_emp)
    db.commit()
    return {"msg": f"Employee {emp.name} created successfully"}

@app.put("/employees/{emp_id}")
def update_employee(emp_id: int, emp_data: schemas.EmployeeUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_role(["manager", "admin"]))):
    db_emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not db_emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    if emp_data.name is not None: db_emp.name = emp_data.name
    if emp_data.emp_id is not None: db_emp.emp_id = emp_data.emp_id
    if emp_data.skills is not None: db_emp.skills = emp_data.skills
    if emp_data.preferred_shift is not None: db_emp.preferred_shift = emp_data.preferred_shift
    if emp_data.max_hours is not None: db_emp.max_hours = emp_data.max_hours
    if emp_data.weekly_off is not None: db_emp.weekly_off = emp_data.weekly_off
    
    db.commit()
    return {"msg": f"Employee {db_emp.name} updated successfully"}

@app.delete("/employees/{emp_id}")
def delete_employee(emp_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_role(["manager", "admin"]))):
    db_emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not db_emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    db.delete(db_emp)
    db.commit()
    return {"msg": "Employee deleted successfully"}

@app.get("/shifts")
def get_shifts(db: Session = Depends(get_db), current_user: User = Depends(require_role(["manager", "admin", "supervisor"]))):
    shifts = db.query(Shift).all()
    return shifts

@app.get("/leaves")
def get_leaves(date: str = None, db: Session = Depends(get_db), current_user: User = Depends(require_role(["manager", "admin", "supervisor"]))):
    if not date:
        date = datetime.date.today().isoformat()
    leaves = db.query(Leave).filter(Leave.date == date).all()
    res = []
    for l in leaves:
        res.append({
            "id": l.id,
            "employee_name": l.employee.name,
            "employee_id": l.employee.emp_id,
            "date": l.date
        })
    return res

@app.get("/dashboard-summary")
@app.get("/summary")
async def get_dashboard_summary(db: Session = Depends(get_db), current_user: User = Depends(require_role(["manager", "admin", "supervisor"]))):
    today = datetime.date.today().isoformat()
    
    # Pre-fetch counts in one pass
    emp_count = db.query(Employee).count()
    shift_count = db.query(Shift).count()
    leave_count = db.query(Leave).filter(Leave.date == today).count()
    
    # Optimized shift data aggregation using GROUP BY
    from sqlalchemy import func
    shift_assignments_query = (
        db.query(Shift.name, func.count(Schedule.id))
        .join(Schedule, Schedule.shift_id == Shift.id)
        .filter(Schedule.date == today)
        .group_by(Shift.name)
        .all()
    )
    
    shift_data = {name: count for name, count in shift_assignments_query}
    
    # Fill in missing shifts with 0
    all_shifts = db.query(Shift.name).all()
    for (s_name,) in all_shifts:
        if s_name not in shift_data:
            shift_data[s_name] = 0
    
    # Weekly off count for today
    target_date_obj = datetime.date.today()
    day_name = target_date_obj.strftime('%A')
    weekly_off_count = db.query(Employee).filter(Employee.weekly_off == day_name).count()

    return { 
        "total_employees": emp_count,
        "active_shifts": shift_count,
        "today_leaves": leave_count,
        "today_weekly_off": weekly_off_count,
        "shift_assignments": shift_data
    }

@app.post("/upload-excel")
async def upload_excel(type: str, file: UploadFile = File(...), db: Session = Depends(get_db), current_user: User = Depends(require_role(["manager", "admin"]))):
    if type not in ["employees", "shifts"]:
        raise HTTPException(status_code=400, detail="Type must be employees or shifts")
    os.makedirs("uploads", exist_ok=True)
    file_path = f"uploads/{file.filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # USER REQUEST: Clear all existing data before loading new Excel data
    ai_scheduler.clear_all_operational_data(db)
    
    if type == "employees":
        ai_scheduler.parse_employees_excel(file_path, db)
    elif type == "shifts":
        ai_scheduler.parse_shifts_excel(file_path, db)
    
    # Ensure system doesn't break if Excel had no shift info
    ai_scheduler.ensure_default_shifts(db)
    
    ai_scheduler.clear_schedule_cache()
    
    # Trigger AI schedule generation
    today = datetime.date.today().isoformat()
    ai_scheduler.generate_ai_schedule(db, today, force_refresh=True)
    
    return {"msg": f"Database cleared. {type} loaded from new file. AI has regenerated the schedule."}

@app.post("/auto-assign-weekly-offs")
async def auto_assign_weekly_offs(db: Session = Depends(get_db), current_user: User = Depends(require_role(["manager", "admin"]))):
    ai_scheduler.auto_assign_weekly_offs(db)
    ai_scheduler.clear_schedule_cache()
    # Regenerate today's schedule to reflect new weekly offs
    today = datetime.date.today().isoformat()
    ai_scheduler.generate_ai_schedule(db, today, force_refresh=True)
    return {"msg": "AI has successfully distributed weekly offs for all employees and updated the schedule."}

@app.post("/generate-schedule")
async def generate_schedule(data: dict, db: Session = Depends(get_db), current_user: User = Depends(require_role(["manager", "admin"]))):
    date_str = data.get("date")
    if not date_str:
        date_str = datetime.date.today().isoformat()
    
    # Inline generation for immediate result, but optimized
    ai_scheduler.generate_ai_schedule(db, date_str, force_refresh=True)
    return {"msg": f"Schedule generated for {date_str}"}


@app.get("/get-schedule")
async def get_schedule(background_tasks: BackgroundTasks, date: str = None, db: Session = Depends(get_db), current_user: User = Depends(require_role(["manager", "supervisor", "admin"]))):
    if not date:
        date = datetime.date.today().isoformat()
    
    # 1. Check if schedule exists for requested date
    existing_schedule = db.query(Schedule).filter(Schedule.date == date).first()
    if not existing_schedule:
        # Generate inline if missing, as it's now fast (< 100ms usually)
        ai_scheduler.generate_ai_schedule(db, date)
    
    # 2. Proactively generate schedule for next day in background
    requested_date = datetime.date.fromisoformat(date)
    next_day = requested_date + datetime.timedelta(days=1)
    next_day_str = next_day.isoformat()
    
    def generate_background(d_str):
        # We need a new session for background tasks
        db_bg = SessionLocal()
        try:
            ai_scheduler.generate_ai_schedule(db_bg, d_str)
        finally:
            db_bg.close()

    background_tasks.add_task(generate_background, next_day_str)
        
    # 3. Fetch and return results quickly with joinedload to avoid N+1
    from sqlalchemy.orm import joinedload
    schedules = (
        db.query(Schedule)
        .options(joinedload(Schedule.shift), joinedload(Schedule.employee), joinedload(Schedule.replaced_employee))
        .filter(Schedule.date == date)
        .all()
    )
    
    # Fetch weekly off employees for today
    day_name = datetime.date.fromisoformat(date).strftime('%A')
    weekly_offs = db.query(Employee).filter(Employee.weekly_off == day_name).all()
    
    res = {
        "shifts": {},
        "weekly_off": [{
            "id": emp.id,
            "emp_id": emp.emp_id,
            "name": emp.name,
            "role": emp.preferred_shift # Using preferred_shift as a proxy for role
        } for emp in weekly_offs]
    }
    
    for sched in schedules:
        shift_name = sched.shift.name
        if shift_name not in res["shifts"]:
            res["shifts"][shift_name] = {
                "shift_details": {"start": sched.shift.start_time, "end": sched.shift.end_time}, 
                "employees": []
            }
        res["shifts"][shift_name]["employees"].append({
            "id": sched.employee.id, 
            "emp_id": sched.employee.emp_id,
            "name": sched.employee.name,
            "is_override": sched.is_override,
            "role": sched.employee.preferred_shift,
            "skills": sched.employee.skills,
            "start_time": sched.shift.start_time,
            "end_time": sched.shift.end_time,
            "replaced_name": sched.replaced_employee.name if sched.replaced_employee else None
        })
    
    return res

@app.post("/apply-leave")
async def apply_leave(leave: schemas.LeaveApply, db: Session = Depends(get_db), current_user: User = Depends(require_role(["supervisor", "manager", "admin"]))):
    emp = db.query(Employee).filter(Employee.name == leave.employee_name).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    new_leave = Leave(employee_id=emp.id, date=leave.date)
    db.add(new_leave)
    db.commit()
    
    # Clear cache and trigger AI auto reassignment
    ai_scheduler.clear_schedule_cache()
    ai_scheduler.handle_leave_request(db, emp.id, leave.date)
    
    # Get current schedule for the leave date optimized with joinedload
    from sqlalchemy.orm import joinedload
    schedules = (
        db.query(Schedule)
        .options(joinedload(Schedule.employee), joinedload(Schedule.shift))
        .filter(Schedule.date == leave.date)
        .all()
    )
    
    replacement_info = []
    for sched in schedules:
        replacement_info.append({
            "employee_name": sched.employee.name,
            "employee_id": sched.employee.emp_id,
            "shift": sched.shift.name,
            "shift_time": f"{sched.shift.start_time}-{sched.shift.end_time}"
        })
    
    return {
        "msg": f"Leave applied for {emp.name} on {leave.date}. AI automatically handled replacement.",
        "replacements": replacement_info
    }

@app.delete("/cancel-leave")
async def cancel_leave(employee_name: str, date: str, db: Session = Depends(get_db), current_user: User = Depends(require_role(["supervisor", "manager", "admin"]))):
    emp = db.query(Employee).filter(Employee.name == employee_name).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    leave = db.query(Leave).filter(Leave.employee_id == emp.id, Leave.date == date).first()
    if not leave:
        raise HTTPException(status_code=404, detail="Leave not found")
    
    db.delete(leave)
    db.commit()
    
    # Clear cache and trigger AI to handle cancellation
    ai_scheduler.clear_schedule_cache()
    ai_scheduler.handle_leave_cancellation(db, emp.id, date)
    return {"msg": f"Leave cancelled for {emp.name} on {date}. AI handled restoration."}

@app.put("/update-schedule")
def update_schedule(data: schemas.ScheduleUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_role(["manager", "admin"]))):
    # Manual override of a specific assignment
    sched = db.query(Schedule).filter(
        Schedule.date == data.date,
        Schedule.shift_id == data.shift_id,
        Schedule.employee_id == data.old_employee_id
    ).first()
    
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule assignment not found")
    
    # Check if new employee exists
    new_emp = db.query(Employee).filter(Employee.id == data.new_employee_id).first()
    if not new_emp:
        raise HTTPException(status_code=404, detail="Target employee not found")
        
    sched.employee_id = data.new_employee_id
    db.commit()
    return {"msg": "Schedule updated successfully"}

# Setup initial admin user
@app.on_event("startup")
def startup_event():
    try:
        db = SessionLocal()
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            hashed_pwd = auth.get_password_hash("admin123")
            new_admin = User(username="admin", password_hash=hashed_pwd, role="admin")
            db.add(new_admin)
            
            # Create default manager and supervisor for testing
            db.add(User(username="manager", password_hash=auth.get_password_hash("manager123"), role="manager"))
            db.add(User(username="supervisor", password_hash=auth.get_password_hash("supervisor123"), role="supervisor"))
            db.commit()
        
        # Auto-generate schedule for today if not exists (with error handling)
        try:
            today = datetime.date.today().isoformat()
            existing_schedule = db.query(Schedule).filter(Schedule.date == today).first()
            if not existing_schedule:
                ai_scheduler.generate_ai_schedule(db, today)
        except Exception as e:
            print(f"[Startup] Error generating today's schedule: {e}")
        
        # Auto-generate schedule for next week (with error handling)
        try:
            next_monday = datetime.date.today()
            next_monday = next_monday + datetime.timedelta(days=(7 - next_monday.weekday()))
            for i in range(7):
                future_date = next_monday + datetime.timedelta(days=i)
                date_str = future_date.isoformat()
                existing_schedule = db.query(Schedule).filter(Schedule.date == date_str).first()
                if not existing_schedule:
                    ai_scheduler.generate_ai_schedule(db, date_str)
        except Exception as e:
            print(f"[Startup] Error generating next week schedule: {e}")
        
        db.close()
    except Exception as e:
        print(f"[Startup] Error during startup: {e}")
        if 'db' in locals():
            db.close()
