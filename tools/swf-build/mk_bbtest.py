#!/usr/bin/env python3
"""Build /tmp/bbtest.html from the EXACT functions shipped in lpo/web.html and report
what the canvas actually draws (ink bounding boxes, wrapping, margins).

Not a re-implementation: the three functions are sliced out of web.html by name, so a
regression in the shipped code is what the harness measures.
"""
import json
import pathlib
import re

WEB = pathlib.Path.home() / "Downloads" / "littleprince-launcher" / "lpo" / "web.html"
src = WEB.read_text("utf-8")

names = ["function bbClipText", "function bbWrapText", "function bbDraw"]
slices = []
for name in names:
    start = src.index(name)
    # find the matching closing brace of the function body
    i = src.index("{", start)
    depth = 0
    while True:
        ch = src[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    slices.append(src[start:i + 1])

canvas_js = "\n\n".join(slices)
assert "bbWrapText" in canvas_js and "bbDraw" in canvas_js

harness = """<!doctype html><meta charset=utf-8><title>bbDraw harness</title>
<style>body{background:#222;color:#eee;font:13px sans-serif}canvas{border:1px solid #555}</style>
<canvas id="bb-canvas" width="694" height="510"></canvas>
<textarea id="bb-text" style="width:694px;height:60px"></textarea>
<script>
const CARD_W=694, CARD_H=510;
const CARDFONT='system-ui,"Segoe UI","Microsoft JhengHei","Noto Sans CJK TC",sans-serif';
let BBIMG=null, BSEL=0, BOARD=[{title:'測試公告'}];
const $=id=>document.getElementById(id);
""" + canvas_js + """
/* ── measurement helpers ── */
function box(y0,y1,thresh){
  const c=$('bb-canvas'), x=c.getContext('2d');
  const im=x.getImageData(0,0,CARD_W,CARD_H).data;
  let minx=1e9,miny=1e9,maxx=-1,maxy=-1;
  for(let y=y0;y<y1;y++){
    for(let xx=8;xx<CARD_W-8;xx++){
      const i=(y*CARD_W+xx)*4, r=im[i], g=im[i+1], b=im[i+2];
      if(r<thresh[0]||g<thresh[1]||b<thresh[2]){
        if(xx<minx)minx=xx; if(xx>maxx)maxx=xx;
        if(y<miny)miny=y; if(y>maxy)maxy=y;
      }
    }
  }
  return {minx,miny,maxx,maxy,empty:maxx<0};
}
function headerBox(){ return box(12,72,[225,215,190]); }  // the title text only (the band's rule sits at y>=57)
function bodyBox(){ return box(84,500,[225,215,190]); }   // caption / placeholder / picture
function mkImg(w,h,colour){
  const c=document.createElement('canvas'); c.width=w; c.height=h;
  const x=c.getContext('2d'); x.fillStyle=colour; x.fillRect(0,0,w,h);
  x.fillStyle='#ffffff'; x.font='600 40px sans-serif'; x.fillText('PIC',20,60);
  return c;
}
window.__run=function(){
  const out={};
  const set=(t)=>{$('bb-text').value=t;};

  // A: short single word, no picture
  BOARD=[{title:'測試公告'}]; set('whatsupp'); BBIMG=null; bbDraw();
  out.A_short_noimg={header:headerBox(),body:bodyBox()};

  // B: long CJK paragraph, no picture
  set('這張公告是在帳號網站的 Admin → Billboard 加的，遊戲裡一開佈告欄就會見到，'
      +'而且文字要懂得自動換行，不要黏在卡片的最底邊。');
  bbDraw();
  out.B_long_cjk_noimg={body:bodyBox()};

  // C: long English paragraph, no picture
  set('This is a deliberately long caption that has to wrap across several lines so the '
      +'card never runs its words off the right edge of the frame.');
  bbDraw();
  out.C_long_en_noimg={body:bodyBox()};

  // D: picture plus caption (portrait picture, the worst case)
  BBIMG=mkImg(600,900,'#c94f4f'); set('A picture with a caption under it.');
  bbDraw();
  out.D_img_caption={body:bodyBox()};

  // E: landscape picture plus long caption
  BBIMG=mkImg(900,400,'#4f7fc9');
  set('Landscape picture and a much longer caption underneath it, wrapping over a few lines.');
  bbDraw();
  out.E_landscape_caption={body:bodyBox()};

  // F: nothing at all
  BBIMG=null; BOARD=[{title:'測試公告'}]; set(''); bbDraw();
  out.F_blank_titled={header:headerBox(),body:bodyBox()};

  // G: long title -> must be clipped with an ellipsis, still inside the band
  BOARD=[{title:'這是一個非常非常長的公告標題用來測試裁切是否會超出標題帶的右邊界線'}];
  set('body'); bbDraw();
  out.G_long_title={header:headerBox()};

  // H: picture alone, no caption
  BOARD=[{title:'測試公告'}]; BBIMG=mkImg(400,300,'#3f9f6f'); set(''); bbDraw();
  out.H_img_only={body:bodyBox()};

  return out;
};
</script>
"""
out = pathlib.Path("/tmp/bbtest.html")
out.write_text(harness, "utf-8")
print("wrote", out, out.stat().st_size, "bytes")
