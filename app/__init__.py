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
        storage_service.init_app(app)

    # Register blueprints/routes
    from app.routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    # Create tables, run safe schema migrations, and seed data
    with app.app_context():
        try:
            db.create_all()
            _run_migrations()
            seed_data()
        except Exception as e:
            print(f"[!] Database connection/seeding failed: {e}")

    # Start the daily backup scheduler
    _start_scheduler(app)

    return app


def _run_migrations():
    """
    Idempotent schema migrations using raw SQL.
    Safe to run on every startup — uses IF NOT EXISTS / column-existence checks
    so repeated calls are no-ops.
    """
    migrations = [
        # 1. Create interview_events table if it doesn't already exist
        """
        CREATE TABLE IF NOT EXISTS interview_events (
            id              SERIAL PRIMARY KEY,
            job_id          INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            round_name      VARCHAR(100) NOT NULL,
            scheduled_at    TIMESTAMP,
            duration_min    INTEGER,
            meeting_link    VARCHAR(500),
            career_site_url VARCHAR(500),
            interviewer     VARCHAR(200),
            notes           TEXT,
            created_at      TIMESTAMP DEFAULT NOW()
        );
        """,
        # 2. Add interview_event_id column to application_history if missing
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='application_history'
                  AND column_name='interview_event_id'
            ) THEN
                ALTER TABLE application_history
                    ADD COLUMN interview_event_id INTEGER
                    REFERENCES interview_events(id) ON DELETE SET NULL;
            END IF;
        END;
        $$;
        """,
    ]

    with db.engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(db.text(sql))
                conn.commit()
            except Exception as e:
                conn.rollback()
                print(f"[!] Migration warning (may be harmless): {e}")

    print("[*] Schema migrations applied.")


def _start_scheduler(app):
    """
    Registers a daily APScheduler job that:
      1. Saves a backup to MinIO (always).
      2. Pushes the same backup to GitHub (if GITHUB_TOKEN + GITHUB_REPO are set).
    Fires at BACKUP_HOUR UTC (default 02:00).
    Safe to call multiple times — the scheduler is only started once.
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        print("[!] APScheduler not installed — daily backup disabled. "
              "Add 'APScheduler' to requirements.txt.")
        return

    backup_hour  = app.config.get('BACKUP_HOUR', 2)
    github_token = app.config.get('GITHUB_TOKEN', '')
    github_repo  = app.config.get('GITHUB_REPO',  '')

    def run_daily_backup():
        from app.services.backup import BackupService
        with app.app_context():
            # 1. MinIO
            try:
                path = BackupService.save_backup_to_minio()
                print(f"[*] Scheduled backup → MinIO: {path}")
            except Exception as e:
                print(f"[!] Scheduled MinIO backup failed: {e}")

            # 2. GitHub (optional)
            if github_token and github_repo:
                try:
                    sha = BackupService.save_backup_to_github(github_token, github_repo)
                    print(f"[*] Scheduled backup → GitHub ({github_repo}): {sha}")
                except Exception as e:
                    print(f"[!] Scheduled GitHub backup failed: {e}")

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        run_daily_backup,
        trigger=CronTrigger(hour=backup_hour, minute=0),
        id='daily_backup',
        replace_existing=True,
    )
    scheduler.start()
    print(f"[*] Daily backup scheduler started — fires at {backup_hour:02d}:00 UTC.")


def seed_data():
    if not User.query.filter_by(email='demo@example.com').first():
        user = User(email='demo@example.com', name='Demo User')
        user.set_password('password')
        db.session.add(user)
        db.session.commit()
        print("[*] Seeded default user: demo@example.com / password")

    if not ResumeProfile.query.first():
        profile = ResumeProfile(
            full_name="Demo User",
            email="demo@example.com",
            phone="+1 (555) 019-9000",
            linkedin="linkedin.com/in/demouser",
            location="San Francisco, CA",
            website="demouser.dev",
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
