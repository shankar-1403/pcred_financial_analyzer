from fastapi import APIRouter
from models.report.bank_account import bank_details
from mongodb import get_db

router = APIRouter()

@router.post("/reports/update-bank-details")
def create(data:bank_details):
    db = get_db()
    bank_dict = data.model_dump()
    report_name = bank_dict["report_name"]
    report_db = db.get_collection(report_name)
    statement_from = bank_dict.pop("statement_from", None)
    statement_to = bank_dict.pop("statement_to", None)
    
    bank_dict["statement_period"] = {
        "from": statement_from,
        "to": statement_to
    }
    result = report_db.update_one({"type": "account"},{"$set": bank_dict})
    
    if result:  
        return ({"message":"Report updated successfully","status":200})
    else:
        return({"message":"Error while submitting details","status":401})