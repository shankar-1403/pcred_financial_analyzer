from pydantic import BaseModel,Field
from typing import Optional

class user_details(BaseModel):
    id:Optional[str] = Field(default=None, alias="_id")
    full_name:str
    email_id:str
    password:str
    role:str
    status:str
    created_at:Optional[str] = None
    created_by:Optional[str] = None
    updated_at:Optional[str] = None
    updated_by:Optional[str] = None
    model_config = {
        "populate_by_name": True
    }