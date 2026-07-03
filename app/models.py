from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Job(db.Model):
    __tablename__ = 'jobs'
    
    id = db.Column(db.Integer, primary_key=True)
    company = db.Column(db.String(100), nullable=False)
    position = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(100), nullable=True)
    salary = db.Column(db.String(100), nullable=True)
    job_url = db.Column(db.String(500), nullable=True)
    job_description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(50), default='Wishlist')
    # Valid statuses: Wishlist | Interested | Applied | Online Assessment | Phone Screen |
    #   Technical Interview | Manager Interview | Final Round | Offer | Rejected | Withdrawn | Ghosted
    applied_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    history          = db.relationship('ApplicationHistory', backref='job', lazy=True, cascade="all, delete-orphan")
    documents        = db.relationship('Document',           backref='job', lazy=True, cascade="all, delete-orphan")
    interview_events = db.relationship('InterviewEvent',     back_populates='job',     lazy=True, cascade="all, delete-orphan")

class InterviewEvent(db.Model):
    """Structured metadata for a specific interview round."""
    __tablename__ = 'interview_events'

    id              = db.Column(db.Integer, primary_key=True)
    job_id          = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)
    round_name      = db.Column(db.String(100), nullable=False)   # e.g. "Phone Screen"
    scheduled_at    = db.Column(db.DateTime, nullable=True)        # date + time
    duration_min    = db.Column(db.Integer,  nullable=True)        # duration in minutes
    meeting_link    = db.Column(db.String(500), nullable=True)     # Zoom / Teams / Google Meet
    career_site_url = db.Column(db.String(500), nullable=True)     # company careers page
    interviewer     = db.Column(db.String(200), nullable=True)     # name / email
    notes           = db.Column(db.Text, nullable=True)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    job = db.relationship('Job', back_populates='interview_events')


class ApplicationHistory(db.Model):
    __tablename__ = 'application_history'

    id                 = db.Column(db.Integer, primary_key=True)
    job_id             = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)
    status             = db.Column(db.String(50), nullable=False)
    changed_at         = db.Column(db.DateTime, default=datetime.utcnow)
    notes              = db.Column(db.Text, nullable=True)
    interview_event_id = db.Column(db.Integer, db.ForeignKey('interview_events.id'), nullable=True)

    interview_event = db.relationship('InterviewEvent', foreign_keys=[interview_event_id])

class Document(db.Model):
    __tablename__ = 'documents'
    
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=True) # Nullable for Master Resume
    type = db.Column(db.String(50), nullable=False) # Master Resume, Generated Resume, Cover Letter, Job Description, Offer, Interview Notes
    filename = db.Column(db.String(255), nullable=False)
    minio_path = db.Column(db.String(500), nullable=False)
    version = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # AI traceability
    model_used = db.Column(db.String(100), nullable=True)
    prompt_used = db.Column(db.Text, nullable=True)

class ResumeProfile(db.Model):
    __tablename__ = 'resume_profile'
    
    id = db.Column(db.Integer, primary_key=True)
    summary = db.Column(db.Text, nullable=True)
    skills = db.Column(db.Text, nullable=True)
    experience_json = db.Column(db.JSON, nullable=True) # List of dicts: company, position, start_date, end_date, description
    education_json = db.Column(db.JSON, nullable=True)  # List of dicts: school, degree, field_of_study, graduation_date, gpa
    projects_json = db.Column(db.JSON, nullable=True)   # List of dicts: title, description, technologies, link
    certifications_json = db.Column(db.JSON, nullable=True) # List of dicts: name, authority, date_obtained, link
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
