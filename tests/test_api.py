import requests

url = "http://localhost:8000/predict"

sample_data = {
    "age": 54,
    "sex": 1,
    "cp": 0,
    "trestbps": 140,
    "chol": 239,
    "fbs": 0,
    "restecg": 1,
    "thalach": 160,
    "exang": 0,
    "oldpeak": 1.2,
    "slope": 1,
    "ca": 0,
    "thal": 3
}

response = requests.post(url, json = sample_data)

print("Status Code:", response.status_code)
print("Raw Text:", response.text)
