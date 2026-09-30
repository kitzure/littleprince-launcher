#!/usr/bin/env python3
"""Add-friend wire check: the mail letter path the client actually drives.

Drives server.dispatch_service with the exact packet the Flash client's
RemoteService sends (NetConnection.call("PrinceOnline.serviceRequest",
responder, reqestList) -> body [[{0: {type, data}}]] ) for the three services the
mail panel touches - getMyFriends2, checkMail, confirmBeFriend - and prints the
decoded payloads, so the reply shapes can be checked against what the client's
handler reads in RemoteService.serviceResponse.

Runs on a scratch copy of the pack's lpo/ - never the pack's own data files.
"""
import json
import pathlib
import shutil
import struct
import sys

PACK = pathlib.Path("/home/yoke/Downloads/littleprince-launcher")
SCRATCH = pathlib.Path("/tmp/lpo_afwire/lpo")
OKS = []


def prep():
    shutil.rmtree(SCRATCH.parent, ignore_errors=True)
    SCRATCH.parent.mkdir(parents=True)
    shutil.copytree(PACK / "lpo", SCRATCH,
                    ignore=shutil.ignore_patterns(
                        "__pycache__", "accounts.json", "friends.json",
                        "mails.json", "pending.json", "notices.json",
                        "notice_content", "level_scores.json", "cloud"))
    (SCRATCH / "accounts.json").write_text('{"accounts": []}')
    # cloud/ is only ever symlinked by the pack; nothing here needs it.
    (SCRATCH / "cloud").symlink_to(PACK / "lpo/cloud")
    print("scratch:", SCRATCH)


prep()
sys.path.insert(0, str(SCRATCH))
import amf0        # noqa: E402
import accounts    # noqa: E402
import server      # noqa: E402


def check(label, got, want=True):
    ok = got == want
    OKS.append(ok)
    print("   %-58s %s  (got %r, want %r)" % (label, "OK " if ok else "FAIL", got, want))


SENT = []


def client_packet(req, target="PrinceOnline.serviceRequest", rid="/1", value=None):
    """The whole gateway packet the publisher's Flash client sends."""
    global SENT
    if value is None:
        value = amf0.encode([[amf0.AmfEcmaArray({"0": amf0.AmfObject(req)})]])
    SENT = [req]
    out = struct.pack("!HHH", 0, 0, 1)
    for s in (target, rid):
        b = s.encode("utf-8")
        out += bytes([0x02]) + struct.pack("!H", len(b)) + b
    return out + struct.pack("!I", len(value)) + value


def send(req, service=None, show=True):
    body = client_packet(req)
    parsed = server.parse_amf0_request(body)
    st, tgt, _rid = server.extract_service_type(parsed)
    if service:
        check("packet names its service (%s)" % service, st.lower(), service.lower())
    blob = server.dispatch_service(st, tgt or "gateway", body)
    out = {}
    for v in amf0.decode(blob):
        if isinstance(v, dict):
            out.update(v)
    if show:
        print("   request  :", json.dumps({k: (str(v) if not isinstance(v, (list, dict)) else v)
                                           for k, v in req.items()}, ensure_ascii=False)[:160])
        print("   reply    : %d bytes, response=%r, keys=%s"
              % (len(blob), out.get("response"), sorted(out.keys())))
    return out, blob


# ---------------------------------------------------------------- accounts
ACCTS = {}
for email, name, sex, uid in (("me@test.local", "Me", 1, "10001"),
                              ("pal@test.local", "Pal", 2, "10002")):
    a = accounts.create(email, "testpass", {"name": name, "sex": sex, "uid": uid},
                        login_name=email.split("@")[0] + "acct")
    ACCTS[email] = a
UID = {e: str(a.get("uid") or (a.get("profile") or {}).get("uid")) for e, a in ACCTS.items()}
print("accounts:", UID)


def as_player(email):
    server.CURRENT_PLAYER = {"email": email, "profile": ACCTS[email]["profile"]}


