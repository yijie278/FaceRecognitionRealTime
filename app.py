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

# Try to import liveness detection modules with fallbacks
try:
    from ultra_simple_liveness import UltraSimpleLivenessDetector as LivenessDetector
    print("[OK] Using ultra-simple movement detection (much more reliable!)")
except ImportError:
    try:
        from simple_blink_detection import SimpleBlinkLivenessDetector as LivenessDetector
        print("[WARNING] Using blink detection as fallback")
    except ImportError:
        from liveness_detection_fixed import LivenessDetectorFixed as LivenessDetector
        print("[WARNING] Using complex detection as last resort")

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Firebase configuration
firebase_available = False
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred, {
            "databaseURL": "https://facerecognitionrealtime-default-rtdb.firebaseio.com/",
            "storageBucket": "facerecognitionrealtime.firebasestorage.app"
        })
    firebase_available = True
    print("[OK] Firebase initialized successfully")
except Exception as e:
    print(f"[WARNING] Firebase initialization failed: {e}")
    firebase_available = False

# Load face encodings
encode_list_known = []
student_ids = []

try:
    with open('EncodeFile.p', 'rb') as file:
        encode_list_known_with_ids = pickle.load(file)
        encode_list_known, student_ids = encode_list_known_with_ids
    print(f"[OK] Loaded {len(encode_list_known)} face encodings")
except FileNotFoundError:
    print("[WARNING] EncodeFile.p not found. Please run EncodeGenerator.py first")

# Initialize liveness detector
liveness_detector = LivenessDetector()

# Mock student data for fallback
mock_students = {
    "321654": {
        "name": "John Doe",
        "major": "Computer Science", 
        "year": "3",
        "standing": "A",
        "starting_year": "2022",
        "Total attendance": 15,
        "last_atttendance_time": "2024-01-15 10:30:00"
    },
    "852741": {
        "name": "Jane Smith",
        "major": "Engineering",
        "year": "2", 
        "standing": "B",
        "starting_year": "2023",
        "Total attendance": 12,
        "last_atttendance_time": "2024-01-14 14:20:00"
    }
}

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
    """Single frame attendance scan"""
    try:
        if 'frame' not in request.files:
            return jsonify({'success': False, 'message': 'No frame provided'})
        
        file = request.files['frame']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No frame selected'})
        
        # Read image
        image_data = file.read()
        nparr = np.frombuffer(image_data, np.uint8)
        bgr_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        rgb_image = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)
        
        # Find faces and encode them
        face_locations = face_recognition.face_locations(rgb_image)
        face_encodings = face_recognition.face_encodings(rgb_image, face_locations)
        
        if not face_encodings:
            return jsonify({'success': False, 'message': 'No face detected'})
        
        if not encode_list_known:
            return jsonify({'success': False, 'message': 'No known faces in database'})
        
        # Find best match
        first_face_encoding = face_encodings[0]
        distances = face_recognition.face_distance(encode_list_known, first_face_encoding)
        match_index = int(np.argmin(distances))
        matches = face_recognition.compare_faces([encode_list_known[match_index]], first_face_encoding)
        
        if matches[0] and distances[match_index] < 0.6:  # Threshold for good match
            matched_id = student_ids[match_index]
            
            # Get current date and time
            now = datetime.now()
            date_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H:%M:%S")
            
            # Check if already marked today
            already_marked = False
            if firebase_available:
                try:
                    today_attendance = db.reference(f'Attendance/{date_str}/{matched_id}').get()
                    if today_attendance:
                        already_marked = True
                except Exception as e:
                    app.logger.error(f"Firebase error: {e}")
            
            if already_marked:
                return jsonify({'success': False, 'message': 'Attendance already marked today'})
            
            # Get student info
            student_info = None
            if firebase_available:
                try:
                    student_info = db.reference(f"Students/{matched_id}").get()
                except Exception as e:
                    app.logger.error(f"Firebase error: {e}")
                    student_info = mock_students.get(matched_id)
            else:
                student_info = mock_students.get(matched_id)
            
            if not student_info:
                return jsonify({'success': False, 'message': 'Student data not found'})
            
            # Mark attendance
            if firebase_available:
                try:
                    # Update attendance record
                    db.reference(f'Attendance/{date_str}/{matched_id}').set(time_str)
                    
                    # Update student's total attendance and last attendance time
                    current_total = student_info.get('Total attendance', 0)
                    db.reference(f'Students/{matched_id}/Total attendance').set(current_total + 1)
                    db.reference(f'Students/{matched_id}/last_atttendance_time').set(f"{date_str} {time_str}")
                    
                    print(f"[OK] Attendance marked for {student_info['name']} ({matched_id})")
                except Exception as e:
                    app.logger.error(f"Firebase error marking attendance: {e}")
                    return jsonify({'success': False, 'message': 'Error saving to database'})
            
            return jsonify({
                'success': True, 
                'name': student_info['name'],
                'student_id': matched_id,
                'time': time_str
            })
        else:
            return jsonify({'success': False, 'message': 'Face not recognized'})
            
    except Exception as e:
        app.logger.error(f"Error in attendance scan: {str(e)}")
        return jsonify({'success': False, 'message': 'Processing error'})

