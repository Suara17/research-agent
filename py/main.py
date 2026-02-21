import sys
import os

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Install dependencies if they're not available
try:
    import curl_cffi
except ImportError:
    print("curl_cffi not found, installing...")
    import subprocess
    import importlib
    subprocess.check_call([sys.executable, "-m", "pip", "install", "curl_cffi"])
    importlib.invalidate_caches()
    import curl_cffi

# Now import the main application
from agent import app

if __name__ == "__main__":
    import uvicorn
    import os
    
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)