def store(name):
    p = SCRATCH / name
    return json.loads(p.read_text()) if p.is_file() else {}


print("\n=== 1. pal asks me to be friends: requestBeFriend (data=[uid, text]) ===")
as_player("pal@test.local")
rep, _ = send({"type": "requestBeFriend",
               "data": [float(UID["me@test.local"]), "我誠意邀請你成為我的朋友。"]},
              service="requestBeFriend")
check("requestBeFriend accepted", rep.get("response"), "requestBeFriend")
check("  a request is not yet a friendship", server.my_friend_uids(), [])

print("\n=== 2. my Mail panel: checkMail - the shape updateView parses ===")
as_player("me@test.local")
rep, _ = send({"type": "checkMail"}, service="checkMail")
ulist, mlist = rep.get("ulist") or [], rep.get("list") or []
print("   ulist rows :", len(ulist))
print("     ulist[0] :", [str(x) for x in ulist[0]])
print("     list[0]  :", [str(x) for x in mlist[0]])
check("checkMail accepted", rep.get("response"), "checkMail")
check("  ulist row len (RemoteService: data2ObjAtt uid,name + splice(2,16))",
      len(ulist[0]), 18)
check("  ulist[0][0] == the sender's uid (matched against list[i][1])",
      str(int(ulist[0][0])), UID["pal@test.local"])
check("  list row len  [mid, uid, date, read, type, message, can_reply]",
      len(mlist[0]), 7)
check("  type == 1 -> Mail.updateView shows the 確認朋友 button", int(mlist[0][4]), 1)

print("\n=== 3. my friend list BEFORE the confirm: getMyFriends2 ===")
as_player("me@test.local")
rep, _ = send({"type": "getMyFriends2"}, service="getMyFriends2")
before = rep.get("list") or []
print("   list rows  :", len(before))
check("getMyFriends2 accepted", rep.get("response"), "getMyFriends2")
check("  no friends yet", len(before), 0)

print("\n=== 4. I press 確認朋友 -> confirmBeFriend(data = sender uid) ===")
as_player("me@test.local")
rep, _ = send({"type": "confirmBeFriend", "data": float(UID["pal@test.local"])},
              service="confirmBeFriend")
print("   reply fid  :", rep.get("fid"), "(client reads param1.fid)")
check("confirmBeFriend accepted", rep.get("response"), "confirmBeFriend")
check("  fid == the confirmed friend", str(int(rep.get("fid", -1))), UID["pal@test.local"])

print("\n=== 5. friend lists after the confirm (what the client then re-reads) ===")
as_player("me@test.local")
rep, _ = send({"type": "getMyFriends2"}, service="getMyFriends2")
after = rep.get("list") or []
print("   my list rows:", len(after), [str(r[0]) for r in after])
check("  getMyFriends2 now reports 1 player", len(after), 1)
check("    and it is the requester", str(int(after[0][0])), UID["pal@test.local"])
check("  mutual: pal's own list holds me",
      sorted(str(u) for u in (store("friends.json").get("pal@test.local") or [])),
      sorted([UID["me@test.local"]]))
check("  pending cleared for me", server.pending_requests("me@test.local"), [])
check("  pending cleared for pal", server.pending_requests("pal@test.local"), [])

print("\n=== 6. what my Mail panel shows next: checkMail again ===")
rep, _ = send({"type": "checkMail"}, service="checkMail")
mlist2 = rep.get("list") or []
print("   letters left in my mailbox:", len(mlist2))
for row in mlist2:
    print("     mid=%s from=%s type=%s read=%s msg=%r"
          % (row[0], row[1], row[4], row[3], str(row[5])[:30]))
LEFT = len(mlist2)
check("  the accepted request letter is consumed", LEFT, 0)
rep, _ = send({"type": "haveNewEmail"}, service="haveNewEmail", show=False)
check("  the owl's unread count is back to 0", str(rep.get("total")), "0")