@app.route('/attendance/scan_multi_frame', methods=['POST'])
def scan_attendance_multi_frame():
    """Multi-frame attendance scan with liveness detection"""
    try:
        if 'frames' not in request.files:
            return jsonify({'success': False, 'message': 'No frames provided'})
        
        frames = request.files.getlist('frames')
        if len(frames) < 3:
            return jsonify({'success': False, 'message': 'Need at least 3 frames for liveness detection'})
        
        # Process frames for liveness detection
        processed_frames = []
        for frame_file in frames:
            image_data = frame_file.read()
            nparr = np.frombuffer(image_data, np.uint8)
            bgr_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            processed_frames.append(bgr_image)
        
        # Check liveness
        is_live = liveness_detector.detect_liveness(processed_frames)
        if not is_live:
            return jsonify({'success': False, 'message': 'Liveness detection failed. Please move naturally.'})
        
        # Use the middle frame for face recognition
        middle_frame = processed_frames[len(processed_frames)//2]
        rgb_image = cv2.cvtColor(middle_frame, cv2.COLOR_BGR2RGB)
        
        # Continue with face recognition (same as single frame)
        face_locations = face_recognition.face_locations(rgb_image)
        face_encodings = face_recognition.face_encodings(rgb_image, face_locations)
        
        if not face_encodings:
            return jsonify({'success': False, 'message': 'No face detected'})
        
        if not encode_list_known:
            return jsonify({'success': False, 'message': 'No known faces in database'})
        
        # Find best match
        first_face_encoding = face_encodings[0]
        distances = face_recognition.face_distance(encode_list_known, first_face_encoding)
        match_index = int(np.argmin(distances))
        matches = face_recognition.compare_faces([encode_list_known[match_index]], first_face_encoding)
        
        if matches[0] and distances[match_index] < 0.6:
            matched_id = student_ids[match_index]
            
            # Same attendance marking logic as single frame
            now = datetime.now()
            date_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H:%M:%S")
            
            # Check if already marked today
            already_marked = False
            if firebase_available:
                try:
                    today_attendance = db.reference(f'Attendance/{date_str}/{matched_id}').get()
                    if today_attendance:
                        already_marked = True
                except Exception as e:
                    app.logger.error(f"Firebase error: {e}")
            
            if already_marked:
                return jsonify({'success': False, 'message': 'Attendance already marked today'})
            
            # Get student info and mark attendance (same as above)
            student_info = None
            if firebase_available:
                try:
                    student_info = db.reference(f"Students/{matched_id}").get()
                except Exception as e:
                    app.logger.error(f"Firebase error: {e}")
                    student_info = mock_students.get(matched_id)
            else:
                student_info = mock_students.get(matched_id)
            
            if not student_info:
                return jsonify({'success': False, 'message': 'Student data not found'})
            
            # Mark attendance
            if firebase_available:
                try:
                    db.reference(f'Attendance/{date_str}/{matched_id}').set(time_str)
                    current_total = student_info.get('Total attendance', 0)
                    db.reference(f'Students/{matched_id}/Total attendance').set(current_total + 1)
                    db.reference(f'Students/{matched_id}/last_atttendance_time').set(f"{date_str} {time_str}")
                    print(f"[VERIFIED] Liveness + Face recognition: {student_info['name']} ({matched_id})")
                except Exception as e:
                    app.logger.error(f"Firebase error marking attendance: {e}")
                    return jsonify({'success': False, 'message': 'Error saving to database'})
            
            return jsonify({
                'success': True, 
                'name': student_info['name'],
                'student_id': matched_id,
                'time': time_str,
                'liveness_verified': True
            })
        else:
            return jsonify({'success': False, 'message': 'Face not recognized'})
            
    except Exception as e:
        app.logger.error(f"Error in multi-frame attendance scan: {str(e)}")
        app.logger.error(f"Traceback: {str(e.__traceback__)}")
        return jsonify({'success': False, 'message': 'Processing error'})

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Simple admin check (in production, use proper authentication)
        if username == 'admin' and password == 'admin123':
            session['admin_logged_in'] = True
            return redirect('/admin/dashboard')
        else:
            flash('Invalid credentials', 'error')
    
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect('/')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not check_admin():
        return redirect('/admin/login')
    
    students = {}
    if firebase_available:
        try:
            students = db.reference('Students').get() or {}
        except Exception as e:
            app.logger.error(f"Firebase error: {e}")
            students = mock_students
    else:
        students = mock_students
    
    return render_template('admin_dashboard.html', students=students)

@app.route('/attendance/records')
def attendance_records():
    if not check_admin():
        return redirect('/admin/login')
    
    # Get attendance records
    records = {}
    total_days = 0
    total_students = 0
    total_attendance = 0
    
    if firebase_available:
        try:
            attendance_data = db.reference('Attendance').get()
            if attendance_data:
                records = attendance_data
                total_days = len(records)
                
                # Calculate stats
                students_set = set()
                for date, daily_records in records.items():
                    total_attendance += len(daily_records)
                    students_set.update(daily_records.keys())
                total_students = len(students_set)
        except Exception as e:
            app.logger.error(f"Firebase error: {e}")
    
    # If no Firebase data, use mock data
    if not records:
        records = {
            "2024-01-15": {
                "321654": "09:15:30",
                "852741": "09:22:45"
            },
            "2024-01-14": {
                "321654": "08:45:20"
            }
        }
        total_days = 2
        total_students = 2
        total_attendance = 3
    
    return render_template('attendance_records.html', 
                         records=records,
                         total_days=total_days,
                         total_students=total_students,
                         total_attendance=total_attendance)

@app.route('/attendance/export_csv')
def export_attendance_csv():
    if not check_admin():
        return redirect('/admin/login')
    
    export_date = request.args.get('date', date.today().strftime("%Y-%m-%d"))
    
    attendance_data = {}
    
    if firebase_available:
        try:
            attendance_ref = db.reference(f"Attendance/{export_date}")
            attendance_data = attendance_ref.get() or {}
        except Exception as e:
            app.logger.error(f"Firebase error in CSV export: {e}")
            firebase_available = False
    
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

@app.route('/attendance/analytics')
def attendance_analytics():
    """Show attendance analytics dashboard"""
    if not check_admin():
        return redirect('/admin/login')
    
    analytics_data = {
        'total_students': 0,
        'total_attendance_records': 0,
        'attendance_by_date': {},
        'attendance_by_student': {},
        'weekly_stats': {},
        'monthly_stats': {},
        'top_students': [],
        'attendance_rate': 0,
        'recent_activity': []
    }
    
    if firebase_available:
        try:
            # Get students data
            students = db.reference('Students').get()
            if students:
                analytics_data['total_students'] = len(students)
            
            # Get attendance data
            attendance_records = db.reference('Attendance').get()
            if attendance_records:
                total_records = 0
                student_attendance_count = {}
                date_attendance_count = {}
                recent_records = []
                
                for date, daily_records in attendance_records.items():
                    date_count = 0
                    for student_id, times in daily_records.items():
                        count = len(times) if isinstance(times, list) else 1
                        total_records += count
                        date_count += count
                        
                        # Count by student
                        if student_id not in student_attendance_count:
                            student_attendance_count[student_id] = 0
                        student_attendance_count[student_id] += count
                        
                        # Recent activity
                        if isinstance(times, list):
                            for time_str in times:
                                recent_records.append({
                                    'date': date,
                                    'student_id': student_id,
                                    'time': time_str,
                                    'student_name': students.get(student_id, {}).get('name', 'Unknown') if students else 'Unknown'
                                })
                        else:
                            recent_records.append({
                                'date': date,
                                'student_id': student_id,
                                'time': times,
                                'student_name': students.get(student_id, {}).get('name', 'Unknown') if students else 'Unknown'
                            })
                    
                    date_attendance_count[date] = date_count
                
                analytics_data['total_attendance_records'] = total_records
                analytics_data['attendance_by_date'] = date_attendance_count
                analytics_data['attendance_by_student'] = student_attendance_count
                
                # Calculate attendance rate
                if analytics_data['total_students'] > 0:
                    analytics_data['attendance_rate'] = round((len(student_attendance_count) / analytics_data['total_students']) * 100, 1)
                
                # Top students (by attendance count)
                top_students = sorted(student_attendance_count.items(), key=lambda x: x[1], reverse=True)[:5]
                analytics_data['top_students'] = [
                    {
                        'student_id': student_id,
                        'name': students.get(student_id, {}).get('name', 'Unknown') if students else 'Unknown',
                        'attendance_count': count
                    }
                    for student_id, count in top_students
                ]
                
                # Recent activity (last 10 records)
                recent_records.sort(key=lambda x: f"{x['date']} {x['time']}", reverse=True)
                analytics_data['recent_activity'] = recent_records[:10]
                
                # Weekly stats (last 7 days)
                from datetime import datetime, timedelta
                today = datetime.now()
                for i in range(7):
                    date = (today - timedelta(days=i)).strftime('%Y-%m-%d')
                    analytics_data['weekly_stats'][date] = date_attendance_count.get(date, 0)
                
        except Exception as e:
            app.logger.error(f"Firebase analytics error: {e}")
    else:
        # Mock data for analytics when Firebase is not available
        analytics_data = {
            'total_students': 2,
            'total_attendance_records': 15,
            'attendance_by_date': {
                '2024-10-01': 5,
                '2024-10-02': 3,
                '2024-10-03': 7
            },
            'attendance_by_student': {
                '321654': 8,
                '852741': 7
            },
            'weekly_stats': {
                '2024-10-03': 7,
                '2024-10-02': 3,
                '2024-10-01': 5,
                '2024-09-30': 0,
                '2024-09-29': 0,
                '2024-09-28': 0,
                '2024-09-27': 0
            },
            'top_students': [
                {'student_id': '321654', 'name': 'John Doe', 'attendance_count': 8},
                {'student_id': '852741', 'name': 'Jane Smith', 'attendance_count': 7}
            ],
            'attendance_rate': 100.0,
            'recent_activity': [
                {'date': '2024-10-03', 'student_id': '321654', 'time': '09:15:30', 'student_name': 'John Doe'},
                {'date': '2024-10-03', 'student_id': '852741', 'time': '09:22:45', 'student_name': 'Jane Smith'}
            ]
        }
    
    return render_template('analytics.html', analytics=analytics_data)

@app.route('/upload')
def upload():
    return render_template('upload.html')

@app.route('/match', methods=['POST'])
def match():
    """Match uploaded image with known faces"""
    try:
        if 'image' not in request.files:
            flash('No image uploaded', 'error')
            return redirect('/upload')
        
        file = request.files['image']
        if file.filename == '':
            flash('No image selected', 'error')
            return redirect('/upload')
        
        image_data = file.read()
        nparr = np.frombuffer(image_data, np.uint8)
        bgr_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        rgb_image = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)
        
        face_locations = face_recognition.face_locations(rgb_image)
        face_encodings = face_recognition.face_encodings(rgb_image, face_locations)
        
        if not face_encodings:
            flash('No face detected in the uploaded image', 'error')
            return redirect('/upload')
        
        if not encode_list_known:
            flash('No known faces in database', 'error')
            return redirect('/upload')
        
        first_face_encoding = face_encodings[0]
        distances = face_recognition.face_distance(encode_list_known, first_face_encoding)
        match_index = int(np.argmin(distances))
        matches = face_recognition.compare_faces([encode_list_known[match_index]], first_face_encoding)
        
        if matches[0]:
            matched_id = student_ids[match_index]
            if firebase_available:
                try:
                    student_info = db.reference(f"Students/{matched_id}").get()
                except Exception as e:
                    app.logger.error(f"Firebase error: {e}")
                    student_info = mock_students.get(matched_id)
            else:
                student_info = mock_students.get(matched_id)
            
            if student_info:
                flash(f'Student identified: {student_info["name"]}', 'success')
                return render_template('result.html', 
                                     matched=True,
                                     matched_id=matched_id,
                                     student_info=student_info,
                                     distance=distances[match_index],
                                     confidence=f"{(1-distances[match_index])*100:.1f}%")
            else:
                flash('Student data not found', 'error')
                return redirect('/upload')
        else:
            flash('Face not recognized in our database', 'error')
            return redirect('/upload')
            
    except Exception as e:
        app.logger.error(f"Error in match: {str(e)}")
        flash(f'Error processing image: {str(e)}', 'error')
        return redirect('/upload')

