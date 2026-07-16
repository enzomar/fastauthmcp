"""Entry point: python -m fastauthmcp.lab run"""

import sys

from fastauthmcp.lab.runner.engine import main

if __name__ == "__main__":
    sys.exit(main())
