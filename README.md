# 🎓 Face Recognition Attendance System

A comprehensive web application for student attendance management using real-time face recognition technology with Firebase integration.

## ✨ Features

- **Real-time Attendance**: Mark attendance using device camera with instant face recognition
- **Admin Dashboard**: Complete student management system for administrators
- **Student Registration**: Add new students with photos and academic information
- **Attendance Records**: View and analyze attendance data with detailed reports
- **Upload & Match**: Upload photos to identify students and view their information
- **Firebase Integration**: Secure cloud storage and real-time database
- **Modern UI**: Beautiful, responsive design with intuitive navigation

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- Firebase project with Realtime Database and Storage
- Webcam or camera-enabled device

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd FaceRecognitionRealTime
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Firebase Setup**
   - Create a Firebase project at [Firebase Console](https://console.firebase.google.com/)
   - Enable Realtime Database and Storage
   - Download your service account key as `serviceAccountKey.json`
   - Place the file in the project root directory

4. **Initialize the system**
   ```bash
   # Add sample students to database
   python AddDataToDatabase.py
   
   # Generate face encodings
   python EncodeGenerator.py
   ```

5. **Run the application**
   ```bash
   python app.py
   ```

6. **Access the application**
   - Open your browser and go to `http://localhost:5000`
   - Use admin credentials: `admin` / `admin123`

## 📱 Usage

### For Students
1. Go to the **Attendance** page
2. Click "Start Camera" to begin
3. Position your face in the camera frame
4. Click "Capture & Scan" to mark attendance
5. Your attendance will be automatically recorded

### For Administrators
1. Login with admin credentials
2. **Add Students**: Register new students with photos and information
3. **View Records**: Check attendance reports and student data
4. **Manage Students**: Delete students or update information
5. **Live Monitoring**: Watch real-time attendance marking

### Upload & Match
1. Go to the **Upload & Match** page
2. Upload a photo containing a face
3. The system will identify the student and show their information
4. Perfect for verification and record checking

## 🏗️ Project Structure

```
FaceRecognitionRealTime/
├── app.py                      # Main Flask application
├── main.py                     # Original desktop application
├── EncodeGenerator.py          # Generates face encodings
├── AddDataToDatabase.py        # Adds sample data to Firebase
├── serviceAccountKey.json      # Firebase service account key
├── EncodeFile.p               # Generated face encodings
├── requirements.txt           # Python dependencies
├── Images/                    # Student photos directory
├── Resources/                 # UI resources
│   ├── background.png
│   └── Models/
└── templates/                 # HTML templates
    ├── index.html            # Home page
    ├── admin_login.html      # Admin login
    ├── admin_dashboard.html  # Admin dashboard
    ├── add_student.html      # Add student form
    ├── attendance.html       # Live attendance
    ├── upload.html           # Upload & match
    ├── attendance_records.html # Attendance reports
    └── result.html           # Match results
```

## 🔧 Configuration

### Firebase Configuration
Update the Firebase URLs in `app.py`:
```python
"databaseURL": "https://your-project-default-rtdb.firebaseio.com/",
"storageBucket": "your-project.firebasestorage.app"
```

### Admin Credentials
Change default admin credentials in `app.py`:
```python
if username == 'admin' and password == 'admin123':
```

## 🛠️ Development

### Adding New Features
1. Create new routes in `app.py`
2. Add corresponding HTML templates
3. Update navigation in all templates
4. Test thoroughly before deployment

### Database Schema
Students are stored in Firebase with the following structure:
```json
{
  "Students": {
    "student_id": {
      "name": "Student Name",
      "major": "Computer Science",
      "year": 3,
      "standing": "A",
      "starting_year": 2022,
      "Total attendance": 15,
      "last_atttendance_time": "2024-01-15 10:30:00"
    }
  }
}
```

## 🔒 Security Considerations

- Change default admin credentials in production
- Use environment variables for sensitive data
- Implement proper authentication for production use
- Regularly update dependencies
- Secure Firebase rules and permissions

## 📊 Performance Tips

- Optimize images before uploading (recommended: 300x300px)
- Use good lighting for better face recognition accuracy
- Regularly regenerate encodings when adding new students
- Monitor Firebase usage and costs

## 🐛 Troubleshooting

### Common Issues

1. **Camera not working**
   - Check browser permissions
   - Ensure HTTPS in production
   - Try different browsers

2. **Face recognition not accurate**
   - Ensure good lighting
   - Use clear, front-facing photos
   - Regenerate encodings after adding students

3. **Firebase connection issues**
   - Verify service account key
   - Check Firebase project settings
   - Ensure proper permissions

4. **Encoding file missing**
   - Run `python EncodeGenerator.py`
   - Ensure Images folder has student photos

## 📝 License

This project is open source and available under the MIT License.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📞 Support

For support and questions, please open an issue in the repository.

---

**Note**: This system is designed for educational purposes. For production use, implement additional security measures and proper authentication systems.

