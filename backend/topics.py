
from datetime import datetime, timezone

from bson import ObjectId
from flask import Blueprint, jsonify, request, session

topics_bp = Blueprint("topics", __name__, url_prefix="/api")


def get_current_user(db):
    username = session.get("user")

    if not username:
        return None

    return db["users"].find_one({"username": username})


def init_topics(app, db):
    topics = db["topics"]
    subjects = db["subjects"]

    @topics_bp.get("/subjects/<sid>/topics")
    def list_topics(sid):
        user = get_current_user(db)

        if not user:
            return jsonify(error="Not logged in"), 401

        subject_id = ObjectId(sid) if ObjectId.is_valid(sid) else None

        if subject_id is None:
            return jsonify(error="Invalid subject id"), 400

        subject = subjects.find_one({"_id": subject_id})

        if not subject:
            return jsonify(error="Subject not found"), 404

        docs = topics.find(
            {"subject": subject_id}
        ).sort("created_at", 1)

        topic_list = []

        for doc in docs:
            topic_list.append({
                "id": str(doc["_id"]),
                "title": doc["title"],
                "status": "not_started",
                "score": None
            })

        return jsonify({
            "subject": {
                "id": str(subject["_id"]),
                "name": subject.get("name", ""),
                "code": subject.get("code", ""),
                "term": subject.get("term", ""),
                "year_level": subject.get("year_level", ""),
                "academic_year": subject.get(
                    "academic_year",
                    subject.get("year", "")
                )
            },
            "topics": topic_list
        }), 200

    @topics_bp.post("/subjects/<sid>/topics")
    def add_topic(sid):
        user = get_current_user(db)

        if not user:
            return jsonify(error="Not logged in"), 401

        # Check the actual role saved in MongoDB.
        if str(user.get("role", "")).strip().lower() != "faculty":
            return jsonify(error="Faculty only"), 403

        subject_id = ObjectId(sid) if ObjectId.is_valid(sid) else None

        if subject_id is None:
            return jsonify(error="Invalid subject id"), 400

        if not subjects.find_one({"_id": subject_id}):
            return jsonify(error="Subject not found"), 404

        data = request.get_json(silent=True) or {}
        title = data.get("title", "")

        if not isinstance(title, str) or not title.strip():
            return jsonify(error="Title is required"), 400

        title = title.strip()

        doc = {
            "title": title,
            "subject": subject_id,
            "created_at": datetime.now(timezone.utc)
        }

        result = topics.insert_one(doc)

        return jsonify({
            "id": str(result.inserted_id),
            "title": title
        }), 201

    app.register_blueprint(topics_bp)
