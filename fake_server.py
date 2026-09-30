#!/usr/bin/env python3
"""
 Little Prince Launcher - fake server  (Starwish Legend / Little Prince / Prince Adventure)
 ------------------------------------------------------------------
 ONE server for ALL THREE games. All of them talk to the very same
 official endpoint:

     http://www.little-prince.com.hk/littleprince/amfservice/gateway.php

 Answers:
   - AMF gateway.php   checkVersion / checkActivation / activation /
                       reactivation / connectActivationServer / anything
                       unknown  ->  e000 "activated"
   - validate.php      ->  valid=true   (LoadVars registration = full cd)
   - any GET           ->  network=1&status=ok  (the ping/online check)

 checkVersion deliberately replies "0.0,,"  — the client does
     if (Number(serverVer) > Number(_root.verNumber)) showUpdatePopup()
 so 0.0 is never "newer" and the update popup never appears, on any of
 the three games.

 HOSTS HANDLING (new)
   On start the server makes sure these lines exist in the hosts file:
       127.0.0.1 www.little-prince.com.hk
       127.0.0.1 little-prince.com.hk
       127.0.0.1 www.sunnyinteractive.com
       127.0.0.1 file.sunnyinteractive.com
   and marks them with "# littleprince-launcher".  When you stop the server
   (Ctrl+C, closing the window, or a normal exit) exactly those marked
   lines are removed again, so there is nothing to undo by hand.
   Needs admin/root for the hosts file; if it cannot write, it says so
   and keeps running (the games are patched anyway).

   Why the redirect matters: the official server is still online and
   answers checkActivation with "e091", which makes the game show
   error 091 ("this computer's activation data is incorrect") and delete
   its activation data.  The redirect must be active while playing.

 Run:  python fake_server.py [port]        (default 80)
"""

import atexit
import os
import signal
import socket
import struct
import sys
import threading
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(SCRIPT_DIR, 'littleprince_patcher.log')

ONLINE_HOST = 'www1.little-prince.com.hk'      # Little Prince Online
ONLINE_PORT = int(os.environ.get('LPO_PORT', '8080'))
DOMAINS = ('www.little-prince.com.hk', 'little-prince.com.hk', ONLINE_HOST,
           'www.sunnyinteractive.com', 'file.sunnyinteractive.com')
MARK = '# littleprince-launcher'

BANNER = (
    "\n"
    "  Little Prince Launcher - fake server\n"
    "  Starwish Legend / Little Prince / Prince Adventure\n"
    "  one server, all three games\n"
)


def log(msg):
    line = time.strftime('%H:%M:%S') + " " + str(msg)
    print(line, flush=True)
    try:
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


# ---------------- hosts file (add on start, revert on exit) ----------------
def hosts_path():
    if os.name != 'nt':
        log("  hosts: this build is for Windows only - no redirect attempted")
        return None
    root = os.environ.get('SystemRoot', r'C:\Windows')
    return os.path.join(root, 'System32', 'drivers', 'etc', 'hosts')


def flush_dns():
    if os.name == 'nt':
        try:
            os.system('ipconfig /flushdns >nul 2>&1')
        except Exception:
            pass


HOSTS_STATE = {'added': [], 'path': None}


def hosts_ensure():
    path = hosts_path()
    HOSTS_STATE['path'] = path
    if not path:
        return
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()
    except Exception as e:
        log("  hosts: cannot read %s (%s) - skipping redirect" % (path, e))
        return
    have = set()
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        parts = s.split()
        if parts and parts[0] == '127.0.0.1':
            have.update(parts[1:])
    lines = [l for l in text.splitlines() if l.strip()]
    redirects = [l.strip() for l in lines
                 if l.split()[:1] == ['127.0.0.1'] and (set(l.split()[1:]) & set(DOMAINS))]
    if all(d in have for d in DOMAINS):
        # someone else (the launcher .bat, or an earlier run) already added them:
        # remember the exact lines so they are cleaned up when this server stops.
        HOSTS_STATE['added'] = redirects
        log("  hosts: redirect already in place (%s) - will be removed on exit" % path)
        return
    block = MARK + "\n" + "".join("127.0.0.1 %s\n" % d for d in DOMAINS)
    try:
        with open(path, 'a', encoding='utf-8') as f:
            if text and not text.endswith('\n'):
                f.write('\n')
            f.write(block)
        HOSTS_STATE['added'] = block.splitlines()
        flush_dns()
        log("  hosts: added 4 redirect lines to %s (removed again on exit)" % path)
    except Exception as e:
        log("  hosts: cannot write %s (%s)" % (path, e))
        log("  hosts: run this server as admin/root to get the redirect")


