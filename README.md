# AI Voice Agent

An open-source, LLM-driven AI voice calling agent. All conversational behaviour is controlled through prompts — Python serves only as a thin runtime and integration layer.

## Architecture

```
Microphone (sounddevice)
       ↓
Audio Enhancer (noisereduce + metrics)
       ↓
Streaming STT (Sarvam AI / Deepgram)
       ↓
Prompt-driven LLM Agent (Groq)
       ↓
Streaming TTS (Sarvam AI / Deepgram)
       ↓
Speaker (sounddevice)
```

The agent is designed around a **prompt-first architecture**: all conversational logic — personality, turn-taking, interruption handling, intent detection, information extraction — is defined in modular prompt files, not Python conditionals.

## Directory Structure

```
voice-agent/
├── main.py                  # CLI entry point
├── requirements.txt         # Python dependencies
├── .env                     # Environment variables (not committed)
├── .env.example             # Environment variable template
├── .gitignore               # Git ignore rules
│
├── agent/                   # Core agent logic
│   ├── __init__.py
│   ├── config.py            # Configuration loader (.env)
│   ├── agent.py             # VoiceAgent (Groq LLM, prompt loader, history)
│   ├── prompt_loader.py     # Dynamic prompt file discovery and assembly
│   └── runtime.py           # Async orchestrator (mic → STT → LLM → TTS → speaker)
│
├── voice/                   # Voice providers (STT, TTS, audio I/O)
│   ├── __init__.py
│   ├── stream.py            # sounddevice microphone/speaker manager
│   ├── enhancement.py       # Real-time noise suppression & audio metrics
│   ├── sarvam.py            # Sarvam AI STT + TTS (primary)
│   └── deepgram.py          # Deepgram STT + TTS (fallback)
│
├── prompts/                 # The brain — all agent behaviour lives here
│   ├── system/
│   │   └── personality.md   # Agent identity and communication style
│   ├── conversation/
│   │   ├── behaviour.md     # Turn-taking, pacing, flow
│   │   └── listening.md     # Active listening, silence handling
│   ├── interruption/
│   │   └── handler.md       # Interruption classification and response
│   ├── reasoning/
│   │   ├── context.md       # Context maintenance and relevance
│   │   └── intent.md        # User intent detection
│   ├── task/
│   │   └── execution.md     # Goal-oriented task execution
│   ├── tools/
│   │   └── selection.md     # When and how to invoke tools
│   ├── extraction/
│   │   └── information.md   # Structured info extraction
│   ├── summary/
│   │   └── call_summary.md  # Post-call summary generation
│   └── output/
│       └── structured.md    # Structured JSON output format
│
├── storage/                 # Data persistence
│   ├── __init__.py
│   └── json_store.py        # Lightweight JSON file storage
│
├── tools/                   # Agent tools (callable functions)
│   ├── __init__.py
│   └── registry.py          # Tool registration and execution
│
├── data/                    # Runtime data (call summaries, etc.)
│   └── .gitkeep
│
└── api/                     # API layer (reserved for future use)
```

## Setup

### 1. Clone and Navigate

```bash
cd voice-agent
```

### 2. Create Virtual Environment

```bash
python -m venv .venv
```

Activate it:

