from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os

DATABASE_URL = "sqlite:///./shift_db_new.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True)
    password_hash = Column(String(255))
    role = Column(String(20)) # admin, manager, supervisor

class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True, index=True)
    emp_id = Column(String(50), unique=True, index=True) # External Employee ID from Excel
    name = Column(String(100), index=True)
    skills = Column(JSON) # List of skills
    preferred_shift = Column(String(50))
    max_hours = Column(Integer)
    weekly_off = Column(String(20)) # Monday, Tuesday, etc.
    
class Shift(Base):
    __tablename__ = "shifts"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50)) # Morning, Evening, Night
    start_time = Column(String(20))
    end_time = Column(String(20))
    required_employees = Column(Integer)

class Schedule(Base):
    __tablename__ = "schedules"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(String(20), index=True)
    shift_id = Column(Integer, ForeignKey("shifts.id"))
    employee_id = Column(Integer, ForeignKey("employees.id"))
    is_override = Column(Boolean, default=False)
    replaced_employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    
    shift = relationship("Shift")
    employee = relationship("Employee", foreign_keys=[employee_id])
    replaced_employee = relationship("Employee", foreign_keys=[replaced_employee_id])

class Leave(Base):
    __tablename__ = "leaves"
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    date = Column(String(20), index=True)
    
    employee = relationship("Employee")
