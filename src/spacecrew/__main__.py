"""Allow `python -m spacecrew` (dev runner, equivalent to the `spacecrew` entry point)."""

from .cli import main

if __name__ == "__main__":
    main()
