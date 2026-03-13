"""Allow ``python -m client``."""
import asyncio
from client import main

asyncio.run(main())
