from datetime import datetime

from ..db import db


class TaskTracker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # Användarens ID eller email.
    user_id = db.Column(db.String, nullable=False)
    task_id = db.Column(db.String, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    rate_limit_remaining = db.Column(db.Integer)
    rate_limit_total = db.Column(db.Integer)
    rate_limit_reset = db.Column(db.DateTime)
    # JSON-serialiserad sträng, t.ex. "[x1, y1, x2, y2]"
    bbox = db.Column(db.Text)
    file_path = db.Column(db.String, nullable=True)
    # Rå GeoJSON-data (kan vara lång, därför Text)
    geojson = db.Column(db.Text, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
