from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=5000)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=64)
    agent_id: Literal[
        "requirement-pre-review",
        "ai-test-analysis",
        "accounting-expert",
        "business-analyst",
        "ai-assistant",
    ]
    file_ids: list[Annotated[str, Field(min_length=1, max_length=64)]] = Field(
        default_factory=list, max_length=5
    )
    client_message_id: str = Field(
        default_factory=lambda: f"client_{uuid4().hex}", min_length=1, max_length=128
    )

    @field_validator("conversation_id", mode="before")
    @classmethod
    def empty_conversation_is_none(cls, value):
        return value or None

    @field_validator("file_ids")
    @classmethod
    def unique_file_ids(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class WorkflowRequest(BaseModel):
    """测试用例工作流专用请求，不向前端暴露聊天 Agent 路由字段。"""

    model_config = ConfigDict(str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=5000)
    client_message_id: str = Field(
        default_factory=lambda: f"client_{uuid4().hex}", min_length=1, max_length=128
    )


class ChatResponse(BaseModel):
    answer: str
    conversation_id: str
    message_id: int


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    conversation_id: str = Field(min_length=1, max_length=64)
    approval_id: str = Field(min_length=1, max_length=128)
    decision: Literal["approve", "reject", "revise"]
    reason: str = Field(default="", max_length=500)


class ApprovalResponse(BaseModel):
    ok: bool


class HealthResponse(BaseModel):
    status: str
