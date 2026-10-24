from flask import Flask, request, session, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
import bcrypt
import os
from dotenv import load_dotenv

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
    out = []
    for s in subjects.find().sort("code", 1):
        out.append({"id": str(s["_id"]), "name": s["name"], "code": s["code"],
                    "term": s["term"], "year": s["year"]})
    return jsonify(out)

@app.post("/api/subjects")
def add_subject():
    if "user" not in session:
        return jsonify(error="Not logged in"), 401
    u = users.find_one({"username": session["user"]})
    if u["role"] != "faculty":
        return jsonify(error="Faculty only"), 403
    d = request.get_json()
    fields = {k: d.get(k, "").strip() for k in ("name", "code", "term", "year")}
    if not all(fields.values()):
        return jsonify(error="All fields are required"), 400
    subjects.insert_one(fields)
    return jsonify(ok=True)

@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(debug=True)