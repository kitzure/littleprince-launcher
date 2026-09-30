#!/usr/bin/env python3
"""Repair dispatch_service: the leaderboard helper was spliced into its body.

`CLIENT_RANK_RESPONSES = {` landed at column 0 in the middle of dispatch_service, which
closed the function right there - every branch below it (the rank boards, the notice
board, the Prince1/2/3 logins, the friends lists) became the body of the helper that
followed, so dispatch_service fell off the end and returned None.  handle_amf_gateway
then crashed on len(None) and LP1's login died.

Fix: lift the helper out (above dispatch_service) so the swallowed branches rejoin the
function they belong to, and make the gateway refuse to crash on a None reply.
"""
import pathlib
import re
import subprocess
import sys

S = pathlib.Path.home() / "Downloads/littleprince-launcher/lpo/server.py"
lines = S.read_text().splitlines()

# ── 1. locate the misplaced helper (module-level, inside the function) ───────
start = next(i for i, l in enumerate(lines) if l.startswith("CLIENT_RANK_RESPONSES = {"))
end = next(i for i in range(start, len(lines))
           if lines[i].strip() == "return service_type")          # last line of the helper
helper = lines[start:end + 1]
print("helper block: lines %d-%d (%d lines)" % (start + 1, end + 1, len(helper)))
assert any("def rank_reply_name" in l for l in helper), "not the helper block"

# the swallowed branches must follow immediately, at indent 4, to rejoin the function
after = lines[end + 1:]
first_body = next(i for i, l in enumerate(after) if l.strip())
print("first line after the helper: %r" % after[first_body][:70])
assert after[first_body].startswith("    "), "the code after the helper is not an indented body"

func = next(i for i, l in enumerate(lines) if l.startswith("def dispatch_service"))
print("dispatch_service starts at line %d" % (func + 1))

# ── 2. move the helper above the function ───────────────────────────────────
rest = lines[:start] + lines[end + 1:]                 # dispatch body is whole again
func2 = next(i for i, l in enumerate(rest) if l.startswith("def dispatch_service"))
new = rest[:func2] + helper + ["", ""] + rest[func2:]
S.write_text("\n".join(new) + "\n")
print("helper moved above dispatch_service (now line %d)" % (func2 + 1))

# ── 3. the gateway must not crash on a None reply ───────────────────────────
src = S.read_text()
OLD = '''            body_data = dispatch_service(service_type, target, raw_body)'''
NEW = '''            body_data = dispatch_service(service_type, target, raw_body)
            if body_data is None:
                # A handler that fell through used to crash the whole gateway on
                # len(None) and kill the client's login.  Answer the generic reply and
                # say so, rather than dropping the connection.
                log.error(f"  dispatch returned nothing for service='{service_type}' "
                          f"target='{target}' - answering the generic reply")
                body_data = build_generic_ok_response()'''
if OLD in src:
    src = src.replace(OLD, NEW, 1)
    print("gateway now survives a None reply")
else:
    print("!! gateway anchor not found")
S.write_text(src)

r = subprocess.run([sys.executable, "-m", "py_compile", str(S)], capture_output=True, text=True)
print("py_compile:", "OK" if r.returncode == 0 else r.stderr[-400:])

# ── 4. structure check: every top-level def must still be top level ─────────
import ast
tree = ast.parse(S.read_text())
top = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
print("top-level defs now:", len(top))
print("  rank_reply_name at top level:", "rank_reply_name" in top)
print("  dispatch_service at top level:", "dispatch_service" in top)
