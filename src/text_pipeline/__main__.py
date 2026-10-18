"""Allow ``python -m text_pipeline``."""

import sys

from text_pipeline.cli import main

if __name__ == "__main__":
    sys.exit(main())
