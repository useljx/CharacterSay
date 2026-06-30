"""CharacterSay — 角色对话扮演系统

启动方式:
    python main.py
    或
    python -m app.main
"""

import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.main import main

if __name__ == "__main__":
    raise SystemExit(main())
