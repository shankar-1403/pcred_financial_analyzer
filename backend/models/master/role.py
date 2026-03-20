from pydantic import BaseModel,Field
from typing import Optional

class role_details(BaseModel):
    id:Optional[str] = Field(default=None, alias="_id")
    role_name:str