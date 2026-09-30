#!/bin/bash
# FFDec-verify each packaged SWF carries the change documented in PATCHING.md
cd /tmp || exit 1
PKG=$HOME/Downloads/prince-3in1-fix
run() {           # $1 = swf path, $2 = label
  local dir=/tmp/vchk_$2
  rm -rf "$dir"; mkdir -p "$dir"
  timeout 420 java -jar /tmp/ffdec/ffdec.jar -export script "$dir/out" "$1" >/dev/null 2>&1
  local n=$(find "$dir/out" -name '*.as' 2>/dev/null | wc -l)
  echo "=== $2  ($n scripts exported) ==="
  grep -rn 'loadFullVersion\|checkInput\|cdsingle\|cddemo\|activationSuccess\|getHDKey\|saveActivation\|loadOpening\|startInit' "$dir/out" --include='*.as' 2>/dev/null \
    | sed 's|/tmp/vchk_[^/]*/out/scripts/||' | head -14
  echo
}
run "$PKG/games/1-Starwish-Legend/start.swf" g1start
run "$PKG/games/3-Prince-Adventure/reg.swf" g3reg
run "$PKG/games/3-Prince-Adventure/login.swf" g3login
echo "=== 2-Little-Prince/reg.swf: script inventory (patch lives in frame 1) ==="
rm -rf /tmp/vchk_lp && mkdir -p /tmp/vchk_lp
timeout 420 java -jar /tmp/ffdec/ffdec.jar -export script /tmp/vchk_lp/out "$PKG/games/2-Little-Prince/reg.swf" >/dev/null 2>&1
find /tmp/vchk_lp/out -name '*.as' | wc -l
sed -n '1,24p' /tmp/vchk_lp/out/scripts/frame_1/DoAction.as 2>/dev/null
