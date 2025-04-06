import os
from functools import wraps

from dotenv import load_dotenv
from flask import flash, redirect, session, url_for

load_dotenv()

LM_consumer_key = os.getenv("LM_consumer_key")
LM_consumer_secret = os.getenv("LM_consumer_secret")


def login_required(f):
    """Decorator to ensure access token exists before accessing route."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "oauth_token" not in session or "user" not in session:
            flash("Du måste vara inloggad först.", "danger")
            return redirect(url_for("home"))
        return f(*args, **kwargs)

    return decorated_function
