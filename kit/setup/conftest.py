import sys
from pathlib import Path

# The setup code uses the wop package from kit/mcp (wopkit.py adds it the same way)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp"))
