import cv2
import face_recognition
import pickle
import os
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
from firebase_admin import storage

#also uplaod image to storage at the same time
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred,{
    'databaseURL': "https://faceattendancerealtime-612a8-default-rtdb.firebaseio.com/",
    'storageBucket': "faceattendancerealtime-612a8.firebasestorage.app"
})


# Importing the student images into a list
folderPath = 'Images'
pathList = os.listdir(folderPath)
imgList = []
studentIds=[]

for path in pathList:
    imgList.append(cv2.imread(os.path.join(folderPath, path)))
    studentIds.append(os.path.splitext(path)[0]) # extract the student id only from the x.png path

    fileName=f'{folderPath}/{path}' # it will create folder called images and in that images folder will add all these images
    bucket=storage.bucket()
    blob=bucket.blob(fileName)
    blob.upload_from_filename(fileName)  # send data to storage in firebase


print(studentIds)


# opencv use BGR, face recognition lib use RGB, so need convert it

def findEncodings(imagesList):
    encodeList = []
    for image in imagesList:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        encode=face_recognition.face_encodings(image)[0]
        encodeList.append(encode)

    return encodeList
print("Encoding started...")
encodeListKnown = findEncodings(imgList)
encodeListUnknownWithIds=[encodeListKnown, studentIds]
print("Encoding completed")

# save in pickle file
file =open("EncodeFile.p", "wb")
pickle.dump(encodeListUnknownWithIds, file)
file.close()
print("File saved")