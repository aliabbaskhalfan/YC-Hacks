from __future__ import annotations

import asyncio
import base64
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


@dataclass(slots=True)
class Transcript:
    text: str
    words: list[dict[str, Any]]
    provider: str


def has_standard_aws_credentials() -> bool:
    """Return whether an AWS SigV4 credential source is configured locally."""
    try:
        import boto3

        credentials = boto3.Session().get_credentials()
        return bool(credentials and credentials.access_key and credentials.secret_key)
    except Exception:
        return False


class NovaSonicTranscriber:
    """Transcribe a finite audio clip through Nova 2 Sonic's bidi API."""

    def __init__(self, region: str, model_id: str) -> None:
        self.region = region
        self.model_id = model_id

    def _client(self) -> Any:
        import boto3

        from aws_sdk_bedrock_runtime.client import BedrockRuntimeClient
        from aws_sdk_bedrock_runtime.config import Config
        from smithy_aws_core.identity.static import StaticCredentialsResolver

        credentials = boto3.Session().get_credentials()
        if credentials is None:
            raise RuntimeError(
                "Nova Sonic requires standard AWS credentials; Bedrock bearer API keys "
                "do not support InvokeModelWithBidirectionalStream"
            )
        frozen = credentials.get_frozen_credentials()

        config = Config(
            endpoint_uri=f"https://bedrock-runtime.{self.region}.amazonaws.com",
            region=self.region,
            aws_access_key_id=frozen.access_key,
            aws_secret_access_key=frozen.secret_key,
            aws_session_token=frozen.token,
            aws_credentials_identity_resolver=StaticCredentialsResolver(),
        )
        return BedrockRuntimeClient(config=config)

    @staticmethod
    async def _pcm(audio_path: str) -> bytes:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-v",
            "error",
            "-i",
            audio_path,
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-ac",
            "1",
            "-ar",
            "16000",
            "pipe:1",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            message = stderr.decode("utf-8", errors="replace").strip()[-500:]
            raise RuntimeError(f"ffmpeg could not decode the audio clip: {message}")
        if not stdout:
            raise RuntimeError("The uploaded audio clip contained no decodable audio")
        return stdout

    @staticmethod
    async def _send(stream: Any, payload: dict[str, Any]) -> None:
        from aws_sdk_bedrock_runtime.models import (
            BidirectionalInputPayloadPart,
            InvokeModelWithBidirectionalStreamInputChunk,
        )

        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        event = InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(bytes_=body)
        )
        await stream.input_stream.send(event)

    @staticmethod
    async def _collect(stream: Any, completed: asyncio.Event) -> list[str]:
        transcripts: list[str] = []
        current_role = ""
        while True:
            try:
                output = await stream.await_output()
                result = await output[1].receive()
            except (StopAsyncIteration, EOFError):
                break
            value = getattr(result, "value", None)
            raw = getattr(value, "bytes_", None)
            if not raw:
                if "Exception" in type(result).__name__:
                    message = getattr(value, "message", None) or type(result).__name__
                    raise RuntimeError(f"Nova Sonic stream failed: {message}")
                continue
            payload = json.loads(raw.decode("utf-8"))
            event = payload.get("event", {})
            if start := event.get("contentStart"):
                current_role = str(start.get("role", ""))
            elif text := event.get("textOutput"):
                if current_role == "USER":
                    content = str(text.get("content", "")).strip()
                    if content:
                        transcripts.append(content)
            elif event.get("contentEnd"):
                if current_role == "USER":
                    completed.set()
        return transcripts

    async def transcribe(self, audio_path: str) -> Transcript:
        from aws_sdk_bedrock_runtime.client import (
            InvokeModelWithBidirectionalStreamOperationInput,
        )

        pcm = await self._pcm(audio_path)
        stream = await self._client().invoke_model_with_bidirectional_stream(
            InvokeModelWithBidirectionalStreamOperationInput(model_id=self.model_id)
        )
        prompt_name = str(uuid.uuid4())
        system_name = str(uuid.uuid4())
        audio_name = str(uuid.uuid4())
        completed = asyncio.Event()
        collector = asyncio.create_task(self._collect(stream, completed))

        try:
            await self._send(
                stream,
                {
                    "event": {
                        "sessionStart": {
                            "inferenceConfiguration": {
                                "maxTokens": 256,
                                "topP": 0.9,
                                "temperature": 0.1,
                            }
                        }
                    }
                },
            )
            await self._send(
                stream,
                {
                    "event": {
                        "promptStart": {
                            "promptName": prompt_name,
                            "textOutputConfiguration": {"mediaType": "text/plain"},
                            "audioOutputConfiguration": {
                                "mediaType": "audio/lpcm",
                                "sampleRateHertz": 24000,
                                "sampleSizeBits": 16,
                                "channelCount": 1,
                                "voiceId": "matthew",
                                "encoding": "base64",
                                "audioType": "SPEECH",
                            },
                        }
                    }
                },
            )
            await self._send(
                stream,
                {
                    "event": {
                        "contentStart": {
                            "promptName": prompt_name,
                            "contentName": system_name,
                            "type": "TEXT",
                            "interactive": False,
                            "role": "SYSTEM",
                            "textInputConfiguration": {"mediaType": "text/plain"},
                        }
                    }
                },
            )
            await self._send(
                stream,
                {
                    "event": {
                        "textInput": {
                            "promptName": prompt_name,
                            "contentName": system_name,
                            "content": (
                                "Accurately transcribe the user's repair note. Preserve technical "
                                "terms, identifiers, measurements, and uncertainty. Do not invent details."
                            ),
                        }
                    }
                },
            )
            await self._send(
                stream,
                {
                    "event": {
                        "contentEnd": {
                            "promptName": prompt_name,
                            "contentName": system_name,
                        }
                    }
                },
            )
            await self._send(
                stream,
                {
                    "event": {
                        "contentStart": {
                            "promptName": prompt_name,
                            "contentName": audio_name,
                            "type": "AUDIO",
                            "interactive": True,
                            "role": "USER",
                            "audioInputConfiguration": {
                                "mediaType": "audio/lpcm",
                                "sampleRateHertz": 16000,
                                "sampleSizeBits": 16,
                                "channelCount": 1,
                                "audioType": "SPEECH",
                                "encoding": "base64",
                            },
                        }
                    }
                },
            )
            for offset in range(0, len(pcm), 3200):
                chunk = base64.b64encode(pcm[offset : offset + 3200]).decode("ascii")
                await self._send(
                    stream,
                    {
                        "event": {
                            "audioInput": {
                                "promptName": prompt_name,
                                "contentName": audio_name,
                                "content": chunk,
                            }
                        }
                    },
                )
                await asyncio.sleep(0.01)
            await self._send(
                stream,
                {
                    "event": {
                        "contentEnd": {
                            "promptName": prompt_name,
                            "contentName": audio_name,
                        }
                    }
                },
            )
            completion_wait = asyncio.create_task(completed.wait())
            done, _ = await asyncio.wait(
                {completion_wait, collector},
                timeout=30,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if collector in done:
                collector.result()
            if completion_wait not in done:
                raise TimeoutError("Nova Sonic did not complete transcription within 30 seconds")
        finally:
            try:
                await self._send(stream, {"event": {"promptEnd": {"promptName": prompt_name}}})
                await self._send(stream, {"event": {"sessionEnd": {}}})
                await stream.input_stream.close()
            except Exception:
                pass

        try:
            parts = await asyncio.wait_for(collector, timeout=5)
        except TimeoutError:
            collector.cancel()
            parts = []
        text = " ".join(parts).strip()
        if not text:
            raise RuntimeError("Nova Sonic returned no user transcript for the audio clip")
        return Transcript(text=text, words=[], provider="amazon-nova-2-sonic")


class SpeechToText:
    def __init__(
        self,
        deepgram_api_key: str | None,
        bedrock_enabled: bool = False,
        aws_region: str = "us-east-1",
        bedrock_model_id: str = "amazon.nova-2-sonic-v1:0",
    ) -> None:
        self.deepgram_api_key = deepgram_api_key
        self.nova = (
            NovaSonicTranscriber(aws_region, bedrock_model_id)
            if bedrock_enabled
            else None
        )

    async def transcribe(self, audio_path: str, content_type: str | None = None) -> Transcript:
        if self.nova:
            return await self.nova.transcribe(audio_path)
        if not self.deepgram_api_key:
            raise RuntimeError(
                "Audio capture requires AWS_BEARER_TOKEN_BEDROCK; use the text fallback meanwhile"
            )
        audio = Path(audio_path).read_bytes()
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://api.deepgram.com/v1/listen?model=nova-3&smart_format=true&punctuate=true",
                headers={
                    "Authorization": f"Token {self.deepgram_api_key}",
                    "Content-Type": content_type or "audio/webm",
                },
                content=audio,
            )
            response.raise_for_status()
        alternative = response.json()["results"]["channels"][0]["alternatives"][0]
        return Transcript(
            text=alternative.get("transcript", "").strip(),
            words=alternative.get("words", []),
            provider="deepgram",
        )