@app.route('/admin/add_student', methods=['GET', 'POST'])
def add_student():
    """Add new student to the system"""
    if not check_admin():
        return redirect('/admin/login')
    
    if request.method == 'POST':
        try:
            # Get form data
            student_id = request.form.get('student_id', '').strip()
            name = request.form.get('name', '').strip()
            major = request.form.get('major', '').strip()
            year = request.form.get('year', '').strip()
            standing = request.form.get('standing', '').strip()
            starting_year = request.form.get('starting_year', '').strip()
            
            # Validate required fields
            if not all([student_id, name, major, year]):
                flash('Please fill in all required fields (Student ID, Name, Major, Year)', 'error')
                return render_template('add_student.html')
            
            # Check if student already exists
            if firebase_available:
                try:
                    existing_student = db.reference(f'Students/{student_id}').get()
                    if existing_student:
                        flash(f'Student with ID {student_id} already exists!', 'error')
                        return render_template('add_student.html')
                except Exception as e:
                    app.logger.error(f"Firebase error checking existing student: {e}")
            
            # Prepare student data
            student_data = {
                'name': name,
                'major': major,
                'year': year,
                'standing': standing or 'Good',
                'starting_year': starting_year or str(datetime.now().year),
                'Total attendance': 0,
                'last_atttendance_time': 'Never'
            }
            
            # Save to Firebase
            if firebase_available:
                try:
                    db.reference(f'Students/{student_id}').set(student_data)
                    flash(f'Student {name} (ID: {student_id}) has been successfully added to the system!', 'success')
                    app.logger.info(f"[OK] Added new student: {name} (ID: {student_id})")
                except Exception as e:
                    app.logger.error(f"Firebase error adding student: {e}")
                    flash(f'Error adding student to Firebase: {str(e)}', 'error')
                    return render_template('add_student.html')
            else:
                # Add to mock data when Firebase is not available
                mock_students[student_id] = student_data
                flash(f'Student {name} (ID: {student_id}) has been added to mock database (Firebase not available)', 'warning')
                app.logger.info(f"[WARNING] Added student to mock data: {name} (ID: {student_id})")
            
            return redirect('/admin/dashboard')
            
        except Exception as e:
            app.logger.error(f"Error in add_student: {str(e)}")
            flash(f'Error adding student: {str(e)}', 'error')
            return render_template('add_student.html')
    
    return render_template('add_student.html')

@app.route('/admin/delete_student/<student_id>', methods=['POST'])
def delete_student(student_id):
    """Delete student from the system"""
    if not check_admin():
        return redirect('/admin/login')
    
    if firebase_available:
        try:
            db.reference(f'Students/{student_id}').delete()
            flash(f'Student {student_id} has been deleted successfully', 'success')
        except Exception as e:
            app.logger.error(f"Error deleting student from Firebase: {e}")
            flash(f'Error deleting student: {str(e)}', 'error')
    else:
        # Remove from mock data
        if student_id in mock_students:
            del mock_students[student_id]
            flash(f'Student {student_id} has been deleted from mock database', 'warning')
    
    return redirect('/admin/dashboard')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)