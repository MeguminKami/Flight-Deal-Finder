"""Quick test for Amadeus credentials"""
from dotenv import load_dotenv
import os
import requests

load_dotenv()

client_id = os.getenv('AMADEUS_CLIENT_ID')
client_secret = os.getenv('AMADEUS_CLIENT_SECRET')
base_url = os.getenv('AMADEUS_BASE_URL', 'https://test.api.amadeus.com')

print("=" * 50)
print("Testing Amadeus API Credentials")
print("=" * 50)
print(f"Base URL: {base_url}")
print(f"Client ID: {client_id[:8]}...{client_id[-4:] if client_id else 'NOT SET'}")
print()

try:
    response = requests.post(
        f'{base_url}/v1/security/oauth2/token',
        data={
            'grant_type': 'client_credentials',
            'client_id': client_id,
            'client_secret': client_secret
        },
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        timeout=10
    )
    
    if response.status_code == 200:
        token_data = response.json()
        print("✅ SUCCESS! Your credentials are VALID.")
        print(f"   Token expires in: {token_data.get('expires_in', 0)} seconds")
        print()
        print("Your app is ready to use Amadeus API!")
    else:
        print(f"❌ FAILED: HTTP {response.status_code}")
        print(f"   Response: {response.text[:300]}")
        
except Exception as e:
    print(f"❌ ERROR: {e}")

print("=" * 50)

