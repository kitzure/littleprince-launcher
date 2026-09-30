#!/bin/bash
# Rebuild importing ONLY the edited class, so nothing else is recompiled.
set -e
cd /tmp
DEP="$HOME/Downloads/littleprince-launcher/lpo/patches/lib/lib.swf"
echo "deployed: $(ls -la "$DEP" | awk '{print $5" bytes"}')  md5 $(md5sum "$DEP" | cut -d' ' -f1)"

rm -rf /tmp/lpo_one /tmp/lib_one.swf /tmp/lpo_one_out
mkdir -p /tmp/lpo_one/scripts/PrinceOnline
cp /tmp/lpo_cur/scripts/PrinceOnline/UI_multiplay.as /tmp/lpo_one/scripts/PrinceOnline/

echo "--- importing single class into a copy of the deployed SWF ---"
cp "$DEP" /tmp/lib_one_base.swf
timeout 550 java -jar "$HOME/lpo_build/ffdec/ffdec-cli.jar" -onerror ignore \
    -importScript /tmp/lib_one_base.swf /tmp/lib_one.swf /tmp/lpo_one < /dev/null 2>&1 | tail -2

echo "base : $(ls -la /tmp/lib_one_base.swf | awk '{print $5}') bytes  md5 $(md5sum /tmp/lib_one_base.swf | cut -d' ' -f1)"
echo "new  : $(ls -la /tmp/lib_one.swf | awk '{print $5}') bytes  md5 $(md5sum /tmp/lib_one.swf | cut -d' ' -f1)"

echo "--- re-export and diff (expect ONLY UI_multiplay.as) ---"
timeout 550 java -jar "$HOME/lpo_build/ffdec/ffdec-cli.jar" -onerror ignore \
    -export script /tmp/lpo_one_out /tmp/lib_one.swf < /dev/null 2>&1 | tail -1
diff -rq /tmp/lpo_cur /tmp/lpo_one_out 2>&1 | head -10

echo "--- markers in the rebuilt SWF ---"
echo "new logging markers   : $(grep -c 'tmp_title:' /tmp/lpo_one_out/scripts/PrinceOnline/UI_multiplay.as)"
echo "earlier fix preserved : $(grep -c 'no retry button on this frame' /tmp/lpo_one_out/scripts/PrinceOnline/UI_multiplay.as)"
echo "earlier fix preserved : $(grep -c 'mp_result body error' /tmp/lpo_one_out/scripts/PrinceOnline/UI_multiplay.as)"
