from fastapi import APIRouter
from bson import ObjectId
from models.master.user import user_details
from mongodb import get_db
import bcrypt

router = APIRouter()

@router.post("/users")
def get():
    db = get_db()
    result = list(db.users.aggregate([
        {
            "$addFields": {
                "role_obj_id": {"$toObjectId": "$role"}
            }
        },
        {
            "$lookup": {
                "from": "roles",
                "localField": "role_obj_id",
                "foreignField": "_id",
                "as": "role_details"
            }
        },
        {"$unwind": {"path": "$role_details", "preserveNullAndEmptyArrays": True}},
        {
            "$project": {
                "_id": 1,
                "full_name": 1,
                "email_id": 1,
                "created_at": 1,
                "created_by": 1,
                "status": 1,
                "updated_at": 1,
                "updated_by": 1,
                "role": {
                    "id": {"$toString": "$role_details._id"},
                    "role_name": "$role_details.role_name"
                } 
            }
        },
    ]))
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
    hashed_password = bcrypt.hashpw(user_dict["password"].encode("utf-8"),bcrypt.gensalt())
    user_dict["password"] = hashed_password
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
        user_dict.pop("_id", None)
        db.users.insert_one(user_dict)
        return {
            "message": "User added successfully",
            "status": 200
        }