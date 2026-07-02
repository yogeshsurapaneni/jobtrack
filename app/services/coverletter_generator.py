import re
from datetime import datetime
from app.models import db, Job, Document, ResumeProfile
from app.services.openrouter import OpenRouterService
from app.services.storage import storage_service
from app.services.parser import markdown_to_pdf, markdown_to_docx
from app.services.resume_generator import slugify

class CoverLetterGeneratorService:
    @classmethod
    def generate_cover_letter(cls, job_id, model=None):
        """
        Generates and stores a cover letter tailored to the job description.
        """
        job = Job.query.get(job_id)
        if not job:
            raise ValueError(f"Job with ID {job_id} not found.")
            
        profile = ResumeProfile.query.first()
        if not profile:
            raise ValueError("Resume Profile is empty. Please complete your Resume Profile first.")
            
        from app.services.resume_generator import ResumeGeneratorService
        profile_markdown = ResumeGeneratorService.format_profile_to_markdown(profile)
        
        system_prompt = (
            "You are a professional cover letter writer for the US tech market.\n"
            "Generate a highly professional, compelling, and tailored cover letter.\n"
            "Adhere strictly to the US business writing style. Keep it professional, clean, and concise (exactly one page).\n"
            "Avoid boring clichés (e.g., 'Please find enclosed my resume').\n"
            "Highlight 1-2 major relevant achievements from the user's profile that directly map to the job requirements.\n"
            "Refer to the company's mission/product if possible to show sincere interest.\n"
            "Do not fabricate achievements, skills, or credentials.\n"
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
            f"Task: Generate a customized 1-page Cover Letter in Markdown format.\n"
            f"Include proper business letter formatting at the top (Date, Applicant Details, Recipient Details if known, Salutation) followed by an engaging introduction, body paragraphs mapping achievements, and a strong conclusion."
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # Call OpenRouter API
        markdown_cl, model_used = OpenRouterService.generate_completion(messages, model)
        
        # Calculate next version
        job_slug = slugify(f"{job.company}-{job.position}")
        existing_cls = Document.query.filter_by(job_id=job.id, type='Cover Letter').all()
        version = len(existing_cls) + 1
        
        # Convert to PDF and DOCX
        pdf_bytes = markdown_to_pdf(markdown_cl)
        docx_bytes = markdown_to_docx(markdown_cl)
        
        # Save PDF to MinIO
        pdf_filename = f"cover_letter_v{version}.pdf"
        pdf_minio_path = f"jobs/{job_slug}/generated/{pdf_filename}"
        storage_service.upload_file(pdf_minio_path, pdf_bytes, content_type='application/pdf')
        
        # Save DOCX to MinIO
        docx_filename = f"cover_letter_v{version}.docx"
        docx_minio_path = f"jobs/{job_slug}/generated/{docx_filename}"
        storage_service.upload_file(docx_minio_path, docx_bytes, content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        
        # Log prompt to MinIO as txt
        prompt_log = f"System Prompt:\n{system_prompt}\n\nUser Prompt:\n{user_prompt}"
        prompt_minio_path = f"jobs/{job_slug}/generated/cover_letter_prompt_v{version}.txt"
        storage_service.upload_file(prompt_minio_path, prompt_log.encode('utf-8'), content_type='text/plain')
        
        # Save Document entries to database
        pdf_doc = Document(
            job_id=job.id,
            type='Cover Letter',
            filename=pdf_filename,
            minio_path=pdf_minio_path,
            version=version,
            model_used=model_used,
            prompt_used=user_prompt
        )
        
        docx_doc = Document(
            job_id=job.id,
            type='Cover Letter',
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
