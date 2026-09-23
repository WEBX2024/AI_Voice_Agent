"""
Diagnostic script to test each component of the voice agent pipeline.
Tests: Microphone → STT → LLM → TTS → Speaker
"""
import asyncio
import os
import sys
import time
import base64
import json
import struct

# Ensure UTF-8 output on Windows terminals
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

# ── Test 1: Microphone capture ──────────────────────────────────────
def test_microphone():
    print("\n" + "=" * 60)
    print("TEST 1: Microphone Capture (3 seconds)")
    print("=" * 60)
    try:
        import sounddevice as sd
        import numpy as np

        sample_rate = 16000
        duration = 3  # seconds
        print(f"  Recording {duration}s of audio at {sample_rate}Hz...")
        print("  🎤 Speak now!")

        audio = sd.rec(int(duration * sample_rate), samplerate=sample_rate,
                       channels=1, dtype='int16')
        sd.wait()

        audio_bytes = audio.tobytes()
        # Check if we got actual audio (not silence)
        audio_float = audio.astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(audio_float ** 2)))

        print(f"  ✅ Captured {len(audio_bytes)} bytes, RMS energy: {rms:.6f}")
        if rms < 0.001:
            print("  ⚠️  WARNING: Audio is near-silent. Check your microphone!")
        else:
            print("  ✅ Audio has speech-level energy.")

        return audio_bytes
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        return None


# ── Test 2: Sarvam STT (REST, one-shot) ────────────────────────────
async def test_stt_rest(audio_bytes):
    print("\n" + "=" * 60)
    print("TEST 2: Sarvam STT (REST one-shot)")
    print("=" * 60)
    import aiohttp
    import io
    import wave

    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        print("  ❌ SARVAM_API_KEY not set")
        return None

    # Wrap raw PCM in a proper WAV container
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(16000)
        wf.writeframes(audio_bytes)
    wav_bytes = wav_buffer.getvalue()

    headers = {"Api-Subscription-Key": api_key}
    form_data = aiohttp.FormData()
    form_data.add_field("file", wav_bytes, filename="audio.wav", content_type="audio/wav")
    form_data.add_field("model", "saaras:v3")
    form_data.add_field("language_code", "en-IN")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.sarvam.ai/speech-to-text",
                headers=headers, data=form_data
            ) as resp:
                status = resp.status
                body = await resp.text()
                print(f"  Status: {status}")
                if status == 200:
                    result = json.loads(body)
                    transcript = result.get("transcript", "")
                    print(f"  ✅ Transcript: \"{transcript}\"")
                    if not transcript:
                        print("  ⚠️  WARNING: Empty transcript — STT returned nothing.")
                    return transcript
                else:
                    print(f"  ❌ Error: {body[:500]}")
                    return None
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        return None


# ── Test 2b: Sarvam STT WebSocket (streaming) ──────────────────────
async def test_stt_websocket(audio_bytes):
    print("\n" + "=" * 60)
    print("TEST 2b: Sarvam STT (WebSocket streaming)")
    print("=" * 60)
    import aiohttp

    api_key = os.getenv("SARVAM_API_KEY")
    model = os.getenv("SARVAM_STT_MODEL", "saaras:v3-realtime")
    lang = os.getenv("SARVAM_LANGUAGE_CODE", "en-IN")

    url = f"wss://api.sarvam.ai/speech-to-text-realtime/ws?language_code={lang}&model={model}"
    headers = {"Api-Subscription-Key": api_key}

    try:
        async with aiohttp.ClientSession() as session:
            ws = await session.ws_connect(url, headers=headers)
            print(f"  ✅ WebSocket connected")

            # Send audio in chunks (simulate streaming)
            chunk_size = 3200  # 200ms of 16kHz 16-bit mono
            total_sent = 0
            transcripts = []

            for i in range(0, len(audio_bytes), chunk_size):
                chunk = audio_bytes[i:i + chunk_size]
                audio_b64 = base64.b64encode(chunk).decode("utf-8")
                await ws.send_json({"event": "audio_input", "audio": audio_b64})
                total_sent += len(chunk)

                # Try to receive any available transcript (non-blocking-ish)
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=0.1)
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        print(f"  📝 Event: {data.get('event')} → {data.get('text', '')}")
                        if data.get("text"):
                            transcripts.append(data["text"])
                except asyncio.TimeoutError:
                    pass

            print(f"  Sent {total_sent} bytes in {total_sent // chunk_size} chunks")

            # Now wait for remaining transcripts
            print("  Waiting for final transcripts...")
            for _ in range(20):  # Wait up to ~10s
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=0.5)
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        event = data.get("event", "")
                        text = data.get("text", "")
                        is_final = data.get("is_final", False)
                        print(f"  📝 Event: {event} | final={is_final} → \"{text}\"")
                        if text:
                            transcripts.append(text)
                        if is_final and text:
                            break
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        print(f"  ⚠️  WebSocket closed: {msg.type}")
                        break
                except asyncio.TimeoutError:
                    pass

            await ws.close()

            if transcripts:
                final = transcripts[-1]
                print(f"  ✅ Final transcript: \"{final}\"")
                return final
            else:
                print("  ⚠️  WARNING: No transcripts received from WebSocket STT!")
                print("  This means the STT provider is not returning any text.")
                print("  The _listen() loop will never accumulate text → agent never replies.")
                return None

    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return None


