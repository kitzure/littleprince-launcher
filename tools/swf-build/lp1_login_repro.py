#!/usr/bin/env python3
"""Reproduce the LP1 login failure: find which step returns None."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher"))
sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher/lpo"))
import server as srv                                                    # noqa: E402

TARGET = "Prince1_personal.serviceRequest"
body = srv.encode_strict_array([{"type": "login", "loginName": "wangzi1",
                                 "data": ["wangzi1", "x"]}])

print("=== step by step, exactly as handle_amf_gateway does ===")
data = srv.dispatch_service("login", TARGET, body)
print("  dispatch_service     ->", type(data).__name__, len(data) if data else data)
if data is None:
    print("  ^^^ THIS is the None")
else:
    data = srv.merge_maze_reply(body, data)
    print("  merge_maze_reply     ->", type(data).__name__,
          len(data) if data is not None else data)
    data = srv.merge_login_reply(body, data, 1)
    print("  merge_login_reply    ->", type(data).__name__,
          len(data) if data is not None else data)
    data = srv.merge_friend_reply(body, data)
    print("  merge_friend_reply   ->", type(data).__name__,
          len(data) if data is not None else data)

print("\n=== and cloud_login_reply directly (what LP1's login should hit) ===")
try:
    out = srv.cloud_login_reply(body, TARGET)
    print("  cloud_login_reply    ->", type(out).__name__,
          len(out) if out is not None else out)
except Exception as e:                                                  # noqa: BLE001
    import traceback
    traceback.print_exc()

print("\n=== does the prince1 branch even run? ===")
try:
    reqs = srv.cloud_requests(body)
    print("  cloud_requests       ->", reqs)
except Exception as e:                                                  # noqa: BLE001
    print("  cloud_requests raised:", e)
print("  known accounts       :", [a.get("login_name") for a in srv.accounts.all_accounts()])
