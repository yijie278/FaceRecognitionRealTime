import firebase_admin
from firebase_admin import credentials
from firebase_admin import db

cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred,{
    'databaseURL': "https://faceattendancerealtime-612a8-default-rtdb.firebaseio.com/"
})

ref=db.reference('Students')

data={
    "321654":
        {
            "name":"Yi Jie Lim",
            "major":"Computer Science",
            "starting_year":2022,
            "Total attendance":6,
            "standing":"G",
            "year":4,
            "last_atttendance_time":"2025-9-28 00:54:34"
        },
    "852741":
        {
            "name": "Ali Jan",
            "major": "Economic",
            "starting_year": 2021,
            "Total attendance": 12,
            "standing": "B",
            "year": 3,
            "last_atttendance_time": "2025-9-28 00:54:34"
        },
    "963852":
        {
            "name": "Elon Musk",
            "major": "Biology",
            "starting_year": 2020,
            "Total attendance": 8,
            "standing": "G",
            "year": 2,
            "last_atttendance_time": "2025-9-28 00:54:34"
        }
}

for key,value in data.items():
    ref.child(key).set(value)
