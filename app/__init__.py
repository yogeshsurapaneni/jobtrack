from flask import Flask
from config import Config
from app.models import db, User, ResumeProfile
from app.services.storage import storage_service
from flask_migrate import Migrate

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    migrate = Migrate(app, db)

    # Initialize services
    with app.app_context():
        # Initialize MinIO client & bucket
        storage_service.init_app(app)

    # Register blueprints/routes
    from app.routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    # Create tables and seed data if not present
    with app.app_context():
        try:
            db.create_all()
            seed_data()
        except Exception as e:
            print(f"[!] Database connection/seeding failed: {e}")

    return app

def seed_data():
    # Seed default user if not exists
    if not User.query.filter_by(email='demo@example.com').first():
        user = User(email='demo@example.com', name='Demo User')
        user.set_password('password')
        db.session.add(user)
        db.session.commit()
        print("[*] Seeded default user: demo@example.com / password")
        
    # Seed default resume profile if none exists
    if not ResumeProfile.query.first():
        profile = ResumeProfile(
            summary="Senior Software Engineer with 6+ years of experience building scalable backend APIs, microservices, and distributed cloud applications. Proficient in Python, Go, and AWS cloud infrastructures.",
            skills="Languages: Python, Go, SQL, Javascript\nFrameworks: FastAPI, Flask, Django, Gin\nDevOps & Infrastructure: Docker, Kubernetes, AWS (S3, EC2, RDS, Lambda), PostgreSQL, Redis, CI/CD",
            experience_json=[
                {
                    "company": "TechSolutions Inc.",
                    "position": "Senior Backend Engineer",
                    "start_date": "2022-03",
                    "end_date": "Present",
                    "description": "- Architected and migrated monolithic APIs to a Python FastAPI microservice architecture, reducing latency by 35%.\n- Integrated AWS cloud infrastructure, optimizing storage and databases which saved $12k/month.\n- Mentored 4 junior engineers and implemented test coverage guidelines increasing overall coverage from 60% to 92%."
                },
                {
                    "company": "Innovate Software",
                    "position": "Software Engineer II",
                    "start_date": "2020-01",
                    "end_date": "2022-02",
                    "description": "- Developed new features for the core Django web app serving 500k monthly active users.\n- Optimized complex PostgreSQL queries and indexing, resulting in a 40% reduction in DB lock occurrences.\n- Designed and implemented payment gateway integrations using Stripe."
                }
            ],
            projects_json=[
                {
                    "title": "CloudSync Engine",
                    "technologies": "Go, MinIO, Docker, gRPC",
                    "description": "- Created a local cloud synchronization daemon in Go that syncs directories securely to S3-compatible backends.\n- Achieved transfer throughput of 200MB/s utilizing worker pool concurrency patterns.",
                    "link": "github.com/demo/cloudsync"
                }
            ],
            education_json=[
                {
                    "school": "State University of Science",
                    "degree": "Bachelor of Science",
                    "field_of_study": "Computer Science",
                    "graduation_date": "2019-06",
                    "gpa": "3.7"
                }
            ],
            certifications_json=[
                {
                    "name": "AWS Certified Solutions Architect – Associate",
                    "authority": "Amazon Web Services",
                    "date_obtained": "2024-05"
                }
            ]
        )
        db.session.add(profile)
        db.session.commit()
        print("[*] Seeded default resume profile.")
