import requests
import json
import sys

url = 'http://localhost:8004/'
headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer test'}
question = 'Which protein was identified as an interactor of PAD4 yet shows no evidence of interacting with ADF3 or contributing to powdery mildew defense or EHM targeting?'
data = {'question': question}

print("Sending request...")
try:
    resp = requests.post(url, json=data, headers=headers, timeout=700)
    print("Status:", resp.status_code)
    result = resp.json()
    print(json.dumps(result, ensure_ascii=False, indent=2))
except Exception as e:
    print("Error:", e)
