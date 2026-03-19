from fastapi import APIRouter
from fastapi.responses import JSONResponse
import requests
from datetime import datetime, timedelta

router = APIRouter()


def fetch_public_holidays(year: int):
    url = f"https://date.nager.at/api/v3/PublicHolidays/{year}/IN"

    try:
        response = requests.get(url, timeout=10)
        holidays = response.json()
    except Exception:
        holidays = []

    return [
        {
            "date": h["date"],
            "name": h["name"]
        }
        for h in holidays
    ]


def get_bank_weekend_holidays(year: int):
    holidays = []

    d = datetime(year, 1, 1)
    end = datetime(year, 12, 31)

    while d <= end:
        if d.weekday() == 6:
            holidays.append(d.strftime("%Y-%m-%d"))

        if d.weekday() == 5:
            week_of_month = (d.day - 1) // 7 + 1
            if week_of_month in [2, 4]:
                holidays.append(d.strftime("%Y-%m-%d"))

        d += timedelta(days=1)

    return holidays


@router.get("/bank-holidays/{year}")
def get_all_bank_holidays(year: int):

    public_holidays = fetch_public_holidays(year)
    weekend_holidays = get_bank_weekend_holidays(year)

    combined = {h["date"]: h["name"] for h in public_holidays}

    for d in weekend_holidays:
        combined.setdefault(d, "Bank Weekend")

    result = [
        {
            "date": datetime.strptime(k, "%Y-%m-%d").strftime("%d/%m/%Y"),
            "name": v
        }
        for k, v in sorted(combined.items())
    ]

    return result