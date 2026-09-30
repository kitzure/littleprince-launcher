#!/usr/bin/env python3
"""LPO multiplayer relay (星願小王子Online LAN 反連服務).

Standalone asyncio WebSocket hub.  Speaks the websockify-style binary
framing that Ruffle's ``socketProxy`` tunnels flash.net.XMLSocket traffic
through, so the patched lib.swf treats it as a plain socket server.

Wire protocol (null-terminated flat ASCII per XMLSocket convention):
    <json>\\0
Envelope fields:
    cmd     connect|post|close      (connect is implicit per socket)
    gameID  lobby name, e.g. "1"
    p2pID   unique client id assigned by server on first message
    type    MultiPlayLobby MSG_* int
    data    arbitrary JSON payload
    roomID  int (-1 = lobby)

Run:  python3 mp_relay.py [--port 8443] [--host 0.0.0.0] [--backend auto]

Backends
    auto        use the `websockets` package when it imports cleanly,
                otherwise fall back to the built-in stdlib server below
    websockets  force the package
    raw         force the built-in server (no third-party dependency)

The relay is normally started by Start_Server_GUI.pyw, which keeps it on
port 8443 and streams its output into the launcher's log.  Running this file
a SECOND time while that one is alive is not an error: it prints which relay
already answers on the port and exits 0.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import socket
import sys
import time
from collections import defaultdict

try:
    import websockets
except Exception as _exc:  # ImportError, or a package too old/new for this Python
    websockets = None
    _WS_IMPORT_ERROR = _exc
else:
    _WS_IMPORT_ERROR = None

# ---------------------------------------------------------------- fallback
# Minimal RFC6455 server (no external deps) used when `websockets` is absent
# or cannot serve on this Python version.
JS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def ws_key_accept(key: str) -> str:
    import base64
    import hashlib

    dig = hashlib.sha1((key + JS_MAGIC).encode("ascii")).digest()
    return base64.b64encode(dig).decode("ascii")


class RawWS:
    """Server-side of one WebSocket conn; yields payload bytes."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer
        self.closed = False

    async def handshake(self, head: bytes = b"") -> bool:
        try:
            line = head + await asyncio.wait_for(self.reader.readline(), 10)
            if b"GET " not in line:
                return False
            headers = {}
            while True:
                line = await self.reader.readline()
                if line in (b"\r\n", b"\n", b""):
                    break
                (k, _, v) = line.decode("latin1").partition(":")
                headers[k.strip().lower()] = v.strip()
            key = headers.get("sec-websocket-key")
            if not key:
                return False
            resp = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {ws_key_accept(key)}\r\n"
                "\r\n"
            )
            self.writer.write(resp.encode("ascii"))
            await self.writer.drain()
            return True
        except Exception:
            return False

    async def recv_msg(self) -> bytes | None:
        buf = b""
        while not self.closed:
            hdr = await self.reader.readexactly(2)
            fin_op = hdr[0]
            masked = (hdr[1] & 0x80) != 0
            ln = hdr[1] & 0x7F
            if ln == 126:
                ln = int.from_bytes(await self.reader.readexactly(2), "big")
            elif ln == 127:
                ln = int.from_bytes(await self.reader.readexactly(8), "big")
            mask = await self.reader.readexactly(4) if masked else None
            payload = await self.reader.readexactly(ln) if ln else b""
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            op = fin_op & 0x0F
            if op == 8:  # close
                self.closed = True
                try:
                    self.writer.write(b"\x88\x00")
                    await self.writer.drain()
                except Exception:
                    pass
                return None
            if op == 9:  # ping
                pong = bytes([0x8A, ln]) + payload
                self.writer.write(pong)
                await self.writer.drain()
                continue
            buf += payload
            if fin_op & 0x80:  # FIN
                return buf

    async def send_msg(self, data: bytes) -> None:
        if self.closed:
            return
        try:
            ln = len(data)
            if ln < 126:
                hdr = bytes([0x82, ln])
            elif ln < 1 << 16:
                hdr = bytes([0x82, 126]) + ln.to_bytes(2, "big")
            else:
                hdr = bytes([0x82, 127]) + ln.to_bytes(8, "big")
            self.writer.write(hdr + data)
            await self.writer.drain()
        except Exception:
            self.closed = True


