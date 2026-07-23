from typing import Any, Union

from pydantic import BaseModel, ConfigDict


class EmbeddingRequest(BaseModel):
    """OpenAI-compatible embeddings request. Extra fields (encoding_format,
    dimensions, user, ...) are passed through to the provider unchanged."""

    model_config = ConfigDict(extra="allow")

    model: str
    input: Union[str, list[str], list[int], list[list[int]]]