def hosts_revert():
    added = HOSTS_STATE.get('added')
    path = HOSTS_STATE.get('path')
    if not added or not path:
        return
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.read().splitlines()
        keep = [l for l in lines if l.strip() not in added]
        with open(path, 'w', encoding='utf-8') as f:
            f.write("\n".join(keep) + "\n")
        flush_dns()
        log("  hosts: redirect removed - %s is back to normal" % path)
    except Exception as e:
        log("  hosts: could not restore %s (%s) - use the Revert hosts button" % (path, e))
    HOSTS_STATE['added'] = []


# --- Windows: closing the console window (X) does NOT run atexit handlers,
# --- so hook the console control events to revert the hosts file anyway.
_WIN_HANDLER = None
_WIN_EVENTS = {0: 'CTRL_C', 1: 'CTRL_BREAK', 2: 'CTRL_CLOSE', 5: 'LOGOFF', 6: 'SHUTDOWN'}


def install_windows_console_handler():
    global _WIN_HANDLER
    if os.name != 'nt':
        return
    try:
        import ctypes
        from ctypes import wintypes
        proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

        def _handler(event):
            log("  console event %s (%d) - reverting hosts" %
                (_WIN_EVENTS.get(event, '?'), event))
            try:
                hosts_revert()
            except Exception:
                pass
            if event in (0, 2, 5, 6):      # C / window close / logoff / shutdown
                os._exit(0)
            return False                   # CTRL_BREAK: let Python handle it

        _WIN_HANDLER = proto(_handler)     # keep a reference or it gets collected
        ctypes.windll.kernel32.SetConsoleCtrlHandler(_WIN_HANDLER, True)
        log("  hosts: console handler installed (closing this window reverts the hosts file)")
    except Exception as e:
        log("  hosts: could not install console handler (%s)" % e)


# ---------------- AMF0 encode / decode ----------------
def e_str(s):
    b = s.encode('utf-8') if isinstance(s, str) else s
    return struct.pack('>H', len(b)) + b


def e_bool(b):
    return bytes([1 if b else 0])


def e_obj(props):
    r = bytes([0x03])
    for name, tbyte, vbytes in props:
        r += e_str(name) + bytes([tbyte]) + vbytes
    r += b'\x00\x00\x09'
    return r


def r_str(d, p):
    l = struct.unpack('>H', d[p:p + 2])[0]
    return d[p + 2:p + 2 + l].decode('utf-8', errors='replace'), p + 2 + l


def r_val(d, p):
    if p >= len(d):
        return None, p
    t = d[p]
    p += 1
    if t == 0x00:                                    # number
        if p + 8 > len(d):
            return None, len(d)
        return struct.unpack('>d', d[p:p + 8])[0], p + 8
    elif t == 0x01:                                  # boolean
        return bool(d[p]), p + 1
    elif t == 0x02:                                  # string
        return r_str(d, p)
    elif t == 0x03:                                  # object
        o = {}
        while p < len(d):
            if d[p:p + 3] == b'\x00\x00\x09':
                return o, p + 3
            k, p = r_str(d, p)
            v, p = r_val(d, p)
            o[k] = v
        return o, p
    elif t == 0x08:                                  # ECMA array
        cnt = struct.unpack('>I', d[p:p + 4])[0]
        p += 4
        o = {}
        while p < len(d):
            if d[p:p + 3] == b'\x00\x00\x09':
                return o, p + 3
            k, p = r_str(d, p)
            v, p = r_val(d, p)
            o[k] = v
        return o, p
    elif t in (0x05, 0x06):                          # null / undefined
        return None, p
    elif t == 0x0A:                                  # strict array
        cnt = struct.unpack('>I', d[p:p + 4])[0]
        p += 4
        arr = []
        for _ in range(cnt):
            if p >= len(d):
                break
            v, p = r_val(d, p)
            arr.append(v)
        return arr, p
    else:
        return '<0x%02x>' % t, len(d)


def find_method(val):
    """The games wrap args as [[{type:'checkActivation', ...}]] - dig deep."""
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return val.get('type') or val.get('method')
    if isinstance(val, list):
        for item in val:
            m = find_method(item)
            if m:
                return m
    return None


def parse_amf_body(body_data):
    try:
        v, bp = r_val(body_data, 0)
        method = find_method(v)
        args = []
        while bp < len(body_data):
            a, bp = r_val(body_data, bp)
            args.append(a)
        return method or 'unknown', args
    except Exception as e:
        log("  parse_amf_body error: " + str(e))
        return 'unknown', []


