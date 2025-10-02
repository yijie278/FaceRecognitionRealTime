"""
Temporary version without Firebase for testing liveness detection.
This allows you to test the liveness detection without Firebase issues.
"""

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
from liveness_detection_fixed import LivenessDetectorFixed as LivenessDetector, quick_liveness_check

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

    # Load encodings at startup
    encode_file_path = os.path.join(os.path.dirname(__file__), "EncodeFile.p")
    if not os.path.exists(encode_file_path):
        app.logger.warning("EncodeFile.p not found. Run EncodeGenerator.py first to generate encodings.")
        encode_list_known = []
        student_ids = []
    else:
        with open(encode_file_path, "rb") as f:
            encode_list_known, student_ids = pickle.load(f)

    # Mock student data for testing
    mock_students = {
        "321654": {
            "name": "Yi Jie Lim",
            "major": "Computer Science",
            "year": 4,
            "Total attendance": 6
        },
        "852741": {
            "name": "Ali Jan", 
            "major": "Economic",
            "year": 3,
            "Total attendance": 12
        },
        "963852": {
            "name": "Elon Musk",
            "major": "Biology", 
            "year": 2,
            "Total attendance": 8
        }
    }

    # Routes
    @app.route('/')
    def index():
        return render_template('index.html')

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
            
            # LIVENESS DETECTION - Check if the face is real
            face_location = face_locations[0]  # Use first face
            # Convert face_recognition format (top, right, bottom, left) to (x, y, w, h)
            top, right, bottom, left = face_location
            face_region = (left, top, right - left, bottom - top)
            
            # Perform liveness check
            is_live = quick_liveness_check(bgr_image, face_region)
            
            if not is_live:
                return jsonify({
                    'success': False, 
                    'message': 'Fake face detected! Please use a real person for attendance.',
                    'liveness_failed': True
                })
            
            # Find best match
            first_face_encoding = face_encodings[0]
            distances = face_recognition.face_distance(encode_list_known, first_face_encoding)
            match_index = int(np.argmin(distances))
            matches = face_recognition.compare_faces([encode_list_known[match_index]], first_face_encoding)
            
            if matches[0]:
                matched_id = student_ids[match_index]
                
                # Get student info from mock data
                student_info = mock_students.get(matched_id)
                
                if student_info:
                    # Update attendance count
                    student_info['Total attendance'] += 1
                    
                    return jsonify({
                        'success': True,
                        'message': f'Attendance recorded for {student_info["name"]} (Liveness Verified)',
                        'student': {
                            'id': matched_id,
                            'name': student_info['name'],
                            'major': student_info.get('major', ''),
                            'year': student_info.get('year', ''),
                            'total_attendance': student_info['Total attendance']
                        }
                    })
                else:
                    return jsonify({'success': False, 'message': 'Student data not found'})
            else:
                return jsonify({'success': False, 'message': 'Face not recognized'})
                
        except Exception as e:
            return jsonify({'success': False, 'message': f'Error processing image: {str(e)}'})

    @app.route('/attendance/scan_multi_frame', methods=['POST'])
    def scan_attendance_multi_frame():
        """Enhanced attendance scanning with multi-frame liveness detection."""
        try:
            # Get JSON data containing multiple frames
            data = request.get_json()
            
            if not data or 'frames' not in data:
                return jsonify({'success': False, 'message': 'No frames provided'})
            
            frames_data = data['frames']
            if len(frames_data) < 5:
                return jsonify({'success': False, 'message': 'At least 5 frames required for liveness detection'})
            
            # Process frames
            frames = []
            face_regions = []
            
            for frame_data in frames_data:
                # Decode base64 image
                import base64
                image_data = base64.b64decode(frame_data.split(',')[1])  # Remove data:image/jpeg;base64, prefix
                nparr = np.frombuffer(image_data, np.uint8)
                bgr_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                if bgr_image is None:
                    continue
                
                # Detect face
                rgb_image = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)
                face_locations = face_recognition.face_locations(rgb_image)
                
                if len(face_locations) == 0:
                    continue
                
                # Convert face location format
                top, right, bottom, left = face_locations[0]
                face_region = (left, top, right - left, bottom - top)
                
                frames.append(bgr_image)
                face_regions.append(face_region)
            
            if len(frames) < 5:
                return jsonify({'success': False, 'message': 'Not enough valid frames with faces detected'})
            
            # Perform comprehensive liveness detection
            liveness_detector = LivenessDetector()
            liveness_result = liveness_detector.multi_frame_analysis(frames, face_regions)
            
            # More strict verification for high accuracy
            if not liveness_result['is_live'] or liveness_result['final_confidence'] < 0.6:
                return jsonify({
                    'success': False,
                    'message': 'Liveness detection failed. Please ensure you are a real person and try again.',
                    'liveness_failed': True,
                    'details': {
                        'confidence': liveness_result['final_confidence'],
                        'blinks_detected': liveness_result['total_blinks'],
                        'blinks_required': liveness_detector.MIN_BLINKS_REQUIRED
                    }
                })
            
            # Proceed with face recognition on the best frame
            best_frame = frames[len(frames)//2]  # Use middle frame
            best_face_region = face_regions[len(frames)//2]
            rgb_image = cv2.cvtColor(best_frame, cv2.COLOR_BGR2RGB)
            
            # Convert face region back to face_recognition format
            x, y, w, h = best_face_region
            face_location = (y, x + w, y + h, x)  # (top, right, bottom, left)
            face_encodings = face_recognition.face_encodings(rgb_image, [face_location])
            
            if len(face_encodings) == 0:
                return jsonify({'success': False, 'message': 'Could not encode face for recognition'})
            
            if not encode_list_known:
                return jsonify({'success': False, 'message': 'No known encodings found'})
            
            # Find best match
            first_face_encoding = face_encodings[0]
            distances = face_recognition.face_distance(encode_list_known, first_face_encoding)
            match_index = int(np.argmin(distances))
            matches = face_recognition.compare_faces([encode_list_known[match_index]], first_face_encoding)
            
            if matches[0]:
                matched_id = student_ids[match_index]
                
                # Get student info from mock data
                student_info = mock_students.get(matched_id)
                
                if student_info:
                    # Update attendance count
                    student_info['Total attendance'] += 1
                    
                    return jsonify({
                        'success': True,
                        'message': f'Attendance recorded for {student_info["name"]} (Liveness Verified)',
                        'student': {
                            'id': matched_id,
                            'name': student_info['name'],
                            'major': student_info.get('major', ''),
                            'year': student_info.get('year', ''),
                            'total_attendance': student_info['Total attendance']
                        },
                        'liveness_details': {
                            'confidence': liveness_result['final_confidence'],
                            'blinks_detected': liveness_result['total_blinks']
                        }
                    })
                else:
                    return jsonify({'success': False, 'message': 'Student data not found'})
            else:
                return jsonify({'success': False, 'message': 'Face not recognized'})
                
        except Exception as e:
            app.logger.error(f"Error in multi-frame attendance scan: {str(e)}")
            return jsonify({'success': False, 'message': f'Error processing frames: {str(e)}'})

    return app

if __name__ == "__main__":
    app = create_app()
    # For public access, use 0.0.0.0 and set debug=False in production
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=True)






