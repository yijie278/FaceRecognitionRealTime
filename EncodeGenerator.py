import cv2
import face_recognition
import pickle
import os

# Importing the student images into a list
folderPath = 'Images'
modePathList = os.listdir(folderPath)
imgList = []
for path in modePathList:
    imgList.append(cv2.imread(os.path.join(folderPath, path)))
#print(len(imgList))