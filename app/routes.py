import json
from flask import Blueprint, render_template, redirect, url_for, request, flash, send_file, jsonify
from app.models import db, User, Job, ApplicationHistory, Document, ResumeProfile
from app.services.resume_generator import ResumeGeneratorService
from app.services.coverletter_generator import CoverLetterGeneratorService
from app.services.storage import storage_service
from app.services.ai_analysis import AIAnalysisService
from datetime import datetime, date

main = Blueprint('main', __name__)

# --- Dashboard Route ---


@main.route('/')
@main.route('/dashboard')
def dashboard():
    jobs = Job.query.all()
    
    total = len(jobs)
    wishlist = sum(1 for j in jobs if j.status == 'Wishlist')
    interested = sum(1 for j in jobs if j.status == 'Interested')
    applied = sum(1 for j in jobs if j.status == 'Applied')
    
    interview_statuses = {'OA', 'Recruiter Screen', 'Technical', 'Manager Round', 'Final Round'}
    interviewing = sum(1 for j in jobs if j.status in interview_statuses)
    offers = sum(1 for j in jobs if j.status == 'Offer')
    rejected = sum(1 for j in jobs if j.status == 'Rejected')
    
    # Calculate response rate: (Any status beyond 'Applied' / Total applied or beyond) * 100
    active_statuses_beyond_applied = {'OA', 'Recruiter Screen', 'Technical', 'Manager Round', 'Final Round', 'Offer', 'Rejected', 'Withdrawn'}
    total_applied_or_more = sum(1 for j in jobs if j.status not in {'Wishlist', 'Interested'})
    positive_responses = sum(1 for j in jobs if j.status in active_statuses_beyond_applied)
    
    response_rate = int((positive_responses / total_applied_or_more * 100)) if total_applied_or_more > 0 else 0

    # Recent activity: last 5 history changes
    recent_activity = ApplicationHistory.query.order_by(ApplicationHistory.changed_at.desc()).limit(8).all()

    # Pipelines by status data for charts
    status_counts = {
        'Wishlist': wishlist,
        'Interested': interested,
        'Applied': applied,
        'Interviewing': interviewing,
        'Offers': offers,
        'Rejected': rejected
    }

    return render_template(
        'dashboard.html',
        total=total,
        wishlist=wishlist,
        interested=interested,
        applied=applied,
        interviewing=interviewing,
        offers=offers,
        rejected=rejected,
        response_rate=response_rate,
        recent_activity=recent_activity,
        status_counts=status_counts
    )


# --- Jobs Routes ---

@main.route('/jobs')
def jobs_list():
    # Search, filter, and sort
    search = request.args.get('search', '')
    status_filter = request.args.get('status', '')
    sort_by = request.args.get('sort', 'updated_at')
    direction = request.args.get('direction', 'desc')

    query = Job.query
    
    if search:
        query = query.filter((Job.company.ilike(f'%{search}%')) | (Job.position.ilike(f'%{search}%')) | (Job.location.ilike(f'%{search}%')))
    
    if status_filter:
        query = query.filter(Job.status == status_filter)

    # Sorting
    if sort_by == 'company':
        field = Job.company
    elif sort_by == 'position':
        field = Job.position
    elif sort_by == 'applied_date':
        field = Job.applied_date
    elif sort_by == 'created_at':
        field = Job.created_at
    else:
        field = Job.updated_at

    if direction == 'asc':
        query = query.order_by(field.asc())
    else:
        query = query.order_by(field.desc())

    jobs = query.all()
    
    return render_template('jobs.html', jobs=jobs, search=search, status_filter=status_filter, sort_by=sort_by, direction=direction)