print("\n=== 7. pressing it again changes nothing (idempotent) ===")
as_player("me@test.local")
for _ in range(2):
    send({"type": "confirmBeFriend", "data": float(UID["pal@test.local"])},
         service=None, show=False)
check("still exactly one friend", sorted(server.my_friend_uids()), sorted([UID["pal@test.local"]]))
check("pal still has exactly one friend",
      sorted(str(u) for u in (store("friends.json").get("pal@test.local") or [])),
      sorted([UID["me@test.local"]]))
rep, _ = send({"type": "checkMail"}, show=False)
check("  still no letters (nothing left to consume)", len(rep.get("list") or []), 0)

print("\n=== 8. only the request letter goes: plain letters / gifts / other senders ===")
as_player("me@test.local")
def add_row(sender, kind, text="x"):
    mp = SCRATCH / "mails.json"
    st = json.loads(mp.read_text()) if mp.is_file() else {}
    rows = st.get("me@test.local") or []
    rows.append({"mid": 900 + len(rows), "from": sender, "date": "2026-09-28",
                 "read": 1, "type": kind, "message": text, "can_reply": 1})
    st["me@test.local"] = rows
    mp.write_text(json.dumps(st, ensure_ascii=False))
    return len(rows)

add_row(UID["pal@test.local"], 0, "a plain letter from pal")
add_row(UID["pal@test.local"], 2, "a gift from pal")
add_row("10007", 1, "a request from someone else")
add_row(UID["pal@test.local"], 1, "a NEW request from pal")
rep, _ = send({"type": "checkMail"}, show=False)
print("   mailbox before the press:", [[str(r[0]), int(r[4])] for r in rep.get("list") or []])
rep, _ = send({"type": "confirmBeFriend", "data": float(UID["pal@test.local"])},
              service="confirmBeFriend", show=False)
rep, _ = send({"type": "checkMail"}, show=False)
rows = rep.get("list") or []
print("   mailbox after the press :", [[str(r[0]), int(r[4]), str(r[5])[:24]] for r in rows])
check("  only pal's type-1 letters were consumed", len(rows), 3)
check("  the plain letter from pal survived (and still reports type 0)",
      any(int(r[4]) == 0 and str(int(r[1])) == UID["pal@test.local"] for r in rows), True)
check("  the gift from pal survived",
      any(int(r[4]) == 2 and str(int(r[1])) == UID["pal@test.local"] for r in rows), True)
check("  the other sender's request survived",
      any(int(r[4]) == 1 and str(int(r[1])) == "10007" for r in rows), True)

print("\n=== 9. a letter whose sender is NOT a local account ===")
as_player("me@test.local")
mp = SCRATCH / "mails.json"
st = json.loads(mp.read_text())
rows = st.get("me@test.local") or []
rows.append({"mid": 999, "from": "88888", "date": "2026-09-28", "read": 0,
             "type": 1, "message": "request from a deleted account", "can_reply": 1})
st["me@test.local"] = rows
mp.write_text(json.dumps(st, ensure_ascii=False))
rep, _ = send({"type": "checkMail"}, show=False)
before = len(rep.get("list") or [])
rep, _ = send({"type": "confirmBeFriend", "data": 88888.0}, service="confirmBeFriend", show=False)
check("confirmBeFriend still answers", rep.get("response"), "confirmBeFriend")
rep, _ = send({"type": "checkMail"}, show=False)
after = rep.get("list") or []
print("   letters %d -> %d ; my friends: %s" % (before, len(after), sorted(server.my_friend_uids())))
check("  its request letter is consumed too", len(after), before - 1)
check("  and the uid is still recorded as my friend",
      "88888" in server.my_friend_uids(), True)

print("\n%d/%d checks passed" % (sum(OKS), len(OKS)))
print("NOTE: the accepted request letter is consumed, so the panel visibly empties.")
sys.exit(0 if all(OKS) else 1)
