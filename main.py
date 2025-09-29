import pickle
import face_recognition
import cv2
import os
import numpy as np
import cvzone
cap = cv2.VideoCapture(0)
cap.set(3,640)  #camera size in image background
cap.set(4,480)

imgBackground=cv2.imread('Resources/background.png')

# Importing the mode images into a list
folderModePath = 'Resources/Models'
modePathList = os.listdir(folderModePath)
imgModeList = []
for path in modePathList:
    imgModeList.append(cv2.imread(os.path.join(folderModePath, path)))
#print(len(imgModeList))

#Load the encoding file
print("Loading Encode file..")
file =open('EncodeFile.p', 'rb') #read file
encodeListUnknownWithIds = pickle.load(file) # add all list and info into encodeListUnknownWithIds
file.close()
encodeListKnown, studentIds= encodeListUnknownWithIds
print("Encode File Loaded")



while True:
    success, img = cap.read()

    imgS=cv2.resize(img,(0,0),None,0.25,0.25)
    imgS = cv2.cvtColor(imgS, cv2.COLOR_BGR2RGB)

    #compare two face one from camera, one from encoding
    faceCurFrame=face_recognition.face_locations(imgS)
    encodeCurFrame=face_recognition.face_encodings(imgS,faceCurFrame)


    imgBackground[162:162+480,55:55+640]=img
    imgBackground[44:44 + 633, 808:808 + 414] = imgModeList[3]

    # use zip so no need separate in two loop, encodeFace is current face
    # the lower distance , the better match
    for encodeFace, faceLoc in zip(encodeCurFrame, faceCurFrame):
        matches = face_recognition.compare_faces(encodeListKnown, encodeFace)
        faceDis=face_recognition.face_distance(encodeListKnown, encodeFace)
        #print("matches",matches)
        #print("faceDis",faceDis)

        #find least index
        matchIndex =np.argmin(faceDis)
        #print("Match Index", matchIndex )

        if matches[matchIndex]:
            #print("Known Face Detected")
            #print(studentIds[matchIndex])
            #draw rectangle means it detect face either opencv or directly use cvzone
            y1,x2,y2,x1 = faceLoc #rectangle detect the face
            y1, x2, y2, x1= y1*4,x2*4,y2*4,x1*4 # multiply back by 4 as last time we reduce image size by 4
            bbox=55+x1, 162+y1, x2-x1, y2-y1
            imgBackground= cvzone.cornerRect(imgBackground,bbox,rt=0) #bounding box with rect thick is zero




    #cv2.imshow("Webcam", img)
    cv2.imshow('Face Attendance', imgBackground)
    cv2.waitKey(1)