class RawXML:
    """Real Flash's XMLSocket: a plain TCP stream whose records are JSON/UTF-8
    terminated by a NUL byte.  No HTTP, no WebSocket framing - this is what the
    publisher browser (Pepper Flash in LittlePrinceBrowserHome) speaks, while
    Ruffle's socketProxy wraps the same bytes in a WebSocket."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                 initial: bytes = b""):
        self.reader = reader
        self.writer = writer
        self.buf = bytearray(initial)
        self.closed = False

    async def handshake(self) -> bool:
        return True  # nothing to negotiate on a raw socket

    async def recv_msg(self) -> bytes | None:
        while not self.closed:
            i = self.buf.find(b"\x00")
            if i >= 0:
                msg = bytes(self.buf[:i])
                del self.buf[:i + 1]
                return msg
            try:
                chunk = await self.reader.read(4096)
            except (ConnectionError, OSError):
                self.closed = True
                return None
            if not chunk:
                self.closed = True
                return None
            self.buf += chunk
        return None

    async def send_msg(self, data: bytes) -> None:
        if self.closed:
            return
        try:
            self.writer.write(data)
            await self.writer.drain()
        except Exception:
            self.closed = True


# ------------------------------------------------------------------ state
class Lobby:
    """gameID-keyed room bookkeeping (mirror of client rooms[10][4])."""

    def __init__(self, game_id: str):
        self.game_id = game_id
        # room -> slot -> p2pID ('' = free)
        self.rooms: dict[int, list[str]] = {
            r: ["", "", "", ""] for r in range(10)
        }
        self.locked: dict[int, bool] = {r: False for r in range(10)}
        # p2pID -> (roomID, slotID) or None
        self.seats: dict[str, tuple[int, int]] = {}
        # p2pID -> the client's last MSG_INSTRO payload (its own myInfo: p2pID,
        # roomID, slotID, status, ...).  A newcomer is replayed these so its
        # room list shows who is already here - without it every fresh joiner
        # saw an empty lobby until someone happened to re-intro.
        self.infos: dict[str, dict] = {}


def _field(sock, name, default=None):
    """Client records are dicts on both backends; accept attribute objects too."""
    if isinstance(sock, dict):
        return sock.get(name, default)
    return getattr(sock, name, default)


class Relay:
    def __init__(self):
        self.clients: dict[str, object] = {}
        self.lobbies: dict[str, Lobby] = {}

    def lobby(self, gid: str) -> Lobby:
        if gid not in self.lobbies:
            self.lobbies[gid] = Lobby(gid)
        return self.lobbies[gid]

    async def broadcast(
        self, ws, lobby: Lobby, sender_id: str | None, envelope: dict
    ):
        """Send envelope to all sockets currently in the same lobby."""
        blob = (json.dumps(envelope) + "\x00").encode("utf-8")
        for pid, sock in list(self.clients.items()):
            if pid == sender_id:
                continue
            if _field(sock, "lobby_key") != lobby.game_id:
                continue  # only same-lobby
            other = _field(sock, "raw")
            if other is None:
                continue
            send = getattr(other, "send_msg", None) or getattr(other, "send", None)
            if send is None:
                continue
            try:
                await send(blob)
            except Exception:
                pass

    async def send(self, ws, target_id: str, envelope: dict):
        t = self.clients.get(target_id)
        if not t:
            return
        other = _field(t, "raw")
        send = getattr(other, "send_msg", None) or getattr(other, "send", None)
        if send is not None:
            try:
                await send((json.dumps(envelope) + "\x00").encode("utf-8"))
            except Exception:
                pass


# ---------------------------------------------------------------- handlers
def parse_frame(data: bytes) -> dict:
    """Split one null-terminated JSON record; missing null => still parse."""
    raw = data.rstrip(b"\x00")
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return {}


RELAY = Relay()
START_TIME = time.time()

# Flash refuses to finish an XMLSocket connection until the server answers its
# socket policy request, so the relay speaks that too.  The request arrives as
# the NUL-terminated ASCII string <policy-file-request/> on the target port (or
# on the master policy port 843, which we also try to listen on).
POLICY_XML = (
    b'<cross-domain-policy><allow-access-from domain="*" to-ports="*"/>'
    b"</cross-domain-policy>\x00"
)
POLICY_REQUEST = b"<policy-file-request"


def make_pid() -> str:
    import uuid

    return uuid.uuid4().hex[:16]


def _apply_state(lobby: Lobby, msg: dict, pid: str) -> None:
    """Server-side seat/quota bookkeeping shared by both backends."""
    typ = msg.get("type")
    if typ == 0:  # INSTRO - remember the client's own record for replays
        data = msg.get("data")
        if isinstance(data, dict):
            lobby.infos[pid] = data
    elif typ == 1:  # INROOM
        room_id = int(msg["data"]["roomID"])
        slot_id = int(msg["data"]["slotID"])
        lobby.rooms[room_id][slot_id] = pid
        lobby.seats[pid] = (room_id, slot_id)
        info = lobby.infos.get(pid)
        if info is not None:
            info["roomID"] = room_id
            info["slotID"] = slot_id
            info["status"] = 2  # STATUS_INROOM - the join gate requires it
    elif typ == 2:  # LEAVEROOM
        seat = lobby.seats.pop(pid, None)
        if seat:
            lobby.rooms[seat[0]][seat[1]] = ""
        info = lobby.infos.get(pid)
        if info is not None:
            info["roomID"] = -1
            info["slotID"] = -1
            info["status"] = 1  # STATUS_INLOBBY
    elif typ == 3:  # SETPLAYERSTATUS - keep the record's ready flag current
        info = lobby.infos.get(pid)
        if info is not None:
            info["status"] = msg.get("data")
    elif typ == 5:  # LOCKROOM
        lobby.locked[int(msg["data"]["roomID"])] = True
    elif typ == 6:  # UNLOCKROOM
        lobby.locked[int(msg["data"]["roomID"])] = False


async def replay_lobby_state(ws, me: dict) -> None:
    """Send a fresh connection the records of everyone already in its lobby.

    The client's room list is built purely from MSG_INSTRO posts it hears, so
    without this a joiner only ever saw players who intro'd after it connected
    - the "not real time" empty room list.  Each record goes out exactly like
    a live post from that player, which is what the client parses.
    """
    gid = me.get("lobby_key")
    pid = me.get("p2pID")
    if not gid or not pid:
        return
    lobby = RELAY.lobbies.get(gid)
    if lobby is None:
        return
    raw = _field(me, "raw")
    send = getattr(raw, "send_msg", None) or getattr(raw, "send", None)
    if send is None:
        return
    for other_pid, info in list(lobby.infos.items()):
        if other_pid == pid:
            continue
        # The stored record is the player's intro snapshot; their seat may have
        # changed since (INROOM only broadcasts the claim, and the relay-side
        # seat is the live truth) - stamp the current seat onto the record or
        # the joiner would see them as still sitting in the lobby.
        record = dict(info)
        seat = lobby.seats.get(other_pid)
        if seat:
            record["roomID"] = seat[0]
            record["slotID"] = seat[1]
            # the join gate on the receiving client refuses any occupant whose
            # status is not INROOM/INROOMREADY - never replay a seated player
            # with the intro-time INLOBBY flag
            try:
                if int(record.get("status") or 1) < 2:
                    record["status"] = 2
            except (TypeError, ValueError):
                record["status"] = 2
        envelope = {"cmd": "post", "p2pID": other_pid, "type": 0, "data": record}
        try:
            await send((json.dumps(envelope) + "\x00").encode("utf-8"))
        except Exception:
            pass


async def handle_conn(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Built-in server path (stdlib only).

    Accepts BOTH transports a client may arrive on:
      * Ruffle web player  -> HTTP/WebSocket upgrade (page socketProxy tunnel)
      * real Flash (Pepper in LittlePrinceBrowserHome, or the Flash projector)
                          -> plain TCP XMLSocket, JSON records NUL-terminated
    """
    peer = writer.get_extra_info("peername")
    head = b""
    silent = False
    try:
        head = await asyncio.wait_for(reader.read(4), 3)
    except asyncio.TimeoutError:
        silent = True
    except (ConnectionError, OSError):
        return
    if head == b"" and not silent:                # connected, then closed: a port check
        # the launcher GUI probes the port on every status refresh - logging that
        # flooded the window once per refresh and looked like the game misbehaving
        writer.close()
        return
    if silent:
        # Flash's XMLSocket will not send a byte until it has the socket policy
        # (its own request can sit behind the player's port-843 attempt), so a
        # silent client gets the policy unprompted - it is harmless to anyone
        # else, and it stops a waiting player from hanging on 連線中.
        writer.write(POLICY_XML)
        await writer.drain()
        print(f"[relay] {peer} silent for 3s - sent the socket policy unprompted",
              flush=True)
        try:
            head = await asyncio.wait_for(reader.read(4), 15)
        except asyncio.TimeoutError:
            head = b""
        except (ConnectionError, OSError):
            return

    if head == b"GET ":
        ws = RawWS(reader, writer)
        if not await ws.handshake(head):
            writer.close()
            return
        await _serve_socket(ws, "websocket/socketProxy (Ruffle)")
    else:
        peer = writer.get_extra_info("peername")
        print(f"[relay] XMLSocket client {peer} first bytes {head!r}", flush=True)
        await _serve_socket(RawXML(reader, writer, head), "xmlsocket (real Flash)")


