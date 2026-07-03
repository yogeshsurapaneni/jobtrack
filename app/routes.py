import json
import threading
from flask import Blueprint, render_template, redirect, url_for, request, flash, send_file, jsonify
from app.models import db, User, Job, ApplicationHistory, Document, ResumeProfile, InterviewEvent
from app.services.resume_generator import ResumeGeneratorService
from app.services.coverletter_generator import CoverLetterGeneratorService
from app.services.storage import storage_service
from app.services.ai_analysis import AIAnalysisService
from datetime import datetime, date

main = Blueprint('main', __name__)


# ---------------------------------------------------------------------------
# Background generation helper
# ---------------------------------------------------------------------------

def _background_generate(app, job_id):
    """
    Runs resume + cover letter generation in a background thread so the
    add-job POST can return immediately. Also triggers match score and
    stores the result on the Job's notes metadata (via app context).
    """
    with app.app_context():
        try:
            ResumeGeneratorService.generate_tailored_resume(job_id)
            print(f"[*] Auto-generated resume for job {job_id}")
        except Exception as e:
            print(f"[!] Auto resume generation failed for job {job_id}: {e}")

        try:
            CoverLetterGeneratorService.generate_cover_letter(job_id)
            print(f"[*] Auto-generated cover letter for job {job_id}")
        except Exception as e:
            print(f"[!] Auto cover letter generation failed for job {job_id}: {e}")

        try:
            result = AIAnalysisService.analyze_job_match(job_id)
            job = Job.query.get(job_id)
            if job:
                # Store match score in the job notes as a JSON prefix so UI can show it
                score_tag = f"[MATCH:{result.get('score', '?')}%:{result.get('grade', '?')}]"
                if job.notes and not job.notes.startswith('[MATCH:'):
                    job.notes = f"{score_tag}\n{job.notes}"
                elif not job.notes:
                    job.notes = score_tag
                db.session.commit()
            print(f"[*] Auto match score computed for job {job_id}: {result.get('score')}%")
        except Exception as e:
            print(f"[!] Auto match score failed for job {job_id}: {e}")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@main.route('/')
@main.route('/dashboard')
def dashboard():
    jobs = Job.query.all()

    total      = len(jobs)
    wishlist   = sum(1 for j in jobs if j.status == 'Wishlist')
    interested = sum(1 for j in jobs if j.status == 'Interested')
    applied    = sum(1 for j in jobs if j.status == 'Applied')

    interview_statuses = {
        'Online Assessment', 'Phone Screen',
        'Technical Interview', 'Manager Interview', 'Final Round'
    }
    interviewing = sum(1 for j in jobs if j.status in interview_statuses)
    offers   = sum(1 for j in jobs if j.status == 'Offer')
    rejected = sum(1 for j in jobs if j.status == 'Rejected')

    active_statuses_beyond_applied = {
        'Online Assessment', 'Phone Screen', 'Technical Interview',
        'Manager Interview', 'Final Round', 'Offer', 'Rejected', 'Withdrawn'
    }
    total_applied_or_more = sum(1 for j in jobs if j.status not in {'Wishlist', 'Interested'})
    positive_responses    = sum(1 for j in jobs if j.status in active_statuses_beyond_applied)
    response_rate = int((positive_responses / total_applied_or_more * 100)) if total_applied_or_more > 0 else 0

    recent_activity = ApplicationHistory.query.order_by(ApplicationHistory.changed_at.desc()).limit(12).all()

    interview_jobs = [j for j in jobs if j.status in interview_statuses]
    rejected_jobs  = [j for j in jobs if j.status == 'Rejected']

    upcoming_events = InterviewEvent.query\
        .filter(InterviewEvent.scheduled_at >= datetime.utcnow())\
        .order_by(InterviewEvent.scheduled_at.asc())\
        .limit(30).all()

    return render_template(
        'dashboard.html',
        total=total, wishlist=wishlist, interested=interested, applied=applied,
        interviewing=interviewing, offers=offers, rejected=rejected,
        response_rate=response_rate, recent_activity=recent_activity,
        interview_jobs=interview_jobs, rejected_jobs=rejected_jobs,
        upcoming_events=upcoming_events,
    )


# ---------------------------------------------------------------------------
# Jobs Routes
# ---------------------------------------------------------------------------

