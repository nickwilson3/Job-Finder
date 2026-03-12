"""LinkedIn session management — li_at token flow."""
import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from web.auth import get_current_user
from web.database import get_db
from web.models import User
from web.storage import inputs_dir

router = APIRouter()


@router.post("/linkedin/save-token")
async def save_token(request: Request, db: Session = Depends(get_db)):
    user: User = get_current_user(request, db)

    body = await request.json()
    li_at = body.get("li_at", "").strip()
    jsessionid = body.get("jsessionid", "").strip()
    bcookie = body.get("bcookie", "").strip()
    bscookie = body.get("bscookie", "").strip()
    if not li_at or not jsessionid or not bcookie or not bscookie:
        return JSONResponse({"detail": "li_at, JSESSIONID, bcookie, and bscookie are all required."}, status_code=400)

    cookies = [
        {"name": "li_at",      "value": li_at,      "domain": ".linkedin.com",     "path": "/", "httpOnly": True,  "secure": True, "sameSite": "None"},
        {"name": "JSESSIONID", "value": jsessionid, "domain": ".www.linkedin.com", "path": "/", "httpOnly": True,  "secure": True, "sameSite": "None"},
        {"name": "bcookie",    "value": bcookie,    "domain": ".linkedin.com",     "path": "/", "httpOnly": False, "secure": True, "sameSite": "None"},
        {"name": "bscookie",   "value": bscookie,   "domain": ".www.linkedin.com", "path": "/", "httpOnly": True,  "secure": True, "sameSite": "None"},
    ]

    session_path = inputs_dir(user.id) / "linkedin_session.json"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(json.dumps(cookies, indent=2))

    user.linkedin_session_expires_at = datetime.utcnow() + timedelta(days=14)
    db.commit()

    return JSONResponse({"status": "saved"})


@router.get("/linkedin/status")
def linkedin_status(request: Request, db: Session = Depends(get_db)):
    user: User = get_current_user(request, db)
    session_path = inputs_dir(user.id) / "linkedin_session.json"
    return JSONResponse({
        "connected": session_path.exists() and bool(user.linkedin_session_expires_at),
        "expires_at": user.linkedin_session_expires_at.isoformat() if user.linkedin_session_expires_at else None,
    })
