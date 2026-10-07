from __future__ import annotations

from typing import Any, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContentPart(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: str
    text: Optional[str] = None


class MemoryMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    role: str = "user"
    content: Union[str, List[Any]]
    timestamp: Optional[int] = None  # unix milliseconds

    def text(self) -> str:
        """Flatten multimodal content to text; images are dropped (textual track)."""
        if isinstance(self.content, str):
            return self.content
        parts: list[str] = []
        for part in self.content:
            if isinstance(part, dict) and part.get("type") == "text" and part.get("text"):
                parts.append(str(part["text"]))
        return "\n".join(parts)


class AddRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    request_id: str
    messages: List[MemoryMessage] = Field(min_length=1)
    user_id: str
    session_id: str

    @field_validator("request_id", "user_id", "session_id")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("identifier must not be blank")
        return value


class AddResponse(BaseModel):
    success: Literal[True] = True
    request_id: str
    user_id: str
    session_id: str


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    query: str
    options: Optional[List[str]] = None
    user_id: str
    top_k: int = Field(default=100, ge=1, le=1000)

    @field_validator("query", "user_id")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value


class MemoryResult(BaseModel):
    id: str
    content: str
    score: Optional[float] = None
    created_at: Optional[str] = None


class SearchResponse(BaseModel):
    data: List[MemoryResult]


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
