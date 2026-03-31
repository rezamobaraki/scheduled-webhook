from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BaseResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
    )


class ErrorResponse(BaseResponse):
    error: str = Field(description="Error message")
    code: str = Field(description="Error code")
    details: list[dict[str, Any]] | None = Field(default=None, description="Additional error details")
