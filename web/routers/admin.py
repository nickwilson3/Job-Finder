from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from web.auth import require_admin
from web.database import get_db
from web.models import Run, User

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")


@router.get("/admin/users", response_class=HTMLResponse)
def admin_users(request: Request, db: Session = Depends(get_db)):
    require_admin(request, db)
    users = db.query(User).order_by(User.created_at.desc()).all()
    # Attach last run info to each user
    user_data = []
    for u in users:
        last_run = db.query(Run).filter(Run.user_id == u.id).order_by(Run.started_at.desc()).first()
        user_data.append({"user": u, "last_run": last_run})
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "user": require_admin(request, db), "active": "admin", "user_data": user_data},
    )


@router.post("/admin/users/{user_id}/toggle")
def toggle_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    require_admin(request, db)
    target = db.get(User, user_id)
    if not target:
        return JSONResponse({"error": "Not found"}, status_code=404)
    target.is_active = not target.is_active
    db.commit()
    return RedirectResponse("/admin/users", status_code=302)