async def _serve_socket(ws, tag: str = ""):
    """Shared protocol loop for both transports."""
    me: dict = {"raw": ws, "lobby_key": None, "p2pID": None}

    try:
        while True:
            raw = await ws.recv_msg()
            if raw is None:
                break
            if raw.strip().startswith(POLICY_REQUEST):
                # Flash asks before it lets the SWF see Event.CONNECT
                await ws.send_msg(POLICY_XML)
                print(f"[relay] served the socket policy to {tag}", flush=True)
                continue
            msg = parse_frame(raw)
            if not msg:
                continue
            cmd = msg.get("cmd", "post")
            game_id = str(msg.get("gameID", "0"))

            if cmd == "connect":
                pid = make_pid()
                me["p2pID"] = pid
                # The connect record's gameID is unreliable: the client sends it
                # before connectGameLobby() has run (its own socket-connect race),
                # so the lobby is resolved from the first post instead - and the
                # replay happens there, once we know which lobby this really is.
                me["lobby_key"] = None
                RELAY.clients[pid] = me
                print(f"[relay] {pid} connected to lobby {game_id}", flush=True)
                await ws.send_msg(
                    (
                        json.dumps(
                            {"cmd": "welcome", "p2pID": pid, "gameID": game_id}
                        )
                        + "\x00"
                    ).encode("utf-8")
                )
                continue

            pid = msg.get("p2pID", me["p2pID"])
            if not pid:
                continue
            me["p2pID"] = pid

            # A post without a gameID (older clients) must stay in the lobby its
            # connection announced - defaulting to "0" split it off into a
            # phantom lobby whose broadcasts reached nobody.
            game_id = str(msg.get("gameID") or me.get("lobby_key") or "0")
            if me["lobby_key"] is None:
                me["lobby_key"] = game_id
                RELAY.clients[pid] = me
                await replay_lobby_state(ws, me)
            lobby = RELAY.lobby(game_id)
            _apply_state(lobby, msg, pid)
            print(f"[relay] post from {pid} type {msg.get('type')} -> lobby {game_id}",
                  flush=True)
            env = {
                "cmd": "post",
                "p2pID": pid,
                "type": msg.get("type"),
                "data": msg.get("data"),
            }
            await RELAY.broadcast(ws, lobby, pid, env)
    except (asyncio.IncompleteReadError, ConnectionError):
        pass
    except Exception as exc:  # keep one bad client from killing the relay
        print(f"[relay] client error: {exc!r}", flush=True)
    finally:
        pid = me.get("p2pID")
        gid = me.get("lobby_key")
        if pid and RELAY.clients.get(pid) is me:
            lobby = RELAY.lobby(gid) if gid else None
            if lobby is not None:
                seat = lobby.seats.pop(pid, None)
                if seat:
                    lobby.rooms[seat[0]][seat[1]] = ""
                lobby.infos.pop(pid, None)
            del RELAY.clients[pid]
            if lobby is not None:
                await RELAY.broadcast(
                    ws, lobby, pid, {"cmd": "post", "p2pID": pid, "type": 2, "data": None}
                )
        try:
            w = getattr(ws, "writer", None)
            if w is not None:
                w.close()
        except Exception:
            pass


