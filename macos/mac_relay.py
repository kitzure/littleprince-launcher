#!/usr/bin/env python3
"""
HTTP relay for the macOS launcher.

The game's SWFs call absolute addresses (www.starwish-fair.com,
www1.little-prince.com.hk, ...). On Windows the launcher redirects those names
with the hosts file and listens on port 80, which needs administrator rights.
Here the browser is started with --proxy-server instead, so every request for
those names arrives at this relay and is handed to the local server on its high
port. No hosts edit, no port 80, no administrator rights.

There is only one backend on purpose, exactly like the Windows launcher: the
same server answers the CD games' activation checks and relays the online world
to the Little Prince Online mirror. That is what fake_server.py already does.
"""

import os
import socket
import sys
import threading

LISTEN_PORT = int(os.environ.get('LPR_RELAY_PORT', '8900'))
SERVER = ('127.0.0.1', int(os.environ.get('LPR_SERVER_PORT', '8081')))
ONLINE = ('127.0.0.1', int(os.environ.get('LPR_ONLINE_PORT', '8950')))

# Exactly the rule fake_server.py applies on Windows: traffic addressed to the
# online world's own host - or to the paths that belong to it - goes to the
# Little Prince Online mirror; everything else is the CD games' server, which
# answers their activation checks and hands their service calls on to the mirror.
ONLINE_HOST = 'www1.little-prince.com.hk'
ONLINE_PREFIXES = ('/web', '/admin', '/play', '/LP/personal/')


def route(host, path):
    plain = host.split(':')[0].strip().lower()
    if plain == ONLINE_HOST or any(path.startswith(p) for p in ONLINE_PREFIXES):
        return ONLINE, 'online world'
    return SERVER, 'cd games'

HOP_BY_HOP = ('connection', 'keep-alive', 'proxy-connection', 'proxy-authorization',
              'te', 'trailers', 'transfer-encoding', 'upgrade')


def log(msg):
    print('[relay] %s' % msg, flush=True)


def read_headers(sock_file):
    """Read one request head. Returns (method, target, [(name, value), ...]) or None."""
    line = sock_file.readline()
    if not line:
        return None
    parts = line.decode('latin-1').rstrip('\r\n').split()
    if len(parts) < 2:
        return None
    method, target = parts[0], parts[1]
    headers = []
    while True:
        line = sock_file.readline()
        if not line or line in (b'\r\n', b'\n'):
            break
        text = line.decode('latin-1').rstrip('\r\n')
        if ':' in text:
            name, _, value = text.partition(':')
            headers.append((name.strip(), value.strip()))
    return method, target, headers


def origin_form(target):
    """Turn the proxy's absolute form into the origin form the server expects."""
    if target.lower().startswith('http://'):
        rest = target[7:]
        return '/' + rest.split('/', 1)[1] if '/' in rest else '/'
    return target


def handle(client, addr):
    client.settimeout(60)
    sock_file = client.makefile('rb')
    request = read_headers(sock_file)
    if not request:
        client.close()
        return
    method, target, headers = request

    if method == 'CONNECT':                       # https - the game only speaks http
        log('CONNECT %s refused' % target)
        try:
            client.sendall(b'HTTP/1.1 501 Not Implemented\r\nContent-Length: 0\r\n\r\n')
        finally:
            client.close()
        return

    path = origin_form(target)

    body = b''
    length = 0
    for name, value in headers:
        if name.lower() == 'content-length':
            try:
                length = int(value)
            except ValueError:
                length = 0
    if length:
        body = sock_file.read(length) or b''

    host = ''
    for name, value in headers:
        if name.lower() == 'host':
            host = value
            break
    dest, label = route(host, path)
    if method != 'GET' or len(body) > 400:
        log('%s %s%s (%d bytes) -> %s' % (method, path[:70], ' [%s]' % host if host else '',
                                          len(body), label))

    try:
        with socket.create_connection(dest, timeout=15) as up:
            up_file = up.makefile('rb')
            # The backend is a plain HTTP server: it must see an origin-form
            # request line ("GET /path HTTP/1.1"), not the proxy's absolute form
            # ("GET http://host/path HTTP/1.1"), or it answers 404.
            lines = ['%s %s HTTP/1.1' % (method, path)]
            for name, value in headers:
                if name.lower() in HOP_BY_HOP:
                    continue
                if name.lower() == 'host':
                    value = '%s:%d' % dest
                lines.append('%s: %s' % (name, value))
            up.sendall(('\r\n'.join(lines) + '\r\n\r\n').encode('latin-1'))
            if body:
                up.sendall(body)
            while True:
                chunk = up_file.read(65536)
                if not chunk:
                    break
                client.sendall(chunk)
    except Exception as exc:
        log('upstream %s:%d failed: %s' % (dest[0], dest[1], exc))
        try:
            client.sendall(b'HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n')
        except Exception:
            pass
    finally:
        try:
            client.close()
        except Exception:
            pass


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('127.0.0.1', LISTEN_PORT))
    srv.listen(64)
    log('listening on 127.0.0.1:%d -> local server 127.0.0.1:%d' % (LISTEN_PORT, SERVER[1]))
    while True:
        try:
            client, addr = srv.accept()
        except KeyboardInterrupt:
            break
        threading.Thread(target=handle, args=(client, addr), daemon=True).start()
    srv.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
