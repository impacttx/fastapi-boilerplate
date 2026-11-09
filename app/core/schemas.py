from typing import Literal

from pydantic import BaseModel, Field


class MessageResponse(BaseModel):
    message: str = Field(
        ...,
        title="Message",
        description="A message describing the result of an operation",
        examples=[
            "Operation completed successfully.",
            "An error occurred while processing your request.",
        ],
    )
    status: Literal["info", "warning", "error", "success"] = Field(
        default="info",
        title="Status",
        description="The status or category of the message",
    )


class ImageUploadedResponse(BaseModel):
    message: str
    image_url: str