@main.route('/jobs')
def jobs_list():
    search       = request.args.get('search', '')
    status_filter = request.args.get('status', '')
    sort_by      = request.args.get('sort', 'updated_at')
    direction    = request.args.get('direction', 'desc')

    query = Job.query

    if search:
        query = query.filter(
            (Job.company.ilike(f'%{search}%')) |
            (Job.position.ilike(f'%{search}%')) |
            (Job.location.ilike(f'%{search}%'))
        )
    if status_filter:
        query = query.filter(Job.status == status_filter)

    field_map = {
        'company': Job.company, 'position': Job.position,
        'applied_date': Job.applied_date, 'created_at': Job.created_at,
    }
    field = field_map.get(sort_by, Job.updated_at)
    query = query.order_by(field.asc() if direction == 'asc' else field.desc())
    jobs = query.all()

    return render_template(
        'jobs.html', jobs=jobs, search=search,
        status_filter=status_filter, sort_by=sort_by, direction=direction
    )


@main.route('/jobs/add', methods=['POST'])
def add_job():
    from flask import current_app
    company         = request.form.get('company')
    position        = request.form.get('position')
    location        = request.form.get('location')
    salary          = request.form.get('salary')
    job_url         = request.form.get('job_url')
    job_description = request.form.get('job_description')
    notes           = request.form.get('notes')
    status          = request.form.get('status', 'Wishlist')

    applied_date = None
    if applied_date_str := request.form.get('applied_date'):
        try:
            applied_date = datetime.strptime(applied_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    job = Job(
        company=company, position=position, location=location,
        salary=salary, job_url=job_url, job_description=job_description,
        notes=notes, status=status, applied_date=applied_date
    )
    db.session.add(job)
    db.session.commit()

    history = ApplicationHistory(job_id=job.id, status=status, notes="Job added to tracker.")
    db.session.add(history)
    db.session.commit()

    # Auto-generate resume, cover letter, and match score in the background
    if job_description:
        app = current_app._get_current_object()
        t = threading.Thread(target=_background_generate, args=(app, job.id), daemon=True)
        t.start()
        flash(f"Added {position} at {company}! Generating tailored CV, cover letter & match score in the background…", "success")
    else:
        flash(f"Added {position} at {company}! Add a job description to enable AI generation.", "info")

    return redirect(url_for('main.job_detail', job_id=job.id))


@main.route('/jobs/<int:job_id>')
def job_detail(job_id):
    job = Job.query.get_or_404(job_id)
    docs         = Document.query.filter_by(job_id=job.id).order_by(Document.version.desc()).all()
    resumes      = [d for d in docs if d.type == 'Generated Resume']
    cover_letters = [d for d in docs if d.type == 'Cover Letter']

    # Group by version: {version: {pdf: doc, docx: doc}}
    def group_by_version(doc_list):
        groups = {}
        for d in doc_list:
            v = d.version
            if v not in groups:
                groups[v] = {}
            ext = d.filename.rsplit('.', 1)[-1].lower()
            groups[v][ext] = d
        return dict(sorted(groups.items(), reverse=True))

    resume_versions = group_by_version(resumes)
    cl_versions     = group_by_version(cover_letters)

    models = [
        ("google/gemini-2.5-flash",               "Gemini 2.5 Flash"),
        ("google/gemini-2.5-pro",                 "Gemini 2.5 Pro"),
        ("anthropic/claude-sonnet-4-5",           "Claude Sonnet 4.5"),
        ("meta-llama/llama-3.1-70b-instruct",     "Llama 3.1 70B"),
        ("deepseek/deepseek-chat",                "DeepSeek V3"),
    ]

    # Parse stored match score from notes prefix
    stored_score = None
    notes_clean  = job.notes or ''
    import re
    m = re.match(r'^\[MATCH:(\d+)%:([A-D?])\]\n?', notes_clean)
    if m:
        stored_score = {"score": int(m.group(1)), "grade": m.group(2)}
        notes_clean  = notes_clean[m.end():]

    interview_events = (InterviewEvent.query.filter_by(job_id=job.id)
                        .order_by(InterviewEvent.scheduled_at.asc().nullslast()).all())

    return render_template(
        'job_detail.html',
        job=job, notes_clean=notes_clean,
        resume_versions=resume_versions,
        cl_versions=cl_versions,
        stored_score=stored_score,
        models=models,
        interview_events=interview_events,
    )


@main.route('/jobs/<int:job_id>/edit', methods=['POST'])
def edit_job(job_id):
    job = Job.query.get_or_404(job_id)
    job.company         = request.form.get('company')
    job.position        = request.form.get('position')
    job.location        = request.form.get('location')
    job.salary          = request.form.get('salary')
    job.job_url         = request.form.get('job_url')
    job.job_description = request.form.get('job_description')
    job.notes           = request.form.get('notes')

    if applied_date_str := request.form.get('applied_date'):
        try:
            job.applied_date = datetime.strptime(applied_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    else:
        job.applied_date = None

    db.session.commit()
    flash("Job details updated successfully.", "success")
    return redirect(url_for('main.job_detail', job_id=job.id))


@main.route('/jobs/<int:job_id>/status', methods=['POST'])
def update_status(job_id):
    job = Job.query.get_or_404(job_id)
    new_status   = request.form.get('status')
    status_notes = request.form.get('notes', '')

    if new_status and new_status != job.status:
        old_status = job.status
        job.status = new_status
        if new_status == 'Applied' and not job.applied_date:
            job.applied_date = date.today()
        history = ApplicationHistory(
            job_id=job.id, status=new_status,
            notes=status_notes or f"Status changed from {old_status} to {new_status}."
        )
        db.session.add(history)
        db.session.commit()
        flash(f"Status updated to {new_status}.", "success")

    return redirect(url_for('main.job_detail', job_id=job.id))


@main.route('/jobs/<int:job_id>/delete', methods=['POST'])
def delete_job(job_id):
    job = Job.query.get_or_404(job_id)
    company, position = job.company, job.position
    db.session.delete(job)
    db.session.commit()
    flash(f"Deleted application for {position} at {company}.", "info")
    return redirect(url_for('main.jobs_list'))


# ---------------------------------------------------------------------------
# Manual AI Generation Routes
# ---------------------------------------------------------------------------

@main.route('/jobs/<int:job_id>/generate-resume', methods=['POST'])
def generate_resume(job_id):
    model = request.form.get('model')
    additional_notes = request.form.get('additional_notes')
    try:
        pdf_doc = ResumeGeneratorService.generate_tailored_resume(job_id, model=model, additional_notes=additional_notes)
        flash(f"Tailored Resume v{pdf_doc.version} generated successfully!", "success")
    except Exception as e:
        flash(f"Failed to generate resume: {str(e)}", "danger")
    return redirect(url_for('main.job_detail', job_id=job_id))


@main.route('/jobs/<int:job_id>/generate-coverletter', methods=['POST'])
def generate_cover_letter(job_id):
    model = request.form.get('model')
    additional_notes = request.form.get('additional_notes')
    try:
        pdf_doc = CoverLetterGeneratorService.generate_cover_letter(job_id, model=model, additional_notes=additional_notes)
        flash(f"Tailored Cover Letter v{pdf_doc.version} generated successfully!", "success")
    except Exception as e:
        flash(f"Failed to generate cover letter: {str(e)}", "danger")
    return redirect(url_for('main.job_detail', job_id=job_id))


# ---------------------------------------------------------------------------
# AI Tools — async/HTMX endpoints
# ---------------------------------------------------------------------------

@main.route('/jobs/<int:job_id>/match-score')
def match_score(job_id):
    model = request.args.get('model')
    try:
        result = AIAnalysisService.analyze_job_match(job_id, model=model)

        # Persist score to job notes
        job = Job.query.get(job_id)
        if job:
            import re
            score_tag   = f"[MATCH:{result.get('score','?')}%:{result.get('grade','?')}]"
            notes_clean = re.sub(r'^\[MATCH:\d+%:[A-D?]\]\n?', '', job.notes or '')
            job.notes   = f"{score_tag}\n{notes_clean}" if notes_clean else score_tag
            db.session.commit()

        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@main.route('/jobs/<int:job_id>/email-gen', methods=['POST'])
def email_gen(job_id):
    model      = request.form.get('model')
    email_type = request.form.get('email_type')
    additional_notes = request.form.get('additional_notes')
    try:
        email_text = AIAnalysisService.generate_email_template(job_id, email_type, model=model, additional_notes=additional_notes)
        import markdown as md_lib
        html_email = md_lib.markdown(email_text)
        return jsonify({"success": True, "html": html_email, "raw": email_text})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@main.route('/jobs/<int:job_id>/rejection-analysis')
def rejection_analysis(job_id):
    model = request.args.get('model')
    try:
        analysis = AIAnalysisService.analyze_rejection(job_id, model=model)
        import markdown as md_lib
        html_analysis = md_lib.markdown(analysis)
        return jsonify({"success": True, "html": html_analysis})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500



# ---------------------------------------------------------------------------
# Resume Profile Route
# ---------------------------------------------------------------------------

@main.route('/resume', methods=['GET', 'POST'])
def resume_profile():
    profile = ResumeProfile.query.first()
    if not profile:
        profile = ResumeProfile(experience_json=[], education_json=[], projects_json=[], certifications_json=[])
        db.session.add(profile)
        db.session.commit()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'save_basic':
            profile.summary = request.form.get('summary')
            profile.skills  = request.form.get('skills')
            db.session.commit()
            flash("Basic profile info updated.", "success")

        elif action == 'add_experience':
            exp = {
                "company":    request.form.get('company'),
                "position":   request.form.get('position'),
                "start_date": request.form.get('start_date'),
                "end_date":   request.form.get('end_date') or 'Present',
                "description": request.form.get('description')
            }
            curr = list(profile.experience_json or [])
            curr.append(exp)
            profile.experience_json = curr
            db.session.commit()
            flash("Work experience entry added.", "success")

        elif action == 'delete_experience':
            idx  = int(request.form.get('index'))
            curr = list(profile.experience_json or [])
            if 0 <= idx < len(curr):
                curr.pop(idx)
                profile.experience_json = curr
                db.session.commit()
                flash("Work experience entry deleted.", "success")

        elif action == 'add_project':
            proj = {
                "title":       request.form.get('title'),
                "technologies": request.form.get('technologies'),
                "description": request.form.get('description'),
                "link":        request.form.get('link')
            }
            curr = list(profile.projects_json or [])
            curr.append(proj)
            profile.projects_json = curr
            db.session.commit()
            flash("Project entry added.", "success")

        elif action == 'delete_project':
            idx  = int(request.form.get('index'))
            curr = list(profile.projects_json or [])
            if 0 <= idx < len(curr):
                curr.pop(idx)
                profile.projects_json = curr
                db.session.commit()
                flash("Project entry deleted.", "success")

        elif action == 'add_education':
            edu = {
                "school":         request.form.get('school'),
                "degree":         request.form.get('degree'),
                "field_of_study": request.form.get('field_of_study'),
                "graduation_date": request.form.get('graduation_date'),
                "gpa":            request.form.get('gpa')
            }
            curr = list(profile.education_json or [])
            curr.append(edu)
            profile.education_json = curr
            db.session.commit()
            flash("Education entry added.", "success")

        elif action == 'delete_education':
            idx  = int(request.form.get('index'))
            curr = list(profile.education_json or [])
            if 0 <= idx < len(curr):
                curr.pop(idx)
                profile.education_json = curr
                db.session.commit()
                flash("Education entry deleted.", "success")

        elif action == 'add_certification':
            cert = {
                "name":          request.form.get('name'),
                "authority":     request.form.get('authority'),
                "date_obtained": request.form.get('date_obtained'),
                "link":          request.form.get('link')
            }
            curr = list(profile.certifications_json or [])
            curr.append(cert)
            profile.certifications_json = curr
            db.session.commit()
            flash("Certification entry added.", "success")

        elif action == 'delete_certification':
            idx  = int(request.form.get('index'))
            curr = list(profile.certifications_json or [])
            if 0 <= idx < len(curr):
                curr.pop(idx)
                profile.certifications_json = curr
                db.session.commit()
                flash("Certification entry deleted.", "success")

        return redirect(url_for('main.resume_profile'))

    from app.services.backup import BackupService
    from flask import current_app
    backups = BackupService.list_backups_in_minio()
    return render_template('resume.html', profile=profile, backups=backups, config=current_app.config)


# ---------------------------------------------------------------------------
# Document Download
# ---------------------------------------------------------------------------

@main.route('/documents/download/<int:doc_id>')
def download_document(doc_id):
    doc = Document.query.get_or_404(doc_id)
    try:
        file_bytes = storage_service.download_file(doc.minio_path)

        if doc.filename.endswith('.pdf'):
            mimetype = 'application/pdf'
        elif doc.filename.endswith('.docx'):
            mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        else:
            mimetype = 'application/octet-stream'

        import io
        return send_file(
            io.BytesIO(file_bytes),
            mimetype=mimetype,
            as_attachment=True,
            download_name=doc.filename
        )
    except Exception as e:
        flash(f"Could not download file from storage: {e}", "danger")
        return redirect(request.referrer or url_for('main.dashboard'))


# ---------------------------------------------------------------------------
# Backup & Restore Routes
# ---------------------------------------------------------------------------

@main.route('/backup/create', methods=['POST'])
def create_backup():
    try:
        from app.services.backup import BackupService
        minio_path = BackupService.save_backup_to_minio()
        flash(f"Database backup created and stored in MinIO: {minio_path}", "success")
    except Exception as e:
        flash(f"Failed to create backup: {str(e)}", "danger")
    return redirect(request.referrer or url_for('main.resume_profile'))


@main.route('/backup/restore-minio', methods=['POST'])
def restore_backup_minio():
    path = request.form.get('path')
    if not path:
        flash("No backup path provided.", "danger")
        return redirect(url_for('main.resume_profile'))
    try:
        from app.services.backup import BackupService
        BackupService.restore_backup_from_minio(path)
        flash("Database state restored successfully from MinIO backup!", "success")
    except Exception as e:
        flash(f"Failed to restore backup: {str(e)}", "danger")
    return redirect(url_for('main.dashboard'))


@main.route('/backup/delete-minio', methods=['POST'])
def delete_backup_minio():
    path = request.form.get('path')
    if not path:
        flash("No backup path provided.", "danger")
        return redirect(url_for('main.resume_profile'))
    try:
        from app.services.backup import BackupService
        BackupService.delete_backup_from_minio(path)
        flash("Backup file deleted from MinIO.", "info")
    except Exception as e:
        flash(f"Failed to delete backup file: {str(e)}", "danger")
    return redirect(url_for('main.resume_profile'))


@main.route('/backup/download-local')
def download_local_backup():
    try:
        from app.services.backup import BackupService
        backup_data = BackupService.create_backup_json()
        backup_str  = json.dumps(backup_data, indent=2)
        backup_bytes = backup_str.encode('utf-8')

        import io
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        return send_file(
            io.BytesIO(backup_bytes),
            mimetype='application/json',
            as_attachment=True,
            download_name=f"jobtracker_backup_{timestamp}.json"
        )
    except Exception as e:
        flash(f"Failed to generate download: {str(e)}", "danger")
        return redirect(request.referrer or url_for('main.resume_profile'))


@main.route('/backup/upload', methods=['POST'])
def upload_backup():
    if 'backup_file' not in request.files:
        flash("No file uploaded.", "danger")
        return redirect(url_for('main.resume_profile'))
    file = request.files['backup_file']
    if file.filename == '':
        flash("No file selected.", "danger")
        return redirect(url_for('main.resume_profile'))
    try:
        if file and file.filename.endswith('.json'):
            file_content = file.read().decode('utf-8')
            backup_data  = json.loads(file_content)
            from app.services.backup import BackupService
            BackupService.restore_backup_from_json(backup_data)
            flash("Database state restored successfully from uploaded JSON file!", "success")
        else:
            flash("Please upload a valid JSON file.", "danger")
    except Exception as e:
        flash(f"Failed to restore backup: {str(e)}", "danger")
    return redirect(url_for('main.dashboard'))


# ---------------------------------------------------------------------------
# Interview Events Routes
# ---------------------------------------------------------------------------

INTERVIEW_STATUSES = {
    'Online Assessment', 'Phone Screen',
    'Technical Interview', 'Manager Interview', 'Final Round'
}

@main.route('/jobs/<int:job_id>/interview-event/add', methods=['POST'])
def add_interview_event(job_id):
    job = Job.query.get_or_404(job_id)
    round_name      = request.form.get('round_name', '')
    scheduled_str   = request.form.get('scheduled_at', '')
    duration_min    = request.form.get('duration_min')
    meeting_link    = request.form.get('meeting_link', '')
    career_site_url = request.form.get('career_site_url', '')
    interviewer     = request.form.get('interviewer', '')
    event_notes     = request.form.get('event_notes', '')

    scheduled_at = None
    if scheduled_str:
        try:
            scheduled_at = datetime.strptime(scheduled_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            pass

    ev = InterviewEvent(
        job_id          = job.id,
        round_name      = round_name,
        scheduled_at    = scheduled_at,
        duration_min    = int(duration_min) if duration_min else None,
        meeting_link    = meeting_link or None,
        career_site_url = career_site_url or None,
        interviewer     = interviewer or None,
        notes           = event_notes or None,
    )
    db.session.add(ev)

    # Also record in history if status is interview-like
    new_status = request.form.get('status') or round_name
    if new_status and new_status != job.status:
        old = job.status
        job.status = new_status
        hist = ApplicationHistory(
            job_id = job.id,
            status = new_status,
            notes  = f'Interview event added: {round_name}'
        )
        db.session.add(hist)

    db.session.commit()
    flash(f'Interview event "{round_name}" added.', 'success')
    return redirect(url_for('main.job_detail', job_id=job.id))


@main.route('/jobs/<int:job_id>/interview-event/<int:ev_id>/delete', methods=['POST'])
def delete_interview_event(job_id, ev_id):
    ev = InterviewEvent.query.get_or_404(ev_id)
    db.session.delete(ev)
    db.session.commit()
    flash('Interview event deleted.', 'info')
    return redirect(url_for('main.job_detail', job_id=job_id))


# ---------------------------------------------------------------------------
# GitHub Backup Routes
# ---------------------------------------------------------------------------

@main.route('/backup/github-push', methods=['POST'])
def backup_github_push():
    from flask import current_app
    token = current_app.config.get('GITHUB_TOKEN', '')
    repo  = current_app.config.get('GITHUB_REPO',  '')
    try:
        from app.services.backup import BackupService
        sha = BackupService.save_backup_to_github(token, repo)
        flash(f'Backup pushed to GitHub ({repo}) — commit {sha[:8]}.', 'success')
    except Exception as e:
        flash(f'GitHub backup failed: {e}', 'danger')
    return redirect(url_for('main.resume_profile'))


@main.route('/backup/github-list')
def backup_github_list():
    from flask import current_app
    token = current_app.config.get('GITHUB_TOKEN', '')
    repo  = current_app.config.get('GITHUB_REPO',  '')
    from app.services.backup import BackupService
    backups = BackupService.list_backups_in_github(token, repo)
    return jsonify({'success': True, 'backups': backups})


@main.route('/backup/github-restore', methods=['POST'])
def backup_github_restore():
    from flask import current_app
    token = current_app.config.get('GITHUB_TOKEN', '')
    repo  = current_app.config.get('GITHUB_REPO',  '')
    path  = request.form.get('path', '')
    if not path:
        flash('No backup file path provided.', 'danger')
        return redirect(url_for('main.resume_profile'))
    try:
        from app.services.backup import BackupService
        BackupService.restore_backup_from_github(token, repo, path)
        flash('Database restored from GitHub backup!', 'success')
    except Exception as e:
        flash(f'GitHub restore failed: {e}', 'danger')
    return redirect(url_for('main.dashboard'))


# ---------------------------------------------------------------------------
# Interview Events (per-job round tracking)
# ---------------------------------------------------------------------------

@main.route('/jobs/<int:job_id>/interview-events/add', methods=['POST'])
def add_interview_event(job_id):
    job = Job.query.get_or_404(job_id)

    round_name      = request.form.get('round_name', '').strip()
    scheduled_str   = request.form.get('scheduled_at', '').strip()
    duration_min    = request.form.get('duration_min', '').strip()
    meeting_link    = request.form.get('meeting_link', '').strip() or None
    career_site_url = request.form.get('career_site_url', '').strip() or None
    interviewer     = request.form.get('interviewer', '').strip() or None
    event_notes     = request.form.get('event_notes', '').strip() or None

    if not round_name:
        flash('Round type is required.', 'danger')
        return redirect(url_for('main.job_detail', job_id=job_id))

    scheduled_at = None
    if scheduled_str:
        try:
            scheduled_at = datetime.fromisoformat(scheduled_str)
        except ValueError:
            flash('Invalid date/time format.', 'danger')
            return redirect(url_for('main.job_detail', job_id=job_id))

    dur = None
    if duration_min:
        try:
            dur = int(duration_min)
        except ValueError:
            pass

    ev = InterviewEvent(
        job_id          = job.id,
        round_name      = round_name,
        scheduled_at    = scheduled_at,
        duration_min    = dur,
        meeting_link    = meeting_link,
        career_site_url = career_site_url,
        interviewer     = interviewer,
        notes           = event_notes,
    )
    db.session.add(ev)
    db.session.commit()
    flash(f'Interview event "{round_name}" scheduled!', 'success')
    return redirect(url_for('main.job_detail', job_id=job_id))


@main.route('/jobs/<int:job_id>/interview-events/<int:ev_id>/delete', methods=['POST'])
def delete_interview_event(job_id, ev_id):
    ev = InterviewEvent.query.filter_by(id=ev_id, job_id=job_id).first_or_404()
    db.session.delete(ev)
    db.session.commit()
    flash('Interview event deleted.', 'info')
    return redirect(url_for('main.job_detail', job_id=job_id))
