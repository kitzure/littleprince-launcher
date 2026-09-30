#!/bin/bash
# INNER: hosts redirect + fake server on :80 + run one CD game under Wine, capture frames.
# $1 = tag, $2 = game dir (linux), $3 = windows path of the exe
export DISPLAY=:0
TAG="$1"; DIR="$2"; WINEXE="$3"
ip link set lo up
mount --bind "$HOSTSFILE" /etc/hosts || exit 1

mkdir -p /tmp/p2/runlog
python3 -u $HOME/Downloads/littleprince-patcher/fake_server.py 80 > "/tmp/p2/runlog/${TAG}_server.log" 2>&1 &
SRV=$!
sleep 3

# fresh activation state for this game in the wine prefix
rm -f "$HOME/.wine/drive_c/Users/Public/Documents/Little Prince/Little Prince/lic.dat" 2>/dev/null
find $HOME/.wine/drive_c/users -ipath '*SharedObjects*' -iname '*.sol' -newermt '2000-01-01' -delete 2>/dev/null

cd "$DIR" || exit 1
WINEDEBUG=-all timeout 180 wine explorer /desktop=G_,1024x768 "Z:$WINEXE" > "/tmp/p2/runlog/${TAG}_wine.log" 2>&1 &
sleep 30

WID=$(xdotool search --name 'G_ - Wine' 2>/dev/null | tail -1)
[ -z "$WID" ] && WID=$(xdotool search --name 'Wine' 2>/dev/null | tail -1)
echo "wine window: ${WID:-none}"
rm -f /tmp/p2/runlog/${TAG}_*.png
if [ -n "$WID" ]; then
  xdotool windowactivate "$WID" 2>/dev/null; xdotool windowraise "$WID" 2>/dev/null; sleep 2
  eval $(xdotool getwindowgeometry --shell "$WID")
  echo "geometry ${WIDTH}x${HEIGHT} at $X,$Y"
  for i in 1 2 3; do
    timeout 20 ffmpeg -loglevel error -f x11grab -video_size ${WIDTH}x${HEIGHT} \
        -i :0.0+${X},${Y} -frames:v 1 -y "/tmp/p2/runlog/${TAG}_$i.png"
    sleep 6
  done
else
  for i in 1 2 3; do timeout 20 ffmpeg -loglevel error -f x11grab -video_size 1024x768 \
      -i :0.0+0,0 -frames:v 1 -y "/tmp/p2/runlog/${TAG}_$i.png"; sleep 6; done
fi
echo "--- server saw ---"
grep -iE "checkActivation|activation|e000|e091|Dispatch" "/tmp/p2/runlog/${TAG}_server.log" | tail -6
echo "--- wine said ---"
grep -iE "error|cannot|failed" "/tmp/p2/runlog/${TAG}_wine.log" | head -4
kill $SRV 2>/dev/null; pkill -f 'start\.exe' 2>/dev/null; pkill -f wineserver 2>/dev/null
exit 0