async def handle_websockets(ws):
    """`websockets`-package path; raw is str for TEXT frames, bytes for BINARY."""
    me: dict = {"raw": ws, "lobby_key": None, "p2pID": None}
    try:
        async for raw in ws:
            data = raw if isinstance(raw, (bytes, bytearray)) else raw.encode("utf-8")
            msg = parse_frame(data)
            if not msg:
                continue
            cmd = msg.get("cmd", "post")
            game_id = str(msg.get("gameID", "0"))
            if cmd == "connect":
                pid = make_pid()
                # lobby_key stays None until the first post - see the raw
                # backend's note on the connect record's unreliable gameID.
                me = {"raw": ws, "lobby_key": None, "p2pID": pid}
                RELAY.clients[pid] = me
                await ws.send(
                    json.dumps({"cmd": "welcome", "p2pID": pid, "gameID": game_id})
                    + "\x00"
                )
                print(f"[relay] {pid} connected to lobby {game_id}", flush=True)
                continue
            pid = msg.get("p2pID", me["p2pID"])
            if not pid:
                continue
            me["p2pID"] = pid
            # keep posts without a gameID in the connection's own lobby (see the
            # raw backend's note: defaulting to "0" split off a phantom lobby)
            game_id = str(msg.get("gameID") or me.get("lobby_key") or "0")
            if me["lobby_key"] is None:
                me["lobby_key"] = game_id
                RELAY.clients[pid] = me
                await replay_lobby_state(ws, me)
            lobby = RELAY.lobby(game_id)
            _apply_state(lobby, msg, pid)
            print(f"[relay] post from {pid} type {msg.get('type')} -> lobby {game_id}",
                  flush=True)
            env = {
                "cmd": "post",
                "p2pID": pid,
                "type": msg.get("type"),
                "data": msg.get("data"),
            }
            await RELAY.broadcast(ws, lobby, pid, env)
    except Exception as exc:
        print(f"[relay] client error: {exc!r}", flush=True)
    finally:
        pid = me.get("p2pID")
        gid = me.get("lobby_key")
        if pid and RELAY.clients.get(pid) is me:
            del RELAY.clients[pid]
        if pid and gid:
            lobby = RELAY.lobby(gid)
            seat = lobby.seats.pop(pid, None)
            if seat:
                lobby.rooms[seat[0]][seat[1]] = ""
            lobby.infos.pop(pid, None)
            await RELAY.broadcast(
                ws, lobby, pid, {"cmd": "post", "p2pID": pid, "type": 2, "data": None}
            )


