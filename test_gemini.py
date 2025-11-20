#!/usr/bin/env python3
"""
Simple Gemini API Test Script
Tests the Gemini API configuration and connectivity
"""

import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_gemini_api():
    """Test Gemini API with a simple request"""

    # Get API key from environment
    GEMINI_KEY = os.getenv("GEMINI_API_KEY")

    if not GEMINI_KEY:
        print("❌ ERROR: Missing GEMINI_API_KEY in .env file")
        return False

    print(f"✓ Found API key: {GEMINI_KEY[:20]}...")

    # Test API endpoint - using stable Gemini 2.5 Flash
    model = "gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_KEY}"

    # Simple test prompt
    payload = {
        "contents": [{
            "parts": [{
                "text": "Say 'Hello! Gemini API is working!' in one sentence."
            }]
        }]
    }

    print(f"\n🔄 Testing Gemini API ({model})...")

    try:
        response = requests.post(url, json=payload, timeout=10)

        if response.status_code == 200:
            result = response.json()
            text = result['candidates'][0]['content']['parts'][0]['text']
            print(f"\n✅ SUCCESS! Gemini responded:")
            print(f"   {text}")
            return True
        else:
            print(f"\n❌ ERROR: API returned status {response.status_code}")
            print(f"   Response: {response.text}")
            return False

    except requests.exceptions.Timeout:
        print("\n❌ ERROR: Request timed out")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Gemini API Test")
    print("=" * 60)

    success = test_gemini_api()

    print("\n" + "=" * 60)
    if success:
        print("✅ Gemini API is configured correctly!")
    else:
        print("❌ Gemini API test failed. Check configuration.")
    print("=" * 60)
