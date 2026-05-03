from dotenv import load_dotenv
import os
import time
from google import genai
from google.genai import errors

# Load API key from .env file
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("❌ ERROR: GEMINI_API_KEY not found in .env file")
else:
    print("✅ API key loaded successfully")

# Configure Gemini client
client = genai.Client(api_key=api_key)

# Send test message with retry logic
print("\n🤖 Sending test message to Gemini...\n")

max_retries = 3
retry_delay = 5

for attempt in range(max_retries):
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Say hello to ARIS - an Autonomous Reasoning & Intelligence System being built by a developer. Keep it short and exciting!"
        )
        
        print("Gemini says:")
        print(response.text)
        print("\n✅ ARIS Phase 0 test complete!")
        break
        
    except errors.ClientError as e:
        if 'RESOURCE_EXHAUSTED' in str(e) or '429' in str(e):  # Rate limit exceeded
            if attempt < max_retries - 1:
                # Simple retry with fixed delay
                print(f"⏳ Rate limit exceeded. Retrying in {retry_delay} seconds... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
                continue
            else:
                print("❌ Rate limit exceeded. Maximum retries reached.")
                print("💡 The Gemini API free tier quota has been exhausted.")
                print("   Please try again later or upgrade your plan at: https://ai.google.dev/gemini-api")
        else:
            print(f"❌ API Error: {e}")
            break
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        break