```bash
# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

**Note:** `sounddevice` requires PortAudio, which is bundled in its pre-built wheels for Windows and macOS. On Linux, install it separately:

- **Linux:** `sudo apt-get install libportaudio2`

### 4. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and fill in your API keys:

```env
SARVAM_API_KEY=your_key_here
DEEPGRAM_API_KEY=your_key_here
GROQ_API_KEY=your_key_here
```

### 5. Run

```bash
python main.py
```

The agent will start listening on your microphone. Speak naturally and it will respond through your speakers.

Press `Ctrl+C` to end the conversation. A call summary will be generated and saved to `data/calls/`.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SARVAM_API_KEY` | (required) | Sarvam AI API subscription key |
| `DEEPGRAM_API_KEY` | (required) | Deepgram API key |
| `GROQ_API_KEY` | (required) | Groq API key |
| `STT_PROVIDER` | `sarvam` | STT provider: `sarvam` or `deepgram` |
| `TTS_PROVIDER` | `sarvam` | TTS provider: `sarvam` or `deepgram` |
| `LLM_PRIMARY_MODEL` | `openai/gpt-oss-120b` | Primary Groq model |
| `LLM_FALLBACK_MODEL` | `qwen/qwen3.6-27b` | Fallback Groq model |
| `SARVAM_STT_MODEL` | `saaras:v4-realtime` | Sarvam STT model |
| `SARVAM_TTS_MODEL` | `bulbul:v3` | Sarvam TTS model |
| `SARVAM_TTS_SPEAKER` | `meera` | Sarvam TTS voice |
| `SARVAM_LANGUAGE_CODE` | `en-IN` | Sarvam language |
| `DEEPGRAM_STT_MODEL` | `nova-3` | Deepgram STT model |
| `DEEPGRAM_TTS_MODEL` | `aura-asteria-en` | Deepgram TTS voice |
| `DEEPGRAM_LANGUAGE` | `en-US` | Deepgram language |
| `AUDIO_SAMPLE_RATE` | `16000` | Audio sample rate in Hz |
| `AUDIO_CHANNELS` | `1` | Audio channels (mono) |
| `AUDIO_CHUNK_MS` | `100` | Audio chunk duration in ms |
| `LOG_LEVEL` | `INFO` | Logging level |

## How the Agent Works

### Voice Pipeline

1. **Audio Capture:** `sounddevice` captures microphone audio in chunks (100ms default) via a callback. Chunks are passed through the `AudioEnhancer` to reduce noise and extract metrics.

2. **Speech-to-Text:** Clean audio chunks are streamed to the STT provider (Sarvam or Deepgram) via WebSocket. The provider returns interim (partial) and final (stable) transcripts.

3. **Turn Detection:** The runtime monitors silence duration after speech is detected. When the user stops speaking (1.5s silence), the accumulated transcript and audio metrics are sent to the LLM.

4. **LLM Processing:** The VoiceAgent sends the full conversation history plus the assembled system prompt to Groq. If the primary model fails, it automatically falls back to the secondary model.

5. **Text-to-Speech:** The LLM response is sent to the TTS provider, which returns audio data.

6. **Playback:** Audio is played through the speaker via PyAudio.

### LLM Pipeline

- All prompts are loaded from the `prompts/` directory at startup by `agent/prompt_loader.py`.
- Prompts are assembled in a defined category order (system → conversation → interruption → reasoning → task → tools → extraction → summary → output).
- The full system prompt + conversation history is sent to Groq on every turn.
- The agent supports both streaming and non-streaming LLM calls.

### Interruption Handling

Interruption logic is defined entirely in `prompts/interruption/handler.md`. The prompt instructs the LLM to classify interruptions (correction, topic change, agreement, urgency, noise) and respond appropriately. At the audio level, the `AudioStream` class supports interrupting playback by draining the output queue.

### Conversation State

Conversation state is maintained as a list of `{role, content}` messages in the `VoiceAgent`. This history is sent to the LLM on every turn, giving it full context. When the conversation ends, the agent generates a structured JSON call summary.

### Tool Architecture

Tools are registered in `tools/registry.py`. Each tool has a name, description, and callable function. The LLM decides when to use tools based on `prompts/tools/selection.md`. Tool results are fed back to the LLM for natural-language interpretation.

To add a new tool:
1. Create a function in `tools/`.
2. Register it with `ToolRegistry.register(name, description, func)`.
3. The LLM will automatically discover it through the tool description prompt.

### Storage Architecture

`storage/json_store.py` provides a lightweight JSON file-based store with `read_all`, `write_all`, `append`, and `find` methods. Each "collection" is a JSON file. This can be replaced by a database later — just implement the same interface.

