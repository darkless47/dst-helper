"""Run from the workspace root: python dst_helper --host localhost --port 8765."""
from pathlib import Path
import sys

APPLICATION_ROOT = Path(__file__).resolve().parents[1] / 'DST_Cooking_Data_v0_1'
sys.path.insert(0, str(APPLICATION_ROOT.parent))
sys.path.insert(0, str(APPLICATION_ROOT))

from dst_helper.server import main

if __name__ == '__main__':
    main()