# ------------------------------------------------------------------- main
def banner(host: str, port: int, backend: str) -> None:
    print(
        f"LPO relay listening on ws://{host}:{port}  [{backend} backend, "
        f"python {sys.version.split()[0]}]",
        flush=True,
    )


async def main(host: str, port: int, backend: str = "auto"):
    """Default: the built-in server, which speaks BOTH transports on one port -
    WebSocket for Ruffle's socketProxy and raw XMLSocket for real Flash.  The
    `websockets` package can only serve the WebSocket half, so it is now opt-in
    (--backend websockets) and cannot serve the publisher browser."""
    if backend == "websockets":
        if websockets is None:
            print(
                "[relay] --backend websockets was requested but the package is not "
                f"usable here ({_WS_IMPORT_ERROR!r}); using the built-in server",
                flush=True,
            )
        else:
            print(
                "[relay] note: the websockets backend serves Ruffle only - a real "
                "Flash XMLSocket client (publisher browser) cannot connect to it",
                flush=True,
            )
            async with websockets.serve(
                lambda ws: handle_websockets(ws), host, port
            ):
                banner(host, port, "websockets (Ruffle only)")
                await asyncio.Future()
                return

    # Flash asks the master policy port 843 first; answering there removes its
    # ~2 s wait before it falls back to the target port.  Best effort: another
    # policy server may already own 843.
    policy = None
    if port != 843:
        try:
            policy = await asyncio.start_server(handle_conn, host, 843)
        except OSError as exc:
            print(f"[relay] master policy port 843 unavailable ({exc}); "
                  f"Flash will ask on port {port} instead", flush=True)

    server = await asyncio.start_server(handle_conn, host, port)
    async with server:
        banner(host, port, "built-in: websocket + raw XMLSocket")
        if policy is not None:
            print("[relay] socket policy also served on port 843", flush=True)
            async with policy:
                await server.serve_forever()
        else:
            await server.serve_forever()


