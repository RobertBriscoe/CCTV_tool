#!/usr/bin/env python3
"""
List available Gemini models for your API key
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

GEMINI_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_KEY:
    print("❌ ERROR: Missing GEMINI_API_KEY")
    exit(1)

url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_KEY}"

print("Fetching available Gemini models...\n")

try:
    response = requests.get(url, timeout=10)

    if response.status_code == 200:
        data = response.json()
        models = data.get('models', [])

        print(f"✅ Found {len(models)} models:\n")
        print("=" * 80)

        for model in models:
            name = model.get('name', 'Unknown')
            display_name = model.get('displayName', 'N/A')
            description = model.get('description', 'N/A')
            methods = model.get('supportedGenerationMethods', [])

            # Only show models that support generateContent
            if 'generateContent' in methods:
                print(f"📦 Model: {name}")
                print(f"   Display Name: {display_name}")
                print(f"   Description: {description[:100]}...")
                print(f"   Methods: {', '.join(methods)}")
                print("-" * 80)

    else:
        print(f"❌ ERROR: Status {response.status_code}")
        print(response.text)

except Exception as e:
    print(f"❌ ERROR: {str(e)}")
