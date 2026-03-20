from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.auth import router as auth_router
from routes.report.report import router as report_router
from routes.report.bank_account import router as bank_router
from routes.master.user import router as user_router
from routes.bank_holiday.bank_holiday import router as bank_holiday_router
from routes.master.role import router as role_router
from mongodb import connectDb
from contextlib import asynccontextmanager

app = FastAPI()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    connectDb()
    print("🚀 App started and DB connected")
    yield
    # Shutdown (optional)
    print("🛑 App shutting down")

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173","http://127.0.0.1:5173"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router,prefix="/auth")
app.include_router(report_router, prefix="/api")
app.include_router(user_router, prefix="/api")
app.include_router(role_router, prefix="/api")
app.include_router(bank_router, prefix="/api")
app.include_router(bank_holiday_router, prefix="/api")