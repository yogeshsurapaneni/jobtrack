import requests
import json
from flask import current_app

class OpenRouterService:
    @staticmethod
    def generate_completion(messages, model=None):
        """
        Sends a chat completion request to the OpenRouter API.
        Returns a tuple of (content, model_used).
        """
        api_key = current_app.config.get('OPENROUTER_API_KEY')
        if not api_key:
            # Fallback or error
            raise ValueError("OpenRouter API key is missing. Please set OPENROUTER_API_KEY in your environment.")
        
        selected_model = model or current_app.config.get('OPENROUTER_MODEL', 'google/gemini-2.5-flash')
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:5000",
            "X-Title": "AI Resume Tailoring Engine"
        }
        
        payload = {
            "model": selected_model,
            "messages": messages,
            "temperature": 0.2  # Keep it low to prevent fabrication and hallucination
        }
        
        try:
            print(f"[*] Dispatching AI generation request to model: {selected_model}")
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                data=json.dumps(payload),
                timeout=60
            )
            response.raise_for_status()
            res_json = response.json()
            
            if 'choices' in res_json and len(res_json['choices']) > 0:
                content = res_json['choices'][0]['message']['content']
                return content, selected_model
            else:
                raise Exception(f"Unexpected response format from OpenRouter: {res_json}")
                
        except Exception as e:
            print(f"[!] OpenRouter API request failed: {e}")
            raise e
