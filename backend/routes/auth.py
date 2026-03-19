from fastapi import APIRouter
from models.login import user_login,user_register
from mongodb import get_db
import bcrypt

router = APIRouter()

@router.post("/register")
def register(data:user_register):
    db = get_db()

    user_dict = data.model_dump()
    existing_user = db.users.find_one({"email_id":user_dict['email_id']},{"full_name":1,"_id":0})

    if(existing_user):
        return ({"message":"Email already registered","status":401})
    
    hashed_password = bcrypt.hashpw(user_dict["password"].encode("utf-8"),bcrypt.gensalt()) 
    user_dict["password"] = hashed_password
    result = db.users.insert_one(user_dict)
    
    if result:  
        return ({"email_id": user_dict["email_id"],"company_name":user_dict["full_name"],"message":"Registered successfully","status":200})
    else:
        return({"message":"Error while submitting details","status":401})


@router.post("/login")
def login(data:user_login):
    db = get_db()

    user_dict = data.model_dump()
    result = db.users.find_one({"email_id":user_dict["email_id"]},{"full_name":1,"password": 1,"_id":0})

    if not result:
        return({"message":"Invalid Credentials","status":401})

    if bcrypt.checkpw(user_dict['password'].encode("utf-8"),result["password"]):
        return ({"email_id": user_dict["email_id"],"company_name":result["full_name"],"message":"Logged in successfully","status":200})
    else:
        return({"message":"Invalid Credentials","status":401})