
from flask import request, session, jsonify, send_from_directory
from bson import ObjectId
from werkzeug.utils import secure_filename
from functools import wraps
from pathlib import Path
import os
import re
import uuid

UPLOAD_DIR = Path(__file__).parent / "uploads" / "presentations"
ALLOWED_EXTENSIONS = {"pdf", "ppt", "pptx"}
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def init_topics(app, db):
    topics = db["topics"]
    users = db["users"]
    subjects = db["subjects"]

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    def current_user():
        username = session.get("user")
        if not username:
            return None
        return users.find_one({"username": username})

    def require_login(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                session.clear()
                return jsonify(error="Not logged in"), 401
            return fn(user, *args, **kwargs)
        return wrapper

    def require_faculty(fn):
        @wraps(fn)
        def wrapper(user, *args, **kwargs):
            if user.get("role") != "faculty":
                return jsonify(error="Faculty only"), 403
            return fn(user, *args, **kwargs)
        return wrapper

    def oid(value):
        try:
            return ObjectId(value)
        except Exception:
            return None

    def public_topic(topic):
        return {
            "id": str(topic["_id"]),
            "subject_id": str(topic["subject_id"]),
            "title": topic.get("title", ""),
            "content": topic.get("content", ""),
            "summary": topic.get("summary", ""),
            "slides": topic.get("slides", []),
            "presentations": topic.get("presentations", []),
            "status": "not_started",
            "created_at": topic.get("created_at", ""),
            "updated_at": topic.get("updated_at", ""),
        }

    def get_topic(topic_id):
        topic_oid = oid(topic_id)
        if topic_oid is None:
            return None
        return topics.find_one({"_id": topic_oid})

    def get_subject(subject_id):
        subject_oid = oid(subject_id)
        if subject_oid is None:
            return None
        return subjects.find_one({"_id": subject_oid})

    def faculty_owns_topic(user, topic):
        # Subjects in this app are shared across faculty.
        # Faculty role is checked separately by the decorators.
        return topic is not None

    @app.get("/api/subjects/<subject_id>/topics")
    @require_login
    def list_topics(user, subject_id):
        subject = get_subject(subject_id)
        if not subject:
            return jsonify(error="Subject not found"), 404

        found = topics.find(
            {"subject_id": subject["_id"]}
        ).sort("_id", 1)

        return jsonify(
            subject={
                "id": str(subject["_id"]),
                "name": subject.get("name", ""),
                "code": subject.get("code", ""),
                "term": subject.get("term", ""),
                "year_level": subject.get("year_level", ""),
                "academic_year": subject.get(
                    "academic_year", subject.get("year", "")
                ),
            },
            topics=[
                {
                    "id": str(t["_id"]),
                    "title": t.get("title", ""),
                    "status": "not_started",
                }
                for t in found
            ],
        )

    @app.post("/api/subjects/<subject_id>/topics")
    @require_login
    @require_faculty
    def create_topic(user, subject_id):
        subject = get_subject(subject_id)
        if not subject:
            return jsonify(error="Subject not found"), 404

        data = request.get_json(silent=True) or {}
        title = data.get("title", "")

        if not isinstance(title, str) or not title.strip():
            return jsonify(error="Topic title is required"), 400

        result = topics.insert_one({
            "subject_id": subject["_id"],
            "title": title.strip(),
            "content": "",
            "summary": "",
            "slides": [],
            "presentations": [],
            "created_by": user["username"],
        })

        return jsonify(
            ok=True,
            id=str(result.inserted_id),
            title=title.strip(),
        ), 201

    @app.get("/api/topics/<topic_id>")
    @require_login
    def get_topic_route(user, topic_id):
        topic = get_topic(topic_id)
        if not topic:
            return jsonify(error="Topic not found"), 404

        if user.get("role") == "student":
            # Students can view topics in existing subjects.
            pass

        return jsonify(topic=public_topic(topic))

    @app.put("/api/topics/<topic_id>")
    @require_login
    @require_faculty
    def update_topic(user, topic_id):
        topic = get_topic(topic_id)
        if not topic:
            return jsonify(error="Topic not found"), 404

        data = request.get_json(silent=True) or {}

        updates = {}
        for key in ("title", "content", "summary"):
            if key in data:
                if not isinstance(data[key], str):
                    return jsonify(error=f"{key} must be text"), 400
                updates[key] = data[key].strip() if key != "content" else data[key]

        if "title" in updates and not updates["title"]:
            return jsonify(error="Topic title is required"), 400

        if "slides" in data:
            slides = data["slides"]
            if not isinstance(slides, list) or len(slides) > 100:
                return jsonify(error="Invalid slides"), 400

            clean_slides = []
            for slide in slides:
                if not isinstance(slide, dict):
                    return jsonify(error="Invalid slide"), 400

                clean_slides.append({
                    "title": str(slide.get("title", ""))[:300],
                    "text": str(slide.get("text", ""))[:10000],
                    "image": str(slide.get("image", ""))[:4000000],
                })

            updates["slides"] = clean_slides

        if not updates:
            return jsonify(error="No lesson changes supplied"), 400

        topics.update_one(
            {"_id": topic["_id"]},
            {"$set": updates},
        )

        updated = get_topic(topic_id)
        return jsonify(ok=True, topic=public_topic(updated))

    @app.post("/api/topics/<topic_id>/presentations")
    @require_login
    @require_faculty
    def upload_presentation(user, topic_id):
        topic = get_topic(topic_id)
        if not topic:
            return jsonify(error="Topic not found"), 404

        file = request.files.get("file")
        if not file or not file.filename:
            return jsonify(error="Choose a presentation file"), 400

        original_name = secure_filename(file.filename)
        if "." not in original_name:
            return jsonify(error="Unsupported file type"), 400

        extension = original_name.rsplit(".", 1)[1].lower()
        if extension not in ALLOWED_EXTENSIONS:
            return jsonify(error="Only PDF, PPT, and PPTX are allowed"), 400

        file.stream.seek(0, os.SEEK_END)
        size = file.stream.tell()
        file.stream.seek(0)

        if size > MAX_UPLOAD_BYTES:
            return jsonify(error="File must be 25 MB or smaller"), 413

        stored_name = f"{uuid.uuid4().hex}.{extension}"
        file.save(UPLOAD_DIR / stored_name)

        presentation = {
            "id": uuid.uuid4().hex,
            "name": original_name,
            "filename": stored_name,
            "size": size,
            "url": f"/api/topics/{topic_id}/presentations/{stored_name}",
        }

        topics.update_one(
            {"_id": topic["_id"]},
            {"$push": {"presentations": presentation}},
        )

        return jsonify(ok=True, presentation=presentation), 201

    @app.get("/api/topics/<topic_id>/presentations/<filename>")
    @require_login
    def download_presentation(user, topic_id, filename):
        topic = get_topic(topic_id)
        if not topic:
            return jsonify(error="Topic not found"), 404

        allowed = any(
            p.get("filename") == filename
            for p in topic.get("presentations", [])
        )
        if not allowed or not re.fullmatch(r"[a-f0-9]+\.(pdf|ppt|pptx)", filename):
            return jsonify(error="Presentation not found"), 404

        return send_from_directory(
            UPLOAD_DIR,
            filename,
            as_attachment=False,
        )

    @app.delete("/api/topics/<topic_id>/presentations/<presentation_id>")
    @require_login
    @require_faculty
    def delete_presentation(user, topic_id, presentation_id):
        topic = get_topic(topic_id)
        if not topic:
            return jsonify(error="Topic not found"), 404

        presentation = next(
            (p for p in topic.get("presentations", [])
             if p.get("id") == presentation_id),
            None,
        )
        if not presentation:
            return jsonify(error="Presentation not found"), 404

        filename = presentation.get("filename", "")
        if re.fullmatch(r"[a-f0-9]+\.(pdf|ppt|pptx)", filename):
            (UPLOAD_DIR / filename).unlink(missing_ok=True)

        topics.update_one(
            {"_id": topic["_id"]},
            {"$pull": {"presentations": {"id": presentation_id}}},
        )
        return jsonify(ok=True)
