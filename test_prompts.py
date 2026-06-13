import os
import json
import requests
from dotenv import load_dotenv
from prompts.review_prompt import logic_bug_prompt, summary_prompt

load_dotenv()

def call_groq(prompt: str) -> str:
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
            "Content-Type": "application/json"
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1
        }
    )
    return response.json()["choices"][0]["message"]["content"]

# Sample buggy patch
patch = """+def divide_numbers(a, b):
+    return a / b
+
+SECRET_KEY = "hardcoded_secret_123"
"""

prompt = logic_bug_prompt("buggy_code.py", patch)
result = call_groq(prompt)

print("--- RAW RESPONSE ---")
print(result)

print("\n--- PARSED ---")
findings = json.loads(result)
print(json.dumps(findings, indent=2))

print("\n--- SUMMARY ---")
summary = call_groq(summary_prompt(findings["findings"]))
print(summary)