## Prompt Architecture

The `prompts/` directory is the brain of the system. Prompts are modular `.md` files organized by category:

| Category | Purpose |
|---|---|
| `system/` | Agent identity, personality, communication style |
| `conversation/` | Turn-taking, pacing, listening behaviour |
| `interruption/` | Classifying and responding to interruptions |
| `reasoning/` | Context tracking, intent detection |
| `task/` | Goal-oriented task execution |
| `tools/` | When and how to invoke tools |
| `extraction/` | Structured information extraction |
| `summary/` | Post-call summary generation |
| `output/` | Structured JSON output schema |

### How to Add or Change Prompts

1. Create or edit a `.md` file in the appropriate `prompts/` subdirectory.
2. Restart the agent. Prompts are loaded at startup.
3. The prompt loader discovers all `.md` files recursively.
4. New categories (subdirectories) are automatically picked up.

### How to Add a New Task

1. Define the task objective and required information in a new prompt file (e.g., `prompts/task/appointment_scheduling.md`).
2. The agent will incorporate the task instructions into its system prompt.
3. No Python code changes are needed for new conversational tasks.

## Provider Replacement

### How to Replace Sarvam

1. Create a new provider file in `voice/` (e.g., `voice/my_provider.py`).
2. Implement classes with the same interface as `SarvamSTT` / `SarvamTTS`:
   - `connect()`, `send_audio()`, `receive_transcript()`, `close()` for STT
   - `connect()`, `synthesize()`, `synthesize_streaming()`, `close()` for TTS
3. Add the provider to `agent/runtime.py` initialization logic.
4. Set `STT_PROVIDER` / `TTS_PROVIDER` in `.env`.

### How to Configure Deepgram Fallback

Set in `.env`:
```env
STT_PROVIDER=deepgram
TTS_PROVIDER=deepgram
```

Or use Sarvam for one and Deepgram for the other:
```env
STT_PROVIDER=sarvam
TTS_PROVIDER=deepgram
```

### How to Add Telephony (Future)

The architecture supports adding a telephony layer without redesigning the agent:

1. Create a telephony adapter (e.g., `voice/twilio.py`) that converts phone audio streams to the same format the runtime expects.
2. Replace `AudioStream` (local mic/speaker) with the telephony adapter.
3. The STT → LLM → TTS pipeline remains unchanged.

## Current Limitations

- **No telephony:** Currently local microphone/speaker only. No paid telephony provider is integrated.
- **No frontend:** CLI-only. React/Vite frontend is planned for v2.
- **No persistent database:** Uses JSON file storage. Database integration is planned.
- **REST TTS in v1:** The runtime currently uses REST-based TTS for reliability. Streaming TTS (lower latency) is supported by the provider modules but not yet wired into the main loop.
- **Single-threaded LLM:** LLM inference is synchronous per turn. Streaming LLM → streaming TTS pipeline is available but not yet the default path.
- **No mock data:** Storage interfaces are ready but no data is pre-loaded. Data will be provided separately.

## Development Workflow

1. Make prompt changes in `prompts/` — no code changes needed.
2. Make provider changes in `voice/` — implement the provider interface.
3. Make agent logic changes in `agent/` — keep it thin, push behaviour to prompts.
4. Add tools in `tools/` — register with `ToolRegistry`.
5. Test locally: `python main.py`.

## Troubleshooting

| Issue | Solution |
|---|---|
| `GROQ_API_KEY is not set` | Check your `.env` file has the key set |
| PyAudio installation fails | Install PortAudio first (see Setup section) |
| No audio input detected | Check microphone permissions and default device |
| STT returns empty transcripts | Verify API key, check network, try Deepgram fallback |
| High latency responses | Check network latency to provider APIs, try Deepgram |
| `ModuleNotFoundError` | Ensure venv is activated and deps installed |
#   A I _ V o i c e _ A g e n t  
 