from pymongo import MongoClient

MONGODB_URI = "mongodb://localhost:27017/"
DB_NAME = "pcred_financial"

client = None
db = None

def connectDb():
    global client, db
    
    if not MONGODB_URI:
        raise ValueError("MONGODB_URI environment variable not set.")
    
    client = MongoClient(MONGODB_URI)
    db = client[DB_NAME]

    if "init_collection" not in db.list_collection_names():
        db.init_collection.insert_one({"status": "initialized"})

    print("✅ MongoDB Connected")

def get_db():
    return db