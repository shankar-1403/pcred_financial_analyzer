from fastapi import APIRouter
from bson import ObjectId
from models.master.user import user_details
from mongodb import get_db

router = APIRouter()

@router.post("/users")
def get():
    db = get_db()
    result = list(db.users.find({},{"password":0}))
    for item in result:
        item["_id"] = str(item["_id"])

    if result:  
        return ({"result":result,"message":"Data fetched successfully","status":200})
    else:
        return({"message":"No data found","status":401})
    

@router.post("/users-update")
def post(data:user_details):
    db = get_db()
    user_dict = data.model_dump(by_alias=True)
    user_id = user_dict.get("_id")
    if user_id:
        user_dict.pop("_id", None)
        updated_user = db.users.find_one_and_update(
            {"_id": ObjectId(user_id)},
            {"$set": user_dict},
        )
        if updated_user:
            return {
                "message": "User updated successfully",
                "status": 200
            }

        return {"message": "User not found", "status": 404}
    else:
        db.users.insert_one(user_dict)
        return {
            "message": "User added successfully",
            "status": 200
        }