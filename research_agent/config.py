import os
from pathlib import Path
from dotenv import load_dotenv

def load_environment():
    """Load environment variables from .env file."""
    try:
        # Load .env file
        load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'), override=True)
        
        # Fallback manual loading if needed (as seen in original code)
        here = Path(__file__).resolve().parent.parent
        candidates = [here / ".env", Path.cwd() / ".env"]
        seen = set()
        for p in candidates:
            if not p.exists():
                continue
            if str(p) in seen:
                continue
            seen.add(str(p))
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if not s or s.startswith("#") or "=" not in s:
                        continue
                    k, v = s.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k and v and k not in os.environ:
                        os.environ[k] = v
    except Exception:
        pass

# Initialize on module import
load_environment()
