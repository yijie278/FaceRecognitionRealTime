import base64
import io
import os
import pickle

from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename

import cv2
import numpy as np
import face_recognition

import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
from firebase_admin import storage


ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}


def is_allowed_filename(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def convert_bgr_image_to_base64_png(image_bgr: np.ndarray) -> str:
    _, buffer = cv2.imencode(".png", image_bgr)
    return base64.b64encode(buffer).decode("utf-8")


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret-key")

    # Initialize Firebase (idempotent if already initialized in this process)
    if not firebase_admin._apps:
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(
            cred,
            {
                "databaseURL": "https://faceattendancerealtime-612a8-default-rtdb.firebaseio.com/",
                "storageBucket": "faceattendancerealtime-612a8.firebasestorage.app",
            },
        )

    bucket = storage.bucket()

    # Load encodings at startup
    encode_file_path = os.path.join(os.path.dirname(__file__), "EncodeFile.p")
    if not os.path.exists(encode_file_path):
        # Helpful message if encodings are missing
        app.logger.warning(
            "EncodeFile.p not found. Run EncodeGenerator.py first to generate encodings."
        )
        encode_list_known = []
        student_ids = []
    else:
        with open(encode_file_path, "rb") as f:
            encode_list_known, student_ids = pickle.load(f)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.post("/match")
    def match():
        if "image" not in request.files:
            flash("No file part in the request.")
            return redirect(url_for("index"))

        file = request.files["image"]
        if file.filename == "":
            flash("No file selected.")
            return redirect(url_for("index"))

        if not is_allowed_filename(file.filename):
            flash("Unsupported file type. Please upload PNG or JPG.")
            return redirect(url_for("index"))

        filename = secure_filename(file.filename)
        file_bytes = np.frombuffer(file.read(), np.uint8)
        bgr_image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        if bgr_image is None:
            flash("Could not read the uploaded image.")
            return redirect(url_for("index"))

        # Prepare for face encoding on uploaded image
        rgb_image = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_image)
        face_encodings = face_recognition.face_encodings(rgb_image, face_locations)

        if len(face_encodings) == 0:
            flash("No face detected in the image.")
            return redirect(url_for("index"))

        if not encode_list_known:
            flash("No known encodings found. Generate encodings first.")
            return redirect(url_for("index"))

        first_face_encoding = face_encodings[0]
        distances = face_recognition.face_distance(encode_list_known, first_face_encoding)
        match_index = int(np.argmin(distances))
        matches = face_recognition.compare_faces([encode_list_known[match_index]], first_face_encoding)

        matched = bool(matches[0])
        matched_id = student_ids[match_index] if matched else None

        student_info = None
        student_photo_base64 = None

        if matched_id is not None:
            # Fetch from Firebase Realtime Database
            student_info = db.reference(f"Students/{matched_id}").get()

            # Fetch image from Storage
            blob = bucket.get_blob(f"Images/{matched_id}.png")
            if blob is None:
                blob = bucket.get_blob(f"Images/{matched_id}.jpg")

            if blob is not None:
                array = np.frombuffer(blob.download_as_string(), np.uint8)
                img_student = cv2.imdecode(array, cv2.IMREAD_COLOR)
                if img_student is not None:
                    img_student = cv2.resize(img_student, (216, 216))
                    student_photo_base64 = convert_bgr_image_to_base64_png(img_student)

            # Optional: update attendance if last scan older than 30s
            if student_info:
                try:
                    last_time_str = student_info.get("last_atttendance_time")
                    if last_time_str:
                        last_dt = datetime.strptime(last_time_str, "%Y-%m-%d %H:%M:%S")
                        seconds_elapsed = (datetime.now() - last_dt).total_seconds()
                    else:
                        seconds_elapsed = 999999

                    if seconds_elapsed > 30:
                        ref = db.reference(f"Students/{matched_id}")
                        new_total = int(student_info.get("Total attendance", 0)) + 1
                        ref.child("Total attendance").set(new_total)
                        ref.child("last_atttendance_time").set(
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        )
                        # Refresh local copy for display
                        student_info = db.reference(f"Students/{matched_id}").get()
                except Exception as e:
                    app.logger.exception("Failed to update attendance: %s", e)

        # Render result
        uploaded_preview_base64 = convert_bgr_image_to_base64_png(bgr_image)
        return render_template(
            "result.html",
            matched=matched,
            matched_id=matched_id,
            student_info=student_info,
            uploaded_preview_base64=uploaded_preview_base64,
            student_photo_base64=student_photo_base64,
            distance=float(distances[match_index]) if len(distances) else None,
            filename=filename,
        )

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)




