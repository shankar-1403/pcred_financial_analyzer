from fastapi import APIRouter, UploadFile, File, Depends
from models.report.report import report_details,report_data,report_data_delete
from apscheduler.schedulers.background import BackgroundScheduler
from mongodb import get_db
import shutil
import os
from parser import parse_bank_statement
from datetime import datetime, timedelta, timezone
from bson import ObjectId

router = APIRouter()

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@router.post("/reports/create-new")
def create(data: report_details = Depends(report_details.as_form),file: UploadFile = File(...)):
    db = get_db()
    report_dict = data.model_dump()
    report_name = report_dict["report_name"]

    folder_path = os.path.join(UPLOAD_FOLDER, report_name)

    os.makedirs(folder_path, exist_ok=True)

    file_path = os.path.join(folder_path, file.filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    parsed_data = parse_bank_statement(file_path)

    report_name = report_dict["report_name"]
    account_details = parsed_data["account"]
    transactions = parsed_data["transactions"]

    report_dict["file_path"] = file_path
    report_dict["created_at"] = datetime.now(timezone.utc)
    report_dict["active"] = 90 - (datetime.now(timezone.utc) - report_dict["created_at"]).days
    result = db.reports.insert_one(report_dict)
    collection = db[report_name]
    account_details["type"] = "account"
    collection.insert_one(account_details)

    for txn in transactions:
        txn["type"] = "transaction"

    collection.insert_many(transactions)

    
    if result:  
        return {"message": "New Report created successfully","status": 200}
    else:
        return {"message":"Error while submitting details","status":401}


@router.post("/reports")
def get():
    db = get_db()
    result = list(db.reports.find())
    for report in result:
        created_at = report["created_at"]
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if report.get("status") == "deleted":
            report["active"] = 0
        else:
            active_days = 90 - (datetime.now(timezone.utc) - created_at).days
            report["active"] = max(active_days, 0)
    for item in result:
        item["_id"] = str(item["_id"])

    if result:  
        return ({"result":result,"message":"Data fetched successfully","status":200})
    else:
        return({"message":"No data found","status":401})
    
@router.post("/report_view")
def post(data:report_data):
    db = get_db()
    report_dict = data.model_dump()
    report_name = report_dict["report_name"]
    collection = db.get_collection(report_name)

    account = collection.find_one({"type":"account"})
    transaction = list(collection.find({"type":"transaction"}))

    if account:
        account["_id"] = str(account["_id"])

    for item in transaction:
        item["_id"] = str(item["_id"])
        
    if account and transaction:  
        return ({"account":account,"transaction":transaction,"message":"Data fetched successfully","status":200})
    else:
        return({"message":"No data found","status":401})


def delete_old_report():
    db = get_db()
    expiry_date = datetime.now(timezone.utc) - timedelta(days=90)

    old_report = db.reports.find({
        "created_at": {"$lt":expiry_date},
        "status": {"$ne": "deleted"},
        "active": {"$gt": 0}
    })

    for report in old_report:
        report_name = report["report_name"]
        # Drop DB Collection
        db[report_name].drop()

        # Delete Uploaded File
        folder_path = os.path.join(UPLOAD_FOLDER, report_name)
        if os.path.exists(folder_path):
            shutil.rmtree(folder_path)

        # Update report status
        db.reports.update_one({"_id": report["_id"]},{"$set": {"status": "deleted","active": 0}})
scheduler = BackgroundScheduler()
scheduler.add_job(delete_old_report,"interval",hours=24)
scheduler.start()


@router.post("/report-delete")
def delete_report(data:report_data_delete):
    db = get_db()
    report_dict = data.model_dump()
    report_name = report_dict["report_name"]
    # Drop DB Collection
    db[report_name].drop()

    # Delete Uploaded File
    folder_path = os.path.join(UPLOAD_FOLDER, report_name)
    if os.path.exists(folder_path):
        shutil.rmtree(folder_path)

    result = db.reports.update_one({"_id": ObjectId(report_dict["id"])},{"$set": {"status": "deleted","active": 0}})

    # Update report status
    if result.modified_count > 0:
        return ({"message":"Report deleted successfully","status":200})
    else:
        return ({"message":"Error while deleting report","status":401})