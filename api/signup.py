"""
POST /api/signup
Creates a new user in Postgres (Supabase) - this is our RDBMS tier.
Why Postgres here: email uniqueness and login credentials benefit from
real constraints (unique index, not-null), which a relational DB gives
us for free.

Expected JSON body:
{
  "email": "jane@example.com",
  "password": "plaintext-password",
  "full_name": "Jane Doe",
  "job_title": "Data Analyst"      (optional)
}
"""

from http.server import BaseHTTPRequestHandler
import json
import os
import bcrypt
import psycopg2
from psycopg2.extras import RealDictCursor


def get_db_connection():
    # SUPABASE_DB_URL is set as an environment variable in Vercel's
    # project settings - never hardcode it in the file.
    return psycopg2.connect(os.environ["SUPABASE_DB_URL"])


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
        full_name = (body.get("full_name") or "").strip()
        job_title = (body.get("job_title") or "").strip()

        if not email or not password or not full_name:
            self._send(400, {"error": "email, password, and full_name are required"})
            return

        # Never store plaintext passwords - bcrypt hashes + salts it.
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                """
                insert into users (email, password_hash, full_name, job_title)
                values (%s, %s, %s, %s)
                returning id, email, full_name, job_title, created_at
                """,
                (email, password_hash, full_name, job_title),
            )
            new_user = cur.fetchone()
            conn.commit()
            cur.close()

            # created_at is a datetime object - convert it so json.dumps doesn't choke
            new_user["created_at"] = str(new_user["created_at"])

            self._send(201, {"message": "Account created", "user": new_user})

        except psycopg2.errors.UniqueViolation:
            if conn:
                conn.rollback()
            self._send(409, {"error": "An account with this email already exists"})

        except Exception as e:
            if conn:
                conn.rollback()
            self._send(500, {"error": f"Server error: {str(e)}"})

        finally:
            if conn:
                conn.close()

    def do_OPTIONS(self):
        # Needed so the React app (running on a different domain) can call this
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
