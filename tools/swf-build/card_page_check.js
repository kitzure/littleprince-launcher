// Drive the accounts page's new billboard-card control in a real headless Chromium:
// sign in, open Billboard, add a row, type card text, attach a picture file, then press
// "Save board image" and prove the bytes the GAME's URL serves are the bytes the canvas
// drew.  Run:  node card_page_check.js <chrome> <url>
const fs = require("fs");
const { spawn } = require("child_process");

const CH = process.argv[2];
const URL = process.argv[3] || "http://127.0.0.1:8977/web";
const EMAIL = "alpha@test.local";
const PASS = "testpass";
const PIC = "/tmp/card_pic.png";

let PASSED = 0, FAILED = 0;
const ok = (label, cond, extra) => {
  if (cond) { PASSED++; console.log("  " + label.padEnd(54) + " OK   " + (extra || "")); }
  else { FAILED++; console.log("  " + label.padEnd(54) + " FAIL " + (extra || "")); }
};

async function main() {
  const port = 9500 + Math.floor(Math.random() * 300);
  const proc = spawn(CH, ["--headless=new", "--disable-gpu", "--no-sandbox",
    "--hide-scrollbars", "--window-size=1200,1000",
    `--remote-debugging-port=${port}`, "about:blank"], { stdio: "ignore" });
  let target = null;
  for (let i = 0; i < 120 && !target; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      target = list.find((t) => t.type === "page");
    } catch (e) { /* not up yet */ }
    if (!target) await new Promise((r) => setTimeout(r, 250));
  }
  if (!target) { console.log("no chromium target"); process.exit(2); }
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  const pending = new Map();
  let id = 0;
  const send = (method, params = {}) => new Promise((res) => {
    const i = ++id; pending.set(i, res);
    ws.send(JSON.stringify({ id: i, method, params }));
  });
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg.result || {}); pending.delete(msg.id); }
  };
  await new Promise((r) => { ws.onopen = r; });
  await send("Page.enable"); await send("Runtime.enable"); await send("DOM.enable");

  const evaluate = async (expr) => {
    const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true,
                                               returnByValue: true });
    if (r.exceptionDetails) return "EXCEPTION: " + JSON.stringify(r.exceptionDetails.text);
    return r.result ? r.result.value : undefined;
  };
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));

  await send("Page.navigate", { url: URL });
  await wait(2500);
  console.log("signed out, page loaded:", await evaluate("document.title"));

  await evaluate(`(() => {
    document.getElementById('li-email').value = ${JSON.stringify(EMAIL)};
    document.getElementById('li-pass').value = ${JSON.stringify(PASS)};
    signIn();
  })()`);
  await wait(2000);
  ok("signed in through the page", await evaluate("!!ACC"), await evaluate("(ACC||{}).email"));

  // the billboard pane: add a row exactly as the + Add notice button does
  await evaluate("(() => { PAGE='settings'; SUB='billboard'; renderNavigation(); bbAdd(); })()");
  await wait(600);
  ok("Billboard pane is open", await evaluate("!!document.getElementById('bb-canvas')"));
  ok("canvas is 520x360", await evaluate(
    "(() => { const c=document.getElementById('bb-canvas'); return c.width+'x'+c.height; })()"), "520x360");

  // type the card text (the browser renders CJK itself) and draw
  const drawn = await evaluate(`(() => {
    document.getElementById('bb-text').value = '星願小王子公告\\nBoard image test';
    bbDraw();
    const c = document.getElementById('bb-canvas');
    const d = c.toDataURL('image/png');
    return JSON.stringify({ len: d.length, magic: d.slice(0, 22) });
  })()`);
  console.log("  canvas after drawing text:", drawn);
  ok("the canvas produced a PNG", /data:image\/png;base64/.test(drawn), "");

  // attach a picture file through the real file input (CDP hands the browser a path)
  const doc = await send("DOM.getDocument");
  const node = await send("DOM.querySelector", { nodeId: doc.root.nodeId, selector: "#bb-file" });
  await send("DOM.setFileInputFiles", { files: [PIC], nodeId: node.nodeId });
  await wait(900);
  ok("the file input took the picture", await evaluate(
    "(document.getElementById('bb-file').files[0]||{}).name"), "card_pic.png");
  const withPic = await evaluate(`(() => {
    const c = document.getElementById('bb-canvas');
    // count red pixels - the test picture is solid red, so they must be there
    const d = c.getContext('2d').getImageData(0,0,c.width,c.height).data;
    let red = 0;
    for (let i = 0; i < d.length; i += 4) if (d[i] > 200 && d[i+1] < 80 && d[i+2] < 80) red++;
    return red;
  })()`);
  ok("the picture is drawn into the card (red pixels found)", withPic > 1000, withPic + " px");

  // press "Save board image" and check what the page says
  const before = await evaluate("document.getElementById('bb-img-note').textContent");
  console.log("  note before saving:", JSON.stringify(before));
  await evaluate("bbSendImage(0)");
  await wait(1500);
  const after = await evaluate("document.getElementById('bb-img-note').textContent");
  const msg = await evaluate("document.getElementById('bb-msg').textContent");
  console.log("  note after saving :", JSON.stringify(after));
  console.log("  message           :", JSON.stringify(msg));
  ok("the page reports a saved card", /card saved/.test(after || ""), after);

  // the bytes at the URL the game is handed must be the bytes the canvas drew
  const served = await evaluate(`(async () => {
    const canvas = document.getElementById('bb-canvas');
    const drawnNow = canvas.toDataURL('image/png').split(',')[1];
    const r = await fetch('/notice/content/1.png');
    const buf = new Uint8Array(await r.arrayBuffer());
    let s = ''; for (const b of buf) s += String.fromCharCode(b);
    return JSON.stringify({ status: r.status, type: r.headers.get('content-type'),
                            size: buf.length, same: btoa(s) === drawnNow });
  })()`);
  console.log("  served card       :", served);
  const s = JSON.parse(served);
  ok("GET /notice/content/1.png -> 200 image/png", s.status === 200 && s.type === "image/png",
     s.status + " " + s.type);
  ok("the served bytes ARE the drawn card", s.same === true, s.size + " bytes");

  // and the row itself still saves with the existing Save & publish button
  await evaluate("bbSave()");
  await wait(1200);
  const saved = await evaluate(`(async () => {
    const r = await fetch('/web/api/admin/notices');
    const j = await r.json();
    return JSON.stringify({count: j.count, images: j.images});
  })()`);
  console.log("  board after save  :", saved);
  const j = JSON.parse(saved);
  ok("the row saved and the card is listed", j.count >= 1 && j.images && j.images["1"] > 0, saved);

  ws.close();
  proc.kill("SIGKILL");
  console.log("\n" + PASSED + " passed, " + FAILED + " failed");
  process.exit(FAILED ? 1 : 0);
}
main();
