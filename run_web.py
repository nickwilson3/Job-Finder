"""Entry point for the Job Finder web server."""
import sys
from pathlib import Path

# Ensure project root is on the path so both `web/` and `src/` are importable
sys.path.insert(0, str(Path(__file__).parent))

# Load .env BEFORE any web modules are imported so env vars are available at import time
from dotenv import load_dotenv
load_dotenv()

import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    dev = os.environ.get("ENVIRONMENT", "development") == "development"
    uvicorn.run("web.app:app", host="0.0.0.0", port=port, reload=dev)
