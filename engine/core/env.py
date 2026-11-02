"""Load engine/.env so credentials survive opening a new terminal.

Exported shell variables vanish with the window, which is a bad way to lose a
demo. Anything already in the environment wins, so a deliberate export still
overrides the file.
"""
import os

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")


def load(path=None):
    path = path or PATH
    loaded = {}
    try:
        with open(path) as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key, value = key.strip(), value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
                    loaded[key] = value
    except OSError:
        return {}
    return loaded
