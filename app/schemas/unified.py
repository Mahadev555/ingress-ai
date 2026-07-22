from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class Message(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: str
    content: Optional[Any] = None


# Gateway-only request fields that must not be forwarded to providers.
GATEWAY_ONLY_FIELDS = {"fallbacks"}


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[Message]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    stream: bool = False
    # Ordered fallback models tried if the primary fails (gateway-only).
    fallbacks: Optional[list[str]] = None


class Choice(BaseModel):
    model_config = ConfigDict(extra="allow")

    index: int
    message: Message
    finish_reason: Optional[str] = None


class Usage(BaseModel):
    model_config = ConfigDict(extra="allow")

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: Optional[Usage] = None
