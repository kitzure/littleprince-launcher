#!/usr/bin/env python3
"""Wire test for the friend-request letter's 確認朋友 (confirmBeFriend) button.

There is no Flash runtime here, so the button cannot be clicked in the real client.
What CAN be proven is the server half of the click: drive `server.dispatch_service`
exactly the way the client's RemoteService does (an AMF0 body carrying the request
object, service type taken from the body by extract_service_type), and assert

  (i)   confirming the letter is ACCEPTED, and the reply is the shape the client's
        handler reads (RemoteService's `confirmBeFriend` branch reads .response
        and .fid);
  (ii)  the friendship becomes MUTUAL (both accounts' friend lists);
  (iii) the letter the client renders is a TYPE-1 letter whose row/ulist shapes are
        what Mail.updateView/RemoteService.checkMail parse (that is what makes the
        確認朋友 button appear at all);
  (iv)  repeating the press does not corrupt state, and the pending request is
        cleared.

Runs on a scratch copy of the pack's lpo/ (never the pack's own data files).
"""
import json
import pathlib
import shutil
import struct
import sys

PACK = pathlib.Path("/home/yoke/Downloads/littleprince-launcher")
SCRATCH = pathlib.Path("/tmp/lpo_mailtest/lpo")
EMAILS = ("alpha@test.local", "beta@test.local", "gamma@test.local")
OKS = []


def prep_scratch():
    shutil.rmtree(SCRATCH.parent, ignore_errors=True)
    SCRATCH.parent.mkdir(parents=True)
    shutil.copytree(PACK / "lpo", SCRATCH,
                    ignore=shutil.ignore_patterns("__pycache__", "accounts.json",
                                                  "friends.json", "mails.json",
                                                  "pending.json", "notices.json",
                                                  "notice_content", "level_scores.json"))
    (SCRATCH / "accounts.json").write_text('{"accounts": []}')
    # cloud/ is only symlinked by the pack; nothing here needs it.
    print("scratch:", SCRATCH)


prep_scratch()
sys.path.insert(0, str(SCRATCH))
import amf0        # noqa: E402
import accounts    # noqa: E402
import server      # noqa: E402


def check(label, got, want=True):
    ok = got == want
    OKS.append(ok)
    print("   %-62s %s   (got %r, want %r)" % (label, "OK " if ok else "FAIL", got, want))


def make_accounts():
    out = {}
    for email, name, sex in (("alpha@test.local", "Alpha", 1),
                             ("beta@test.local", "Beta", 2),
                             ("gamma@test.local", "Gamma", 1)):
        acct = accounts.create(email, "testpass", {"name": name, "sex": sex},
                              login_name=email.split("@")[0])
        out[email] = acct
    return out


ACCTS = make_accounts()
UID = {e: str(a["uid"]) for e, a in ACCTS.items()}
print("uids:", UID)


def as_player(email):
    server.CURRENT_PLAYER = {"email": email, "profile": ACCTS[email]["profile"]}


def client_packet(req, target="PrinceOnline.serviceRequest", rid="/1", value=None):
    """A whole gateway packet, the envelope the publisher's Flash client sends.

    `_parse_body_header` variant A: 0x02 <len> target, 0x02 <len> response id,
    <u32 len> value - and the value is the request object one array deep
    (RemoteService.call("PrinceOnline.serviceRequest", responder, reqestList)).
    """
    if value is None:
        value = amf0.encode([[amf0.AmfEcmaArray({"0": amf0.AmfObject(req)})]])
    out = struct.pack("!HHH", 0, 0, 1)
    for s in (target, rid):
        b = s.encode("utf-8")
        out += bytes([0x02]) + struct.pack("!H", len(b)) + b
    return out + struct.pack("!I", len(value)) + value


def send(req, service=None):
    body = client_packet(req)
    parsed = server.parse_amf0_request(body)
    service_type, target, _rid = server.extract_service_type(parsed)
    if service:
        check("   packet names its service (%s)" % service, service_type.lower(), service.lower())
        check("   packet target", target, "PrinceOnline.serviceRequest")
    blob = server.dispatch_service(service_type, target or "gateway", body)
    out = {}
    for v in amf0.decode(blob):
        if isinstance(v, dict):
            out.update(v)
    return out, blob


def store(name):
    p = SCRATCH / name
    return json.loads(p.read_text()) if p.is_file() else {}


print("\n1. alpha asks beta (requestBeFriend) - the letter the button lives on")
as_player("alpha@test.local")
rep, _ = send({"type": "requestBeFriend", "data": [float(UID["beta@test.local"]),
                                                   "我誠意邀請你成為我的朋友。"]},
              service="requestBeFriend")
print("   requestBeFriend reply:", json.dumps({k: rep.get(k) for k in ("response", "fid", "pending")},
                                              ensure_ascii=False))
check("requestBeFriend accepted", rep.get("response"), "requestBeFriend")
check("  alpha is not a friend yet (a request is not the friendship)",
      server.my_friend_uids(), [])