def _port_answers(host: str, port: int, timeout: float = 1.5) -> bool:
    """True only when the listener on host:port answers a WebSocket handshake -
    i.e. it really is an LPO relay and not some unrelated program."""
    import base64
    import os

    probe_host = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    req = (
        f"GET / HTTP/1.1\r\nHost: {probe_host}:{port}\r\nUpgrade: websocket\r\n"
        f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    ).encode("ascii")
    try:
        with socket.create_connection((probe_host, port), timeout=timeout) as s:
            s.sendall(req)
            s.settimeout(timeout)
            data = s.recv(1024)
            # only the status line matters; the rest of the handshake head may
            # still be in flight (it is longer than one recv window)
            return data.startswith(b"HTTP/1.1 101")
    except OSError:
        return False


def main_cli() -> int:
    p = argparse.ArgumentParser(description="LPO LAN multiplayer relay")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8443)
    p.add_argument("--backend", choices=("auto", "websockets", "raw"), default="auto")
    args = p.parse_args()

    try:
        asyncio.run(main(args.host, args.port, args.backend))
    except KeyboardInterrupt:
        print("[relay] stopped", flush=True)
        return 0
    except OSError as exc:
        if _port_answers(args.host, args.port):
            print(
                f"[relay] port {args.port} is already taken by a running relay - "
                "the game will connect to that one, nothing to do here.",
                flush=True,
            )
            print(
                "[relay] (started by Start_Server_GUI.pyw, or by another copy of this "
                "file. Close that window first if you want to restart it; use "
                "--port 8444 to run a second relay for testing.)",
                flush=True,
            )
            return 0
        winerr = getattr(exc, "winerror", None)
        print(
            f"[relay] could not listen on {args.host}:{args.port} - {exc}"
            + (f" (WinError {winerr})" if winerr else ""),
            flush=True,
        )
        print(
            "[relay] another program owns the port and does not answer like a relay. "
            "Change it with --port, or free the port and retry.",
            flush=True,
        )
        return 2
    except Exception as exc:
        import traceback

        print(f"[relay] startup failed: {exc!r}", flush=True)
        traceback.print_exc()
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main_cli())
