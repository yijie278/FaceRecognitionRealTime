# 🔥 Firebase JWT Signature Error - SOLUTION

## 🚨 **Current Problem:**
```
Error: ('invalid_grant: Invalid JWT Signature.', {'error': 'invalid_grant', 'error_description': 'Invalid JWT Signature.'})
```

## ✅ **IMMEDIATE SOLUTIONS:**

### **Option 1: Test Liveness Detection (No Firebase)**
```bash
python test_liveness_only.py
```
**Access:** http://127.0.0.1:5002/attendance

This version tests ONLY liveness detection without Firebase. Perfect for testing if your camera and liveness detection work!

### **Option 2: Use Main App (Firebase Auto-Fallback)**
```bash
python app.py
```
**Access:** http://127.0.0.1:5000/attendance

The main app now automatically handles Firebase errors and falls back to local mode.

---

## 🔑 **PERMANENT FIX: Generate New Firebase Key**

Your current `serviceAccountKey.json` has an expired/invalid JWT signature. You need a **fresh key**:

### **Steps:**
1. **Go to:** https://console.firebase.google.com/
2. **Select:** `faceattendancerealtime-612a8` project
3. **Click:** ⚙️ Settings → Project Settings
4. **Go to:** "Service Accounts" tab
5. **Scroll down:** "Firebase Admin SDK" section
6. **Click:** "Generate new private key"
7. **Download:** The JSON file
8. **Replace:** Your current `serviceAccountKey.json` with the new file

### **After replacing the key:**
```bash
python app.py
```

---

## 🎯 **What Each Version Does:**

| Version | Firebase | Liveness | Face Recognition | Port |
|---------|----------|----------|------------------|------|
| `test_liveness_only.py` | ❌ No | ✅ Full | ✅ Yes | 5002 |
| `app.py` | ✅ Auto-fallback | ✅ Full | ✅ Yes | 5000 |

---

## 🚀 **Test Your Liveness Detection NOW:**

**Run:** `python test_liveness_only.py`
**Go to:** http://127.0.0.1:5002/attendance

1. Click "Start Camera & Verify Real Person"
2. Look at camera and blink naturally
3. Should see "Real person verified!"
4. Click "Mark Attendance"

**Expected Results:**
- ✅ Real face: "Liveness verified!"
- ❌ Photo: "Fake face detected!"
- 🔍 Shows blink count and confidence

---

## 📞 **Need Help?**
If liveness detection doesn't work in the test version, the issue is with the camera/detection code, not Firebase.
If it works in test but fails in main app, then Firebase is the issue.



