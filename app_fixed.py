import os
import cv2
import numpy as np
import face_recognition
import pickle
from datetime import datetime, date, timedelta
import io
import csv
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, make_response
import secrets

import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
from firebase_admin import storage

try:
    from simple_blink_detection import SimpleBlinkLivenessDetector as LivenessDetector
except ImportError:
    # Fallback to the complex version if simple one fails
    print("Warning: Could not import simple blink detection, using fallback")
    from liveness_detection_fixed import LivenessDetectorFixed as LivenessDetector

# Configuration
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}
UPLOAD_FOLDER = 'Images'
SECRET_KEY = os.environ.get("FLASK_SECRET", secrets.token_hex(16))

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Global variables for Firebase
firebase_available = False
bucket = None

# Initialize Firebase
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate("venv/serviceAccountKey.json")
        firebase_admin.initialize_app(
            cred,
            {
                "databaseURL": "https://faceattendancerealtime-612a8-default-rtdb.firebaseio.com/",
                "storageBucket": "faceattendancerealtime-612a8.firebasestorage.app",
            },
        )
    bucket = storage.bucket()
    firebase_available = True
    app.logger.info("Firebase initialized successfully")
except Exception as e:
    app.logger.error(f"Firebase initialization failed: {e}")
    firebase_available = False

# Mock student data for local fallback
mock_students = {
    "321654": {"name": "John Doe", "major": "Computer Science", "year": "3", "Total attendance": 15},
    "852741": {"name": "Jane Smith", "major": "Engineering", "year": "2", "Total attendance": 12},
    "963852": {"name": "Bob Johnson", "major": "Mathematics", "year": "4", "Total attendance": 18}
}

# Load known face encodings
try:
    with open('EncodeFile.p', 'rb') as file:
        encode_list_known_with_ids = pickle.load(file)
    encode_list_known, student_ids = encode_list_known_with_ids
    app.logger.info(f"Loaded {len(encode_list_known)} known face encodings")
except Exception as e:
    app.logger.error(f"Could not load face encodings: {e}")
    encode_list_known, student_ids = [], []

def check_admin():
    """Check if user is logged in as admin"""
    return session.get('admin_logged_in', False)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/attendance')
def attendance():
    return render_template('attendance.html')

@app.route('/attendance/scan', methods=['POST'])
def scan_attendance():
    """Simple attendance scanning with face recognition only"""
    global firebase_available
    
    try:
        # Get uploaded image
        if 'image' not in request.files:
            return jsonify({'success': False, 'message': 'No image uploaded'})
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No image selected'})
        
        # Read and process image
        image_data = file.read()
        nparr = np.frombuffer(image_data, np.uint8)
        bgr_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        rgb_image = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)
        
        # Find faces and encode them
        face_locations = face_recognition.face_locations(rgb_image)
        face_encodings = face_recognition.face_encodings(rgb_image, face_locations)
        
        if not face_encodings:
            return jsonify({'success': False, 'message': 'No face detected in image'})
        
        if not encode_list_known:
            return jsonify({'success': False, 'message': 'No known faces in database'})
        
        # Find best match
        first_face_encoding = face_encodings[0]
        distances = face_recognition.face_distance(encode_list_known, first_face_encoding)
        match_index = int(np.argmin(distances))
        matches = face_recognition.compare_faces([encode_list_known[match_index]], first_face_encoding)
        
        if matches[0]:
            matched_id = student_ids[match_index]
            
            # Get student info (Firebase or mock data)
            if firebase_available:
                try:
                    student_info = db.reference(f"Students/{matched_id}").get()
                except Exception as e:
                    app.logger.error(f"Firebase error: {e}")
                    student_info = mock_students.get(matched_id)
                    firebase_available = False
            else:
                student_info = mock_students.get(matched_id)
            
            if student_info:
                # Check if attendance already recorded today (24-hour check)
                current_time = datetime.now()
                today = current_time.strftime("%Y-%m-%d")
                
                if firebase_available:
                    try:
                        attendance_ref = db.reference(f"Attendance/{today}")
                        attendance_data = attendance_ref.get() or {}
                        
                        can_mark_attendance = True
                        if matched_id in attendance_data:
                            # Check if last attendance was within 24 hours
                            last_attendance_str = attendance_data[matched_id].get('time', '')
                            if last_attendance_str:
                                try:
                                    last_attendance = datetime.strptime(last_attendance_str, "%Y-%m-%d %H:%M:%S")
                                    time_diff = current_time - last_attendance
                                    if time_diff.total_seconds() < 24 * 3600:  # 24 hours in seconds
                                        can_mark_attendance = False
                                except ValueError:
                                    # If time parsing fails, allow attendance
                                    pass
                        
                        if can_mark_attendance:
                            # Record attendance in Firebase
                            attendance_data[matched_id] = {
                                'name': student_info['name'],
                                'time': current_time.strftime("%Y-%m-%d %H:%M:%S"),
                                'major': student_info.get('major', ''),
                                'year': student_info.get('year', '')
                            }
                            attendance_ref.set(attendance_data)
                            
                            # Update student's total attendance
                            ref = db.reference(f"Students/{matched_id}")
                            new_total = int(student_info.get("Total attendance", 0)) + 1
                            ref.child("Total attendance").set(new_total)
                            ref.child("last_atttendance_time").set(current_time.strftime("%Y-%m-%d %H:%M:%S"))
                            
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
                            # Attendance already marked within 24 hours
                            return jsonify({
                                'success': False,
                                'message': f'{student_info["name"]} has already marked attendance today. Please wait 24 hours.'
                            })
                    except Exception as e:
                        app.logger.error(f"Firebase error: {e}")
                        firebase_available = False
                        # Fall through to local mode
                
                # Process attendance in local mode (if Firebase failed or not available)
                return jsonify({
                    'success': True,
                    'message': f'Attendance recorded for {student_info["name"]} (Local Mode)',
                    'student': {
                        'id': matched_id,
                        'name': student_info['name'],
                        'major': student_info.get('major', 'Unknown'),
                        'year': student_info.get('year', 'Unknown'),
                        'total_attendance': student_info.get('Total attendance', 1)
                    }
                })
            else:
                return jsonify({'success': False, 'message': 'Student data not found'})
        else:
            return jsonify({'success': False, 'message': 'Face not recognized'})
            
    except Exception as e:
        app.logger.error(f"Error in attendance scan: {str(e)}")
        return jsonify({'success': False, 'message': f'Error processing image: {str(e)}'})

