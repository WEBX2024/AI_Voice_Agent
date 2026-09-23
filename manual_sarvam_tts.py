import base64
import os

import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("SARVAM_API_KEY")
url = "https://api.sarvam.ai/text-to-speech"

headers = {
    "api-subscription-key": api_key,
    "Content-Type": "application/json",
}

payload = {
    "inputs": ["Hello, this is a test of Sarvam text to speech."],
    "target_language_code": "en-IN",
    "model": "bulbul:v3",
    "speaker": "shubh",
    "speech_sample_rate": 16000,
    "output_audio_codec": "wav",
}

print("Sending request to Sarvam TTS...")
response = requests.post(url, headers=headers, json=payload)

print("STATUS:", response.status_code)
print("RESPONSE:", response.text[:2000])

if response.ok:
    data = response.json()
    if "audios" in data and len(data["audios"]) > 0:
        audio = base64.b64decode(data["audios"][0])
        with open("sarvam_test.wav", "wb") as f:
            f.write(audio)
        print("SUCCESS: sarvam_test.wav created")
    else:
        print("SUCCESS from API but no 'audios' in response.")
