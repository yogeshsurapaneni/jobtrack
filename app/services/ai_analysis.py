from app.models import Job, ResumeProfile
from app.services.openrouter import OpenRouterService
from app.services.resume_generator import ResumeGeneratorService
import json
import re


class AIAnalysisService:
    @classmethod
    def analyze_job_match(cls, job_id, model=None):
        """
        Analyzes the Resume Profile against the Job Description.
        Returns a compact JSON dict with: score (int), grade (str),
        strengths (list[str] max 3), gaps (list[str] max 3), tip (str).
        """
        job = Job.query.get(job_id)
        if not job:
            raise ValueError(f"Job with ID {job_id} not found.")

        profile = ResumeProfile.query.first()
        if not profile:
            raise ValueError("Resume Profile is empty. Please complete your Resume Profile first.")

        profile_markdown = ResumeGeneratorService.format_profile_to_markdown(profile)

        system_prompt = (
            "You are an expert ATS evaluator and technical recruiter.\n"
            "Analyze the resume profile against the job description with precision.\n"
            "Respond ONLY with a valid JSON object — no markdown, no extra text.\n"
            "The JSON must follow this exact schema:\n"
            "{\n"
            '  "score": <integer 0-100>,\n'
            '  "grade": <"A"|"B"|"C"|"D">,\n'
            '  "strengths": [<string>, <string>, <string>],\n'
            '  "gaps": [<string>, <string>, <string>],\n'
            '  "tip": <one actionable sentence to improve the score>\n'
            "}"
        )

        user_prompt = (
            f"Resume Profile:\n{profile_markdown}\n\n"
            f"Job: {job.position} at {job.company}\n"
            f"Description:\n{job.job_description or 'No description provided.'}\n\n"
            "Evaluate and return ONLY the JSON object."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt}
        ]

        raw, model_used = OpenRouterService.generate_completion(messages, model)

        # Strip code fences if model wraps in ```json
        raw = raw.strip()
        raw = re.sub(r'^```[a-zA-Z]*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)

        try:
            return json.loads(raw.strip())
        except json.JSONDecodeError:
            # Fallback: return a minimal dict so the UI never breaks
            return {
                "score": 0,
                "grade": "?",
                "strengths": ["Could not parse analysis."],
                "gaps": [],
                "tip": raw[:300]
            }

    @classmethod
    def generate_email_template(cls, job_id, email_type, model=None):
        """
        Generates a detailed, professional outreach email with full body.
        Returns the email as markdown text.
        """
        job = Job.query.get(job_id)
        if not job:
            raise ValueError(f"Job with ID {job_id} not found.")

        profile = ResumeProfile.query.first()
        profile_markdown = ResumeGeneratorService.format_profile_to_markdown(profile) if profile else ""

        system_prompt = (
            "You are a senior professional business writer specializing in career communications.\n"
            "Write detailed, complete, ready-to-send emails — not templates with vague placeholders.\n"
            "Use specific details from the candidate's profile and the job description.\n"
            "Tone: warm, confident, and professional (US business style).\n"
            "Structure: Subject Line, then full email body.\n"
            "Output clean Markdown."
        )

        user_prompt = (
            f"Candidate Profile:\n{profile_markdown}\n\n"
            f"Target Role: {job.position} at {job.company}\n"
            f"Job Description Snippet:\n{(job.job_description or 'N/A')[:600]}\n\n"
            f"Email Type: {email_type}\n\n"
            f"Write a complete, detailed, ready-to-send email for this scenario.\n"
            f"Include:\n"
            f"- A specific, compelling subject line\n"
            f"- A full greeting\n"
            f"- 2-3 substantive body paragraphs that reference specific achievements from the profile and relate them to the role\n"
            f"- A clear call-to-action\n"
            f"- A professional sign-off\n"
            f"Do NOT use generic placeholder text. Make it feel personal and specific."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt}
        ]

        email_text, model_used = OpenRouterService.generate_completion(messages, model)
        return email_text
