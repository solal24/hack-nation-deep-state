"""Thin wrapper around the Claude API. Import `ask` / `ask_json` from anywhere in src/."""
import os

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()
MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5")
client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from .env


def ask(prompt: str, system: str = "You are a helpful assistant.", max_tokens: int = 16000) -> str:
    """Plain text answer."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in response.content if b.type == "text")


def ask_json(prompt: str, schema: type[BaseModel], system: str = "You are a helpful assistant.",
             model: str = None) -> BaseModel:
    """Answer validated against a Pydantic schema (structured outputs)."""
    response = client.messages.parse(
        model=model or MODEL,
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        output_format=schema,
    )
    return response.parsed_output


if __name__ == "__main__":
    class Idea(BaseModel):
        title: str
        one_liner: str

    print(ask("Say hi in five words."))
    print(ask_json("Give one AI hackathon idea.", Idea))
