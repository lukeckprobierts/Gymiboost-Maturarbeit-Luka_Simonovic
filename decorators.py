from functools import wraps
from flask import redirect, url_for, session, flash, request, current_app, jsonify
from models import User
from extensions import db
import time

# In-memory global rate limit store: per-user counts for minute/day windows
_RATE_LIMIT_STATE = {}

def _check_global_rate_limit():
    uid = session.get("user_id") or request.remote_addr or "anon"
    now = time.time()
    minute_key = int(now // 60)
    day_key = int(now // 86400)

    state = _RATE_LIMIT_STATE.setdefault(uid, {
        "minute": {"key": minute_key, "count": 0},
        "day": {"key": day_key, "count": 0}
    })

    if state["minute"]["key"] != minute_key:
        state["minute"] = {"key": minute_key, "count": 0}
    if state["day"]["key"] != day_key:
        state["day"] = {"key": day_key, "count": 0}

    minute_limit = current_app.config.get("GLOBAL_RATE_LIMIT_PER_MINUTE", 60)
    day_limit = current_app.config.get("GLOBAL_RATE_LIMIT_PER_DAY", 2000)

    if state["minute"]["count"] >= minute_limit or state["day"]["count"] >= day_limit:
        # Prefer JSON response for API calls
        if request.is_json or "application/json" in (request.headers.get("Accept") or ""):
            return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429
        flash("Nutzungslimit überschritten. Bitte versuchen Sie es später erneut.", "warning")
        return redirect(url_for('dashboard'))

    state["minute"]["count"] += 1
    state["day"]["count"] += 1
    return None

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Bitte melden Sie sich an, um fortzufahren", "warning")
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def subscription_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Bitte melden Sie sich an, um fortzufahren", "warning")
            return redirect(url_for('login'))
        
        user = User.query.get(session["user_id"])
        if not user:
            session.clear()
            flash("Benutzer nicht gefunden", "danger")
            return redirect(url_for('login'))

        # Apply global high-level rate limits on expensive endpoints for all users
        endpoint = request.endpoint or ''
        expensive = ["send_message", "generate_tasks", "submit_exam", "process_with_gpt4o"]
        if any(endpoint == name or endpoint.endswith(name) for name in expensive):
            resp = _check_global_rate_limit()
            if resp is not None:
                return resp

        # If user has active subscription, allow
        if user.has_active_subscription:
            return f(*args, **kwargs)

        # Free trial: unlimited for 7 days from first use/registration
        from datetime import datetime, timedelta
        if not user.free_trial_start:
            user.free_trial_start = datetime.utcnow()
            db.session.commit()

        if datetime.utcnow() - user.free_trial_start <= timedelta(days=7):
            return f(*args, **kwargs)

        # After free trial expired: allow viewing some pages, block core features
        if endpoint in ["dashboard", "exam_selection", "task_generation", "chat", "chat_history", "delete_session", "upload_file"]:
            return f(*args, **kwargs)

        flash("Ihre kostenlose Testphase ist abgelaufen. Bitte abonnieren Sie, um diese Funktion zu nutzen.", "warning")
        return redirect(url_for('pricing'))

    return decorated_function

def redirect_if_logged_in(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" in session:
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            
            user = User.query.get(session["user_id"])
            if user and user.has_active_subscription:
                return redirect(url_for('chat'))
            return redirect(url_for('landing'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Bitte melden Sie sich an", "danger")
            return redirect(url_for('login'))
        user = User.query.get(session["user_id"])
        if not user or not user.is_admin:
            flash("Zugriff verweigert: Administratorrechte erforderlich", "danger")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function