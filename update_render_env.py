import json, urllib.request

API_KEY = "rnd_zkMo7R1LvTVdtjha31FedJN04pXs"
SERVICE_ID = "srv-d9fr49u7r5hc73fei39g"
BASE = f"https://api.render.com/v1/services/{SERVICE_ID}/env-vars"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

# Get existing env vars
req = urllib.request.Request(BASE, headers=headers)
resp = urllib.request.urlopen(req)
existing = json.loads(resp.read())

# Build list from existing (keep GOOGLE_APPLICATION_CONTENTS as-is from Render)
env_vars = []
for item in existing:
    ev = item["envVar"]
    env_vars.append({"key": ev["key"], "value": ev["value"]})

# Only add/update the simple vars
simple_vars = {
    "LLM_PROVIDER": "cerebras",
    "CEREBRAS_API_KEY": "csk-6m2krnyfn34t4n9ct6f2ck5x2vj9p32f8tv9c2yky9myyc6m",
    "CACHE_TTL": "3600",
}
for k, v in simple_vars.items():
    found = False
    for ev in env_vars:
        if ev["key"] == k:
            ev["value"] = v
            found = True
            break
    if not found:
        env_vars.append({"key": k, "value": v})

body = json.dumps({"envVars": env_vars})
print(f"PUT {len(env_vars)} env vars ({len(body)} bytes)")
print(f"Keys: {[e['key'] for e in env_vars]}")

req2 = urllib.request.Request(BASE, data=body.encode("utf-8"), headers=headers, method="PUT")
try:
    resp2 = urllib.request.urlopen(req2)
    data = json.loads(resp2.read())
    print(f"SUCCESS: {len(data)} env vars set")
    for e in data:
        k = e["envVar"]["key"]
        v = e["envVar"]["value"][:30]
        print(f"  {k} = {v}...")
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code}: {e.reason}")
    print(e.read().decode()[:500])
