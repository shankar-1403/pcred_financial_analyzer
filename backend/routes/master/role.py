from fastapi import APIRouter
from bson import ObjectId
from models.master.role import role_details
from mongodb import get_db

router = APIRouter()

@router.post("/roles")
def get():
    db = get_db()
    result = list(db.roles.find())
    for item in result:
        item["_id"] = str(item["_id"])

    if result:  
        return ({"result":result,"message":"Data fetched successfully","status":200})
    else:
        return({"message":"No data found","status":401})
    

@router.post("/role-update")
def post(data:role_details):
    db = get_db()
    role_dict = data.model_dump(by_alias=True)
    role_id = role_dict.get("_id")
    if role_id:
        role_dict.pop("_id", None)
        updated_role = db.roles.find_one_and_update(
            {"_id": ObjectId(role_id)},
            {"$set": role_dict},
        )
        if updated_role:
            return {
                "message": "Role updated successfully",
                "status": 200
            }

        return {"message": "Role not found", "status": 404}
    else:
        role_dict.pop("_id", None)
        db.roles.insert_one(role_dict)
        return {
            "message": "Role added successfully",
            "status": 200
        }