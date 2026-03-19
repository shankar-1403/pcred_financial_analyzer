from pydantic import BaseModel
from typing import Optional

class bank_details(BaseModel):
    report_name:str
    type:str
    bank_name:Optional[str] = None
    acc_type:Optional[str] = None
    account_holder:Optional[str] = None
    account_number:Optional[str] = None
    analysis_from:Optional[str] = None
    analysis_to:Optional[str] = None
    statement_from:Optional[str] = None
    statement_to:Optional[str] = None
    account_opening_date:Optional[str] = None
    account_status:Optional[str] = None
    ifsc:Optional[str] = None
    micr:Optional[str] = None
    branch:Optional[str] = None
    branch_address:Optional[str] = None
    joint_holder:Optional[str] = None
    email_address:Optional[str] = None
    phone_no:Optional[str] = None
    pan:Optional[str] = None