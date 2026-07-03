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
    def generate_tailored_resume(cls, job_id, model=None, additional_notes=None):
        """
        Orchestrates resume tailoring flow.
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
            "You are an elite executive resume writer for the US technology market.\n"
            "Your goal: produce the BEST possible ATS-optimized resume that maximizes interview callbacks.\n\n"
            "STRICT RULES:\n"
            "1. Use ONLY information from the Master Resume Profile — never fabricate dates, companies, titles, or metrics.\n"
            "2. Maximize keyword density from the Job Description naturally woven into bullet points.\n"
            "3. Use strong action verbs to start every bullet (Architected, Engineered, Delivered, Led, Reduced, Increased, etc.).\n"
            "4. Each bullet point MUST be on its own line and start with a hyphen space ('- '). Never output bullet points inline or on a single line separated by asterisks or dashes. Never output a paragraph containing asterisks or dashes as lists. Every single bullet point must start on a brand new line.\n"
            "5. Quantify achievements wherever the profile provides numbers (%, $, users, latency, etc.).\n"
            "6. Keep to 1-2 pages maximum. Omit irrelevant experience sections if needed.\n"
            "7. Output ONLY clean standard Markdown. No HTML, no tables, no custom characters.\n"
            "8. Section headers must use '## ' prefix exactly (e.g. '## Professional Experience').\n"
            "9. Job entry sub-headers: '### Position | Company' on one line, then '#### Location | Start – End' below it."
        )

        user_prompt = (
            f"MASTER RESUME PROFILE:\n"
            f"{'='*60}\n"
            f"{profile_markdown}\n"
            f"{'='*60}\n\n"
            f"TARGET JOB DESCRIPTION:\n"
            f"Company: {job.company}\n"
            f"Position: {job.position}\n"
            f"Location: {job.location or 'Not specified'}\n"
            f"Description:\n{job.job_description or 'No description provided.'}\n"
            f"{'='*60}\n\n"
            f"TASK: Generate the best possible ATS-tailored resume in Markdown using ONLY the profile above.\n"
            f"Structure:\n"
            f"1. Start with '# Full Name' (centered via h1)\n"
            f"2. Next line: contact info paragraph (email | phone | location | LinkedIn)\n"
            f"3. '## Summary' — 2-3 sentence value proposition targeting this specific role\n"
            f"4. '## Skills' — comma-separated or pipe-separated, grouped by category\n"
            f"5. '## Professional Experience' — each role as ### Position | Company, then #### Location | Dates, then bullet points\n"
            f"6. '## Projects' (if relevant)\n"
            f"7. '## Education'\n"
            f"8. '## Certifications' (if any)\n"
            f"Ensure every single bullet starts on a brand new line with '- '."
        )

        if additional_notes:
            user_prompt += (
                f"\n\nADDITIONAL INSTRUCTIONS / KEYWORD REQUESTS FROM THE USER (FOLLOW THESE STRICTLY):\n"
                f"{additional_notes}\n"
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
