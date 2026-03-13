"""server.py  --  Thin launcher for the server package.

Run with:  python server.py
Or:        python -m server
"""
import asyncio
from server import main

asyncio.run(main())
