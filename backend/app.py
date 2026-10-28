from flask import Flask, request, session, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
import bcrypt
import os
from dotenv import load_dotenv

from topics import init_topics

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-to-something-random")

CORS(
    app,
    supports_credentials=True,
    origins=[
        "http://localhost:5500",
        "http://127.0.0.1:5500"
    ]
)

db = MongoClient(os.environ["MONGO_URI"])["ITClassroom"]
users = db["users"]

users.create_index("username", unique=True)
init_topics(app, db)

# Roles people can pick when they register. "admin" (or anything else) is never allowed here.
SELF_REGISTER_ROLES = ("student", "faculty")


@app.post("/api/register")
def register():
    d = request.get_json() or {}

    username = d.get("username", "").strip()
    password = d.get("password", "")
    role = str(d.get("role", "student")).lower()

    if not username or not isinstance(password, str) or len(password) < 6:
        return jsonify(
            error="Username required, password at least 6 characters"
        ), 400

    if role not in SELF_REGISTER_ROLES:
        return jsonify(error="Invalid role"), 400

    try:
        users.insert_one({
            "username": username,
            "password": bcrypt.hashpw(
                password.encode("utf-8"),
                bcrypt.gensalt()
            ),
            "role": role
        })
    except DuplicateKeyError:
        return jsonify(error="Username taken"), 409

    session["user"] = username
    return jsonify(ok=True), 201


@app.post("/api/login")
def login():
    d = request.get_json() or {}

    username = d.get("username", "")
    password = d.get("password", "")

    if not isinstance(username, str) or not isinstance(password, str):
        return jsonify(error="Wrong username or password"), 401

    u = users.find_one({"username": username})

    if u and bcrypt.checkpw(
        password.encode("utf-8"),
        u["password"]
    ):
        session["user"] = u["username"]
        return jsonify(ok=True)

    return jsonify(error="Wrong username or password"), 401


@app.get("/api/me")
def me():
    if "user" not in session:
        return jsonify(error="Not logged in"), 401

    u = users.find_one({"username": session["user"]})

    if not u:
        session.clear()
        return jsonify(error="Not logged in"), 401

    return jsonify(
        username=u["username"],
        role=u["role"]
    )

subjects = db["subjects"]


@app.get("/api/subjects")
def list_subjects():
    if "user" not in session:
        return jsonify(error="Not logged in"), 401

    user = users.find_one({"username": session["user"]})

    if not user:
        session.clear()
        return jsonify(error="Not logged in"), 401

    out = []

    for s in subjects.find().sort("code", 1):
        out.append({
            "id": str(s["_id"]),
            "name": s.get("name", ""),
            "code": s.get("code", ""),
            "term": s.get("term", ""),

            # Support older records created before these fields existed.
            "year_level": s.get("year_level", ""),
            "academic_year": s.get(
                "academic_year",
                s.get("year", "")
            ),

            # Actual quiz progress will be implemented later.
            "progress": 0
        })

    return jsonify(out), 200


@app.post("/api/subjects")
def add_subject():
    if "user" not in session:
        return jsonify(error="Not logged in"), 401

    user = users.find_one({"username": session["user"]})

    if not user:
        session.clear()
        return jsonify(error="Not logged in"), 401

    if user.get("role") != "faculty":
        return jsonify(error="Faculty only"), 403

    d = request.get_json(silent=True) or {}

    fields = {
        "name": d.get("name", "").strip()
            if isinstance(d.get("name", ""), str) else "",
        "code": d.get("code", "").strip()
            if isinstance(d.get("code", ""), str) else "",
        "term": d.get("term", "").strip()
            if isinstance(d.get("term", ""), str) else "",
        "year_level": d.get("year_level", "").strip()
            if isinstance(d.get("year_level", ""), str) else "",
        "academic_year": d.get("academic_year", "").strip()
            if isinstance(d.get("academic_year", ""), str) else ""
    }

    if not all(fields.values()):
        return jsonify(error="All fields are required"), 400

    if fields["term"] not in (
        "1st Semester", "2nd Semester", "Summer"
    ):
        return jsonify(error="Invalid semester"), 400

    if fields["year_level"] not in (
        "1st Year", "2nd Year", "3rd Year",
        "4th Year"
    ):
        return jsonify(error="Invalid year level"), 400

    import re

    if not re.fullmatch(
        r"\d{4}-\d{4}", fields["academic_year"]
    ):
        return jsonify(
            error="Academic year must use the format YYYY-YYYY"
        ), 400

    start_year, end_year = map(
        int, fields["academic_year"].split("-")
    )

    if end_year != start_year + 1:
        return jsonify(
            error="Academic year must contain consecutive years"
        ), 400

    subjects.insert_one(fields)

    return jsonify(ok=True), 201


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(debug=True)