import sys
from app import create_app
from app.models import db

app = create_app()
with app.app_context():
    try:
        # Create any new tables (like interview_events)
        db.create_all()
        print("[*] db.create_all() executed.")
        
        # Manually alter application_history table if needed
        # We check if columns exist first
        conn = db.engine.connect()
        # Add interview_event_id column to application_history
        try:
            conn.execute(db.text("ALTER TABLE application_history ADD COLUMN interview_event_id INTEGER REFERENCES interview_events(id) ON DELETE SET NULL;"))
            db.session.commit()
            print("[*] Column interview_event_id added to application_history.")
        except Exception as ex:
            # Column might already exist, rollback transaction
            db.session.rollback()
            print(f"[*] ALTER TABLE failed or column already exists: {ex}")
            
    except Exception as e:
        print(f"[!] Error updating database schema: {e}", file=sys.stderr)
        sys.exit(1)
