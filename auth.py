from functools import wraps
from flask import session, redirect, url_for, flash, request

ROLE_SUPERVISOR = "supervisor"
ROLE_DRIVER = "driver"

def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "role" not in session:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapper

def role_required(*roles):
    def deco(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if "role" not in session:
                return redirect(url_for("login"))
            if session["role"] not in roles:
                flash("无权限访问该页面。", "error")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)
        return wrapper
    return deco

def current_user():
    return {
        "role": session.get("role"),
        "driver_id": session.get("driver_id"),
        "supervisor_id": session.get("supervisor_id"),
        "fleet_id": session.get("fleet_id"),
        "center_id": session.get("center_id"),
    }
