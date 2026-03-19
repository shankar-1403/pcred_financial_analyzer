import mongoose from "mongoose";

const mongodb_uri = import.meta.env.MONGODB_URI;

if(!mongodb_uri){
    throw new Error("ERROR");
}

export async function connectDB() {
  try{
    await mongoose.connect(mongodb_uri)
  }catch(error){
    console.log(error);
  }
}