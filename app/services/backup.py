import io
import json
import base64
import urllib.request
import urllib.error
from datetime import datetime, date
from app.models import db, Job, ApplicationHistory, Document, ResumeProfile, InterviewEvent
from app.services.storage import storage_service


# ---------------------------------------------------------------------------
# Core JSON serialisation
# ---------------------------------------------------------------------------

class BackupService:
    @staticmethod
    def create_backup_json() -> dict:
        """
        Export all data into a portable JSON dictionary.
        Includes: resume profile, jobs, history, documents, and interview events.
        """
        profile = ResumeProfile.query.first()
        profile_data = {}
        if profile:
            profile_data = {
                "summary":              profile.summary,
                "skills":               profile.skills,
                "experience_json":      profile.experience_json,
                "education_json":       profile.education_json,
                "projects_json":        profile.projects_json,
                "certifications_json":  profile.certifications_json,
            }

        jobs_list = []
        for job in Job.query.all():
            events = []
            for ev in job.interview_events:
                events.append({
                    "round_name":      ev.round_name,
                    "scheduled_at":    ev.scheduled_at.isoformat() if ev.scheduled_at else None,
                    "duration_min":    ev.duration_min,
                    "meeting_link":    ev.meeting_link,
                    "career_site_url": ev.career_site_url,
                    "interviewer":     ev.interviewer,
                    "notes":           ev.notes,
                })

            history = []
            for h in job.history:
                history.append({
                    "status":     h.status,
                    "notes":      h.notes,
                    "changed_at": h.changed_at.isoformat() if h.changed_at else None,
                })

            docs = []
            for d in job.documents:
                docs.append({
                    "type":        d.type,
                    "filename":    d.filename,
                    "minio_path":  d.minio_path,
                    "version":     d.version,
                    "model_used":  d.model_used,
                    "prompt_used": d.prompt_used,
                    "created_at":  d.created_at.isoformat() if d.created_at else None,
                })

            jobs_list.append({
                "company":         job.company,
                "position":        job.position,
                "location":        job.location,
                "salary":          job.salary,
                "job_url":         job.job_url,
                "job_description": job.job_description,
                "status":          job.status,
                "applied_date":    job.applied_date.isoformat() if job.applied_date else None,
                "notes":           job.notes,
                "created_at":      job.created_at.isoformat() if job.created_at else None,
                "updated_at":      job.updated_at.isoformat() if job.updated_at else None,
                "interview_events": events,
                "history":         history,
                "documents":       docs,
            })

        return {
            "backup_version": "2.0",
            "created_at":     datetime.utcnow().isoformat(),
            "resume_profile": profile_data,
            "jobs":           jobs_list,
        }

    # ---------------------------------------------------------------------------
    # MinIO
    # ---------------------------------------------------------------------------

    @classmethod
    def save_backup_to_minio(cls) -> str:
        """Upload JSON backup to MinIO. Returns the minio_path."""
        backup_bytes = json.dumps(cls.create_backup_json(), indent=2).encode('utf-8')
        timestamp    = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        minio_path   = f"backups/backup_{timestamp}.json"
        storage_service.upload_file(minio_path, backup_bytes, content_type="application/json")
        return minio_path

    @staticmethod
    def list_backups_in_minio() -> list:
        backups = []
        try:
            objects = storage_service.client.list_objects(
                storage_service.bucket_name, prefix="backups/", recursive=True
            )
            for obj in objects:
                fn = obj.object_name.split('/')[-1]
                if fn and fn.endswith('.json'):
                    backups.append({
                        "filename":      fn,
                        "path":          obj.object_name,
                        "size":          f"{obj.size / 1024:.2f} KB",
                        "last_modified": obj.last_modified.strftime('%Y-%m-%d %H:%M:%S') if obj.last_modified else 'N/A',
                        "source":        "minio",
                    })
            backups.sort(key=lambda x: x['filename'], reverse=True)
        except Exception as e:
            print(f"[!] Error listing MinIO backups: {e}")
        return backups

    @classmethod
    def restore_backup_from_minio(cls, minio_path: str):
        file_bytes  = storage_service.download_file(minio_path)
        backup_data = json.loads(file_bytes.decode('utf-8'))
        cls.restore_backup_from_json(backup_data)

    @staticmethod
    def delete_backup_from_minio(minio_path: str):
        storage_service.client.remove_object(storage_service.bucket_name, minio_path)

    # ---------------------------------------------------------------------------
    # GitHub Gist / Repo backup
    # ---------------------------------------------------------------------------

    @classmethod
    def _github_api(cls, method: str, url: str, token: str, payload: dict = None) -> dict:
        """Thin wrapper around urllib for GitHub API calls (no extra deps)."""
        data = json.dumps(payload).encode('utf-8') if payload else None
        req  = urllib.request.Request(url, data=data, method=method)
        req.add_header('Authorization', f'token {token}')
        req.add_header('Content-Type',  'application/json')
        req.add_header('Accept',        'application/vnd.github.v3+json')
        req.add_header('User-Agent',    'CareerOS-Backup/2.0')
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8')
            raise RuntimeError(f"GitHub API {method} {url} → {e.code}: {body}")

    @classmethod
    def save_backup_to_github(cls, token: str, repo: str) -> str:
        """
        Push a backup JSON as a commit to the GitHub repo at:
          backups/backup_YYYYMMDD_HHMMSS.json

        repo format: "owner/repo-name"
        Returns the GitHub commit SHA.
        """
        if not token or not repo:
            raise ValueError("GITHUB_TOKEN and GITHUB_REPO must be configured.")

        content      = json.dumps(cls.create_backup_json(), indent=2)
        content_b64  = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        timestamp    = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        path         = f"backups/backup_{timestamp}.json"
        api_url      = f"https://api.github.com/repos/{repo}/contents/{path}"

        payload = {
            "message": f"chore: auto-backup {timestamp} (CareerOS)",
            "content": content_b64,
        }
        result = cls._github_api('PUT', api_url, token, payload)
        sha = result.get('commit', {}).get('sha', 'unknown')
        print(f"[*] GitHub backup committed: {path} @ {sha}")
        return sha

    @classmethod
    def list_backups_in_github(cls, token: str, repo: str) -> list:
        """List backup files from the GitHub repo's backups/ directory."""
        if not token or not repo:
            return []
        api_url = f"https://api.github.com/repos/{repo}/contents/backups"
        try:
            items = cls._github_api('GET', api_url, token)
            backups = []
            for item in items:
                if item.get('name', '').endswith('.json'):
                    backups.append({
                        "filename":    item['name'],
                        "path":        item['path'],
                        "sha":         item['sha'],
                        "download_url": item['download_url'],
                        "size":        f"{item.get('size', 0) / 1024:.2f} KB",
                        "source":      "github",
                    })
            backups.sort(key=lambda x: x['filename'], reverse=True)
            return backups
        except Exception as e:
            print(f"[!] Error listing GitHub backups: {e}")
            return []

    @classmethod
    def restore_backup_from_github(cls, token: str, repo: str, path: str):
        """Download a specific backup file from GitHub and restore the database."""
        if not token or not repo:
            raise ValueError("GITHUB_TOKEN and GITHUB_REPO must be configured.")
        api_url  = f"https://api.github.com/repos/{repo}/contents/{path}"
        meta     = cls._github_api('GET', api_url, token)
        raw_b64  = meta.get('content', '')
        # GitHub returns base64 with newlines; clean them
        content  = base64.b64decode(raw_b64.replace('\n', '')).decode('utf-8')
        backup   = json.loads(content)
        cls.restore_backup_from_json(backup)

    # ---------------------------------------------------------------------------
    # Combined restore from JSON dict
    # ---------------------------------------------------------------------------

    @classmethod
    def restore_backup_from_json(cls, backup_data: dict):
        """
        Wipe the database and reconstruct all models from a backup dict.
        Supports backup_version 1.0 (legacy) and 2.0 (with interview_events).
        """
        # Delete in dependency order
        ApplicationHistory.query.delete()
        InterviewEvent.query.delete()
        Document.query.delete()
        Job.query.delete()
        ResumeProfile.query.delete()
        db.session.commit()

        # Restore Resume Profile
        pd = backup_data.get("resume_profile", {})
        if pd:
            db.session.add(ResumeProfile(
                summary             = pd.get("summary"),
                skills              = pd.get("skills"),
                experience_json     = pd.get("experience_json"),
                education_json      = pd.get("education_json"),
                projects_json       = pd.get("projects_json"),
                certifications_json = pd.get("certifications_json"),
            ))

        # Restore Jobs
        for jd in backup_data.get("jobs", []):
            applied_date = None
            if jd.get("applied_date"):
                try:
                    applied_date = date.fromisoformat(jd["applied_date"])
                except ValueError:
                    pass

            job = Job(
                company         = jd["company"],
                position        = jd["position"],
                location        = jd.get("location"),
                salary          = jd.get("salary"),
                job_url         = jd.get("job_url"),
                job_description = jd.get("job_description"),
                status          = jd.get("status", "Wishlist"),
                applied_date    = applied_date,
                notes           = jd.get("notes"),
                created_at      = _parse_dt(jd.get("created_at")),
                updated_at      = _parse_dt(jd.get("updated_at")),
            )
            db.session.add(job)
            db.session.flush()

            # Interview events (v2.0+)
            for ev in jd.get("interview_events", []):
                db.session.add(InterviewEvent(
                    job_id          = job.id,
                    round_name      = ev.get("round_name", ""),
                    scheduled_at    = _parse_dt(ev.get("scheduled_at")),
                    duration_min    = ev.get("duration_min"),
                    meeting_link    = ev.get("meeting_link"),
                    career_site_url = ev.get("career_site_url"),
                    interviewer     = ev.get("interviewer"),
                    notes           = ev.get("notes"),
                ))

            for hd in jd.get("history", []):
                db.session.add(ApplicationHistory(
                    job_id     = job.id,
                    status     = hd["status"],
                    notes      = hd.get("notes"),
                    changed_at = _parse_dt(hd.get("changed_at")),
                ))

            for dd in jd.get("documents", []):
                db.session.add(Document(
                    job_id     = job.id,
                    type       = dd["type"],
                    filename   = dd["filename"],
                    minio_path = dd["minio_path"],
                    version    = dd.get("version", 1),
                    model_used = dd.get("model_used"),
                    prompt_used= dd.get("prompt_used"),
                    created_at = _parse_dt(dd.get("created_at")),
                ))

        db.session.commit()


def _parse_dt(s):
    if not s:
        return datetime.utcnow()
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return datetime.utcnow()
