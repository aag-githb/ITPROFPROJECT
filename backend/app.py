from flask import Flask, request, session, jsonify, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError, ServerSelectionTimeoutError
from bson import ObjectId
import bcrypt
import os
import csv
import io
import secrets
import string
import hashlib
import smtplib
from email.message import EmailMessage
from datetime import datetime, timezone
from pathlib import Path
from markupsafe import escape
from dotenv import load_dotenv

from topics import init_topics

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
load_dotenv(BASE_DIR / ".env")

# Keep existing local setups working while configuration is moved out of the
# frontend folder. Backend configuration should ultimately live in backend/.env.
if not os.environ.get("MONGO_URI"):
    load_dotenv(BASE_DIR.parent / "frontend" / ".env")

if not os.environ.get("MONGO_URI"):
    raise RuntimeError(
        "MONGO_URI is not configured. Create backend/.env from "
        "backend/.env.example and set the MongoDB connection string."
    )

app = Flask(
    __name__,
    static_folder=str(FRONTEND_DIR),
    static_url_path="",
)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-to-something-random")


@app.after_request
def prevent_cached_responses(response):
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


@app.get("/")
def frontend_index():
    return send_from_directory(FRONTEND_DIR, "login.html")

CORS(
    app,
    supports_credentials=True,
    origins=[
        "http://localhost:5500",
        "http://127.0.0.1:5500"
    ]
)

mongo_client = MongoClient(
    os.environ["MONGO_URI"],
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    socketTimeoutMS=10000,
)
try:
    mongo_client.admin.command("ping")
except ServerSelectionTimeoutError as error:
    raise RuntimeError(
        "MongoDB could not be reached within 5 seconds. "
        "Check MONGO_URI and confirm the database is running or "
        "the Atlas network access list allows this device."
    ) from error

db = mongo_client["ITClassroom"]
users = db["users"]

users.create_index("username", unique=True)
users.create_index("email", unique=True, sparse=True)
users.update_one(
    {"username": "famini", "role": "faculty"},
    {"$set": {"email": "ck.famini@gmail.com", "email_verified": True}},
)
users.update_one(
    {
        "username": {"$regex": "^TUPT-23-1098$", "$options": "i"},
        "role": "student",
    },
    {"$set": {"email": "telfamini@gmail.com", "email_verified": True}},
)
init_topics(app, db)

# Roles people can pick when they register. "admin" (or anything else) is never allowed here.
SELF_REGISTER_ROLES = ("student", "faculty")
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_SENDER = os.environ.get("SMTP_SENDER", "")
SMTP_PASSWORD = os.environ.get("SMTP_APP_PASSWORD", "")


def send_verification_email(recipient, token):
    if not SMTP_SENDER or not SMTP_PASSWORD:
        raise RuntimeError("Email delivery is not configured")
    message = EmailMessage()
    message["Subject"] = "Verify your ITClassroom email"
    message["From"] = SMTP_SENDER
    message["To"] = recipient
    message.set_content(
        "Verify your ITClassroom account by opening this link:\n\n"
        f"http://{request.host}/api/verify-email/{token}\n\n"
        "This link expires in 24 hours."
    )
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
        server.starttls()
        server.login(SMTP_SENDER, SMTP_PASSWORD)
        server.send_message(message)


@app.post("/api/register")
def register():
    d = request.get_json() or {}

    username = d.get("username", "").strip()
    password = d.get("password", "")
    email = d.get("email", "").strip().lower()
    role = str(d.get("role", "student")).lower()

    if not username or not isinstance(password, str) or len(password) < 6:
        return jsonify(
            error="Username required, password at least 6 characters"
        ), 400

    if role not in SELF_REGISTER_ROLES:
        return jsonify(error="Invalid role"), 400
    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        return jsonify(error="A valid email is required"), 400

    token = secrets.token_urlsafe(32)
    user = {
        "username": username,
        "email": email,
        "email_verified": False,
        "verification_token_hash": hashlib.sha256(token.encode()).hexdigest(),
        "verification_expires": datetime.now(timezone.utc).timestamp() + 86400,
        "password": bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()),
        "role": role,
        "disabled": False,
    }

    try:
        users.insert_one(user)
    except DuplicateKeyError:
        return jsonify(error="Username or email is already registered"), 409

    try:
        send_verification_email(email, token)
    except RuntimeError as error:
        users.delete_one({"_id": user["_id"]})
        app.logger.error("Verification email configuration failed: %s", error)
        return jsonify(
            error=(
                "Registration is temporarily unavailable because email "
                "verification is not configured on the server."
            )
        ), 503
    except Exception as error:
        users.delete_one({"_id": user["_id"]})
        app.logger.error("Verification email failed: %s", error)
        return jsonify(
            error=(
                "We could not send the verification email. "
                "Check the address and try again later."
            )
        ), 503

    return jsonify(ok=True, message="Check your email to verify your account."), 201