# ── Test 3: Groq LLM ───────────────────────────────────────────────
def test_llm(user_text):
    print("\n" + "=" * 60)
    print("TEST 3: Groq LLM")
    print("=" * 60)
    from groq import Groq

    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("LLM_PRIMARY_MODEL", "openai/gpt-oss-120b")

    if not api_key:
        print("  ❌ GROQ_API_KEY not set")
        return None

    try:
        client = Groq(api_key=api_key)
        print(f"  Sending to model: {model}")
        start = time.time()
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful voice assistant. Keep responses short."},
                {"role": "user", "content": user_text},
            ],
            temperature=0.7,
            max_tokens=256,
        )
        elapsed = time.time() - start
        response = completion.choices[0].message.content
        print(f"  ✅ Response ({elapsed:.2f}s): \"{response}\"")
        return response
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        return None


# ── Test 4: Sarvam TTS ─────────────────────────────────────────────
async def test_tts(text):
    print("\n" + "=" * 60)
    print("TEST 4: Sarvam TTS")
    print("=" * 60)
    import aiohttp

    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        print("  ❌ SARVAM_API_KEY not set")
        return None

    headers = {
        "Api-Subscription-Key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "inputs": [text],
        "model": os.getenv("SARVAM_TTS_MODEL", "bulbul:v3"),
        "speaker": os.getenv("SARVAM_TTS_SPEAKER", "meera"),
        "target_language_code": os.getenv("SARVAM_LANGUAGE_CODE", "en-IN"),
    }

    try:
        async with aiohttp.ClientSession() as session:
            start = time.time()
            async with session.post(
                "https://api.sarvam.ai/text-to-speech",
                headers=headers, json=payload
            ) as resp:
                elapsed = time.time() - start
                status = resp.status
                print(f"  Status: {status} ({elapsed:.2f}s)")

                if status == 200:
                    result = await resp.json()
                    audios = result.get("audios", [])
                    if audios:
                        audio_data = base64.b64decode(audios[0])
                        # Strip WAV header if present
                        if audio_data.startswith(b"RIFF"):
                            pcm_data = audio_data[44:]
                            print(f"  ✅ Got WAV audio: {len(audio_data)} bytes → {len(pcm_data)} bytes PCM")
                        else:
                            pcm_data = audio_data
                            print(f"  ✅ Got raw PCM audio: {len(pcm_data)} bytes")
                        return pcm_data
                    else:
                        print("  ⚠️  WARNING: No 'audios' in response!")
                        print(f"  Response keys: {list(result.keys())}")
                        return None
                else:
                    error = await resp.text()
                    print(f"  ❌ Error: {error[:500]}")
                    return None
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        return None


# ── Test 5: Speaker playback ───────────────────────────────────────
def test_playback(pcm_data):
    print("\n" + "=" * 60)
    print("TEST 5: Speaker Playback")
    print("=" * 60)
    try:
        import sounddevice as sd
        import numpy as np

        audio_array = np.frombuffer(pcm_data, dtype=np.int16)
        audio_array = audio_array.reshape(-1, 1)
        duration = len(audio_array) / 16000
        print(f"  Playing {duration:.2f}s of audio...")
        sd.play(audio_array, samplerate=16000)
        sd.wait()
        print("  ✅ Playback complete")
    except Exception as e:
        print(f"  ❌ FAILED: {e}")


# ── Main ────────────────────────────────────────────────────────────
async def main():
    print("🔍 Voice Agent Pipeline Diagnostics")
    print("=" * 60)

    # Test 1: Mic
    audio_bytes = test_microphone()
    if not audio_bytes:
        print("\n❌ Cannot proceed without microphone audio.")
        return

    # Test 2: STT REST
    transcript_rest = await test_stt_rest(audio_bytes)

    # Test 2b: STT WebSocket (this is what the agent actually uses)
    transcript_ws = await test_stt_websocket(audio_bytes)

    # Use whichever transcript worked
    transcript = transcript_ws or transcript_rest or "Hello, how are you?"
    if not transcript_ws and not transcript_rest:
        print("\n⚠️  Both STT methods failed. Using fallback text for LLM test.")

    # Test 3: LLM
    llm_response = test_llm(transcript)
    if not llm_response:
        llm_response = "Hello! I am doing well, thank you for asking."
        print("  Using fallback text for TTS test.")

    # Test 4: TTS
    pcm_data = await test_tts(llm_response)

    # Test 5: Playback
    if pcm_data:
        test_playback(pcm_data)
    else:
        print("\n⚠️  No TTS audio to play.")

    # Summary
    print("\n" + "=" * 60)
    print("📊 DIAGNOSIS SUMMARY")
    print("=" * 60)
    print(f"  Microphone:    {'✅' if audio_bytes else '❌'}")
    print(f"  STT REST:      {'✅' if transcript_rest else '❌'}")
    print(f"  STT WebSocket: {'✅' if transcript_ws else '❌'} ← used by agent")
    print(f"  LLM (Groq):    {'✅' if llm_response else '❌'}")
    print(f"  TTS (Sarvam):  {'✅' if pcm_data else '❌'}")
    print(f"  Playback:      {'✅' if pcm_data else '⏭️  skipped'}")

    if not transcript_ws:
        print("\n🔴 ROOT CAUSE: STT WebSocket is not returning transcripts.")
        print("   The agent's _listen() loop never gets text, so it never")
        print("   calls the LLM, and never speaks a response.")
        print("\n   Possible fixes:")
        print("   1. Check SARVAM_STT_MODEL — current:", os.getenv("SARVAM_STT_MODEL"))
        print("   2. Check SARVAM_API_KEY subscription/quota")
        print("   3. The receive_transcript() timeout (5s) may be blocking audio sends")


if __name__ == "__main__":
    asyncio.run(main())
