"""
POST /api/login
Verifies email + password against Postgres, then logs the login event
to Upstash Redis - our serverless database tier.

Why Redis/Upstash here: login events are simple, high-write, key-based
records (who logged in, when) with no need for relational structure.
That access pattern is exactly what a serverless key-value store is
built for, and it scales to zero when nobody's logging in.

Expected JSON body:
{
  "email": "jane@example.com",
  "password": "plaintext-password"
}
"""

from http.server import BaseHTTPRequestHandler
import json
import os
import time
import bcrypt
import psycopg2
from psycopg2.extras import RealDictCursor
import requests


def get_db_connection():
    return psycopg2.connect(os.environ["SUPABASE_DB_URL"])


def log_session_to_redis(user_id):
    """
    Upstash's REST API lets us talk to Redis with plain HTTP calls -
    no special Redis client or persistent connection needed, which is
    exactly what makes it work well in a short-lived serverless function.
    """
    url = os.environ["UPSTASH_REDIS_REST_URL"]
    token = os.environ["UPSTASH_REDIS_REST_TOKEN"]
    timestamp = str(int(time.time()))

    key = f"session:{user_id}:{timestamp}"
    # Upstash REST commands are just URL path segments: /SET/key/value
    requests.post(
        f"{url}/set/{key}/{timestamp}",
        headers={"Authorization": f"Bearer {token}"},
    )
    return timestamp


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length)

        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError:
            self._send(400, {"error": "Invalid JSON body"})
            return

        email = (body.get("email") or "").strip().lower()
        password = body.get("password") or ""

        if not email or not password:
            self._send(400, {"error": "email and password are required"})
            return

        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                "select id, email, full_name, password_hash from users where email = %s",
                (email,),
            )
            user = cur.fetchone()
            cur.close()

            if not user or not bcrypt.checkpw(
                password.encode(), user["password_hash"].encode()
            ):
                self._send(401, {"error": "Invalid email or password"})
                return

            login_time = log_session_to_redis(user["id"])

            self._send(
                200,
                {
                    "message": "Login successful",
                    "user_id": user["id"],
                    "full_name": user["full_name"],
                    "login_time": login_time,
                },
            )

        except Exception as e:
            self._send(500, {"error": f"Server error: {str(e)}"})

        finally:
            if conn:
                conn.close()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _send(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
