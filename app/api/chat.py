from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.schemas.unified import ChatCompletionRequest, ChatCompletionResponse

router = APIRouter()

@router.post("/chat/completions")
async def create_chat_completion(request: ChatCompletionRequest):
    # TODO: wire through auth, routing, provider adapters, and normalization
    return JSONResponse({"message": "gateway skeleton", "request": request.dict()})
