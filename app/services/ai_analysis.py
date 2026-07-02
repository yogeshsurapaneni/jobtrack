from app.models import Job, ResumeProfile
from app.services.openrouter import OpenRouterService
from app.services.resume_generator import ResumeGeneratorService

class AIAnalysisService:
    @classmethod
    def analyze_job_match(cls, job_id, model=None):
        """
        Analyzes the Resume Profile against the Job Description.
        Calculates Match Score, identifies Missing Skills, and suggests ATS improvements.
        """
        job = Job.query.get(job_id)
        if not job:
            raise ValueError(f"Job with ID {job_id} not found.")
            
        profile = ResumeProfile.query.first()
        if not profile:
            raise ValueError("Resume Profile is empty. Please complete your Resume Profile first.")
            
        profile_markdown = ResumeGeneratorService.format_profile_to_markdown(profile)
        
        system_prompt = (
            "You are an expert technical recruiter and ATS evaluation system.\n"
            "Analyze the resume profile against the job description.\n"
            "Be objective, constructive, and realistic. Do not make up achievements.\n"
            "Format the output strictly in Markdown using the headers specified."
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
            f"Please generate a comprehensive analysis containing:\n"
            f"1. **Job Match Score**: Give an overall match percentage (e.g. 75%) and break down why.\n"
            f"2. **Missing Skills**: List specific technical and soft skills mentioned in the job description that are missing or weak in the resume profile.\n"
            f"3. **ATS Score Details**: Break down the score by: Keywords matched, Formatting, Length (2-page target), Readability, and Overall Score.\n"
            f"4. **Actionable Suggestions**: Specific changes to keywords or phrasing to improve ATS optimization."
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        analysis, model_used = OpenRouterService.generate_completion(messages, model)
        return analysis

    @classmethod
    def generate_interview_prep(cls, job_id, model=None):
        """
        Generates customized interview prep material based on Job Description and Resume Profile.
        """
        job = Job.query.get(job_id)
        if not job:
            raise ValueError(f"Job with ID {job_id} not found.")
            
        profile = ResumeProfile.query.first()
        if not profile:
            raise ValueError("Resume Profile is empty. Please complete your Resume Profile first.")
            
        profile_markdown = ResumeGeneratorService.format_profile_to_markdown(profile)
        
        system_prompt = (
            "You are an elite interview coach preparing a candidate for a technical/management interview.\n"
            "Generate realistic questions based on the job description and answer guidelines tailored to the candidate's actual experience.\n"
            "Output in professional Markdown."
        )
        
        user_prompt = (
            f"Candidate Resume Profile:\n"
            f"{profile_markdown}\n\n"
            f"Job Position: {job.position} at {job.company}\n"
            f"Job Description:\n{job.job_description or 'No description'}\n\n"
            f"Please generate:\n"
            f"1. **Top 5 Behavioral Questions**: Tailored questions with suggested STAR answers based on the candidate's profile.\n"
            f"2. **Top 5 Technical Questions**: Questions relevant to the job requirements with concise conceptual explanations.\n"
            f"3. **Smart Questions to Ask the Interviewer**: 3 unique, strategic questions about the company's tech stack or domain."
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        prep_guide, model_used = OpenRouterService.generate_completion(messages, model)
        return prep_guide

    @classmethod
    def generate_email_template(cls, job_id, email_type, model=None):
        """
        Generates professional email outreach templates (Follow-up, Thank You, Negotiation, etc.).
        """
        job = Job.query.get(job_id)
        if not job:
            raise ValueError(f"Job with ID {job_id} not found.")
            
        profile = ResumeProfile.query.first()
        name = profile.summary.split('\n')[0] if (profile and profile.summary) else "Applicant"
        
        system_prompt = (
            "You are a professional business writer.\n"
            "Generate a polished, natural-sounding email template.\n"
            "Keep the tone respectful, clear, and professional. Use brackets like [Your Name] for placeholders."
        )
        
        user_prompt = (
            f"Candidate Name: {name}\n"
            f"Job Position: {job.position}\n"
            f"Company: {job.company}\n"
            f"Email Type: {email_type} (e.g. Recruiter Follow-up, Post-Interview Thank You, Offer Negotiation, Withdrawal)\n\n"
            f"Please generate a subject line and body for a professional email tailored for this scenario. Keep it concise."
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        email_template, model_used = OpenRouterService.generate_completion(messages, model)
        return email_template