def parse_amf_packet(data):
    p = 6
    msgs = []
    msg_count = struct.unpack('>H', data[4:6])[0] if len(data) >= 6 else 1
    for _ in range(msg_count):
        tgt, p = r_str(data, p)
        ruri, p = r_str(data, p)
        bl = struct.unpack('>I', data[p:p + 4])[0]
        p += 4
        bd = data[p:p + bl]
        p += bl
        method, args = parse_amf_body(bd)
        msgs.append({'target': tgt, 'response_uri': ruri,
                     'method': method, 'args': args})
    return msgs


def build_amf_response(ruri, result_body):
    pkt = struct.pack('>H', 0) + struct.pack('>H', 0) + struct.pack('>H', 1)
    pkt += e_str(ruri + '/onResult')
    pkt += e_str('null')
    pkt += struct.pack('>I', len(result_body)) + result_body
    return pkt


# ---------------- handlers (flat format: the games read .message directly) ----------------
def h_check_version(args):
    # 0.0 is never newer than the local verNumber -> no update popup, all games.
    return e_obj([('response', 0x02, e_str('checkVersionResult')),
                  ('message', 0x02, e_str('0.0,,'))])


def h_check_activation(args):
    return e_obj([('response', 0x02, e_str('checkActivationResult')),
                  ('message', 0x02, e_str('e000,e000')),
                  ('activated', 0x01, e_bool(True)),
                  ('activationKey', 0x02, e_str('ACTIVATED'))])


def h_activation(args):
    for a in args:
        if isinstance(a, dict):
            for k, v in a.items():
                log("    %s: %s" % (k, str(v)[:80]))
    return e_obj([('response', 0x02, e_str('activationResult')),
                  ('message', 0x02, e_str('e000')),
                  ('activationKey', 0x02, e_str('ACTIVATED-12345')),
                  ('activated', 0x01, e_bool(True)),
                  ('rkey', 0x02, e_str('ABC123-xyz'))])


def h_connect_activation_server(args):
    return e_obj([('response', 0x02, e_str('activationResponse')),
                  ('message', 0x02, e_str('e000')),
                  ('activated', 0x01, e_bool(True)),
                  ('activationKey', 0x02, e_str('ACTIVATED'))])


def h_reactivation(args):
    return e_obj([('response', 0x02, e_str('reactivationResult')),
                  ('message', 0x02, e_str('e000'))])


HANDLERS = {
    'checkVersion': h_check_version,
    'checkActivation': h_check_activation,
    'activation': h_activation,
    'reactivation': h_reactivation,
    'connectActivationServer': h_connect_activation_server,
}


def send(conn, body, ctype=b'text/plain'):
    header = b"HTTP/1.1 200 OK\r\nContent-Type: " + ctype + b"\r\n"
    header += ("Content-Length: %d\r\n" % len(body)).encode()
    header += b"Connection: close\r\nCache-Control: no-cache\r\n\r\n"
    conn.sendall(header + body)


def relay_online(conn, request):
    """Pass Little Prince Online traffic to its own server, untouched."""
    try:
        head, sep, body = request.partition(b'\r\n\r\n')
        lines = [l for l in head.decode('utf-8', 'replace').split('\r\n')
                 if not l.lower().startswith('connection:')]
        lines.append('Connection: close')
        fixed = '\r\n'.join(lines).encode('utf-8') + sep + body
        with socket.create_connection(('127.0.0.1', ONLINE_PORT), timeout=10) as up:
            up.sendall(fixed)
            up.settimeout(60)
            while True:
                chunk = up.recv(65536)
                if not chunk:
                    break
                conn.sendall(chunk)
    except Exception as e:
        log("  online relay failed (%s) - is the online server running on port %d?"
            % (e, ONLINE_PORT))
        try:
            send(conn, b'online=0')
        except Exception:
            pass


