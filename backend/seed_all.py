from database import SessionLocal, User, Employee, Shift, Schedule, Base, engine
from auth import get_password_hash
import ai_scheduler
from datetime import date

def seed_everything():
    Base.metadata.drop_all(bind=engine) # Start fresh
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    
    print("Seeding Users...")
    db.add(User(username="admin", password_hash=get_password_hash("admin123"), role="admin"))
    db.add(User(username="manager", password_hash=get_password_hash("manager123"), role="manager"))
    db.add(User(username="supervisor", password_hash=get_password_hash("supervisor123"), role="supervisor"))
    
    print("Seeding Shifts...")
    shifts = [
        Shift(name="Morning", start_time="06:00", end_time="12:00", required_employees=3),
        Shift(name="Afternoon", start_time="12:00", end_time="18:00", required_employees=3),
        Shift(name="Evening", start_time="18:00", end_time="00:00", required_employees=2),
        Shift(name="Night", start_time="00:00", end_time="06:00", required_employees=2)
    ]
    for s in shifts:
        db.add(s)
    
    print("Seeding 25 Employees...")
    skills_pool = ["Billing", "Security", "Support", "Manager", "IT", "Cleaning"]
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    
    for i in range(1, 26):
        emp_id = f"EMP{i:03d}"
        name = f"Employee {i}"
        skills = [skills_pool[i % len(skills_pool)]]
        if i % 3 == 0: skills.append("Backup")
        
        db.add(Employee(
            emp_id=emp_id,
            name=name,
            skills=skills,
            preferred_shift=shifts[i % 4].name,
            max_hours=40,
            weekly_off=days[i % 7]
        ))
    
    db.commit()
    
    print("Generating Schedule...")
    ai_scheduler.generate_ai_schedule(db, date.today().isoformat(), force_refresh=True)
    
    db.close()
    print("Full system seed complete. Login with admin/admin123")

if __name__ == "__main__":
    seed_everything()
