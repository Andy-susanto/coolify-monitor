#!/usr/bin/env python3
"""Update the monitor-agent service on Coolify with new compose."""
import requests, os, json, base64, sys
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

url = os.getenv('COOLIFY_URL')
key = os.getenv('COOLIFY_API_KEY')
if not url or not key:
    print("ERROR: Set COOLIFY_URL and COOLIFY_API_KEY in .env")
    sys.exit(1)

s = requests.Session()
s.verify = False
s.headers.update({'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})

# Find existing monitor agent service
print("Looking for existing Monitor Agent service...")
services = s.get(f'{url}/api/v1/services', timeout=10).json()
agent_svc = None
for svc in (services if isinstance(services, list) else services.get('data', [])):
    if 'monitor' in (svc.get('name') or '').lower():
        agent_svc = svc
        break

if not agent_svc:
    print("No existing monitor agent found. Run deploy_agent.py first.")
    sys.exit(1)

svc_uuid = agent_svc['uuid']
print(f"Found: {agent_svc.get('name')} ({svc_uuid})")

# Read updated compose
compose = open(os.path.join(os.path.dirname(__file__), 'deploy_agent_compose.yaml')).read()
compose_b64 = base64.b64encode(compose.encode()).decode()

print(f"Compose: {len(compose)} bytes")
print("Updating service...")

r = s.put(f'{url}/api/v1/services/{svc_uuid}', json={'docker_compose_raw': compose_b64}, timeout=30)
print(f"Status: {r.status_code}")
try:
    print(f"Response: {json.dumps(r.json(), indent=2)[:500]}")
except:
    print(f"Response: {r.text[:500]}")

# Restart the service
print("\nRestarting service...")
r2 = s.post(f'{url}/api/v1/services/{svc_uuid}/restart', timeout=30)
print(f"Restart status: {r2.status_code}")
try:
    print(f"Response: {json.dumps(r2.json(), indent=2)[:300]}")
except:
    print(f"Response: {r2.text[:300]}")
