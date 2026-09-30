#!/usr/bin/env python3
"""Run the pack's REAL server.py against the scratch tree, on a chosen port.

`server.py`'s main() ignores argv (PORT is a module constant) and it also kicks off
cloud auto-repair threads, so bind the handler directly instead: the scratch
instance serves the shipped code, on my port, with none of the network side jobs.

    python3 bb_serve.py <port> [lpo-dir]
"""
import os
import sys
from pathlib import Path

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8977
LPO = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/tmp/lpo_scratch/lpo")
sys.path.insert(0, str(LPO))
os.chdir(str(LPO))
import server                                                   # noqa: E402

server.PORT = PORT
srv = server.ReusableTCPServer((server.HOST, PORT), server.LittlePrinceHandler)
print("serving %s on %s:%d (scratch)" % (LPO, server.HOST, PORT), flush=True)
srv.serve_forever()
