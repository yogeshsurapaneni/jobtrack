import re
from datetime import datetime
from app.models import db, Job, Document, ResumeProfile
from app.services.openrouter import OpenRouterService
from app.services.storage import storage_service
from app.services.parser import markdown_to_pdf, markdown_to_docx

def slugify(text):
    """
    Simplistic slugifier for folder names in MinIO
    """
    text = text.lower()
    text = re.sub(r'[^a-z0-9\-]', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')

class ResumeGeneratorService:
    @staticmethod
    def format_profile_to_markdown(profile):
        """
        Formats a ResumeProfile model object into clean markdown representation for the LLM prompt.
        """
        md = []
        if profile.summary:
            md.append(f"# Professional Summary\n{profile.summary}\n")
        
        if profile.skills:
            md.append(f"# Technical Skills\n{profile.skills}\n")
        
        if profile.experience_json:
            md.append("# Work Experience")
            for exp in profile.experience_json:
                company = exp.get('company', '')
                pos = exp.get('position', '')
                start = exp.get('start_date', '')
                end = exp.get('end_date', '')
                desc = exp.get('description', '')
                md.append(f"## {pos} | {company} ({start} - {end})")
                md.append(f"{desc}\n")
                
        if profile.projects_json:
            md.append("# Projects")
            for proj in profile.projects_json:
                title = proj.get('title', '')
                tech = proj.get('technologies', '')
                desc = proj.get('description', '')
                link = proj.get('link', '')
                link_str = f" ({link})" if link else ""
                md.append(f"## {title}{link_str}")
                if tech:
                    md.append(f"**Technologies Used:** {tech}")
                md.append(f"{desc}\n")
                
        if profile.education_json:
            md.append("# Education")
            for edu in profile.education_json:
                school = edu.get('school', '')
                degree = edu.get('degree', '')
                field = edu.get('field_of_study', '')
                grad = edu.get('graduation_date', '')
                gpa = edu.get('gpa', '')
                gpa_str = f" | GPA: {gpa}" if gpa else ""
                md.append(f"## {degree} in {field}\n{school} (Graduated: {grad}{gpa_str})\n")
                
        if profile.certifications_json:
            md.append("# Certifications")
            for cert in profile.certifications_json:
                name = cert.get('name', '')
                auth = cert.get('authority', '')
                date = cert.get('date_obtained', '')
                md.append(f"- {name} — {auth} ({date})")
                
        return "\n".join(md)

    @classmethod
    def generate_tailored_resume(cls, job_id, model=None):
        """
        Orchestrates resume tailoring flow.
        1. Fetch Job and ResumeProfile.
        2. Generate Prompt.
        3. Call OpenRouter.
        4. Render to PDF/DOCX.
        5. Store in MinIO and register in DB.
        """
        job = Job.query.get(job_id)
        if not job:
            raise ValueError(f"Job with ID {job_id} not found.")
            
        profile = ResumeProfile.query.first()
        if not profile:
            raise ValueError("Resume Profile is empty. Please complete your Resume Profile first.")
            
        profile_markdown = cls.format_profile_to_markdown(profile)
        
        # Define prompts
        system_prompt = (
            "You are an executive resume writer for the US technology market.\n"
            "Optimize for ATS compatibility, readability, and impact.\n"
            "Do not fabricate experience, credentials, or dates. Tailor wording and focus, but keep it honest.\n"
            "Prioritize matching keywords from the job description naturally.\n"
            "Keep formatting clean, professional, and standard. Avoid custom characters/tables.\n"
            "Output valid, standard Markdown format only."
        )
        
        user_prompt = (
            f"Here is my Master Resume Profile:\n"
            f"=================================\n"
            f"{profile_markdown}\n"
            f"=================================\n\n"
            f"Here is the Job Description:\n"
            f"Company: {job.company}\n"
            f"Position: {job.position}\n"
            f"Location: {job.location or 'N/A'}\n"
            f"Description:\n{job.job_description or 'No description provided.'}\n"
            f"=================================\n\n"
            f"Task: Generate an ATS-tailored resume in Markdown based ONLY on the details in my Master Resume Profile.\n"
            f"Focus on highlighting my experience that matches the Job Description. Keep the resume to at most 2 pages.\n"
            f"Always start the output with a centered header containing name, contact details (email, phone, location, LinkedIn) at the very top. Use standard headers like '## Professional Experience', '## Skills', etc."
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # Call OpenRouter API
        markdown_resume, model_used = OpenRouterService.generate_completion(messages, model)
        
        # Calculate next version
        job_slug = slugify(f"{job.company}-{job.position}")
        existing_resumes = Document.query.filter_by(job_id=job.id, type='Generated Resume').all()
        version = len(existing_resumes) + 1
        
        # Convert to PDF and DOCX
        pdf_bytes = markdown_to_pdf(markdown_resume)
        docx_bytes = markdown_to_docx(markdown_resume)
        
        # Save PDF to MinIO
        pdf_filename = f"resume_v{version}.pdf"
        pdf_minio_path = f"jobs/{job_slug}/generated/{pdf_filename}"
        storage_service.upload_file(pdf_minio_path, pdf_bytes, content_type='application/pdf')
        
        # Save DOCX to MinIO
        docx_filename = f"resume_v{version}.docx"
        docx_minio_path = f"jobs/{job_slug}/generated/{docx_filename}"
        storage_service.upload_file(docx_minio_path, docx_bytes, content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        
        # Log prompt to MinIO as txt
        prompt_log = f"System Prompt:\n{system_prompt}\n\nUser Prompt:\n{user_prompt}"
        prompt_minio_path = f"jobs/{job_slug}/generated/prompt_v{version}.txt"
        storage_service.upload_file(prompt_minio_path, prompt_log.encode('utf-8'), content_type='text/plain')
        
        # Save Document entries to database
        pdf_doc = Document(
            job_id=job.id,
            type='Generated Resume',
            filename=pdf_filename,
            minio_path=pdf_minio_path,
            version=version,
            model_used=model_used,
            prompt_used=user_prompt
        )
        
        docx_doc = Document(
            job_id=job.id,
            type='Generated Resume',
            filename=docx_filename,
            minio_path=docx_minio_path,
            version=version,
            model_used=model_used,
            prompt_used=user_prompt
        )
        
        db.session.add(pdf_doc)
        db.session.add(docx_doc)
        db.session.commit()
        
        return pdf_doc
