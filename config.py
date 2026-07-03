import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production-19283746')
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'postgresql://jobtracker:jobtrackerpwd@localhost:5432/jobtracker')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # MinIO Object Storage
    MINIO_ENDPOINT   = os.environ.get('MINIO_ENDPOINT',   'localhost:9000')
    MINIO_ACCESS_KEY = os.environ.get('MINIO_ACCESS_KEY', 'minioadmin')
    MINIO_SECRET_KEY = os.environ.get('MINIO_SECRET_KEY', 'minioadmin')
    MINIO_SECURE     = os.environ.get('MINIO_SECURE', 'False').lower() in ('true', '1', 't')
    MINIO_BUCKET     = os.environ.get('MINIO_BUCKET',     'job-platform')
    
    # OpenRouter API
    OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY', '')
    OPENROUTER_MODEL   = os.environ.get('OPENROUTER_MODEL',   'google/gemini-2.5-flash')

    # GitHub Backup
    # GITHUB_TOKEN  – personal access token with repo scope
    # GITHUB_REPO   – owner/repo  e.g.  "yourgithub/careeros-backups"
    # BACKUP_HOUR   – UTC hour (0-23) at which the daily backup fires (default 02:00 UTC)
    GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
    GITHUB_REPO  = os.environ.get('GITHUB_REPO',  '')   # e.g. "user/careeros-backups"
    BACKUP_HOUR  = int(os.environ.get('BACKUP_HOUR', '2'))
