import json

with open(r"C:\Users\Fredr\Desktop\Backup\Other\School\Stockholm School of Economics\Formula\gcloud-creds.json") as f:
    data = json.load(f)

print(json.dumps(data))