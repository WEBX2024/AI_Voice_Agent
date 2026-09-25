"""
VoiceAgent — the core LLM-driven agent.

Manages conversation history, loads prompts dynamically, and streams
chat completions from Groq. All conversational behaviour is driven by
the prompts/ directory, not by Python conditionals.
"""

import json
import logging
import time

from groq import Groq

from agent.config import Config
from agent.prompt_loader import assemble_system_prompt, load_prompts_from_directory

logger = logging.getLogger(__name__)


class VoiceAgent:
    """
    LLM-driven voice agent using Groq for inference.

    The agent loads all prompts from the prompts/ directory at startup,
    assembles them into a system prompt, maintains conversation history,
    and streams responses from the LLM.
    """

    def __init__(self, config: Config):
        self.config = config
        self.client = Groq(api_key=config.groq_api_key)
        self.primary_model = config.llm_primary_model
        self.fallback_model = config.llm_fallback_model

        # Load and assemble prompts
        raw_prompts = load_prompts_from_directory(config.prompts_dir)
        self.system_prompt = assemble_system_prompt(raw_prompts)
        logger.info(
            "System prompt assembled: %d characters from %d prompt files",
            len(self.system_prompt),
            len(raw_prompts),
        )

        # Conversation history: list of {"role": ..., "content": ...}
        self.history: list[dict[str, str]] = []

        # Conversation metadata
        self.start_time: float = time.time()
        self.turn_count: int = 0

    def reset(self):
        """Clear conversation history and start fresh."""
        self.history.clear()
        self.start_time = time.time()
        self.turn_count = 0
        logger.info("Conversation reset")

    def _build_messages(self, user_text: str, audio_metrics: dict | None = None) -> list[dict[str, str]]:
        """Build the full message list for the LLM call."""
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.history)
        
        if audio_metrics:
            context = {
                "user_speech": user_text,
                "audio_context": audio_metrics
            }
            content = json.dumps(context)
        else:
            content = user_text
            
        messages.append({"role": "user", "content": content})
        return messages

    def process_turn(self, user_text: str, audio_metrics: dict | None = None) -> str:
        """
        Process a single conversational turn (non-streaming).

        Sends the user's text to the LLM with full conversation history,
        system prompt, and audio metrics. Returns the agent's response text.
        """
        if not user_text.strip():
            return ""

        self.turn_count += 1
        logger.info("Turn %d — User: %s", self.turn_count, user_text[:100])

        messages = self._build_messages(user_text, audio_metrics)
        models_to_try = [self.primary_model, self.fallback_model]

        for model in models_to_try:
            try:
                completion = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=512,
                )

                response_text = completion.choices[0].message.content or ""
                agent_reply = self._extract_response_text(response_text)

                # Keep history clean of JSON wrapping for future turns
                self.history.append({"role": "user", "content": user_text})
                self.history.append({"role": "assistant", "content": response_text})

                logger.info("Turn %d — Agent: %s", self.turn_count, agent_reply[:100])
                return agent_reply

            except Exception as e:  # noqa: BLE001
                logger.warning("LLM error with model %s on turn %d: %s", model, self.turn_count, e)
                continue

        logger.error("All LLM models failed on turn %d", self.turn_count)
        return "I'm sorry, I'm having a technical issue right now. Could you repeat that?"

    def process_turn_streaming(self, user_text: str, audio_metrics: dict | None = None):
        """
        Process a turn with streaming. Yields text chunks as they arrive.
        Handles structured JSON extraction on the fly.
        
        Yields:
            ("text", str): A chunk of spoken text
            ("done", dict): The fully parsed JSON response at the end
        """
        if not user_text.strip():
            return

        self.turn_count += 1
        logger.info("Turn %d (streaming) — User: %s", self.turn_count, user_text[:100])

        messages = self._build_messages(user_text, audio_metrics)

        full_response = ""
        yielded_raw_length = 0
        
        import re
        # Regex to match the response_text value in the streaming JSON
        text_regex = re.compile(r'"response_text"\s*:\s*"((?:[^"\\]|\\.)*)')

        try:
            stream = self.client.chat.completions.create(
                model=self.primary_model,
                messages=messages,
                temperature=0.7,
                max_tokens=512,
                stream=True,
            )

            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    full_response += delta
                    
                    match = text_regex.search(full_response)
                    if match:
                        extracted = match.group(1)
                        if len(extracted) > yielded_raw_length:
                            new_raw = extracted[yielded_raw_length:]
                            yielded_raw_length = len(extracted)
                            
                            # Clean up JSON escapes for spoken text
                            clean_chunk = new_raw.replace('\\"', '"').replace('\\n', ' ')
                            if clean_chunk:
                                yield ("text", clean_chunk)

            # Update history with complete response
            self.history.append({"role": "user", "content": user_text})
            self.history.append({"role": "assistant", "content": full_response})
            logger.info("Turn %d (streaming) — complete (%d chars)", self.turn_count, len(full_response))
            
            parsed = self._parse_json_response(full_response)
            yield ("done", parsed)

        except Exception as e:  # noqa: BLE001
            logger.error("LLM streaming error on turn %d: %s", self.turn_count, e)
            yield ("text", "I'm sorry, I'm having a technical issue. Could you repeat that?")
            yield ("done", {})

    def generate_call_summary(self) -> dict:
        """
        Generate a structured call summary after the conversation ends.

        Uses the call_summary prompt and full conversation history.
        """
        if not self.history:
            return {"call_summary": {"summary": "No conversation took place."}}

        summary_prompt = (
            "Generate a structured JSON call summary for the conversation so far. "
            "Follow the call summary format from your instructions."
        )

        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.history)
        messages.append({"role": "user", "content": summary_prompt})

        try:
            completion = self.client.chat.completions.create(
                model=self.primary_model,
                messages=messages,
                temperature=0.3,
                max_tokens=1024,
            )

            raw = completion.choices[0].message.content or "{}"
            # Try to extract JSON from the response
            return self._parse_json_response(raw)

        except Exception as e:  # noqa: BLE001
            logger.error("Failed to generate call summary: %s", e)
            return {"error": str(e)}

    def _extract_response_text(self, raw_response: str) -> str:
        """
        Extract the spoken response text from the LLM output.

        If the LLM returns structured JSON (possibly wrapped in markdown
        code blocks), extract response_text. Otherwise, use the raw text as-is.
        """
        # Strip markdown code blocks if present
        cleaned = raw_response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        cleaned = cleaned.removesuffix("```")
        cleaned = cleaned.strip()

        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict) and "response_text" in parsed:
                return parsed["response_text"]
        except (json.JSONDecodeError, KeyError):
            pass

        return raw_response

    def _parse_json_response(self, raw: str) -> dict:
        """Attempt to parse a JSON response, handling markdown code blocks."""
        # Strip markdown code blocks if present
        cleaned = raw.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        cleaned = cleaned.removesuffix("```")
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("Could not parse JSON from LLM response")
            return {"raw_response": raw}
