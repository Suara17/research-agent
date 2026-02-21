import urllib.request
import sys

try:
    response = urllib.request.urlopen('http://127.0.0.1:8080')
    content = response.read().decode('utf-8')
    print(content[:1000])
except urllib.error.HTTPError as e:
    print(f"HTTP Error: {e.code}")
    print(e.read().decode('utf-8')[:2000])
except Exception as e:
    print(f"Error: {e}")
