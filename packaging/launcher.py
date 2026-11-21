"""打包后的程序入口（PyInstaller 需要一个脚本文件，不能直接指向 `-m gloss`）。"""

import sys

from gloss.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
