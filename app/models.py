from __future__ import annotations

from typing import Any, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _require_text(name: str, value: str) -> str:
    if not value or not value.strip():
        raise ValueError(f"{name} must contain at least one non-whitespace character")
    return value


class MemoryMessage(BaseModel):
    """One turn of the source conversation. `content` may be a string or a list of content parts;
    only text parts are kept (textual track), image parts are dropped."""
    model_config = ConfigDict(extra="ignore")
    role: str = "user"
    content: Union[str, List[Any]]
    timestamp: Optional[int] = None  # unix milliseconds, optional per the contract

    def text(self) -> str:
        if isinstance(self.content, str):
            return self.content
        pieces = [str(p.get("text")) for p in self.content
                  if isinstance(p, dict) and p.get("type") == "text" and p.get("text")]
        return "\n".join(pieces)


class AddRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    request_id: str
    messages: List[MemoryMessage] = Field(min_length=1)
    user_id: str
    session_id: str

    @field_validator("request_id")
    @classmethod
    def _rid(cls, v: str) -> str:
        return _require_text("request_id", v)

    @field_validator("user_id")
    @classmethod
    def _uid(cls, v: str) -> str:
        return _require_text("user_id", v)

    @field_validator("session_id")
    @classmethod
    def _sid(cls, v: str) -> str:
        return _require_text("session_id", v)


class AddResponse(BaseModel):
    success: bool = True
    request_id: str
    user_id: str
    session_id: str


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    query: str
    options: Optional[List[str]] = None
    user_id: str
    top_k: int = Field(default=100, ge=1, le=1000)

    @field_validator("query")
    @classmethod
    def _q(cls, v: str) -> str:
        return _require_text("query", v)

    @field_validator("user_id")
    @classmethod
    def _uid(cls, v: str) -> str:
        return _require_text("user_id", v)


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
