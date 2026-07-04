"""
POST /api/profile   -> create/update flexible profile details in MongoDB
GET  /api/profile?user_id=xxx -> combine Postgres + MongoDB data for the
                                  profile view page

Why MongoDB here: bio, skills, and social links are optional and vary
per user - one person might list 10 skills and 3 links, another none.
Forcing that into fixed relational columns would mean lots of empty
columns or awkward extra tables. A document naturally holds "whatever
this user has."

POST body:
{
  "user_id": "uuid-from-signup",
  "bio": "Aspiring data engineer...",
  "skills": ["Python", "SQL", "React"],
  "social_links": {"linkedin": "...", "github": "..."}
}

GET query string:
  /api/profile?user_id=uuid-from-signup
"""

from http.server import BaseHTTPRequestHandler
import json
import os
from urllib.parse import urlparse, parse_qs
from pymongo import MongoClient
import psycopg2
from psycopg2.extras import RealDictCursor


def get_pg_connection():
    return psycopg2.connect(os.environ["SUPABASE_DB_URL"])


def get_mongo_collection():
    client = MongoClient(os.environ["MONGODB_URI"])
    db = client["profileapp"]
    return db["profile_details"]


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length)

        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError:
            self._send(400, {"error": "Invalid JSON body"})
            return

        user_id = body.get("user_id")
        if not user_id:
            self._send(400, {"error": "user_id is required"})
            return

        profile_doc = {
            "user_id": user_id,
            "bio": body.get("bio", ""),
            "skills": body.get("skills", []),
            "social_links": body.get("social_links", {}),
        }

        try:
            collection = get_mongo_collection()
            # upsert: create it if it doesn't exist yet, update it if it does
            collection.update_one(
                {"user_id": user_id}, {"$set": profile_doc}, upsert=True
            )
            self._send(200, {"message": "Profile saved", "profile": profile_doc})
        except Exception as e:
            self._send(500, {"error": f"Server error: {str(e)}"})

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        user_id = query.get("user_id", [None])[0]

        if not user_id:
            self._send(400, {"error": "user_id query parameter is required"})
            return

        pg_conn = None
        try:
            # 1. Core identity fields come from Postgres
            pg_conn = get_pg_connection()
            cur = pg_conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                "select id, email, full_name, job_title, created_at from users where id = %s",
                (user_id,),
            )
            user = cur.fetchone()
            cur.close()

            if not user:
                self._send(404, {"error": "User not found"})
                return

            user["created_at"] = str(user["created_at"])
            user["id"] = str(user["id"])

            # 2. Flexible profile fields come from MongoDB
            collection = get_mongo_collection()
            profile = collection.find_one({"user_id": user_id}, {"_id": 0})

            # Combine both into a single response for the frontend
            combined = {**user, **(profile or {})}
            self._send(200, combined)

        except Exception as e:
            self._send(500, {"error": f"Server error: {str(e)}"})

        finally:
            if pg_conn:
                pg_conn.close()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _send(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
