# How these patches were made

A short, repeatable recipe for the three games in this package — where the licence
check lives, which script holds it, and how each one was changed. Written so the
same thing can be re-derived from a clean copy of any of the three games.

---

## 1. Tools

* **JPEXS Free Flash Decompiler** (FFDec) — decompiles and recompiles AS2/AS3.
  The trees under `games/<game>/<swf>/scripts/` came from it:
  ```bash
  java -jar ffdec.jar -export script,text  out/  game.swf     # scripts/ + texts/
  java -jar ffdec.jar -format script:pcode -export script out/ game.swf   # pcode/
  ```
* A hex editor or Python (`zlib`, `struct`) for the byte-level checks.

## 2. Find the SWF that is actually loaded

The games ship as a **Zinc projector** (`start.exe`, UPX-packed). Two traps:

* The projector's **entry SWF is embedded inside the exe** — editing any external
  copy of it does nothing.
* The pages it loads at runtime (`reg.swf`, `login.swf`, …) are read **from the
  content folder**, so those *are* patchable.

Confirm which is which before spending time:

```bash
# what does the exe reference?
strings -a start.exe | grep -iE 'zinc|mdmwrdata|swfdata'
# which SWFs even mention the licence functions?
python3 - <<'EOF'
import zlib, glob, os
for p in sorted(glob.glob('content/*.swf')):
    d = open(p, 'rb').read()
    if d[:3] == b'CWS':
        try: d = d[:8] + zlib.decompress(d[8:])
        except Exception: continue
    hits = [k for k in (b'activationSuccess', b'checkActivation',
                        b'startInit', b'connectActivationServer') if k in d]
    if hits: print(os.path.basename(p), [h.decode() for h in hits])
EOF
```

Functions that are only **referenced** here (e.g. `reg.swf` calling
`_root.checkActivation()`) live in the embedded entry SWF and cannot be edited.
Functions that are **defined** here can be.

## 3. Find the script to patch

List every script with its frame label — the label is part of the name and you
need it verbatim later:

```bash
java -jar ffdec.jar -dumpAS2 game.swf
# /frame 1/DoAction
# /frame 3 (name: form)/DoAction
# /frame 15 (name: success)/DoAction
# /DefineButton2 (chid: 105)/BUTTONCONDACTION on(release)
```

Then read the decompiled tree and look for two things:

**a) the Activate button handler** — the green "start the game" button. It calls
the validator, usually `checkInput()` or `connectActivationServer()`. Sometimes the
button itself is a `DefineButton2` `on(release)` action instead of a frame script.

**b) the licence gate** — a function that answers "is this copy valid?". Search the
whole tree for it:

```bash
grep -rn "activationSuccess\|checkActivation\|startInit\|loadOpening\|loadFullVersion" \
     scripts/ | head -40
```

Two shapes show up:

* the gate is a **defined function** in an SWF you can patch → override it;
* the gate lives in the embedded entry SWF → you cannot edit it, but you *can*
  overwrite it at runtime from a loaded SWF, because the game's root timeline is
  `_level0`:
  ```actionscript
  _level0.activationSuccess = function(sn, hdkey, akey) { return true; };
  ```
  This is the trick all three games rely on.

## 4. The two changes that do the work

**A. Redirect the Activate button** — skip the serial/email/phone validator and
call the game's own *full-version* entry point instead:

```actionscript
btn_activate.onRelease = function()
{
   _root.startInit();          // was: this._parent.checkInput();
};
```

Point it at whatever the game's own success path calls — `_root.startInit()`,
`_root.loadFullVersion()`, or an AS3 class method such as
`Prince3.PrinceSystem.loadOpening()`.

**B. Force the licence gate** — `activationSuccess(sn, hdkey, akey)` guards both
full-version detection *and* account save/load, so returning `true` unlocks both.

Some builds additionally compare a stored hardware key against `getHDKey()`
before they run the gate, so that switch needs pinning too — otherwise the stored
`hdkey` and the compared one come from the same source and the check can fail:

```actionscript
_level0.getHDKey = function() { return "AAAA-AAA3"; };
```

And where the game only branches to full when an activation record exists, seed one:

```actionscript
if(_level0.saveActivation)
{
   _level0.saveActivation("Player","00000000","player@example.com",
                          "P1-ABCD-EFGH-IJKL-MNOP", _level0.getHDKey(), "e000");
}
```

