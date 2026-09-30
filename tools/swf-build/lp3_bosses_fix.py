import pathlib
import re
import subprocess
import sys

S = pathlib.Path.home() / "Downloads/littleprince-launcher/lpo/server.py"
src = S.read_text()

OLD = '''        "detail": "process = 3, which is exactly what the client's own killBoss() counts "
                  "up to (it increments process[0] until it reaches 3).  The %d boss "
                  "cards in the card panel only open for purchase at 3, so pair this "
                  "with Max out the points." % boss_cards,'''
NEW = '''        "detail": "process = 3, which is exactly what the client's own killBoss() counts "
                  "up to (it increments process[0] until it reaches 3).  The 4 boss "
                  "cards in the card panel only open for purchase at 3, so pair this "
                  "with Max out the points.",'''
if OLD in src:
    src = src.replace(OLD, NEW, 1)
    print("fixed: the %d placeholder is now a literal (the 4 boss cards)")
else:
    print("!! the broken block was not found verbatim - printing the region instead")
    i = src.find("lp3_bosses")
    print(src[i - 60:i + 700])
    sys.exit(1)

S.write_text(src)
r = subprocess.run([sys.executable, "-m", "py_compile", str(S)], capture_output=True, text=True)
print("py_compile:", "OK" if r.returncode == 0 else r.stderr[-300:])

sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher"))
sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher/lpo"))
import server as srv                                                    # noqa: E402

print("import OK - LP3 presets:", [p["id"] for p in srv.MODS_PRESETS if p["game"] == "LP3"])

EMAIL = "wangzi1@littleprince.local"
body = srv.encode_strict_array([{"type": "login", "loginName": "wangzi1",
                                 "data": ["wangzi1", "x"]}])


def lp3_login():
    blobs = srv.amf0.decode(srv.dispatch_service(
        "login", "Prince3_personal.serviceRequest", body))
    return next(b for b in blobs if isinstance(b, dict) and "response" in b)


print("\nprocess before:", lp3_login().get("process"))
acct, written = srv.apply_mods(EMAIL, "lp3_bosses")
print("preset wrote  :", sorted(written))
p = lp3_login()
print("process after :", p.get("process"))

setting = pathlib.Path("/tmp/lp3_src/scripts/__Packages/Prince3/Setting.as").read_text(errors="ignore")
cards = re.search(r"cardSetting\s*=\s*new Array\((.*?)\);", setting, re.S).group(1)
boss_flags = [b == "true" for b in re.findall(r"bosscard:(true|false)", cards)]
proc = [int(x) for x in str(p.get("process") or "0").split(",") if str(x).strip()]
proc0 = proc[0] if proc else 0
allowed = [i for i, is_boss in enumerate(boss_flags) if not (proc0 != 3 and is_boss)]
print("\n=== BuyCard's own gate, replayed ===")
print("   process[0] =", proc0)
print("   cards buyable: %d of %d" % (len(allowed), len(boss_flags)))
print("   every boss card buyable:", all(i in allowed
                                         for i, b in enumerate(boss_flags) if b))
