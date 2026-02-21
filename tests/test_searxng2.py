import urllib.request

try:
    req = urllib.request.Request('http://127.0.0.1:8080')
    req.add_header('User-Agent', 'Mozilla/5.0')
    response = urllib.request.urlopen(req)
    print(response.read().decode('utf-8')[:1000])
except urllib.error.HTTPError as e:
    print(f"=== HTTP Error {e.code} ===")
    content = e.read().decode('utf-8', errors='ignore')
    print(content)
except Exception as e:
    print(f"Error: {e}")