def handle_client(conn, addr):
    try:
        conn.settimeout(30)
        request = b''
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            request += chunk
            if b'\r\n\r\n' in request:
                header_end = request.index(b'\r\n\r\n')
                headers_raw = request[:header_end].decode('utf-8', errors='replace')
                cl = 0
                for line in headers_raw.split('\r\n'):
                    if line.lower().startswith('content-length:'):
                        cl = int(line.split(':', 1)[1].strip())
                        break
                if len(request) - (header_end + 4) >= cl:
                    break

        if not request:
            return

        headers_raw = request[:request.index(b'\r\n\r\n')].decode('utf-8', errors='replace')
        first_line = headers_raw.split('\r\n')[0]
        parts = first_line.split(' ')
        method = parts[0] if parts else 'GET'
        path = parts[1] if len(parts) > 1 else '/'
        host = ''
        for line in headers_raw.split('\r\n')[1:]:
            if line.lower().startswith('host:'):
                host = line.split(':', 1)[1].strip()
                break

        tag = (" [" + host + "]") if host else ''

        # Little Prince Online runs on its own port - hand its traffic over
        plain_host = host.split(':')[0].lower()
        # The cloud games live under /LP/personal/ and link to themselves on both
        # publisher hosts, so serve that path whatever the hostname says.
        if (plain_host == ONLINE_HOST
                or path.startswith(('/web', '/admin', '/play', '/LP/personal/'))):
            log("relay %s%s -> online server (port %d)" % (path, tag, ONLINE_PORT))
            relay_online(conn, request)
            return

        if method in ('GET', 'HEAD'):
            if path.endswith('policy.xml'):
                log("GET %s%s -> cross-domain policy" % (path, tag))
                send(conn, b'<?xml version="1.0"?>'
                           b'<cross-domain-policy>'
                           b'<allow-access-from domain="*" to-ports="*" secure="false"/>'
                           b'</cross-domain-policy>', ctype=b'application/xml')
                return
            if path.startswith('/crossdomain.xml') or path.startswith('/clientaccesspolicy.xml'):
                log("GET %s%s -> crossdomain policy" % (path, tag))
                send(conn, b'<?xml version="1.0"?>'
                           b'<cross-domain-policy>'
                           b'<allow-access-from domain="*" to-ports="*" secure="false"/>'
                           b'</cross-domain-policy>', ctype=b'application/xml')
                return
            log("GET %s%s -> network ok" % (path, tag))
            send(conn, b'network=1&status=ok')
            return

        header_end = request.index(b'\r\n\r\n')
        body = request[header_end + 4:]
        log("POST %s%s (%d bytes)" % (path, tag, len(body)))

        # The cloud games (LP1/LP2/LP3) call .../gateway.php on this same host, but
        # their services belong to the online server - hand those over untouched.
        if (b'Prince1_personal' in body or b'Prince2_personal' in body
                or b'Prince3_personal' in body):
            log("  [cloud game service] -> online server (port %d)" % ONLINE_PORT)
            relay_online(conn, request)
            return

        # LoadVars registration check -> valid=true means "full cd"
        if 'validate.php' in path:
            log("  [validate.php] -> valid=true (fullcd)")
            send(conn, b'valid=true')
            return

        # AMF gateway.php
        # The cloud games open their NetConnection with an empty POST.  Parsing that
        # raised ("unpack requires a buffer of 2 bytes") and the connection was answered
        # with nothing at all, which real Flash tolerates but Ruffle does not - the game
        # then sits on its loading screen forever.  Answer with a valid, empty AMF packet
        # instead: six zero bytes are version 0, no headers, no bodies.
        if len(body) < 8:
            log("  [empty AMF request] -> valid empty AMF packet")
            send(conn, b'\x00\x00\x00\x00\x00\x00', b'application/x-amf')
            return
        try:
            msgs = parse_amf_packet(body)
            for msg in msgs:
                m = msg['method']
                log("  method: %s   target: %s" % (m, msg['target']))
                handler = HANDLERS.get(m)
                if handler:
                    result = handler(msg['args'])
                else:
                    log("  [unknown method] -> e000")
                    result = e_obj([('response', 0x02, e_str(m + 'Result')),
                                    ('message', 0x02, e_str('e000'))])
                resp_body = build_amf_response(msg['response_uri'], result)
                log("  -> responded %d bytes" % len(resp_body))
                send(conn, resp_body, b'application/x-amf')
                return
        except Exception as e:
            log("  AMF ERROR: " + str(e))
            import traceback
            traceback.print_exc()

        send(conn, b'')
    except Exception as e:
        log("connection error: " + str(e))
    finally:
        try:
            conn.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        conn.close()


def bye(signum=None, frame=None):
    hosts_revert()
    log("server stopped")
    sys.exit(0)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 80
    print(BANNER)
    if '--no-hosts' not in sys.argv:
        install_windows_console_handler()
        hosts_ensure()
        atexit.register(hosts_revert)
        for s in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(s, bye)
            except Exception:
                pass
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(('0.0.0.0', port))
    except OSError as e:
        log("Could not bind port %d: %s" % (port, e))
        log("Port 80 needs admin rights on Windows - run the .bat (it elevates),")
        log("or:  python fake_server.py 8080")
        hosts_revert()
        sys.exit(1)
    sock.listen(8)
    log("listening on 0.0.0.0:%d  (all three games)" % port)
    log("checkVersion -> 0.0,,")
    log("everything else -> e000 (activated) / valid=true")
    log("waiting for game requests ...  (Ctrl+C stops the server AND reverts hosts)")
    while True:
        conn, addr = sock.accept()
        threading.Thread(target=handle_client, args=(conn, addr),
                         daemon=True).start()


if __name__ == '__main__':
    main()