@app.route('/attendance/scan_multi_frame', methods=['POST'])
def scan_attendance_multi_frame():
    """Simple blink detection for liveness verification"""
    global firebase_available
    
    try:
        # Get JSON data containing multiple frames
        data = request.get_json()
        
        if not data or 'frames' not in data:
            return jsonify({'success': False, 'message': 'No frames provided'})
        
        frames_data = data['frames']
        if len(frames_data) < 3:  # Reduced from 5 to 3 for faster detection
            return jsonify({'success': False, 'message': 'At least 3 frames required for blink detection'})
        
        # Process frames
        frames = []
        
        for frame_data in frames_data:
            # Decode base64 image
            import base64
            image_data = base64.b64decode(frame_data.split(',')[1])  # Remove data:image/jpeg;base64, prefix
            nparr = np.frombuffer(image_data, np.uint8)
            bgr_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if bgr_image is None:
                continue
            
            frames.append(bgr_image)
        
        if len(frames) < 3:
            return jsonify({'success': False, 'message': 'Not enough valid frames processed'})
        
        # Use simple blink detection
        liveness_detector = LivenessDetector()
        liveness_result = liveness_detector.verify_liveness(frames)
        
        app.logger.info(f"Blink detection: {liveness_result.get('message', 'No message')}")
        app.logger.info(f"Blinks: {liveness_result.get('total_blinks', 0)}, Live: {liveness_result.get('is_live', False)}")
        
        # Check if detection is still in progress
        if not liveness_result.get('is_live', False) and liveness_result.get('progress', 0) < 1.0:
            return jsonify({
                'success': False,
                'message': liveness_result.get('message', 'Detecting blinks...'),
                'in_progress': True,
                'details': {
                    'blinks_detected': liveness_result.get('total_blinks', 0),
                    'blinks_required': liveness_detector.MIN_BLINKS_REQUIRED,
                    'time_elapsed': liveness_result.get('time_elapsed', 0),
                    'progress': liveness_result.get('progress', 0)
                }
            })
        
        # Check if liveness detection failed
        if not liveness_result.get('is_live', False):
            return jsonify({
                'success': False,
                'message': f'Please blink {liveness_detector.MIN_BLINKS_REQUIRED} times clearly to verify you are real. Try again.',
                'liveness_failed': True,
                'details': {
                    'blinks_detected': liveness_result.get('total_blinks', 0),
                    'blinks_required': liveness_detector.MIN_BLINKS_REQUIRED,
                    'time_elapsed': liveness_result.get('time_elapsed', 0)
                }
            })
        
        # Liveness passed! 
        app.logger.info(f"✅ REAL PERSON VERIFIED! Blinks detected: {liveness_result.get('total_blinks', 0)}")
        
        # Return immediate success for liveness verification
        return jsonify({
            'success': False,  # Not full success yet, just liveness passed
            'message': f'✅ Real person verified! Please click "Mark Attendance" to complete.',
            'liveness_passed': True,
            'liveness_details': {
                'blinks_detected': liveness_result.get('total_blinks', 0),
                'blinks_required': liveness_detector.MIN_BLINKS_REQUIRED,
                'time_elapsed': liveness_result.get('time_elapsed', 0),
                'confidence': liveness_result.get('confidence', 0)
            }
        })
            
    except Exception as e:
        import traceback
        app.logger.error(f"Error in multi-frame attendance scan: {str(e)}")
        app.logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({
            'success': False, 
            'message': f'Error processing frames: {str(e)}',
            'error_type': type(e).__name__
        })

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Simple admin credentials
        if username == 'admin' and password == 'admin123':
            session['admin_logged_in'] = True
            flash('Login successful!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid credentials!', 'error')
    
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/admin/dashboard')
def admin_dashboard():
    global firebase_available
    
    if not check_admin():
        flash('Please login as admin first!', 'error')
        return redirect(url_for('admin_login'))
    
    # Get all students from Firebase or use mock data
    if firebase_available:
        try:
            students_ref = db.reference('Students')
            students = students_ref.get() or {}
        except Exception as e:
            app.logger.error(f"Firebase error in admin dashboard: {e}")
            students = mock_students
            firebase_available = False
            flash('Firebase connection lost. Using local data.', 'warning')
    else:
        students = mock_students
        flash('Using local data (Firebase not available).', 'info')
    
    return render_template('admin_dashboard.html', students=students)