@app.get("/api/verify-email/<token>")
def verify_email(token):
    def verification_page(title, message, success):
        status_class = "success" if success else "error"
        status_symbol = "✓" if success else "!"
        login_link = (
            '<a class="button" href="/login.html">Continue to login</a>'
            if success else
            '<a class="button secondary" href="/login.html">Return to login</a>'
        )
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} | ITClassroom</title>
  <style>
    :root {{
      --periwinkle:#e3d9fc;
      --magenta:#bf40fa;
      --blue:#4928c2;
      --black:#040607;
    }}
    * {{ box-sizing:border-box; }}
    body {{
      min-height:100vh;
      margin:0;
      display:grid;
      place-items:center;
      padding:24px;
      color:var(--periwinkle);
      font-family:"Segoe UI",system-ui,sans-serif;
      background:
        radial-gradient(ellipse 60% 55% at 8% 12%,rgba(73,40,194,.75),transparent 70%),
        radial-gradient(ellipse 55% 50% at 90% 90%,rgba(191,64,250,.35),transparent 70%),
        var(--black);
    }}
    .card {{
      width:min(520px,100%);
      padding:42px 38px;
      text-align:center;
      border:1px solid rgba(227,217,252,.22);
      border-radius:28px;
      background:rgba(18,12,42,.88);
      box-shadow:0 28px 80px rgba(0,0,0,.5);
    }}
    .brand {{
      display:inline-flex;
      align-items:center;
      gap:10px;
      margin-bottom:30px;
      color:var(--periwinkle);
      font-family:Georgia,serif;
      font-size:1.45rem;
      font-weight:700;
    }}
    .star {{
      color:var(--magenta);
      font-size:2rem;
      line-height:1;
    }}
    .status {{
      display:grid;
      place-items:center;
      width:64px;
      height:64px;
      margin:0 auto 22px;
      border-radius:50%;
      color:white;
      font-size:2rem;
      font-weight:700;
    }}
    .status.success {{ background:var(--blue); }}
    .status.error {{ background:#9d2342; }}
    h1 {{
      margin:0 0 12px;
      color:var(--periwinkle);
      font-family:Georgia,serif;
      font-size:clamp(1.8rem,5vw,2.4rem);
    }}
    p {{
      margin:0 auto 28px;
      max-width:38ch;
      color:rgba(227,217,252,.78);
      line-height:1.65;
    }}
    .button {{
      display:inline-block;
      padding:12px 22px;
      border-radius:12px;
      color:white;
      background:var(--blue);
      font-weight:700;
      text-decoration:none;
    }}
    .button:hover {{ background:#5b35d8; }}
    .button.secondary {{
      border:1px solid rgba(227,217,252,.35);
      background:transparent;
      color:var(--periwinkle);
    }}
  </style>
</head>
<body>
  <main class="card">
    <div class="brand"><span class="star" aria-hidden="true">✦</span>ITClassroom</div>
    <div class="status {status_class}" aria-hidden="true">{status_symbol}</div>
    <h1>{escape(title)}</h1>
    <p>{escape(message)}</p>
    {login_link}
  </main>
</body>
</html>"""

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    user = users.find_one({
        "verification_token_hash": token_hash,
        "verification_expires": {"$gt": datetime.now(timezone.utc).timestamp()},
    })
    if not user:
        return verification_page(
            "Verification link unavailable",
            "This verification link is invalid or has expired. Please request a new verification email.",
            False,
        ), 400
    users.update_one({"_id": user["_id"]}, {"$set": {
        "email_verified": True,
        "verification_token_hash": None,
        "verification_expires": None,
    }})
    return verification_page(
        "Email verified",
        "Your ITClassroom email has been verified successfully. You can now log in to your account.",
        True,
    )


@app.post("/api/login")
def login():
    d = request.get_json() or {}

    username = d.get("username", "")
    password = d.get("password", "")

    if not isinstance(username, str) or not isinstance(password, str):
        return jsonify(error="Wrong username or password"), 401

    u = users.find_one({"username": username})

    if u and u.get("disabled"):
        return jsonify(error="This account is disabled"), 403
    if u and not u.get("email_verified", u.get("username") == "famini"):
        return jsonify(error="Please verify your email before logging in"), 403
    if u and bcrypt.checkpw(
        password.encode("utf-8"),
        u["password"]
    ):
        session.clear()
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


@app.get("/api/profile")
def profile():
    if "user" not in session:
        return jsonify(error="Not logged in"), 401
    user = users.find_one({"username": session["user"]})
    if not user:
        session.clear()
        return jsonify(error="Not logged in"), 401
    return jsonify(
        username=user["username"],
        email=user.get("email", ""),
        email_verified=bool(user.get("email_verified")),
        role=user.get("role", ""),
        disabled=bool(user.get("disabled")),
    )


def authenticated_profile_user():
    username = session.get("user")
    user = users.find_one({"username": username}) if username else None
    if not user:
        session.clear()
        return None, (jsonify(error="Not logged in"), 401)
    return user, None


@app.put("/api/profile")
def update_profile():
    user, error = authenticated_profile_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    current_password = data.get("current_password", "")
    if not isinstance(current_password, str) or not bcrypt.checkpw(
        current_password.encode(), user["password"]
    ):
        return jsonify(error="Current password is incorrect"), 403

    updates = {}
    if "username" in data:
        if not isinstance(data["username"], str):
            return jsonify(error="Username is required"), 400
        username = data["username"].strip()
        if not username:
            return jsonify(error="Username is required"), 400
        if username != user["username"]:
            return jsonify(
                error="Username changes are not supported because they would "
                "break existing class and quiz records"
            ), 400
        updates["username"] = username
    if "password" in data:
        password = data["password"]
        if not isinstance(password, str) or len(password) < 6:
            return jsonify(error="New password must be at least 6 characters"), 400
        updates["password"] = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    if "email" in data:
        email = data["email"].strip().lower()
        if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            return jsonify(error="A valid email is required"), 400
        if email != user.get("email", "").lower():
            if users.find_one({
                "email": email,
                "_id": {"$ne": user["_id"]},
            }):
                return jsonify(error="Username or email is already in use"), 409
            token = secrets.token_urlsafe(32)
            updates.update({
                "email": email,
                "email_verified": False,
                "verification_token_hash": hashlib.sha256(token.encode()).hexdigest(),
                "verification_expires": datetime.now(timezone.utc).timestamp() + 86400,
            })
    if not updates:
        return jsonify(error="No profile changes supplied"), 400
    if "email" in updates:
        try:
            send_verification_email(updates["email"], token)
        except Exception as send_error:
            app.logger.error("Profile verification email failed: %s", send_error)
            return jsonify(
                error="Profile was not changed because the verification email "
                "could not be sent"
            ), 503
    try:
        users.update_one({"_id": user["_id"]}, {"$set": updates})
    except DuplicateKeyError:
        return jsonify(error="Username or email is already in use"), 409
    if "username" in updates:
        session["user"] = updates["username"]
    return jsonify(ok=True, requires_email_verification="email" in updates), 200


@app.post("/api/profile/status")
def profile_status():
    user, error = authenticated_profile_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    if not isinstance(data.get("disabled"), bool):
        return jsonify(error="Disabled must be true or false"), 400
    users.update_one({"_id": user["_id"]}, {"$set": {"disabled": data["disabled"]}})
    return jsonify(ok=True), 200


@app.delete("/api/profile")
def delete_profile():
    user, error = authenticated_profile_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    password = data.get("current_password", "")
    if not isinstance(password, str) or not bcrypt.checkpw(
        password.encode(), user["password"]
    ):
        return jsonify(error="Current password is incorrect"), 403
    if subjects.find_one({"created_by": user["username"]}):
        return jsonify(error="Delete your subjects before deleting this account"), 409
    enrollments.delete_many({"username": user["username"]})
    student_progress.delete_many({"username": user["username"]})
    quiz_attempts.delete_many({"username": user["username"]})
    users.delete_one({"_id": user["_id"]})
    session.clear()
    return jsonify(ok=True), 200

subjects = db["subjects"]
enrollments = db["enrollments"]
student_progress = db["student_progress"]
topics = db["topics"]
quizzes = db["quizzes"]
quiz_attempts = db["quiz_attempts"]

enrollments.create_index(
    [("subject_id", 1), ("username", 1)],
    unique=True
)
subjects.create_index("join_code", unique=True, sparse=True)


def seed_general_knowledge_content():
    general_subjects = list(subjects.find({
        "name": {"$regex": "^General Knowledge$", "$options": "i"},
    }))
    for subject in general_subjects:
        if topics.count_documents({"subject_id": subject["_id"]}):
            continue

        lessons = [
            {
                "title": "World Geography Essentials",
                "description": "Explore continents, oceans, landmarks, and the natural features that shape our world.",
                "content": "This lesson introduces major geographic features and important places around the world.",
                "questions": [
                    ("Which is the largest continent by area?", ["Asia", "Africa", "Europe", "Australia"], "Asia"),
                    ("What is the largest ocean on Earth?", ["Atlantic Ocean", "Indian Ocean", "Pacific Ocean", "Arctic Ocean"], "Pacific Ocean"),
                    ("The Sahara Desert is located primarily on which continent?", ["Asia", "Africa", "South America", "Europe"], "Africa"),
                    ("What is the capital city of Japan?", ["Seoul", "Beijing", "Tokyo", "Bangkok"], "Tokyo"),
                    ("Which imaginary line divides Earth into Northern and Southern Hemispheres?", ["Prime Meridian", "Equator", "Tropic of Cancer", "International Date Line"], "Equator"),
                    ("Mount Everest is part of which mountain range?", ["Andes", "Alps", "Rockies", "Himalayas"], "Himalayas"),
                    ("Which country is shaped like a boot?", ["Italy", "Greece", "Chile", "Portugal"], "Italy"),
                    ("What is the smallest continent by land area?", ["Europe", "Antarctica", "Australia", "South America"], "Australia"),
                    ("Which river is commonly associated with ancient Egypt?", ["Nile", "Amazon", "Danube", "Yangtze"], "Nile"),
                    ("What do we call a body of land surrounded by water on all sides?", ["Peninsula", "Island", "Plateau", "Valley"], "Island"),
                ],
            },
            {
                "title": "Science in Everyday Life",
                "description": "Review basic ideas from biology, physics, chemistry, and space science.",
                "content": "Science helps explain the living world, matter, energy, and the universe around us.",
                "questions": [
                    ("What gas do humans need to breathe to survive?", ["Oxygen", "Nitrogen", "Carbon dioxide", "Hydrogen"], "Oxygen"),
                    ("What force pulls objects toward Earth?", ["Friction", "Gravity", "Magnetism", "Pressure"], "Gravity"),
                    ("Which organ pumps blood throughout the human body?", ["Lungs", "Brain", "Heart", "Liver"], "Heart"),
                    ("What is H2O commonly known as?", ["Salt", "Water", "Oxygen", "Hydrogen"], "Water"),
                    ("Which planet is known as the Red Planet?", ["Venus", "Mars", "Jupiter", "Mercury"], "Mars"),
                    ("What process do green plants use to make food from sunlight?", ["Digestion", "Respiration", "Photosynthesis", "Fermentation"], "Photosynthesis"),
                    ("What is the center of an atom called?", ["Electron", "Molecule", "Nucleus", "Cell"], "Nucleus"),
                    ("Which state of matter has a definite volume but no definite shape?", ["Solid", "Liquid", "Gas", "Plasma"], "Liquid"),
                    ("What instrument is used to measure temperature?", ["Barometer", "Thermometer", "Compass", "Microscope"], "Thermometer"),
                    ("How many bones are in the typical adult human body?", ["106", "206", "306", "406"], "206"),
                ],
            },
            {
                "title": "History, Culture, and Society",
                "description": "Learn foundational facts about important historical periods, cultural ideas, and civic life.",
                "content": "History and culture help us understand how communities developed and how people shape society.",
                "questions": [
                    ("Which ancient civilization built the pyramids at Giza?", ["Romans", "Egyptians", "Mayans", "Vikings"], "Egyptians"),
                    ("Who is widely credited with inventing the telephone?", ["Alexander Graham Bell", "Thomas Edison", "Isaac Newton", "Nikola Tesla"], "Alexander Graham Bell"),
                    ("What document begins with the words “We the People”?", ["The Constitution", "The Magna Carta", "The Declaration of Independence", "The Bill of Rights"], "The Constitution"),
                    ("Which invention is Johannes Gutenberg associated with?", ["Steam engine", "Printing press", "Light bulb", "Radio"], "Printing press"),
                    ("What is democracy commonly understood to mean?", ["Rule by one person", "Rule by the people", "Rule by the military", "Rule by a monarch"], "Rule by the people"),
                    ("Which celebration is associated with the start of a new calendar year?", ["New Year’s Day", "Harvest Festival", "Labor Day", "Earth Day"], "New Year’s Day"),
                    ("What is a primary purpose of a museum?", ["To preserve and educate", "To manufacture goods", "To issue passports", "To forecast weather"], "To preserve and educate"),
                    ("Which language has the greatest number of native speakers worldwide?", ["English", "Spanish", "Mandarin Chinese", "French"], "Mandarin Chinese"),
                    ("What is the study of past events called?", ["Geology", "History", "Astronomy", "Economics"], "History"),
                    ("A group of people living in the same area and sharing institutions is called what?", ["Community", "Equation", "Constellation", "Laboratory"], "Community"),
                ],
            },
        ]

        for lesson in lessons:
            topic_id = topics.insert_one({
                "subject_id": subject["_id"],
                "title": lesson["title"],
                "description": lesson["description"],
                "content": lesson["content"],
                "summary": lesson["description"],
                "slides": [],
                "presentations": [],
                "created_by": subject.get("created_by", "famini"),
            }).inserted_id
            questions = [
                {
                    "id": secrets.token_hex(8),
                    "text": question,
                    "type": "multiple_choice",
                    "choices": choices,
                    "correct_answer": answer,
                }
                for question, choices, answer in lesson["questions"]
            ]
            quizzes.insert_one({
                "topic_id": topic_id,
                "questions": questions,
                "created_by": subject.get("created_by", "famini"),
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            })


seed_general_knowledge_content()


def new_join_code():
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(6))
        if not subjects.find_one({"join_code": code}, {"_id": 1}):
            return code


def require_faculty_user():
    username = session.get("user")
    if not username:
        return None, (jsonify(error="Not logged in"), 401)
    user = users.find_one({"username": username})
    if not user:
        session.clear()
        return None, (jsonify(error="Not logged in"), 401)
    if user.get("role") != "faculty":
        return None, (jsonify(error="Faculty only"), 403)
    return user, None


def quiz_score_dashboard(
    subject_id=None,
    topic_id=None,
    category=None,
    year_level=None,
    section=None,
    academic_year=None,
    faculty_username=None,
):
    quiz_map = {}
    topic_ids = set()
    for quiz in quizzes.find({}, {"questions": 0}):
        quiz_map[quiz["_id"]] = quiz
        topic_ids.add(quiz.get("topic_id"))

    topic_map = {
        topic["_id"]: topic
        for topic in topics.find({"_id": {"$in": list(topic_ids)}})
    }

    rows = {}
    for attempt in quiz_attempts.find(
        {"status": {"$in": ["completed", "expired"]}}
    ).sort("finished_at", -1):
        quiz = quiz_map.get(attempt.get("quiz_id"))
        topic = topic_map.get(attempt.get("topic_id"))
        if not quiz or not topic:
            continue
        if subject_id and str(topic.get("subject_id")) != subject_id:
            continue
        if topic_id and str(topic.get("_id")) != topic_id:
            continue
        subject = subjects.find_one({"_id": topic.get("subject_id")})
        if not subject:
            continue
        if faculty_username and subject.get("created_by") != faculty_username:
            continue
        if category and subject.get("category", "") != category:
            continue
        if year_level and subject.get("year_level", "") != year_level:
            continue
        if section and subject.get("section", "") != section:
            continue
        if academic_year and subject.get(
            "academic_year", subject.get("year", "")
        ) != academic_year:
            continue

        username = attempt.get("username", "")
        row = rows.setdefault(username, {
            "student": username,
            "quiz_count": 0,
            "attempt_count": 0,
            "passed_count": 0,
            "average_score": 0,
            "best_score": 0,
            "scores": [],
        })
        score = float(attempt.get("score", 0) or 0)
        row["attempt_count"] += 1
        row["scores"].append(score)
        row["passed_count"] += int(bool(attempt.get("passed")))
        row["best_score"] = max(row["best_score"], score)
        row.setdefault("_quizzes", {})[str(quiz["_id"])] = {
            "subject_id": str(topic.get("subject_id", "")),
            "topic": topic.get("title", ""),
            "score": score,
            "passed": bool(attempt.get("passed")),
            "status": attempt.get("status", ""),
            "finished_at": attempt.get("finished_at"),
        }

    result = []
    for row in rows.values():
        row["quiz_count"] = len(row.pop("_quizzes"))
        row["average_score"] = round(
            sum(row["scores"]) / len(row["scores"]), 2
        ) if row["scores"] else 0
        row.pop("scores", None)
        result.append(row)
    return sorted(result, key=lambda row: row["student"].lower())


@app.get("/api/faculty/quiz-dashboard")
def faculty_quiz_dashboard():
    user, error = require_faculty_user()
    if error:
        return error

    rows = quiz_score_dashboard(
        request.args.get("subject_id", "").strip() or None,
        request.args.get("topic_id", "").strip() or None,
        request.args.get("category", "").strip() or None,
        request.args.get("year_level", "").strip() or None,
        request.args.get("section", "").strip() or None,
        request.args.get("academic_year", "").strip() or None,
        user["username"],
    )
    return jsonify(
        students=rows,
        passing_score=75,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/api/faculty/quiz-dashboard/student/<path:student_username>")
def faculty_student_quiz_records(student_username):
    user, error = require_faculty_user()
    if error:
        return error

    filters = {
        "subject_id": request.args.get("subject_id", "").strip() or None,
        "topic_id": request.args.get("topic_id", "").strip() or None,
    }
    quiz_map = {
        quiz["_id"]: quiz
        for quiz in quizzes.find({}, {"questions": 0})
    }
    topic_ids = [quiz.get("topic_id") for quiz in quiz_map.values()]
    topic_map = {
        topic["_id"]: topic
        for topic in topics.find({"_id": {"$in": topic_ids}})
    }
    records = []
    for attempt in quiz_attempts.find({
        "username": student_username,
        "status": {"$in": ["completed", "expired"]},
    }).sort("finished_at", -1):
        topic = topic_map.get(attempt.get("topic_id"))
        quiz = quiz_map.get(attempt.get("quiz_id"))
        if not topic or not quiz:
            continue
        subject = subjects.find_one({"_id": topic.get("subject_id")})
        if not subject or subject.get("created_by") != user["username"]:
            continue
        if filters["subject_id"] and str(topic["subject_id"]) != filters["subject_id"]:
            continue
        if filters["topic_id"] and str(topic["_id"]) != filters["topic_id"]:
            continue
        records.append({
            "id": str(attempt["_id"]),
            "subject": subject.get("name", ""),
            "subject_code": subject.get("code", ""),
            "topic": topic.get("title", ""),
            "score": float(attempt.get("score", 0) or 0),
            "passed": bool(attempt.get("passed")),
            "status": attempt.get("status", ""),
            "finished_at": attempt.get("finished_at"),
        })
    scores = [record["score"] for record in records]
    return jsonify(
        student=student_username,
        records=records,
        average_score=round(sum(scores) / len(scores), 2) if scores else 0,
        best_score=max(scores) if scores else 0,
        passed_count=sum(record["passed"] for record in records),
        passing_score=75,
    )


@app.get("/api/faculty/quiz-dashboard.csv")
def faculty_quiz_dashboard_csv():
    user, error = require_faculty_user()
    if error:
        return error

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "student", "quizzes", "attempts", "passed_attempts",
        "average_score", "best_score"
    ])
    rows = quiz_score_dashboard(
        request.args.get("subject_id", "").strip() or None,
        request.args.get("topic_id", "").strip() or None,
        request.args.get("category", "").strip() or None,
        request.args.get("year_level", "").strip() or None,
        request.args.get("section", "").strip() or None,
        request.args.get("academic_year", "").strip() or None,
        user["username"],
    )
    for row in rows:
        writer.writerow([
            row["student"], row["quiz_count"], row["attempt_count"],
            row["passed_count"], row["average_score"], row["best_score"]
        ])

    response = app.response_class(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = (
        'attachment; filename="all-quiz-scores-by-student.csv"'
    )
    return response


@app.get("/api/faculty/table-of-contents")
def faculty_table_of_contents():
    user, error = require_faculty_user()
    if error:
        return error

    subject_rows = []
    for subject in subjects.find(
        {"created_by": user["username"]}
    ).sort("code", 1):
        subject_topics = topics.find(
            {"subject_id": subject["_id"]}
        ).sort("_id", 1)
        topic_rows = []
        for topic in subject_topics:
            quiz = quizzes.find_one(
                {"topic_id": topic["_id"]},
                {"_id": 1, "questions": 1},
            )
            topic_rows.append({
                "id": str(topic["_id"]),
                "title": topic.get("title", ""),
                "quiz_id": str(quiz["_id"]) if quiz else None,
                "question_count": len(quiz.get("questions", [])) if quiz else 0,
            })
        subject_rows.append({
            "id": str(subject["_id"]),
            "name": subject.get("name", ""),
            "code": subject.get("code", ""),
            "category": subject.get("category", ""),
            "year_level": subject.get("year_level", ""),
            "section": subject.get("section", ""),
            "term": subject.get("term", ""),
            "academic_year": subject.get(
                "academic_year", subject.get("year", "")
            ),
            "topics": topic_rows,
        })
    return jsonify(subjects=subject_rows)


@app.get("/api/subjects")
def list_subjects():
    if "user" not in session:
        return jsonify(error="Not logged in"), 401

    user = users.find_one({"username": session["user"]})

    if not user:
        session.clear()
        return jsonify(error="Not logged in"), 401

    out = []
    hidden_subjects = {
        str(subject_id)
        for subject_id in user.get("hidden_subjects", [])
    }

    for s in subjects.find().sort("code", 1):
        if user.get("role") == "faculty" and s.get("created_by") != user["username"]:
            continue
        if not s.get("join_code"):
            subjects.update_one(
                {"_id": s["_id"]},
                {"$set": {"join_code": new_join_code()}}
            )
            s["join_code"] = subjects.find_one(
                {"_id": s["_id"]}, {"join_code": 1}
            ).get("join_code")

        enrolled = user.get("role") == "faculty" or bool(
            enrollments.find_one({
                "subject_id": s["_id"],
                "username": user["username"]
            })
        )
        if user.get("role") == "student" and not enrolled:
            continue
        if str(s["_id"]) in hidden_subjects:
            continue

        topic_count = db["topics"].count_documents({"subject_id": s["_id"]})
        passed_count = student_progress.count_documents({
            "username": user["username"],
            "subject_id": s["_id"],
            "passed": True,
        })
        progress = round((passed_count / topic_count) * 100) if topic_count else 0
        out.append({
            "id": str(s["_id"]),
            "name": s.get("name", ""),
            "code": s.get("code", ""),
            "category": s.get("category", ""),
            "section": s.get("section", ""),
            "term": s.get("term", ""),

            # Support older records created before these fields existed.
            "year_level": s.get("year_level", ""),
            "academic_year": s.get(
                "academic_year",
                s.get("year", "")
            ),
            "join_code": s.get("join_code", ""),
            "enrolled": enrolled,
            "progress": progress
        })

    return jsonify(out), 200


@app.get("/api/student/progress")
def student_progress_summary():
    if "user" not in session:
        return jsonify(error="Not logged in"), 401

    user = users.find_one({"username": session["user"]})
    if not user:
        session.clear()
        return jsonify(error="Not logged in"), 401
    if user.get("role") != "student":
        return jsonify(error="Students only"), 403

    enrolled_ids = [
        enrollment["subject_id"]
        for enrollment in enrollments.find(
            {"username": user["username"]}, {"subject_id": 1}
        )
    ]
    result = []
    for subject in subjects.find({"_id": {"$in": enrolled_ids}}).sort("code", 1):
        subject_topics = list(
            topics.find({"subject_id": subject["_id"]}).sort("_id", 1)
        )
        topic_ids = [topic["_id"] for topic in subject_topics]
        quizzes_by_topic = {
            quiz["topic_id"]: quiz
            for quiz in quizzes.find(
                {"topic_id": {"$in": topic_ids}},
                {"_id": 1, "topic_id": 1},
            )
        } if topic_ids else {}
        quiz_ids = [quiz["_id"] for quiz in quizzes_by_topic.values()]
        attempts_by_quiz = {}
        if quiz_ids:
            for attempt in quiz_attempts.find({
                "username": user["username"],
                "quiz_id": {"$in": quiz_ids},
                "status": {"$in": ["completed", "expired"]},
            }).sort("finished_at", -1):
                attempts_by_quiz.setdefault(attempt["quiz_id"], []).append({
                    "score": float(attempt.get("score", 0) or 0),
                    "passed": bool(attempt.get("passed")),
                    "status": attempt.get("status", ""),
                    "finished_at": (
                        attempt["finished_at"].isoformat()
                        if hasattr(attempt.get("finished_at"), "isoformat")
                        else attempt.get("finished_at", "")
                    ),
                })

        passed_topics = student_progress.count_documents({
            "username": user["username"],
            "subject_id": subject["_id"],
            "passed": True,
        })
        topic_rows = []
        for topic in subject_topics:
            quiz = quizzes_by_topic.get(topic["_id"])
            topic_rows.append({
                "id": str(topic["_id"]),
                "title": topic.get("title", ""),
                "has_quiz": bool(quiz),
                "attempts": attempts_by_quiz.get(quiz["_id"], []) if quiz else [],
            })

        result.append({
            "id": str(subject["_id"]),
            "name": subject.get("name", ""),
            "code": subject.get("code", ""),
            "term": subject.get("term", ""),
            "year_level": subject.get("year_level", ""),
            "academic_year": subject.get(
                "academic_year", subject.get("year", "")
            ),
            "topic_count": len(subject_topics),
            "passed_topics": passed_topics,
            "progress": round(
                (passed_topics / len(subject_topics)) * 100
            ) if subject_topics else 0,
            "topics": topic_rows,
        })

    return jsonify(subjects=result), 200


@app.get("/api/subjects/hidden")
def list_hidden_subjects():
    if "user" not in session:
        return jsonify(error="Not logged in"), 401

    user = users.find_one({"username": session["user"]})
    if not user:
        session.clear()
        return jsonify(error="Not logged in"), 401

    hidden_ids = {
        str(subject_id)
        for subject_id in user.get("hidden_subjects", [])
    }
    out = []
    for subject in subjects.find().sort("code", 1):
        if str(subject["_id"]) not in hidden_ids:
            continue
        if user.get("role") == "faculty":
            accessible = subject.get("created_by") == user["username"]
        else:
            accessible = bool(enrollments.find_one({
                "subject_id": subject["_id"],
                "username": user["username"],
            }))
        if not accessible:
            continue
        out.append({
            "id": str(subject["_id"]),
            "name": subject.get("name", ""),
            "code": subject.get("code", ""),
            "category": subject.get("category", ""),
            "term": subject.get("term", ""),
            "year_level": subject.get("year_level", ""),
            "section": subject.get("section", ""),
            "academic_year": subject.get(
                "academic_year", subject.get("year", "")
            ),
            "join_code": subject.get("join_code", ""),
            "enrolled": True,
        })
    return jsonify(out), 200


@app.put("/api/subjects/<subject_id>/visibility")
def set_subject_visibility(subject_id):
    if "user" not in session:
        return jsonify(error="Not logged in"), 401

    user = users.find_one({"username": session["user"]})
    if not user:
        session.clear()
        return jsonify(error="Not logged in"), 401

    try:
        subject = subjects.find_one({"_id": ObjectId(subject_id)})
    except Exception:
        subject = None
    if not subject:
        return jsonify(error="Subject not found"), 404

    if user.get("role") == "faculty":
        accessible = subject.get("created_by") == user["username"]
    else:
        accessible = bool(enrollments.find_one({
            "subject_id": subject["_id"],
            "username": user["username"],
        }))
    if not accessible:
        return jsonify(error="You do not have access to this subject"), 403

    data = request.get_json(silent=True) or {}
    if not isinstance(data.get("hidden"), bool):
        return jsonify(error="Hidden must be true or false"), 400

    hidden_subjects = {
        str(value)
        for value in user.get("hidden_subjects", [])
    }
    if data["hidden"]:
        hidden_subjects.add(str(subject["_id"]))
    else:
        hidden_subjects.discard(str(subject["_id"]))

    users.update_one(
        {"_id": user["_id"]},
        {"$set": {"hidden_subjects": sorted(hidden_subjects)}},
    )
    return jsonify(ok=True, hidden=data["hidden"]), 200


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
        "category": d.get("category", "").strip()
            if isinstance(d.get("category", ""), str) else "",
        "section": d.get("section", "").strip()
            if isinstance(d.get("section", ""), str) else "",
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

    fields["join_code"] = new_join_code()
    fields["created_by"] = user["username"]
    subjects.insert_one(fields)

    return jsonify(ok=True, join_code=fields["join_code"]), 201


@app.put("/api/subjects/<subject_id>")
def update_subject(subject_id):
    if "user" not in session:
        return jsonify(error="Not logged in"), 401

    user = users.find_one({"username": session["user"]})
    if not user:
        session.clear()
        return jsonify(error="Not logged in"), 401
    if user.get("role") != "faculty":
        return jsonify(error="Faculty only"), 403

    try:
        object_id = ObjectId(subject_id)
    except Exception:
        return jsonify(error="Invalid subject"), 400

    subject = subjects.find_one({"_id": object_id})
    if not subject:
        return jsonify(error="Subject not found"), 404
    if subject.get("created_by") != user["username"]:
        return jsonify(error="You can only edit your own subjects"), 403

    d = request.get_json(silent=True) or {}
    fields = {
        "name": d.get("name", "").strip()
            if isinstance(d.get("name", ""), str) else "",
        "code": d.get("code", "").strip()
            if isinstance(d.get("code", ""), str) else "",
        "category": d.get("category", "").strip()
            if isinstance(d.get("category", ""), str) else "",
        "section": d.get("section", "").strip()
            if isinstance(d.get("section", ""), str) else "",
        "term": d.get("term", "").strip()
            if isinstance(d.get("term", ""), str) else "",
        "year_level": d.get("year_level", "").strip()
            if isinstance(d.get("year_level", ""), str) else "",
        "academic_year": d.get("academic_year", "").strip()
            if isinstance(d.get("academic_year", ""), str) else ""
    }

    if not all(fields.values()):
        return jsonify(error="All fields are required"), 400
    if fields["term"] not in ("1st Semester", "2nd Semester", "Summer"):
        return jsonify(error="Invalid semester"), 400
    if fields["year_level"] not in (
        "1st Year", "2nd Year", "3rd Year", "4th Year"
    ):
        return jsonify(error="Invalid year level"), 400

    import re

    if not re.fullmatch(r"\d{4}-\d{4}", fields["academic_year"]):
        return jsonify(
            error="Academic year must use the format YYYY-YYYY"
        ), 400

    start_year, end_year = map(int, fields["academic_year"].split("-"))
    if end_year != start_year + 1:
        return jsonify(
            error="Academic year must contain consecutive years"
        ), 400

    subjects.update_one({"_id": object_id}, {"$set": fields})
    return jsonify(ok=True), 200


@app.delete("/api/subjects/<subject_id>")
def delete_subject(subject_id):
    if "user" not in session:
        return jsonify(error="Not logged in"), 401

    user = users.find_one({"username": session["user"]})
    if not user:
        session.clear()
        return jsonify(error="Not logged in"), 401
    if user.get("role") != "faculty":
        return jsonify(error="Faculty only"), 403

    try:
        object_id = ObjectId(subject_id)
    except Exception:
        return jsonify(error="Invalid subject"), 400

    subject = subjects.find_one({"_id": object_id})
    if not subject:
        return jsonify(error="Subject not found"), 404
    if subject.get("created_by") != user["username"]:
        return jsonify(error="You can only delete your own subjects"), 403

    topic_ids = [
        topic["_id"]
        for topic in db["topics"].find(
            {"subject_id": object_id}, {"_id": 1}
        )
    ]
    quiz_ids = [
        quiz["_id"]
        for quiz in db["quizzes"].find(
            {"topic_id": {"$in": topic_ids}}, {"_id": 1}
        )
    ] if topic_ids else []
    db["subjects"].delete_one({"_id": object_id})
    enrollments.delete_many({"subject_id": object_id})
    db["topics"].delete_many({"subject_id": object_id})
    if quiz_ids:
        db["quizzes"].delete_many({"_id": {"$in": quiz_ids}})
        db["quiz_attempts"].delete_many({"quiz_id": {"$in": quiz_ids}})
    if topic_ids:
        db["student_progress"].delete_many({"topic_id": {"$in": topic_ids}})
    users.update_many(
        {},
        {"$pull": {"hidden_subjects": str(object_id)}},
    )

    return jsonify(ok=True), 200


@app.post("/api/subjects/<subject_id>/enroll")
def enroll_in_subject(subject_id):
    if "user" not in session:
        return jsonify(error="Not logged in"), 401

    user = users.find_one({"username": session["user"]})
    if not user:
        session.clear()
        return jsonify(error="Not logged in"), 401
    if user.get("role") != "student":
        return jsonify(error="Only students can enroll"), 403

    try:
        subject = subjects.find_one({"_id": ObjectId(subject_id)})
    except Exception:
        subject = None
    if not subject:
        return jsonify(error="Subject not found"), 404

    join_code = request.get_json(silent=True) or {}
    join_code = join_code.get("join_code", "")
    if not isinstance(join_code, str) or join_code.strip().upper() != subject.get("join_code"):
        return jsonify(error="That subject join code is incorrect"), 403

    enrollments.update_one(
        {"subject_id": subject["_id"], "username": user["username"]},
        {"$setOnInsert": {
            "subject_id": subject["_id"],
            "username": user["username"],
            "enrolled_at": datetime.now(timezone.utc),
        }},
        upsert=True
    )
    return jsonify(ok=True, enrolled=True)


@app.post("/api/subjects/enroll")
def enroll_by_join_code():
    if "user" not in session:
        return jsonify(error="Not logged in"), 401

    user = users.find_one({"username": session["user"]})
    if not user:
        session.clear()
        return jsonify(error="Not logged in"), 401
    if user.get("role") != "student":
        return jsonify(error="Only students can enroll"), 403

    data = request.get_json(silent=True) or {}
    join_code = data.get("join_code", "")
    if not isinstance(join_code, str) or not join_code.strip():
        return jsonify(error="Subject code is required"), 400

    subject = subjects.find_one({"join_code": join_code.strip().upper()})
    if not subject:
        return jsonify(error="No subject was found for that code"), 404

    enrollments.update_one(
        {"subject_id": subject["_id"], "username": user["username"]},
        {"$setOnInsert": {
            "subject_id": subject["_id"],
            "username": user["username"],
            "enrolled_at": datetime.now(timezone.utc),
        }},
        upsert=True
    )
    return jsonify(
        ok=True,
        enrolled=True,
        subject={"id": str(subject["_id"]), "name": subject.get("name", "")}
    )


@app.get("/api/subjects/<subject_id>/people")
def subject_people(subject_id):
    if "user" not in session:
        return jsonify(error="Not logged in"), 401

    user = users.find_one({"username": session["user"]})
    if not user:
        session.clear()
        return jsonify(error="Not logged in"), 401

    try:
        subject = subjects.find_one({"_id": ObjectId(subject_id)})
    except Exception:
        subject = None
    if not subject:
        return jsonify(error="Subject not found"), 404
    if user.get("role") == "faculty" and subject.get("created_by") != user["username"]:
        return jsonify(error="You can only view people in your own subjects"), 403
    if user.get("role") == "student" and not enrollments.find_one({
        "subject_id": subject["_id"],
        "username": user["username"],
    }):
        return jsonify(error="Join this subject with its join code first"), 403

    enrolled = list(enrollments.find(
        {"subject_id": subject["_id"]},
        {"_id": 0, "username": 1, "enrolled_at": 1}
    ).sort("username", 1))
    return jsonify(
        faculty=[{"username": subject.get("created_by", "")}]
        if subject.get("created_by") else [],
        students=[
            {"username": person["username"]}
            for person in enrolled
        ]
    )


@app.delete("/api/subjects/<subject_id>/students/<username>")
def remove_subject_student(subject_id, username):
    if "user" not in session:
        return jsonify(error="Not logged in"), 401

    user = users.find_one({"username": session["user"]})
    if not user:
        session.clear()
        return jsonify(error="Not logged in"), 401
    if user.get("role") != "faculty":
        return jsonify(error="Faculty only"), 403

    try:
        subject = subjects.find_one({"_id": ObjectId(subject_id)})
    except Exception:
        subject = None
    if not subject:
        return jsonify(error="Subject not found"), 404
    if subject.get("created_by") != user["username"]:
        return jsonify(error="You can only manage your own subjects"), 403
    if username == subject.get("created_by"):
        return jsonify(error="The subject owner cannot be removed"), 403

    result = enrollments.delete_one({
        "subject_id": subject["_id"],
        "username": username,
    })
    if not result.deleted_count:
        return jsonify(error="Student is not enrolled in this subject"), 404

    topic_ids = [
        topic["_id"]
        for topic in db["topics"].find(
            {"subject_id": subject["_id"]}, {"_id": 1}
        )
    ]
    if topic_ids:
        quiz_ids = [
            quiz["_id"]
            for quiz in db["quizzes"].find(
                {"topic_id": {"$in": topic_ids}}, {"_id": 1}
            )
        ]
        db["student_progress"].delete_many({
            "username": username,
            "topic_id": {"$in": topic_ids},
        })
        if quiz_ids:
            db["quiz_attempts"].delete_many({
                "username": username,
                "quiz_id": {"$in": quiz_ids},
            })

    return jsonify(ok=True), 200


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(debug=True)