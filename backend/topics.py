
from flask import request, session, jsonify, send_from_directory
from bson import ObjectId
from werkzeug.utils import secure_filename
from functools import wraps
from pathlib import Path
from datetime import datetime, timezone, timedelta
import csv
import io
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
    enrollments = db["enrollments"]
    quizzes = db["quizzes"]
    attempts = db["quiz_attempts"]
    progress = db["student_progress"]

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
            topic_id = kwargs.get("topic_id")
            subject_id = kwargs.get("subject_id")
            subject = None
            if topic_id:
                topic = get_topic(topic_id)
                subject = get_subject(str(topic["subject_id"])) if topic else None
            elif subject_id:
                subject = get_subject(subject_id)
            if not subject:
                return jsonify(error="Subject not found"), 404
            if subject.get("created_by") != user["username"]:
                return jsonify(error="You can only manage your own subjects"), 403
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
            "description": topic.get("description", ""),
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

    def student_enrolled(user, subject):
        return user.get("role") != "student" or bool(enrollments.find_one({
            "subject_id": subject["_id"],
            "username": user["username"],
        }))

    def faculty_owns_topic(user, topic):
        if not topic:
            return False
        subject = get_subject(str(topic["subject_id"]))
        return bool(subject and subject.get("created_by") == user["username"])

    def now():
        return datetime.now(timezone.utc)

    def utc_datetime(value):
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def topic_order(topic):
        return list(topics.find({"subject_id": topic["subject_id"]}).sort("_id", 1))

    def passed_topic(username, topic):
        return bool(progress.find_one({
            "username": username, "topic_id": topic["_id"], "passed": True
        }))

    def topic_is_unlocked(username, topic):
        ordered = topic_order(topic)
        try:
            index = next(i for i, item in enumerate(ordered)
                         if item["_id"] == topic["_id"])
        except StopIteration:
            return False
        return index == 0 or passed_topic(username, ordered[index - 1])

    def student_topic_status(username, topic):
        if passed_topic(username, topic):
            return "passed"
        return "unlocked" if topic_is_unlocked(username, topic) else "locked"

    def public_question(question):
        result = {
            "id": question["id"],
            "text": question["text"],
            "type": question["type"],
        }
        if question.get("choices"):
            result["choices"] = question["choices"]
        return result

    def public_quiz(quiz, include_answers=False):
        result = {
            "id": str(quiz["_id"]),
            "topic_id": str(quiz["topic_id"]),
            "question_count": len(quiz["questions"]),
            "questions": [public_question(q) for q in quiz["questions"]],
            "updated_at": quiz.get("updated_at"),
        }
        if include_answers:
            result["questions"] = [
                dict(public_question(q), correct_answer=q["correct_answer"])
                for q in quiz["questions"]
            ]
        return result

    def validate_quiz(data):
        if not isinstance(data, dict):
            return None, "Request body must be a JSON object"
        questions = data.get("questions")
        if not isinstance(questions, list) or not 10 <= len(questions) <= 20:
            return None, "A quiz must contain 10 to 20 questions"
        cleaned = []
        for number, item in enumerate(questions, 1):
            if not isinstance(item, dict):
                return None, f"Question {number} must be an object"
            text = item.get("text", item.get("question", ""))
            kind = item.get("type", "multiple_choice")
            if not isinstance(text, str) or not text.strip() or len(text.strip()) > 5000:
                return None, f"Question {number} text is required and must be 5000 characters or fewer"
            if kind not in ("multiple_choice", "simple", "practical"):
                return None, f"Question {number} has an invalid type"
            choices = item.get("choices", [])
            if choices is None:
                choices = []
            if not isinstance(choices, list) or (choices and not 2 <= len(choices) <= 10):
                return None, f"Question {number} needs 2 to 10 choices when choices are supplied"
            if any(not isinstance(c, str) or not c.strip() or len(c.strip()) > 1000
                   for c in choices) or len({c.strip() for c in choices}) != len(choices):
                return None, f"Question {number} has invalid or duplicate choices"
            choices = [c.strip() for c in choices]
            answer = item.get("correct_answer")
            if not isinstance(answer, str) or not answer.strip() or len(answer.strip()) > 1000:
                return None, f"Question {number} correct_answer is required"
            answer = answer.strip()
            if choices and answer not in choices:
                return None, f"Question {number} correct_answer must match a choice"
            cleaned.append({
                "id": str(item.get("id") or uuid.uuid4().hex),
                "text": text.strip(),
                "type": kind,
                "choices": choices,
                "correct_answer": answer,
            })
        return {"questions": cleaned}, None

    def answer_value(question, answer):
        if isinstance(answer, int) and not isinstance(answer, bool):
            choices = question.get("choices", [])
            return choices[answer] if 0 <= answer < len(choices) else None
        return answer.strip() if isinstance(answer, str) else None

    def topic_quiz(topic):
        return quizzes.find_one({"topic_id": topic["_id"]})

    @app.route("/api/topics/<topic_id>/quiz", methods=["POST", "PUT"])
    @require_login
    @require_faculty
    def save_quiz(user, topic_id):
        topic = get_topic(topic_id)
        if not topic:
            return jsonify(error="Topic not found"), 404
        quiz_data, error = validate_quiz(request.get_json(silent=True) or {})
        if error:
            return jsonify(error=error), 400
        existing = topic_quiz(topic)
        if request.method == "POST" and existing:
            return jsonify(error="This topic already has a quiz; use PUT to update it"), 409
        if existing and attempts.count_documents({
            "quiz_id": existing["_id"],
            "status": "in_progress",
        }):
            return jsonify(
                error="Cannot edit a quiz with active student attempts"
            ), 409
        stamp = now()
        if existing:
            quizzes.update_one({"_id": existing["_id"]}, {"$set": {
                **quiz_data, "updated_at": stamp, "updated_by": user["username"]
            }})
            saved = topic_quiz(topic)
        else:
            result = quizzes.insert_one({
                **quiz_data, "topic_id": topic["_id"], "created_by": user["username"],
                "created_at": stamp, "updated_at": stamp,
            })
            saved = quizzes.find_one({"_id": result.inserted_id})
        return jsonify(ok=True, quiz=public_quiz(saved, include_answers=True)), 201 if not existing else 200

    @app.delete("/api/topics/<topic_id>/quiz")
    @require_login
    @require_faculty
    def delete_quiz(user, topic_id):
        topic = get_topic(topic_id)
        if not topic:
            return jsonify(error="Topic not found"), 404
        quiz = topic_quiz(topic)
        if not quiz:
            return jsonify(error="Quiz not found"), 404
        active = attempts.count_documents({"quiz_id": quiz["_id"], "status": "in_progress"})
        if active:
            return jsonify(error="Cannot delete a quiz with active student attempts"), 409
        quizzes.delete_one({"_id": quiz["_id"]})
        attempts.delete_many({"quiz_id": quiz["_id"]})
        progress.delete_many({"topic_id": topic["_id"]})
        return jsonify(ok=True)

    def load_quiz_for_user(user, topic_id):
        topic = get_topic(topic_id)
        if not topic:
            return jsonify(error="Topic not found"), 404
        subject = get_subject(str(topic["subject_id"]))
        if user.get("role") == "faculty" and not faculty_owns_topic(user, topic):
            return jsonify(error="You can only view quizzes in your own subjects"), 403
        if subject and not student_enrolled(user, subject):
            return jsonify(error="Join this subject with its join code before taking quizzes"), 403
        quiz = topic_quiz(topic)
        if not quiz:
            return jsonify(error="Quiz not found"), 404
        if user.get("role") == "student" and not topic_is_unlocked(user["username"], topic):
            return jsonify(error="Topic is locked until the previous topic is passed"), 403
        if user.get("role") != "student":
            return jsonify(quiz=public_quiz(quiz, include_answers=True))
        active = attempts.find_one({
            "quiz_id": quiz["_id"], "username": user["username"], "status": "in_progress"
        }, sort=[("started_at", -1)])
        if not active:
            active_started_at = now()
            active_id = attempts.insert_one({
                "quiz_id": quiz["_id"], "topic_id": topic["_id"],
                "subject_id": topic["subject_id"], "username": user["username"],
                "started_at": active_started_at, "status": "in_progress",
                "question_ids": [q["id"] for q in quiz["questions"]],
            }).inserted_id
            active = attempts.find_one({"_id": active_id})
        response = public_quiz(quiz)
        response["attempt_id"] = str(active["_id"])
        return jsonify(quiz=response)

    @app.get("/api/topics/<topic_id>/quiz")
    @require_login
    def fetch_quiz(user, topic_id):
        return load_quiz_for_user(user, topic_id)

    @app.post("/api/topics/<topic_id>/quiz/start")
    @require_login
    def start_quiz(user, topic_id):
        return load_quiz_for_user(user, topic_id)

    @app.post("/api/topics/<topic_id>/quiz/submit")
    @require_login
    def submit_quiz(user, topic_id):
        if user.get("role") != "student":
            return jsonify(error="Students only"), 403
        topic = get_topic(topic_id)
        if not topic:
            return jsonify(error="Topic not found"), 404
        subject = get_subject(str(topic["subject_id"]))
        if subject and not student_enrolled(user, subject):
            return jsonify(error="Join this subject with its join code before submitting quizzes"), 403
        quiz = topic_quiz(topic)
        if not quiz:
            return jsonify(error="Quiz not found"), 404
        data = request.get_json(silent=True) or {}
        attempt_oid = oid(data.get("attempt_id", ""))
        raw_answers = data.get("answers")
        if attempt_oid is None or not isinstance(raw_answers, dict):
            return jsonify(error="attempt_id and answers object are required"), 400
        attempt = attempts.find_one({
            "_id": attempt_oid, "quiz_id": quiz["_id"], "topic_id": topic["_id"],
            "username": user["username"]
        })
        if not attempt:
            return jsonify(error="Attempt not found"), 404
        if attempt["status"] != "in_progress":
            return jsonify(error="Attempt is no longer active"), 409
        finished = now()
        valid_ids = {q["id"] for q in quiz["questions"]}
        if any(not isinstance(key, str) or key not in valid_ids for key in raw_answers):
            return jsonify(error="Answers contain an unknown question id"), 400
        if len(raw_answers) > len(valid_ids):
            return jsonify(error="Too many answers"), 400
        correct = total = 0
        submitted = {}
        for question in quiz["questions"]:
            if question["id"] not in raw_answers:
                continue
            value = answer_value(question, raw_answers[question["id"]])
            if value is None:
                return jsonify(error=f"Invalid answer for question {question['id']}"), 400
            submitted[question["id"]] = value
            total += 1
            if value.strip().casefold() == question["correct_answer"].strip().casefold():
                correct += 1
        score = round((correct / len(quiz["questions"])) * 100, 2)
        passed = score >= 75
        finalized = attempts.update_one(
            {"_id": attempt["_id"], "status": "in_progress"},
            {"$set": {
                "status": "completed", "finished_at": finished,
                "answers": submitted, "correct_count": correct,
                "answered_count": total, "score": score, "passed": passed
            }},
        )
        if finalized.modified_count != 1:
            return jsonify(error="Attempt is no longer active"), 409
        progress.update_one(
            {"username": user["username"], "topic_id": topic["_id"]},
            {"$set": {
                "username": user["username"], "topic_id": topic["_id"],
                "subject_id": topic["subject_id"], "passed": passed or passed_topic(user["username"], topic),
                "last_score": score, "updated_at": finished
            }}, upsert=True
        )
        ordered_topics = topic_order(topic)
        next_topic_id = None
        for index, ordered_topic in enumerate(ordered_topics):
            if ordered_topic["_id"] == topic["_id"] and index + 1 < len(ordered_topics):
                next_topic_id = str(ordered_topics[index + 1]["_id"])
                break
        return jsonify(ok=True, score=score, correct=correct,
                       total=len(quiz["questions"]), passed=passed,
                       passing_score=75, attempt_id=str(attempt["_id"]),
                       next_topic_id=next_topic_id)

    @app.get("/api/topics/<topic_id>/quiz/history")
    @require_login
    def quiz_history(user, topic_id):
        topic = get_topic(topic_id)
        if not topic:
            return jsonify(error="Topic not found"), 404
        quiz = topic_quiz(topic)
        if not quiz:
            return jsonify(error="Quiz not found"), 404
        query = {"quiz_id": quiz["_id"]}
        if user.get("role") == "student":
            query["username"] = user["username"]
        rows = []
        for attempt in attempts.find(query, {
            "answers": 0, "question_ids": 0
        }).sort("started_at", -1):
            rows.append({
                "id": str(attempt["_id"]), "username": attempt.get("username"),
                "status": attempt.get("status"), "score": attempt.get("score", 0),
                "passed": bool(attempt.get("passed")),
                "started_at": attempt.get("started_at"),
                "finished_at": attempt.get("finished_at"),
            })
        return jsonify(attempts=rows)

    @app.get("/api/topics/<topic_id>/quiz/attempts")
    @require_login
    @require_faculty
    def quiz_attempts(user, topic_id):
        topic = get_topic(topic_id)
        if not topic:
            return jsonify(error="Topic not found"), 404
        quiz = topic_quiz(topic)
        if not quiz:
            return jsonify(error="Quiz not found"), 404
        rows = []
        for attempt in attempts.find({"quiz_id": quiz["_id"], "status": {"$in": ["completed", "expired"]}}).sort("finished_at", -1):
            rows.append({
                "id": str(attempt["_id"]), "username": attempt["username"],
                "score": attempt.get("score", 0), "passed": bool(attempt.get("passed")),
                "status": attempt["status"], "started_at": attempt.get("started_at"),
                "finished_at": attempt.get("finished_at"),
            })
        return jsonify(topic_id=topic_id, attempts=rows)

    @app.get("/api/topics/<topic_id>/quiz/summary")
    @require_login
    @require_faculty
    def quiz_summary(user, topic_id):
        topic = get_topic(topic_id)
        if not topic:
            return jsonify(error="Topic not found"), 404
        quiz = topic_quiz(topic)
        if not quiz:
            return jsonify(error="Quiz not found"), 404
        completed = list(attempts.find({"quiz_id": quiz["_id"], "status": "completed"}))
        scores = [a.get("score", 0) for a in completed]
        return jsonify(topic_id=topic_id, question_count=len(quiz["questions"]),
                       attempt_count=len(completed),
                       passed_count=sum(bool(a.get("passed")) for a in completed),
                       average_score=round(sum(scores) / len(scores), 2) if scores else 0,
                       passing_score=75)

    @app.get("/api/topics/<topic_id>/quiz/report.csv")
    @require_login
    @require_faculty
    def quiz_report(user, topic_id):
        topic = get_topic(topic_id)
        if not topic:
            return jsonify(error="Topic not found"), 404
        quiz = topic_quiz(topic)
        if not quiz:
            return jsonify(error="Quiz not found"), 404
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["student", "score", "passed", "status", "started_at", "finished_at"])
        for attempt in attempts.find({"quiz_id": quiz["_id"]}).sort("finished_at", -1):
            writer.writerow([attempt.get("username", ""), attempt.get("score", 0),
                             "yes" if attempt.get("passed") else "no", attempt.get("status", ""),
                             attempt.get("started_at", ""), attempt.get("finished_at", "")])
        response = app.response_class(output.getvalue(), mimetype="text/csv")
        response.headers["Content-Disposition"] = f'attachment; filename="quiz-{topic_id}-attempts.csv"'
        return response

    @app.get("/api/subjects/<subject_id>/topics")
    @require_login
    def list_topics(user, subject_id):
        subject = get_subject(subject_id)
        if not subject:
            return jsonify(error="Subject not found"), 404
        if user.get("role") == "faculty" and subject.get("created_by") != user["username"]:
            return jsonify(error="You can only view your own subjects"), 403
        if not student_enrolled(user, subject):
            return jsonify(error="Join this subject with its join code before viewing lessons"), 403

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
                "category": subject.get("category", ""),
                "section": subject.get("section", ""),
                "join_code": (
                    subject.get("join_code", "")
                    if user.get("role") == "faculty" else ""
                ),
            },
            topics=[
                {
                    "id": str(t["_id"]),
                    "title": t.get("title", ""),
                    "description": t.get("description", ""),
                    "status": (
                        student_topic_status(user["username"], t)
                        if user.get("role") == "student" else "available"
                    ),
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
        description = data.get("description", "")

        if not isinstance(title, str) or not title.strip():
            return jsonify(error="Topic title is required"), 400
        if not isinstance(description, str) or len(description.strip()) > 1000:
            return jsonify(error="Topic description must be 1000 characters or fewer"), 400

        result = topics.insert_one({
            "subject_id": subject["_id"],
            "title": title.strip(),
            "description": description.strip(),
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

        subject = get_subject(str(topic["subject_id"]))
        if user.get("role") == "faculty" and not faculty_owns_topic(user, topic):
            return jsonify(error="You can only view lessons in your own subjects"), 403
        if subject and not student_enrolled(user, subject):
            return jsonify(error="Join this subject with its join code before viewing lessons"), 403

        if user.get("role") == "student":
            if not topic_is_unlocked(user["username"], topic):
                return jsonify(error="Topic is locked until the previous topic is passed"), 403

        payload = public_topic(topic)
        payload["has_quiz"] = bool(topic_quiz(topic))
        if user.get("role") == "student":
            payload["status"] = student_topic_status(user["username"], topic)
        return jsonify(topic=payload)

    @app.put("/api/topics/<topic_id>")
    @require_login
    @require_faculty
    def update_topic(user, topic_id):
        topic = get_topic(topic_id)
        if not topic:
            return jsonify(error="Topic not found"), 404

        data = request.get_json(silent=True) or {}

        updates = {}
        for key in ("title", "description", "content", "summary"):
            if key in data:
                if not isinstance(data[key], str):
                    return jsonify(error=f"{key} must be text"), 400
                updates[key] = data[key].strip() if key != "content" else data[key]

        if "title" in updates and not updates["title"]:
            return jsonify(error="Topic title is required"), 400
        if "description" in updates and len(updates["description"]) > 1000:
            return jsonify(error="Topic description must be 1000 characters or fewer"), 400

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

    @app.delete("/api/topics/<topic_id>")
    @require_login
    @require_faculty
    def delete_topic(user, topic_id):
        topic = get_topic(topic_id)
        if not topic:
            return jsonify(error="Topic not found"), 404

        quiz = topic_quiz(topic)
        if quiz:
            active = attempts.count_documents({
                "quiz_id": quiz["_id"],
                "status": "in_progress",
            })
            if active:
                return jsonify(
                    error="Cannot delete a topic with active student attempts"
                ), 409
            quizzes.delete_one({"_id": quiz["_id"]})
            attempts.delete_many({"quiz_id": quiz["_id"]})

        for presentation in topic.get("presentations", []):
            filename = presentation.get("filename", "")
            if re.fullmatch(r"[a-f0-9]+\.(pdf|ppt|pptx)", filename):
                (UPLOAD_DIR / filename).unlink(missing_ok=True)

        progress.delete_many({"topic_id": topic["_id"]})
        topics.delete_one({"_id": topic["_id"]})
        return jsonify(ok=True)

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
