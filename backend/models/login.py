from pydantic import BaseModel
from typing import Optional

class user_login(BaseModel):
    email_id:str
    password:str

class user_register(BaseModel):
    full_name:str
    email_id:str
    password:str