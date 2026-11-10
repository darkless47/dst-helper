"""Run from any working directory: python path/to/run_handbook.py."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dst_helper.server import main

if __name__ == '__main__':
    main()
