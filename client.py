"""client.py  --  Thin launcher for the client package.

Run with:  python client.py [--name NAME] [--room ROOM] [--host HOST] [--port PORT]
Or:        python -m client
"""
import asyncio
from client import main

asyncio.run(main())
