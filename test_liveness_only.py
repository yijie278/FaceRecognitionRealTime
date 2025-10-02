"""
Pure Liveness Detection Test - No Firebase Required
This version tests ONLY the liveness detection without any Firebase dependencies.
"""

import base64
import os
import pickle
from flask import Flask, render_template, request, jsonify
import cv2
import numpy as np
import face_recognition
from liveness_detection_fixed import LivenessDetectorFixed as LivenessDetector, quick_liveness_check

app = Flask(__name__)
app.secret_key = "test-key-for-liveness"

# Load encodings
encode_file_path = "EncodeFile.p"
if os.path.exists(encode_file_path):
    with open(encode_file_path, "rb") as f:
        encode_list_known, student_ids = pickle.load(f)
else:
    encode_list_known = []
    student_ids = []

# Test student data
test_students = {
    "321654": {"name": "Yi Jie Lim", "major": "Computer Science", "year": 4, "Total attendance": 6},
    "852741": {"name": "Ali Jan", "major": "Economic", "year": 3, "Total attendance": 12},
    "963852": {"name": "Elon Musk", "major": "Biology", "year": 2, "Total attendance": 8}
}

@app.route('/')
def index():
    return render_template('attendance.html')

@app.route('/attendance')
def attendance():
    return render_template('attendance.html')

@app.route('/upload')
def upload():
    return "Upload feature not available in test mode"

@app.route('/admin/login')
def admin_login():
    return "Admin features not available in test mode"

@app.route('/admin/dashboard')
def admin_dashboard():
    return "Admin features not available in test mode"

@app.route('/attendance/scan_multi_frame', methods=['POST'])
def scan_multi_frame():
    """Test multi-frame liveness detection without Firebase."""
    try:
        data = request.get_json()
        
        if not data or 'frames' not in data:
            return jsonify({'success': False, 'message': 'No frames provided'})
        
        frames_data = data['frames']
        if len(frames_data) < 5:
            return jsonify({'success': False, 'message': 'At least 5 frames required'})
        
        # Process frames
        frames = []
        face_regions = []
        
        for frame_data in frames_data:
            try:
                # Decode base64 image
                image_data = base64.b64decode(frame_data.split(',')[1])
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
            except Exception as e:
                print(f"Error processing frame: {e}")
                continue
        
        if len(frames) < 5:
            return jsonify({'success': False, 'message': 'Not enough valid frames with faces'})
        
        # Perform liveness detection
        liveness_detector = LivenessDetector()
        liveness_result = liveness_detector.multi_frame_analysis(frames, face_regions)
        
        print(f"Liveness Result: {liveness_result['is_live']}")
        print(f"Confidence: {liveness_result['final_confidence']:.2f}")
        print(f"Blinks: {liveness_result['total_blinks']}")
        
        # Check liveness
        if not liveness_result['is_live'] or liveness_result['final_confidence'] < 0.6:
            return jsonify({
                'success': False,
                'message': 'Liveness detection failed. Please ensure you are a real person.',
                'liveness_failed': True,
                'details': {
                    'confidence': liveness_result['final_confidence'],
                    'blinks_detected': liveness_result['total_blinks'],
                    'blinks_required': 1
                }
            })
        
        # Face recognition (if encodings available)
        if encode_list_known and len(frames) > 0:
            best_frame = frames[len(frames)//2]
            rgb_image = cv2.cvtColor(best_frame, cv2.COLOR_BGR2RGB)
            face_encodings = face_recognition.face_encodings(rgb_image)
            
            if len(face_encodings) > 0:
                first_face_encoding = face_encodings[0]
                distances = face_recognition.face_distance(encode_list_known, first_face_encoding)
                match_index = int(np.argmin(distances))
                matches = face_recognition.compare_faces([encode_list_known[match_index]], first_face_encoding)
                
                if matches[0]:
                    matched_id = student_ids[match_index]
                    student_info = test_students.get(matched_id, {
                        'name': f'Student {matched_id}',
                        'major': 'Unknown',
                        'year': 1,
                        'Total attendance': 1
                    })
                    
                    # Increment attendance
                    student_info['Total attendance'] += 1
                    
                    return jsonify({
                        'success': True,
                        'message': f'Attendance recorded for {student_info["name"]} (Liveness Verified!)',
                        'student': {
                            'id': matched_id,
                            'name': student_info['name'],
                            'major': student_info['major'],
                            'year': student_info['year'],
                            'total_attendance': student_info['Total attendance']
                        },
                        'liveness_details': {
                            'confidence': liveness_result['final_confidence'],
                            'blinks_detected': liveness_result['total_blinks']
                        }
                    })
        
        # If no face recognition or no match, still return liveness success
        return jsonify({
            'success': True,
            'message': 'Liveness verified! (Face not in database)',
            'student': {
                'id': 'unknown',
                'name': 'Unknown Person',
                'major': 'N/A',
                'year': 'N/A',
                'total_attendance': 1
            },
            'liveness_details': {
                'confidence': liveness_result['final_confidence'],
                'blinks_detected': liveness_result['total_blinks']
            }
        })
        
    except Exception as e:
        print(f"Error in liveness test: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/attendance/scan', methods=['POST'])
def scan_single():
    """Single frame scan for testing."""
    if 'image' not in request.files:
        return jsonify({'success': False, 'message': 'No image provided'})
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No image selected'})
    
    try:
        # Process image
        file_bytes = np.frombuffer(file.read(), np.uint8)
        bgr_image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        
        if bgr_image is None:
            return jsonify({'success': False, 'message': 'Could not read image'})
        
        # Face detection
        rgb_image = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_image)
        
        if len(face_locations) == 0:
            return jsonify({'success': False, 'message': 'No face detected'})
        
        # Liveness check
        top, right, bottom, left = face_locations[0]
        face_region = (left, top, right - left, bottom - top)
        is_live = quick_liveness_check(bgr_image, face_region)
        
        if not is_live:
            return jsonify({
                'success': False,
                'message': 'Fake face detected! Please use a real person.',
                'liveness_failed': True
            })
        
        return jsonify({
            'success': True,
            'message': 'Real person detected!',
            'student': {
                'id': 'test',
                'name': 'Test Person',
                'major': 'Testing',
                'year': 1,
                'total_attendance': 1
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

if __name__ == "__main__":
    print("Pure Liveness Detection Test Server")
    print("No Firebase required - testing liveness detection only!")
    print("Access at: http://127.0.0.1:5002/attendance")
    app.run(host="0.0.0.0", port=5002, debug=True)
