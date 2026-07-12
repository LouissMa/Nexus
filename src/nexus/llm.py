from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Mapping


class LLMError(RuntimeError):
    """Raised when an LLM request cannot be completed."""


@dataclass(frozen=True)
class LLMConfig:
    api_key: str | None
    model: str = "gpt-4o-mini"
    base_url: str = "https://api.openai.com/v1"
    timeout_seconds: int = 30

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "LLMConfig":
        values = env or os.environ
        timeout = values.get("NEXUS_LLM_TIMEOUT_SECONDS", "30")
        return cls(
            api_key=values.get("NEXUS_LLM_API_KEY") or values.get("OPENAI_API_KEY"),
            model=values.get("NEXUS_LLM_MODEL", "gpt-4o-mini"),
            base_url=values.get("NEXUS_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            timeout_seconds=int(timeout),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


class OpenAICompatibleLLM:
    def __init__(self, config: LLMConfig):
        self.config = config

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        if not self.config.api_key:
            raise LLMError("LLM is not configured. Set NEXUS_LLM_API_KEY or OPENAI_API_KEY.")

        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.4,
            "max_tokens": 700,
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.config.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise LLMError(f"LLM request failed with HTTP {error.code}: {detail}") from error
        except urllib.error.URLError as error:
            raise LLMError(f"LLM request failed: {error.reason}") from error
        except TimeoutError as error:
            raise LLMError("LLM request timed out.") from error

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise LLMError(f"LLM response had an unexpected shape: {data}") from error

        return str(content).strip()
