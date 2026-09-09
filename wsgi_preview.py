"""
Preview/dev server entry point (no debug reloader — stable for detached runs).
Canonical dev launch remains `python app.py`; Render uses gunicorn.
"""

import os

from app import app

# Preview convenience: pick up template/CSS edits without a server restart
app.config["TEMPLATES_AUTO_RELOAD"] = True

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
