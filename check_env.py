import json, urllib.request

API_KEY = "rnd_zkMo7R1LvTVdtjha31FedJN04pXs"
SERVICE_ID = "srv-d9fr49u7r5hc73fei39g"
BASE = f"https://api.render.com/v1/services/{SERVICE_ID}/env-vars"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json",
}

req = urllib.request.Request(BASE, headers=headers)
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())

for item in data:
    ev = item["envVar"]
    k = ev["key"]
    v = ev["value"]
    if k == "GOOGLE_APPLICATION_CONTENTS":
        print(f"{k}: length={len(v)}")
        try:
            parsed = json.loads(v)
            print(f"  Valid JSON: project_id={parsed.get('project_id')}")
            # Re-serialize to ensure consistent formatting
            clean = json.dumps(parsed, separators=(",", ":"))
            print(f"  Clean length: {len(clean)}")
        except Exception as e:
            print(f"  NOT valid JSON: {e}")
