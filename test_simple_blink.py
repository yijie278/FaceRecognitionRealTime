"""
Test script for simple blink detection
"""

import cv2
import numpy as np
from simple_blink_detection import SimpleBlinkLivenessDetector

def test_simple_detection():
    """Test the simple blink detection with webcam"""
    
    print("=== Simple Blink Detection Test ===")
    print("This test uses ONLY blink detection for liveness verification")
    print("How it works:")
    print("1. 👁️ Detects your face using OpenCV")
    print("2. 👀 Monitors your eyes for blinks")
    print("3. ✅ Verifies you're real if you blink 1+ times within 8 seconds")
    print("")
    print("Instructions:")
    print("- Look at the camera")
    print("- Blink normally (1 or more times)")
    print("- The system will verify you're a real person")
    print("- Press 'q' to quit, 'r' to restart")
    print("")
    
    detector = SimpleBlinkLivenessDetector()
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("❌ Error: Could not open camera")
        return
    
    frames_collected = []
    collecting_frames = False
    
    while True:
        ret, frame = cap.read()
        if not ret:
            print("❌ Error: Could not read frame")
            break
        
        # Display instructions on frame
        cv2.putText(frame, "Simple Blink Detection Test", (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame, "Press SPACE to start test, 'q' to quit", (10, 60), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        if collecting_frames:
            frames_collected.append(frame.copy())
            cv2.putText(frame, f"Collecting frames: {len(frames_collected)}/10", (10, 90), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            cv2.putText(frame, "Please blink normally!", (10, 120), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            
            # Collect 10 frames for testing
            if len(frames_collected) >= 10:
                print("\n🔍 Testing blink detection...")
                
                # Test the detection
                result = detector.verify_liveness(frames_collected)
                
                print(f"📊 Results:")
                print(f"   Is Live: {result.get('is_live', False)}")
                print(f"   Blinks Detected: {result.get('total_blinks', 0)}")
                print(f"   Confidence: {result.get('confidence', 0):.2f}")
                print(f"   Time Elapsed: {result.get('time_elapsed', 0):.1f}s")
                print(f"   Message: {result.get('message', 'No message')}")
                
                if result.get('is_live', False):
                    print("✅ SUCCESS: Real person detected!")
                else:
                    print("❌ FAILED: Not enough blinks detected or fake person")
                
                print("\nPress SPACE to test again, 'q' to quit\n")
                
                # Reset for next test
                frames_collected = []
                collecting_frames = False
                detector.reset_detection()
        
        cv2.imshow('Simple Blink Detection Test', frame)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord(' '):  # Space to start test
            frames_collected = []
            collecting_frames = True
            detector.reset_detection()
            print("▶️ Starting blink detection test...")
    
    cap.release()
    cv2.destroyAllWindows()
    print("👋 Test completed!")

if __name__ == "__main__":
    test_simple_detection()
