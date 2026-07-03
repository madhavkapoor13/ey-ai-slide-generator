import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.llm.prompt_loader import initialize_prompts
from backend.routes import router

logging.basicConfig(level=logging.INFO)
initialize_prompts()

app = FastAPI(
    title="EY AI Slide Generator",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://localhost:3000",
        "https://127.0.0.1:3000",
    ],
    allow_credentials=False,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

app.include_router(router)

@app.get("/")
def home():
    return {"message": "EY AI Slide Generator API Running"}
