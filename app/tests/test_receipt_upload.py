import requests

# Path to your receipt image (jpg, png, etc.)
image_path = "test-kvitto.png"  # ← Replace with your actual image path

url = "http://localhost:8000/process-receipt"  # Update if your port is different

with open(image_path, "rb") as f:
    files = {"file": f}
    response = requests.post(url, files=files)

print("Status Code:", response.status_code)
print("Response JSON:")
print(response.json())