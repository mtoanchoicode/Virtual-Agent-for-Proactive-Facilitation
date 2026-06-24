from typing import Optional
from pydantic import BaseModel

class ChatRequest(BaseModel):
    message: Optional[str] = None
