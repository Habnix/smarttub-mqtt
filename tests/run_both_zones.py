#!/usr/bin/env python3
"""Run light mode tests for both zones"""

import subprocess
import sys
import time

# Get credentials from Docker container
try:
    email = subprocess.check_output(
        ['docker', 'exec', 'smarttub-mqtt', 'printenv', 'SMARTTUB_EMAIL'],
        text=True
    ).strip()
    password = subprocess.check_output(
        ['docker', 'exec', 'smarttub-mqtt', 'printenv', 'SMARTTUB_PASSWORD'],
        text=True
    ).strip()
except Exception as e:
    print(f"❌ Error getting credentials: {e}")
    sys.exit(1)

print("🚀 Starting Light Mode Tests for Both Zones")
print("=" * 50)
print(f"Email: {email}")
print()

# Test parameters
params = [
    '--quick',
    '--wait', '4.0',
    '--verify', '5',
    '--delay', '2.5'
]

# Zone 1
print("📍 Testing Zone 1 (Quick - 8 modes)...")
print()
result1 = subprocess.run(
    [
        'python3', 'tests/test_light_modes.py',
        '--email', email,
        '--password', password,
        '--zone', '1',
        *params,
        '--output', f'zone1_quick_{int(time.time())}.json'
    ],
    cwd='/var/python/smarttub-mqtt'
)

print()
print("✅ Zone 1 completed!")
print()
print("⏳ Waiting 10 seconds before Zone 2...")
time.sleep(10)
print()

# Zone 2
print("📍 Testing Zone 2 (Quick - 8 modes)...")
print()
result2 = subprocess.run(
    [
        'python3', 'tests/test_light_modes.py',
        '--email', email,
        '--password', password,
        '--zone', '2',
        *params,
        '--output', f'zone2_quick_{int(time.time())}.json'
    ],
    cwd='/var/python/smarttub-mqtt'
)

print()
print("✅ Zone 2 completed!")
print()
print("🎉 All tests completed!")
print()
print("Results saved in tests/results/")

sys.exit(max(result1.returncode, result2.returncode))
