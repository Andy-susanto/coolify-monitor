#!/usr/bin/env python3
"""Start the deployed monitor-agent service."""
import requests, os, json
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

url = os.getenv('COOLIFY_URL')
key = os.getenv('COOLIFY_API_KEY')
s = requests.Session()
s.headers.update({'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})

svc_uuid = 'i5vufbsm70r01t3tss0fltbj'

# Check service status
r = s.get(f'{url}/api/v1/services/{svc_uuid}', timeout=10)
print(f'Service status: {r.status_code}')
if r.status_code == 200:
    data = r.json()
    print(f'Name: {data.get("name")}')
    print(f'Status: {data.get("status")}')

# Start the service
print()
print('Starting service...')
r = s.post(f'{url}/api/v1/services/{svc_uuid}/start', timeout=30)
print(f'Start status: {r.status_code}')
try:
    print(f'Response: {json.dumps(r.json(), indent=2)[:300]}')
except:
    print(f'Response: {r.text[:300]}')
