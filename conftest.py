import sys
from pathlib import Path

# Make the p1/ package root importable in tests (config, validator).
sys.path.insert(0, str(Path(__file__).resolve().parent))