@app.route('/attendance/records')
def attendance_records():
    global firebase_available
    
    if not check_admin():
        flash('Please login as admin first!', 'error')
        return redirect(url_for('admin_login'))
    
    attendance_records = {}
    
    if firebase_available:
        try:
            for i in range(7):  # Only check last 7 days for faster loading
                check_date = (date.today() - timedelta(days=i)).strftime("%Y-%m-%d")
                attendance_ref = db.reference(f"Attendance/{check_date}")
                day_records = attendance_ref.get()
                if day_records:
                    attendance_records[check_date] = day_records
        except Exception as e:
            app.logger.error(f"Firebase error in attendance_records: {e}")
            firebase_available = False
            flash('Firebase connection lost. Showing mock data.', 'warning')
    
    if not firebase_available:
        today = date.today().strftime("%Y-%m-%d")
        yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        attendance_records = {
            today: {
                "321654": {"name": "John Doe", "time": "09:15:30", "major": "Computer Science", "year": "3"},
                "852741": {"name": "Jane Smith", "time": "09:22:45", "major": "Engineering", "year": "2"}
            },
            yesterday: {
                "963852": {"name": "Bob Johnson", "time": "08:45:12", "major": "Mathematics", "year": "4"},
                "321654": {"name": "John Doe", "time": "09:10:20", "major": "Computer Science", "year": "3"}
            }
        }
    
    total_days = len(attendance_records)
    total_attendance = sum(len(day_records) for day_records in attendance_records.values())
    
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
    global firebase_available
    
    if not check_admin():
        flash('Please login as admin first!', 'error')
        return redirect(url_for('admin_login'))
    
    export_date = request.args.get('date', date.today().strftime("%Y-%m-%d"))
    
    attendance_data = {}
    
    if firebase_available:
        try:
            attendance_ref = db.reference(f"Attendance/{export_date}")
            attendance_data = attendance_ref.get() or {}
        except Exception as e:
            app.logger.error(f"Firebase error in CSV export: {e}")
            firebase_available = False
            flash('Firebase connection lost. Using mock data.', 'warning')
    
    if not firebase_available:
        if export_date == date.today().strftime("%Y-%m-%d"):
            attendance_data = {
                "321654": {"name": "John Doe", "time": "09:15:30", "major": "Computer Science", "year": "3"},
                "852741": {"name": "Jane Smith", "time": "09:22:45", "major": "Engineering", "year": "2"}
            }
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['Student ID', 'Name', 'Time', 'Major', 'Year', 'Date'])
    
    for student_id, info in attendance_data.items():
        writer.writerow([
            student_id,
            info.get('name', ''),
            info.get('time', ''),
            info.get('major', ''),
            info.get('year', ''),
            export_date
        ])
    
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=attendance_{export_date}.csv'
    
    return response

@app.route('/upload')
def upload():
    return render_template('upload.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
