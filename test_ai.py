"""
test_ai.py
----------
Verifies that the Groq AI is accessible and returning responses.
"""
import os
from dotenv import load_dotenv
load_dotenv()

from groq import Groq

api_key = os.environ.get('GROQ_API_KEY')
if not api_key:
    print("[FAIL] GROQ_API_KEY not found in .env — AI will not work!")
    exit(1)

print(f"[OK] GROQ_API_KEY loaded: {api_key[:12]}...")

client = Groq(api_key=api_key)

try:
    response = client.chat.completions.create(
        messages=[
            {"role": "system", "content": "You are ClassPulse AI, a friendly teaching assistant. Be concise (max 20 words)."},
            {"role": "user", "content": "What is the capital of France?"}
        ],
        model="llama-3.3-70b-versatile",
        temperature=0.5,
        max_tokens=50
    )
    answer = response.choices[0].message.content
    print(f"[OK] Groq AI responded: {answer}")
    print()
    print("[DONE] AI is working perfectly!")
except Exception as e:
    print(f"[FAIL] Groq AI error: {e}")
