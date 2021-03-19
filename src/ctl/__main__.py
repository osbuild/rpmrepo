"""RPMrepo CLI Main

This is the entrypoint of the rpmrepoctl executable. We simply import from the
ctl module and execute the provided CLI entrypoint.
"""

import sys
from .cli import Cli as Main


if __name__ == "__main__":
    with Main(sys.argv) as global_main:
        sys.exit(global_main.run())
