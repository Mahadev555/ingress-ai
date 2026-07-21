from pydantic import BaseModel

class UsageRecord(BaseModel):
    key_id: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: float
    latency_ms: int
