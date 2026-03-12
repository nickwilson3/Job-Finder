from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from web.auth import create_access_token, get_current_user, hash_password, verify_password
from web.database import get_db
from web.models import User
from web.storage import ensure_user_dirs

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("auth/register.html", {"request": request, "error": None})


@router.post("/register")
def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    display_name: str = Form(""),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse(
            "auth/register.html", {"request": request, "error": "Email already registered."}
        )
    if len(password) < 8:
        return templates.TemplateResponse(
            "auth/register.html", {"request": request, "error": "Password must be at least 8 characters."}
        )
    user = User(email=email, hashed_password=hash_password(password), display_name=display_name or email.split("@")[0])
    db.add(user)
    db.commit()
    db.refresh(user)
    ensure_user_dirs(user.id)
    token = create_access_token(user.id, user.email, user.is_admin)
    resp = RedirectResponse("/settings", status_code=302)
    resp.set_cookie("access_token", token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30)
    return resp


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("auth/login.html", {"request": request, "error": None})


@router.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            "auth/login.html", {"request": request, "error": "Invalid email or password."}
        )
    if not user.is_active:
        return templates.TemplateResponse(
            "auth/login.html", {"request": request, "error": "Account disabled. Contact the administrator."}
        )
    token = create_access_token(user.id, user.email, user.is_admin)
    resp = RedirectResponse("/dashboard", status_code=302)
    resp.set_cookie("access_token", token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30)
    return resp


@router.post("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("access_token")
    return resp


@router.get("/")
def root(request: Request, db: Session = Depends(get_db)):
    try:
        get_current_user(request, db)
        return RedirectResponse("/dashboard", status_code=302)
    except Exception:
        return RedirectResponse("/login", status_code=302)
