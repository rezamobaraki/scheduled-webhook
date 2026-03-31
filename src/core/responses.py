from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T", bound=BaseModel)


class BaseResponse(BaseModel, Generic[T]):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True, validate_assignment=True)


class RetrieveResponse(BaseResponse, Generic[T]):
    data: T


class ErrorResponse(BaseResponse):
    error: str = Field(description="Error message")
    code: str = Field(description="Error code")
    details: dict[str, Any] | None = Field(default=None, description="Additional error details")