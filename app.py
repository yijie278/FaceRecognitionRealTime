import base64
import io
import os
import pickle
import secrets
import csv
from datetime import datetime, date, timedelta
from werkzeug.utils import secure_filename

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, make_response
import cv2
import numpy as np
import face_recognition

import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
from firebase_admin import storage

# Configuration
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}
UPLOAD_FOLDER = 'Images'
SECRET_KEY = os.environ.get("FLASK_SECRET", secrets.token_hex(16))

def is_allowed_filename(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def convert_bgr_image_to_base64_png(image_bgr: np.ndarray) -> str:
    _, buffer = cv2.imencode(".png", image_bgr)
    return base64.b64encode(buffer).decode("utf-8")

def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = SECRET_KEY
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

    # Initialize Firebase
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
        app.logger.warning("EncodeFile.p not found. Run EncodeGenerator.py first to generate encodings.")
        encode_list_known = []
        student_ids = []
    else:
        with open(encode_file_path, "rb") as f:
            encode_list_known, student_ids = pickle.load(f)

    # Helper function to check admin login
    def check_admin():
        return session.get('admin_logged_in', False)

    # Helper function to regenerate encodings
    def regenerate_encodings():
        try:
            # Import and run the encoding generator
            import subprocess
            result = subprocess.run(['python', 'EncodeGenerator.py'], capture_output=True, text=True)
            if result.returncode == 0:
                # Reload encodings
                with open(encode_file_path, "rb") as f:
                    encode_list_known, student_ids = pickle.load(f)
                return True
            return False
        except Exception as e:
            app.logger.error(f"Error regenerating encodings: {e}")
            return False

    # Routes
    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/admin/login', methods=['GET', 'POST'])
    def admin_login():
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            
            # Simple hardcoded admin credentials (in production, use proper authentication)
            if username == 'admin' and password == 'admin123':
                session['admin_logged_in'] = True
                flash('Successfully logged in as admin!', 'success')
                return redirect(url_for('admin_dashboard'))
            else:
                flash('Invalid credentials!', 'error')
        
        return render_template('admin_login.html')

    @app.route('/admin/logout')
    def admin_logout():
        session.pop('admin_logged_in', None)
        flash('Logged out successfully!', 'info')
        return redirect(url_for('index'))

    @app.route('/admin/dashboard')
    def admin_dashboard():
        if not check_admin():
            flash('Please login as admin first!', 'error')
            return redirect(url_for('admin_login'))
        
        # Get all students from Firebase
        students_ref = db.reference('Students')
        students = students_ref.get() or {}
        
        return render_template('admin_dashboard.html', students=students)

    @app.route('/admin/add_student', methods=['GET', 'POST'])
    def add_student():
        if not check_admin():
            flash('Please login as admin first!', 'error')
            return redirect(url_for('admin_login'))
        
        if request.method == 'POST':
            student_id = request.form.get('student_id')
            name = request.form.get('name')
            major = request.form.get('major')
            year = request.form.get('year')
            standing = request.form.get('standing')
            starting_year = request.form.get('starting_year')
            
            # Handle image upload
            if 'image' not in request.files:
                flash('No image file provided!', 'error')
                return redirect(url_for('add_student'))
            
            file = request.files['image']
            if file.filename == '':
                flash('No image selected!', 'error')
                return redirect(url_for('add_student'))
            
            if not is_allowed_filename(file.filename):
                flash('Unsupported file type. Please upload PNG or JPG.', 'error')
                return redirect(url_for('add_student'))
            
            # Save image locally
            filename = secure_filename(f"{student_id}.{file.filename.rsplit('.', 1)[1].lower()}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Upload to Firebase Storage
            blob = bucket.blob(f"Images/{filename}")
            blob.upload_from_filename(filepath)
            
            # Add student data to Firebase Database
            student_data = {
                'name': name,
                'major': major,
                'year': int(year),
                'standing': standing,
                'starting_year': int(starting_year),
                'Total attendance': 0,
                'last_atttendance_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            students_ref = db.reference('Students')
            students_ref.child(student_id).set(student_data)
            
            flash(f'Student {name} added successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
        
        return render_template('add_student.html')

    @app.route('/admin/delete_student/<student_id>')
    def delete_student(student_id):
        if not check_admin():
            flash('Please login as admin first!', 'error')
            return redirect(url_for('admin_login'))
        
        try:
            # Delete from Firebase Database
            students_ref = db.reference('Students')
            students_ref.child(student_id).delete()
            
            # Delete image from Firebase Storage
            blob = bucket.blob(f"Images/{student_id}.png")
            if blob.exists():
                blob.delete()
            else:
                blob = bucket.blob(f"Images/{student_id}.jpg")
                if blob.exists():
                    blob.delete()
            
            # Delete local image
            for ext in ['png', 'jpg', 'jpeg']:
                local_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{student_id}.{ext}")
                if os.path.exists(local_path):
                    os.remove(local_path)
                    break
            
            flash(f'Student {student_id} deleted successfully!', 'success')
            
            # Regenerate encodings
            if regenerate_encodings():
                flash('Face encodings updated successfully!', 'info')
            else:
                flash('Warning: Could not update face encodings. Please run EncodeGenerator.py manually.', 'warning')
                
        except Exception as e:
            flash(f'Error deleting student: {str(e)}', 'error')
        
        return redirect(url_for('admin_dashboard'))

    @app.route('/attendance')
    def attendance():
        return render_template('attendance.html')

    @app.route('/attendance/scan', methods=['POST'])
    def scan_attendance():
        if 'image' not in request.files:
            return jsonify({'success': False, 'message': 'No image provided'})
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No image selected'})
        
        try:
            # Process the image
            file_bytes = np.frombuffer(file.read(), np.uint8)
            bgr_image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
            
            if bgr_image is None:
                return jsonify({'success': False, 'message': 'Could not read the image'})
            
            # Face recognition
            rgb_image = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)
            face_locations = face_recognition.face_locations(rgb_image)
            face_encodings = face_recognition.face_encodings(rgb_image, face_locations)
            
            if len(face_encodings) == 0:
                return jsonify({'success': False, 'message': 'No face detected'})
            
            if not encode_list_known:
                return jsonify({'success': False, 'message': 'No known encodings found'})
            
            # Find best match
            first_face_encoding = face_encodings[0]
            distances = face_recognition.face_distance(encode_list_known, first_face_encoding)
            match_index = int(np.argmin(distances))
            matches = face_recognition.compare_faces([encode_list_known[match_index]], first_face_encoding)
            
            if matches[0]:
                matched_id = student_ids[match_index]
                
                # Get student info
                student_info = db.reference(f"Students/{matched_id}").get()
                
                if student_info:
                    # Check if attendance already recorded today
                    today = date.today().strftime("%Y-%m-%d")
                    attendance_ref = db.reference(f"Attendance/{today}")
                    attendance_data = attendance_ref.get() or {}
                    
                    if matched_id not in attendance_data:
                        # Record attendance
                        attendance_data[matched_id] = {
                            'name': student_info['name'],
                            'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            'major': student_info.get('major', ''),
                            'year': student_info.get('year', '')
                        }
                        attendance_ref.set(attendance_data)
                        
                        # Update student's total attendance
                        ref = db.reference(f"Students/{matched_id}")
                        new_total = int(student_info.get("Total attendance", 0)) + 1
                        ref.child("Total attendance").set(new_total)
                        ref.child("last_atttendance_time").set(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                        
                        return jsonify({
                            'success': True,
                            'message': f'Attendance recorded for {student_info["name"]}',
                            'student': {
                                'id': matched_id,
                                'name': student_info['name'],
                                'major': student_info.get('major', ''),
                                'year': student_info.get('year', ''),
                                'total_attendance': new_total
                            }
                        })
                    else:
                        return jsonify({
                            'success': False,
                            'message': f'{student_info["name"]} has already marked attendance today'
                        })
                else:
                    return jsonify({'success': False, 'message': 'Student data not found'})
            else:
                return jsonify({'success': False, 'message': 'Face not recognized'})
                
        except Exception as e:
            return jsonify({'success': False, 'message': f'Error processing image: {str(e)}'})

    @app.route('/attendance/records')
    def attendance_records():
        if not check_admin():
            flash('Please login as admin first!', 'error')
            return redirect(url_for('admin_login'))
        
        # Get attendance records for the last 30 days
        attendance_records = {}
        for i in range(30):
            check_date = (date.today() - timedelta(days=i)).strftime("%Y-%m-%d")
            attendance_ref = db.reference(f"Attendance/{check_date}")
            day_records = attendance_ref.get()
            if day_records:
                attendance_records[check_date] = day_records
        
        # Calculate statistics
        total_days = len(attendance_records)
        total_attendance = sum(len(day_records) for day_records in attendance_records.values())
        
        # Get unique students
        unique_students = set()
        for day_records in attendance_records.values():
            unique_students.update(day_records.keys())
        unique_students_count = len(unique_students)
        
        return render_template('attendance_records.html', 
                             records=attendance_records,
                             total_days=total_days,
                             total_attendance=total_attendance,
                             unique_students_count=unique_students_count)

    @app.route('/attendance/export_csv')
    def export_attendance_csv():
        if not check_admin():
            flash('Please login as admin first!', 'error')
            return redirect(url_for('admin_login'))
        
        # Get attendance records for the last 30 days
        attendance_records = {}
        for i in range(30):
            check_date = (date.today() - timedelta(days=i)).strftime("%Y-%m-%d")
            attendance_ref = db.reference(f"Attendance/{check_date}")
            day_records = attendance_ref.get()
            if day_records:
                attendance_records[check_date] = day_records
        
        # Create CSV content
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Date', 'Student ID', 'Name', 'Major', 'Year', 'Time'])
        
        # Write data
        for date_str, day_records in attendance_records.items():
            for student_id, attendance_data in day_records.items():
                writer.writerow([
                    date_str,
                    student_id,
                    attendance_data.get('name', ''),
                    attendance_data.get('major', ''),
                    attendance_data.get('year', ''),
                    attendance_data.get('time', '')
                ])
        
        # Create response
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=attendance_records_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        
        return response

    @app.route('/attendance/analytics')
    def attendance_analytics():
        if not check_admin():
            flash('Please login as admin first!', 'error')
            return redirect(url_for('admin_login'))
        
        # Get attendance records for analytics
        attendance_records = {}
        for i in range(30):
            check_date = (date.today() - timedelta(days=i)).strftime("%Y-%m-%d")
            attendance_ref = db.reference(f"Attendance/{check_date}")
            day_records = attendance_ref.get()
            if day_records:
                attendance_records[check_date] = day_records
        
        # Calculate analytics
        total_attendance = sum(len(day_records) for day_records in attendance_records.values())
        total_days = len(attendance_records)
        
        # Get unique students
        unique_students = set()
        for day_records in attendance_records.values():
            unique_students.update(day_records.keys())
        
        # Calculate average attendance per day
        avg_attendance = total_attendance / total_days if total_days > 0 else 0
        
        # Get student attendance counts
        student_attendance_counts = {}
        for day_records in attendance_records.values():
            for student_id in day_records.keys():
                student_attendance_counts[student_id] = student_attendance_counts.get(student_id, 0) + 1
        
        analytics_data = {
            'total_attendance': total_attendance,
            'total_days': total_days,
            'unique_students': len(unique_students),
            'avg_attendance_per_day': round(avg_attendance, 2),
            'student_attendance_counts': student_attendance_counts,
            'records': attendance_records
        }
        
        return render_template('attendance_analytics.html', analytics=analytics_data)

    @app.route('/upload')
    def upload():
        return render_template('upload.html')

    @app.route('/match', methods=['POST'])
    def match():
        if "image" not in request.files:
            flash("No file part in the request.")
            return redirect(url_for("upload"))

        file = request.files["image"]
        if file.filename == "":
            flash("No file selected.")
            return redirect(url_for("upload"))

        if not is_allowed_filename(file.filename):
            flash("Unsupported file type. Please upload PNG or JPG.")
            return redirect(url_for("upload"))

        filename = secure_filename(file.filename)
        file_bytes = np.frombuffer(file.read(), np.uint8)
        bgr_image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        if bgr_image is None:
            flash("Could not read the uploaded image.")
            return redirect(url_for("upload"))

        # Face recognition logic (same as before)
        rgb_image = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_image)
        face_encodings = face_recognition.face_encodings(rgb_image, face_locations)

        if len(face_encodings) == 0:
            flash("No face detected in the image.")
            return redirect(url_for("upload"))

        if not encode_list_known:
            flash("No known encodings found. Generate encodings first.")
            return redirect(url_for("upload"))

        first_face_encoding = face_encodings[0]
        distances = face_recognition.face_distance(encode_list_known, first_face_encoding)
        match_index = int(np.argmin(distances))
        matches = face_recognition.compare_faces([encode_list_known[match_index]], first_face_encoding)

        matched = bool(matches[0])
        matched_id = student_ids[match_index] if matched else None

        student_info = None
        student_photo_base64 = None

        if matched_id is not None:
            student_info = db.reference(f"Students/{matched_id}").get()
            
            blob = bucket.get_blob(f"Images/{matched_id}.png")
            if blob is None:
                blob = bucket.get_blob(f"Images/{matched_id}.jpg")

            if blob is not None:
                array = np.frombuffer(blob.download_as_string(), np.uint8)
                img_student = cv2.imdecode(array, cv2.IMREAD_COLOR)
                if img_student is not None:
                    img_student = cv2.resize(img_student, (216, 216))
                    student_photo_base64 = convert_bgr_image_to_base64_png(img_student)

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
    # For public access, use 0.0.0.0 and set debug=False in production
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
