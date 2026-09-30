#!/usr/bin/env python3
"""Drive the LPO multiplayer relay the way the client does - no Flash needed.
Run:  python3 mp_fix_verify_relay.py [port]   (default port 18443)

Proves: (a) real-Flash XMLSocket path (policy request on the target port, then
connect JSON -> welcome), (b) silent-client path (unprompted policy), (c) the
Ruffle/socketProxy WebSocket path, (d) the post/broadcast dispatch the MP lobby
uses.  All assertions are on the on-the-wire payload shapes the client's own
decoder (SOL.Network.P2P.decode) parses.
"""
import json
import socket
import subprocess
import sys
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18443
import os
RELAY = os.environ.get("LPO_MP_RELAY", "/home/yoke/Downloads/littleprince-launcher/lpo/mp_relay.py")

POLICY = b"<policy-file-request/>\x00"


def start_relay():
    p = subprocess.Popen([sys.executable, "-u", RELAY, "--port", str(PORT),
                          "--host", "127.0.0.1", "--backend", "auto"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=0.3) as s:
                pass
            return p
        except OSError:
            time.sleep(0.1)
    raise SystemExit("relay did not listen")


def read_until_nul(sock, timeout=5.0):
    sock.settimeout(timeout)
    buf = b""
    try:
        while b"\x00" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
    except socket.timeout:
        pass
    return buf


def t1_real_flash_policy_then_connect():
    print("== T1 real Flash XMLSocket: policy request -> policy -> connect -> welcome")
    s = socket.create_connection(("127.0.0.1", PORT), timeout=3)
    s.sendall(POLICY)
    pol = read_until_nul(s)
    assert b"cross-domain-policy" in pol, ("no policy on target port", pol[:200])
    print("   policy served:", pol[:80])
    sent = json.dumps({"cmd": "connect", "gameID": "1", "name": "tester",
                       "cloth": []}) + "\x00"
    s.sendall(sent.encode())
    data = read_until_nul(s)
    assert b"\x00" in data, ("no NUL-terminated reply", data[:200])
    msg = json.loads(data.rstrip(b"\x00").decode())
    print("   welcome:", msg)
    assert msg.get("cmd") == "welcome", msg
    assert msg.get("p2pID"), "welcome carries no p2pID"
    # what the client does next: introMySelf posts type 0
    pid = msg["p2pID"]
    post = json.dumps({"cmd": "post", "gameID": "1", "p2pID": pid, "type": 0,
                       "data": {"p2pID": pid, "roomID": -1, "slotID": -1,
                                "status": 1}}) + "\x00"
    s.sendall(post.encode())
    time.sleep(0.3)
    s.close()
    return pid


def t2_silent_client():
    print("== T2 silent client: relay sends the policy unprompted (~3s)")
    s = socket.create_connection(("127.0.0.1", PORT), timeout=3)
    t0 = time.time()
    pol = read_until_nul(s, timeout=6)
    dt = time.time() - t0
    assert b"cross-domain-policy" in pol, ("no unprompted policy after %.1fs" % dt, pol[:120])
    print("   unprompted policy after %.1fs" % dt)
    s.close()


def t3_websocket():
    print("== T3 Ruffle/socketProxy WebSocket path")
    import asyncio
    import websockets

    async def go():
        async with websockets.connect("ws://127.0.0.1:%d/" % PORT) as ws:
            await ws.send(json.dumps({"cmd": "connect", "gameID": "1",
                                      "name": "ruffle", "cloth": []}))
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            msg = json.loads(raw.rstrip("\x00") if isinstance(raw, str)
                             else raw.rstrip(b"\x00").decode())
            print("   welcome:", msg)
            assert msg.get("cmd") == "welcome", msg
            return msg["p2pID"]

    return asyncio.run(go())


def t4_broadcast():
    print("== T4 post/broadcast dispatch (two clients, same lobby)")

    def client(name):
        s = socket.create_connection(("127.0.0.1", PORT), timeout=3)
        s.sendall(POLICY)
        read_until_nul(s)
        s.sendall((json.dumps({"cmd": "connect", "gameID": "7", "name": name,
                               "cloth": []}) + "\x00").encode())
        w = json.loads(read_until_nul(s).rstrip(b"\x00").decode())
        return s, w["p2pID"]

    a, pid_a = client("A")
    time.sleep(0.2)
    b, pid_b = client("B")
    time.sleep(0.2)
    # The real client announces itself from the LOBBY_CONNECTED handler
    # (MultiplayFlow -> p2p.introMySelf()), and the relay only learns which lobby a
    # socket belongs to from that first post - so B must intro too, exactly like the
    # client does, or it is not part of the lobby yet and hears nothing.
    for sock, pid in ((a, pid_a), (b, pid_b)):
        sock.sendall((json.dumps({"cmd": "post", "gameID": "7", "p2pID": pid,
                                  "type": 0, "data": {"p2pID": pid, "roomID": -1,
                                                      "slotID": -1, "status": 1}})
                      + "\x00").encode())
    time.sleep(0.3)
    # A introduces itself -> B must hear it as a post with type 0 (MSG_INSTRO)
    rec = {"p2pID": pid_a, "roomID": 0, "slotID": 1, "status": 2}
    a.sendall((json.dumps({"cmd": "post", "gameID": "7", "p2pID": pid_a,
                           "type": 0, "data": rec}) + "\x00").encode())
    heard = read_until_nul(b, timeout=3)
    print("   B heard:", heard[:160])
    assert pid_a.encode() in heard, "B never heard A's intro"
    msg = json.loads(heard.rstrip(b"\x00").decode())
    assert msg.get("cmd") == "post" and msg.get("type") == 0, msg
    assert isinstance(msg.get("data"), dict) and msg["data"].get("p2pID") == pid_a
    a.close()
    b.close()


if __name__ == "__main__":
    proc = start_relay()
    ok = True
    try:
        t1_real_flash_policy_then_connect()
        t2_silent_client()
        t3_websocket()
        t4_broadcast()
    except AssertionError as e:
        ok = False
        print("   FAIL:", e)
    finally:
        proc.terminate()
        try:
            print("---- relay log ----")
            print(proc.communicate(timeout=3)[0][:4000])
        except Exception:
            pass
    print("RESULT:", "ALL PASS" if ok else "FAILURES PRESENT")
    sys.exit(0 if ok else 1)