print("\n2. the letter beta's Mail panel renders (checkMail shapes the client parses)")
as_player("beta@test.local")
rep, _ = send({"type": "checkMail"}, service="checkMail")
ulist, mlist = rep.get("ulist") or [], rep.get("list") or []
print("   checkMail reply: ulist=%d row(s), list=%d row(s)" % (len(ulist), len(mlist)))
print("     ulist[0][:2] =", ulist[0][:2], "(uid, name) + %d appearance parts" % (len(ulist[0]) - 2))
print("     list[0]      =", [str(x) for x in mlist[0]])
check("checkMail accepted", rep.get("response"), "checkMail")
check("one letter", len(mlist), 1)
check("  ulist row is [uid, name, *16] (>= 18 so splice(2,16) keeps uid/name)",
      len(ulist[0]), 18)
check("  ulist uid == the sender (RemoteService matches list[1] against it)",
      str(int(ulist[0][0])), UID["alpha@test.local"])
check("  list row is [mid, uid, date, read, type, message, can_reply]", len(mlist[0]), 7)
check("  sender uid in the row", str(int(mlist[0][1])), UID["alpha@test.local"])
check("  type == 1 -> Mail.updateView shows the 確認朋友 button", int(mlist[0][4]), 1)
check("  message is the invitation", str(mlist[0][5]), "我誠意邀請你成為我的朋友。")
check("  can_reply is set", int(mlist[0][6]), 1)

print("\n3. beta presses 確認朋友 -> confirmBeFriend(data = the sender's uid)")
as_player("beta@test.local")
rep, blob = send({"type": "confirmBeFriend", "data": float(UID["alpha@test.local"])},
                 service="confirmBeFriend")
print("   confirmBeFriend reply:", json.dumps({k: rep.get(k) for k in ("response", "fid")}))
check("confirmBeFriend accepted", rep.get("response"), "confirmBeFriend")
check("  fid == the confirmed friend (the client reads param1.fid)",
      int(rep.get("fid", -1)), int(UID["alpha@test.local"]))

print("\n4. the friendship is mutual and the pending request is gone")
check("beta's friends hold alpha", server.my_friend_uids(), [UID["alpha@test.local"]])
check("alpha's friends hold beta",
      [str(u) for u in (store("friends.json").get("alpha@test.local") or [])],
      [UID["beta@test.local"]])
check("beta's pending row is cleared", server.pending_requests("beta@test.local"), [])
check("alpha has no pending row either", server.pending_requests("alpha@test.local"), [])

print("\n5. pressing it twice (and the letter button's double path) changes nothing")
as_player("beta@test.local")
for _ in range(3):
    rep, _ = send({"type": "confirmBeFriend", "data": float(UID["alpha@test.local"])})
check("still exactly one friend", server.my_friend_uids(), [UID["alpha@test.local"]])
check("alpha still has exactly one friend",
      [str(u) for u in (store("friends.json").get("alpha@test.local") or [])],
      [UID["beta@test.local"]])
check("no pending row came back", server.pending_requests("beta@test.local"), [])
rep, _ = send({"type": "checkMail"})
check("beta's mailbox is emptied: the accepted request letter was consumed",
      len(rep.get("list") or []), 0)
check("  (there is no type-1 letter left to press again)",
      all(int(r[4]) != 1 for r in (rep.get("list") or [])))

print("\n6. an unknown / malformed uid is refused without touching the lists")
as_player("gamma@test.local")
rep, _ = send({"type": "confirmBeFriend", "data": float(UID["gamma@test.local"])})
check("confirming yourself is a no-op", server.my_friend_uids(), [])
check("  gamma's stored row is untouched",
      [str(u) for u in (store("friends.json").get("gamma@test.local") or [])], [])

print("\n7. the same service is reachable from every request shape the client uses")
as_player("gamma@test.local")
req = {"type": "confirmBeFriend", "data": float(UID["alpha@test.local"])}
for label, val in (("bare OBJECT body", amf0.encode([amf0.AmfObject(req)])),
                   ("STRICT_ARRAY > STRICT_ARRAY > OBJECT", amf0.encode([[amf0.AmfObject(req)]])),
                   ("STRICT_ARRAY > ECMA_ARRAY{0: OBJECT} (the client's shape)",
                    amf0.encode([[amf0.AmfEcmaArray({"0": amf0.AmfObject(req)})]]))):
    body = client_packet(req, value=val)
    parsed = server.parse_amf0_request(body)
    st, tgt, _ = server.extract_service_type(parsed)
    out = {}
    for v in amf0.decode(server.dispatch_service(st, tgt or "gateway", body)):
        if isinstance(v, dict):
            out.update(v)
    check("%s -> dispatched as confirmBeFriend" % label, out.get("response"), "confirmBeFriend")
check("  (this last step did confirm alpha<->gamma, as the reply says it would)",
      sorted(server.my_friend_uids()), sorted([UID["alpha@test.local"]]))

print("\n%d/%d checks passed" % (sum(OKS), len(OKS)))
sys.exit(0 if all(OKS) else 1)