Put all of this at the **top of frame 1 of the loaded form SWF**, wrapped in
`if(_level0){ … }` so it runs before the form's own preloader.

## 5. Exactly what was changed in this package

| Game | SWF | Script | Method | Change |
|---|---|---|---|---|
| Starwish Legend 星願外傳 | `1-Starwish-Legend/reg.swf` | `frame_3/DoAction_2` | `btn_activate.onRelease` | `this._parent.checkInput();` → `_root.loadFullVersion();` |
| Starwish Legend | `1-Starwish-Legend/start.swf` | `frame_3/DoAction_15` | `loadOpening()` | `if(reg._currentframe == 15) loadFullVersion(); else loadTrialVersion();` → `loadFullVersion();` |
| Starwish Legend | `1-Starwish-Legend/start.swf` | `frame_3/DoAction_32` | `loadTrialVersion()` | removed the auto-created DEMO user; `initSystem("cddemo")` → `initSystem("cdsingle")` |
| Starwish Legend | `1-Starwish-Legend/index.swf` | `frame_3/DoAction_34` | `loadTrialVersion()` | `initSystem("cddemo")` → `initSystem("cdsingle")` |
| Little Prince 星願小王子 | `2-Little-Prince/reg.swf` | `frame_1/DoAction` | frame 1 | prepended the `activationSuccess` / `getHDKey` / `saveActivation` block, body wrapped in `if(_level0){…}` |
| Little Prince | `2-Little-Prince/reg.swf` | `frame_3/DoAction` | `btn_activate.onRelease` | `this._parent.checkInput();` → `_root.startInit();` |
| Prince Adventure 星願歷奇 | `3-Prince-Adventure/reg.swf` | `frame_1/DoAction` | end of frame 1 | appended `if(_level0){ _level0.activationSuccess = function(){ return true; }; }` |
| Prince Adventure | `3-Prince-Adventure/reg.swf` | `frame_3/DoAction` | `btn_activate.onRelease` | `this._parent.checkInput();` → `Prince3.PrinceSystem.loadOpening();` |
| Prince Adventure | `3-Prince-Adventure/login.swf` | `frame_1/DoAction` | frame 1 | prepended the same `activationSuccess` override |

## 6. Recompiling

Always patch **onto the pristine original**, and replace **only the scripts you
edited** — every other script is left byte-identical:

```bash
# script name must come from -dumpAS2, frame label included
java -jar ffdec.jar -replace original.swf step1.swf "/frame 1/DoAction" edited_frame1.as
java -jar ffdec.jar -replace step1.swf patched.swf  "/frame 3 (name: form)/DoAction" edited_frame3.as
```

A bare `/frame 3/DoAction` is **not** recognised once the frame has a label —
`-replace` fails with *"not recognized as a CharacterId or a script name"*.

## 7. Verify before shipping

```bash
# 1. same number of scripts as the original
java -jar ffdec.jar -export script out/ patched.swf
find out -name '*.as' | wc -l

# 2. only the intended scripts differ
diff -rq pristine_out/ out/

# 3. run it
```

Step 2 is the one that catches real damage. A recompile that silently drops the
rest of a frame's script still produces a loadable SWF — it just changes behaviour
later.

For step 3, run the game with the bundled server up and confirm it reaches the
**world map**, with no error dialog and no trial banner. What the failure modes
look like:

| Symptom | Meaning |
|---|---|
| `錯誤:090` / `錯誤:091` "啟動資料不正確", then the game deletes `lic.dat` and closes | the licence gate still failed |
| registration form appears and the Activate button does nothing | the button redirect didn't land |
| black or white screen, game process alive | the patch skipped initialization the game needs |

## 8. Pitfalls

* **Don't gut the form frame.** `frame_3 (name: form)` also does `setBtn(...)`,
  the `restrict`/`tabIndex` setup and `stop()`. Leaving only the button handler
  produces a form with dead button states and a timeline that doesn't halt.
* **Never null-pad a constant-pool string** to change its length — the padding
  becomes phantom empty entries and shifts every following pool index. Shrink the
  array and update the pool length, the tag length and the SWF length together.
* **Don't "fix" the SWF length field** to the real file size. Some of these SWFs
  carry a wildly wrong value and the player tolerates it; correcting it can break
  tag parsing.
* **The entry SWF is embedded in the exe.** Patching the external `start.swf` or
  `index.swf` of a Zinc projector usually has no effect.
* **Keep the original SWFs** alongside the patched ones so the change stays
  reversible.
