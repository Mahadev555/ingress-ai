from fastapi import FastAPI
from app.api import chat

app = FastAPI(title="Ingress AI Gateway")

app.include_router(chat.router, prefix="/v1")
