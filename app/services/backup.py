import json
from datetime import datetime, date
from app.models import db, Job, ApplicationHistory, Document, ResumeProfile
from app.services.storage import storage_service

class BackupService:
    @staticmethod
    def create_backup_json() -> dict:
        """
        Export all resume profiles, jobs, application histories, and documents
        into a nested JSON-compatible dictionary format.
        """
        # 1. Export Resume Profile
        profile = ResumeProfile.query.first()
        profile_data = {}
        if profile:
            profile_data = {
                "summary": profile.summary,
                "skills": profile.skills,
                "experience_json": profile.experience_json,
                "education_json": profile.education_json,
                "projects_json": profile.projects_json,
                "certifications_json": profile.certifications_json
            }

        # 2. Export Jobs, History, and Documents
        jobs_list = []
        jobs = Job.query.all()
        for job in jobs:
            job_data = {
                "company": job.company,
                "position": job.position,
                "location": job.location,
                "salary": job.salary,
                "job_url": job.job_url,
                "job_description": job.job_description,
                "status": job.status,
                "applied_date": job.applied_date.isoformat() if job.applied_date else None,
                "notes": job.notes,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "updated_at": job.updated_at.isoformat() if job.updated_at else None,
                "history": [],
                "documents": []
            }

            # Export history for this job
            for hist in job.history:
                job_data["history"].append({
                    "status": hist.status,
                    "notes": hist.notes,
                    "changed_at": hist.changed_at.isoformat() if hist.changed_at else None
                })

            # Export documents for this job
            for doc in job.documents:
                job_data["documents"].append({
                    "type": doc.type,
                    "filename": doc.filename,
                    "minio_path": doc.minio_path,
                    "version": doc.version,
                    "model_used": doc.model_used,
                    "prompt_used": doc.prompt_used,
                    "created_at": doc.created_at.isoformat() if doc.created_at else None
                })

            jobs_list.append(job_data)

        # Assemble package
        backup = {
            "backup_version": "1.0",
            "created_at": datetime.utcnow().isoformat(),
            "resume_profile": profile_data,
            "jobs": jobs_list
        }
        return backup

    @classmethod
    def save_backup_to_minio(cls) -> str:
        """
        Generate JSON backup and upload it directly to MinIO.
        """
        backup_data = cls.create_backup_json()
        backup_str = json.dumps(backup_data, indent=2)
        backup_bytes = backup_str.encode('utf-8')
        
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        minio_path = f"backups/backup_{timestamp}.json"
        
        storage_service.upload_file(
            minio_path,
            backup_bytes,
            content_type="application/json"
        )
        return minio_path

    @staticmethod
    def list_backups_in_minio() -> list:
        """
        List all backup JSON files stored in the MinIO bucket.
        """
        backups = []
        try:
            # We fetch all objects under prefix "backups/"
            objects = storage_service.client.list_objects(
                storage_service.bucket_name,
                prefix="backups/",
                recursive=True
            )
            for obj in objects:
                # Format: backups/backup_YYYYMMDD_HHMMSS.json
                filename = obj.object_name.split('/')[-1]
                if filename and filename.endswith('.json'):
                    backups.append({
                        "filename": filename,
                        "path": obj.object_name,
                        "size": f"{obj.size / 1024:.2f} KB",
                        "last_modified": obj.last_modified.strftime('%Y-%m-%d %H:%M:%S') if obj.last_modified else 'N/A'
                    })
            # Sort newest first
            backups.sort(key=lambda x: x['filename'], reverse=True)
        except Exception as e:
            print(f"[!] Error listing backups in MinIO: {e}")
        return backups

    @classmethod
    def restore_backup_from_json(cls, backup_data: dict):
        """
        Given a backup dictionary, wipe the database and reconstruct all models.
        """
        # Wipe existing data
        # Order matters for foreign key constraint cascades
        ApplicationHistory.query.delete()
        Document.query.delete()
        Job.query.delete()
        ResumeProfile.query.delete()
        db.session.commit()

        # 1. Restore Resume Profile
        profile_data = backup_data.get("resume_profile")
        if profile_data:
            profile = ResumeProfile(
                summary=profile_data.get("summary"),
                skills=profile_data.get("skills"),
                experience_json=profile_data.get("experience_json"),
                education_json=profile_data.get("education_json"),
                projects_json=profile_data.get("projects_json"),
                certifications_json=profile_data.get("certifications_json")
            )
            db.session.add(profile)

        # 2. Restore Jobs, Histories, and Documents
        for job_data in backup_data.get("jobs", []):
            applied_date = None
            if job_data.get("applied_date"):
                applied_date = date.fromisoformat(job_data["applied_date"])

            job = Job(
                company=job_data["company"],
                position=job_data["position"],
                location=job_data.get("location"),
                salary=job_data.get("salary"),
                job_url=job_data.get("job_url"),
                job_description=job_data.get("job_description"),
                status=job_data.get("status", "Wishlist"),
                applied_date=applied_date,
                notes=job_data.get("notes"),
                created_at=datetime.fromisoformat(job_data["created_at"]) if job_data.get("created_at") else datetime.utcnow(),
                updated_at=datetime.fromisoformat(job_data["updated_at"]) if job_data.get("updated_at") else datetime.utcnow()
            )
            db.session.add(job)
            db.session.flush()  # Generates job.id

            # Add History
            for hist_data in job_data.get("history", []):
                hist = ApplicationHistory(
                    job_id=job.id,
                    status=hist_data["status"],
                    notes=hist_data.get("notes"),
                    changed_at=datetime.fromisoformat(hist_data["changed_at"]) if hist_data.get("changed_at") else datetime.utcnow()
                )
                db.session.add(hist)

            # Add Documents
            for doc_data in job_data.get("documents", []):
                doc = Document(
                    job_id=job.id,
                    type=doc_data["type"],
                    filename=doc_data["filename"],
                    minio_path=doc_data["minio_path"],
                    version=doc_data.get("version", 1),
                    model_used=doc_data.get("model_used"),
                    prompt_used=doc_data.get("prompt_used"),
                    created_at=datetime.fromisoformat(doc_data["created_at"]) if doc_data.get("created_at") else datetime.utcnow()
                )
                db.session.add(doc)

        db.session.commit()

    @classmethod
    def restore_backup_from_minio(cls, minio_path: str):
        """
        Download backup file from MinIO, read JSON and restore db.
        """
        file_bytes = storage_service.download_file(minio_path)
        backup_data = json.loads(file_bytes.decode('utf-8'))
        cls.restore_backup_from_json(backup_data)

    @staticmethod
    def delete_backup_from_minio(minio_path: str):
        """
        Delete a backup JSON file from the MinIO bucket.
        """
        storage_service.client.remove_object(
            storage_service.bucket_name,
            minio_path
        )
