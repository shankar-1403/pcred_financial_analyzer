from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta, timezone
from fastapi import Form

class report_details(BaseModel):
    report_name:str
    reference_id:str
    status:str
    created_by:str

    @classmethod
    def as_form(
        cls,
        report_name: str = Form(...),
        reference_id: str = Form(...),
        status: str = Form(...),
        created_by: str = Form(...),
    ):
        return cls(
            report_name=report_name,
            reference_id=reference_id,
            status=status,
            created_by=created_by,
        )
    
class report_data(BaseModel):
    report_name:str

class report_data_delete(BaseModel):
    id:str
    report_name:str

class account_data(BaseModel):
    account_holder:str
    acc_type:str
    account_number:str
    bank_name:str
    branch:str
    currency:str
    customer_id:str
    ifsc:str
    joint_holder:str
    micr:str
    from_date:str
    to_date:str
    statement_request_date:str

class transaction_details(BaseModel):
    date:str
    cheque_ref:str
    description:str
    debit:str
    credit:str
    balance:str