@main.route('/jobs/add', methods=['POST'])
def add_job():
    company = request.form.get('company')
    position = request.form.get('position')
    location = request.form.get('location')
    salary = request.form.get('salary')
    job_url = request.form.get('job_url')
    job_description = request.form.get('job_description')
    notes = request.form.get('notes')
    status = request.form.get('status', 'Wishlist')
    
    applied_date_str = request.form.get('applied_date')
    applied_date = None
    if applied_date_str:
        try:
            applied_date = datetime.strptime(applied_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    job = Job(
        company=company,
        position=position,
        location=location,
        salary=salary,
        job_url=job_url,
        job_description=job_description,
        notes=notes,
        status=status,
        applied_date=applied_date
    )
    db.session.add(job)
    db.session.commit()

    # Track initial status change
    history = ApplicationHistory(
        job_id=job.id,
        status=status,
        notes="Job added to tracker."
    )
    db.session.add(history)
    db.session.commit()

    flash(f"Added job for {position} at {company}!", "success")
    return redirect(url_for('main.jobs_list'))

@main.route('/jobs/<int:job_id>')
def job_detail(job_id):
    job = Job.query.get_or_404(job_id)
    # Group generated documents by type for cleaner display
    docs = Document.query.filter_by(job_id=job.id).order_by(Document.version.desc()).all()
    
    resumes = [d for d in docs if d.type == 'Generated Resume']
    cover_letters = [d for d in docs if d.type == 'Cover Letter']
    
    # We can pass lists of model selections
    models = [
        ("google/gemini-2.5-flash", "Gemini 2.5 Flash"),
        ("google/gemini-2.5-pro", "Gemini 2.5 Pro"),
        ("anthropic/claude-3-sonnet", "Claude 3 Sonnet"),
        ("meta-llama/llama-3.1-70b-instruct", "Llama 3.1 70B"),
        ("deepseek/deepseek-chat", "DeepSeek V3")
    ]
    
    return render_template(
        'job_detail.html',
        job=job,
        resumes=resumes,
        cover_letters=cover_letters,
        models=models
    )

@main.route('/jobs/<int:job_id>/edit', methods=['POST'])
def edit_job(job_id):
    job = Job.query.get_or_404(job_id)
    job.company = request.form.get('company')
    job.position = request.form.get('position')
    job.location = request.form.get('location')
    job.salary = request.form.get('salary')
    job.job_url = request.form.get('job_url')
    job.job_description = request.form.get('job_description')
    job.notes = request.form.get('notes')
    
    applied_date_str = request.form.get('applied_date')
    if applied_date_str:
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
    new_status = request.form.get('status')
    status_notes = request.form.get('notes', '')

    if new_status and new_status != job.status:
        old_status = job.status
        job.status = new_status
        if new_status == 'Applied' and not job.applied_date:
            job.applied_date = date.today()
            
        history = ApplicationHistory(
            job_id=job.id,
            status=new_status,
            notes=status_notes or f"Status changed from {old_status} to {new_status}."
        )
        db.session.add(history)
        db.session.commit()
        flash(f"Status updated to {new_status}.", "success")
        
    return redirect(url_for('main.job_detail', job_id=job.id))

@main.route('/jobs/<int:job_id>/delete', methods=['POST'])
def delete_job(job_id):
    job = Job.query.get_or_404(job_id)
    company = job.company
    position = job.position
    db.session.delete(job)
    db.session.commit()
    flash(f"Deleted application for {position} at {company}.", "info")
    return redirect(url_for('main.jobs_list'))


# --- AI Generation Routes ---

@main.route('/jobs/<int:job_id>/generate-resume', methods=['POST'])
def generate_resume(job_id):
    model = request.form.get('model')
    try:
        pdf_doc = ResumeGeneratorService.generate_tailored_resume(job_id, model=model)
        flash(f"Tailored Resume v{pdf_doc.version} generated successfully!", "success")
    except Exception as e:
        flash(f"Failed to generate resume: {str(e)}", "danger")
        
    return redirect(url_for('main.job_detail', job_id=job_id))

@main.route('/jobs/<int:job_id>/generate-coverletter', methods=['POST'])
def generate_cover_letter(job_id):
    model = request.form.get('model')
    try:
        pdf_doc = CoverLetterGeneratorService.generate_cover_letter(job_id, model=model)
        flash(f"Tailored Cover Letter v{pdf_doc.version} generated successfully!", "success")
    except Exception as e:
        flash(f"Failed to generate cover letter: {str(e)}", "danger")
        
    return redirect(url_for('main.job_detail', job_id=job_id))


# --- AI Tools & Productivity Routes ---

@main.route('/jobs/<int:job_id>/match-score')
def match_score(job_id):
    model = request.args.get('model')
    try:
        analysis = AIAnalysisService.analyze_job_match(job_id, model=model)
        import markdown
        html_analysis = markdown.markdown(analysis)
        return jsonify({"success": True, "html": html_analysis})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@main.route('/jobs/<int:job_id>/interview-prep')
def interview_prep(job_id):
    model = request.args.get('model')
    try:
        prep_data = AIAnalysisService.generate_interview_prep(job_id, model=model)
        import markdown
        html_prep = markdown.markdown(prep_data)
        return jsonify({"success": True, "html": html_prep})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@main.route('/jobs/<int:job_id>/email-gen', methods=['POST'])
def email_gen(job_id):
    model = request.form.get('model')
    email_type = request.form.get('email_type')
    try:
        email_content = AIAnalysisService.generate_email_template(job_id, email_type, model=model)
        import markdown
        html_email = markdown.markdown(email_content)
        return jsonify({"success": True, "html": html_email, "raw": email_content})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- Resume Profile Route ---

@main.route('/resume', methods=['GET', 'POST'])
def resume_profile():
    profile = ResumeProfile.query.first()
    if not profile:
        # Create an empty one
        profile = ResumeProfile(experience_json=[], education_json=[], projects_json=[], certifications_json=[])
        db.session.add(profile)
        db.session.commit()

    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'save_basic':
            profile.summary = request.form.get('summary')
            profile.skills = request.form.get('skills')
            db.session.commit()
            flash("Basic profile info updated.", "success")
            
        elif action == 'add_experience':
            exp = {
                "company": request.form.get('company'),
                "position": request.form.get('position'),
                "start_date": request.form.get('start_date'),
                "end_date": request.form.get('end_date') or 'Present',
                "description": request.form.get('description')
            }
            # SQLAlchemy mutable json gotcha: we must reassign or use flag_modified
            curr = list(profile.experience_json or [])
            curr.append(exp)
            profile.experience_json = curr
            db.session.commit()
            flash("Work experience entry added.", "success")
            
        elif action == 'delete_experience':
            idx = int(request.form.get('index'))
            curr = list(profile.experience_json or [])
            if 0 <= idx < len(curr):
                curr.pop(idx)
                profile.experience_json = curr
                db.session.commit()
                flash("Work experience entry deleted.", "success")

        elif action == 'add_project':
            proj = {
                "title": request.form.get('title'),
                "technologies": request.form.get('technologies'),
                "description": request.form.get('description'),
                "link": request.form.get('link')
            }
            curr = list(profile.projects_json or [])
            curr.append(proj)
            profile.projects_json = curr
            db.session.commit()
            flash("Project entry added.", "success")
            
        elif action == 'delete_project':
            idx = int(request.form.get('index'))
            curr = list(profile.projects_json or [])
            if 0 <= idx < len(curr):
                curr.pop(idx)
                profile.projects_json = curr
                db.session.commit()
                flash("Project entry deleted.", "success")

        elif action == 'add_education':
            edu = {
                "school": request.form.get('school'),
                "degree": request.form.get('degree'),
                "field_of_study": request.form.get('field_of_study'),
                "graduation_date": request.form.get('graduation_date'),
                "gpa": request.form.get('gpa')
            }
            curr = list(profile.education_json or [])
            curr.append(edu)
            profile.education_json = curr
            db.session.commit()
            flash("Education entry added.", "success")
            
        elif action == 'delete_education':
            idx = int(request.form.get('index'))
            curr = list(profile.education_json or [])
            if 0 <= idx < len(curr):
                curr.pop(idx)
                profile.education_json = curr
                db.session.commit()
                flash("Education entry deleted.", "success")

        elif action == 'add_certification':
            cert = {
                "name": request.form.get('name'),
                "authority": request.form.get('authority'),
                "date_obtained": request.form.get('date_obtained'),
                "link": request.form.get('link')
            }
            curr = list(profile.certifications_json or [])
            curr.append(cert)
            profile.certifications_json = curr
            db.session.commit()
            flash("Certification entry added.", "success")
            
        elif action == 'delete_certification':
            idx = int(request.form.get('index'))
            curr = list(profile.certifications_json or [])
            if 0 <= idx < len(curr):
                curr.pop(idx)
                profile.certifications_json = curr
                db.session.commit()
                flash("Certification entry deleted.", "success")

        return redirect(url_for('main.resume_profile'))

    from app.services.backup import BackupService
    backups = BackupService.list_backups_in_minio()
    return render_template('resume.html', profile=profile, backups=backups)


# --- Document Proxy Download Route ---

@main.route('/documents/download/<int:doc_id>')
def download_document(doc_id):
    doc = Document.query.get_or_404(doc_id)
    try:
        # Download from MinIO
        file_bytes = storage_service.download_file(doc.minio_path)
        
        # Determine content type
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


# --- Backup & Restore Routes ---

@main.route('/backup/create', methods=['POST'])
def create_backup():
    try:
        from app.services.backup import BackupService
        minio_path = BackupService.save_backup_to_minio()
        flash(f"Database backup created successfully and stored in MinIO: {minio_path}", "success")
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
        backup_str = json.dumps(backup_data, indent=2)
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
            backup_data = json.loads(file_content)
            from app.services.backup import BackupService
            BackupService.restore_backup_from_json(backup_data)
            flash("Database state restored successfully from uploaded JSON file!", "success")
        else:
            flash("Please upload a valid JSON file.", "danger")
    except Exception as e:
        flash(f"Failed to restore backup: {str(e)}", "danger")
    return redirect(url_for('main.dashboard'))
