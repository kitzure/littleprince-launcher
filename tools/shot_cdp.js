// Real-time page capture over CDP: screenshot after a genuine wait, plus the
// page's console output and any failed/4xx requests.  (--virtual-time-budget
// freezes a Flash intro at frame 1, so it cannot tell a blank page from a
// slow-starting game.)
const fs = require("fs");
const { spawn } = require("child_process");

const CH = process.argv[2];
const url = process.argv[3];
const out = process.argv[4];
const waitMs = parseInt(process.argv[5] || "15000", 10);

async function main() {
  const port = 9300 + Math.floor(Math.random() * 400);
  const extra = (process.env.CHROME_FLAGS || "").split(" ").filter(Boolean);
  const proc = spawn(CH, ["--headless=new", "--disable-gpu", "--no-sandbox",
    "--hide-scrollbars", "--window-size=900,640",
    `--remote-debugging-port=${port}`, ...extra, "about:blank"], { stdio: "ignore" });

  let target = null;
  for (let i = 0; i < 100 && !target; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      target = list.find((t) => t.type === "page");
    } catch (e) { /* not up yet */ }
    if (!target) await new Promise((r) => setTimeout(r, 250));
  }
  if (!target) { console.log(JSON.stringify({ error: "no devtools target" })); process.exit(1); }

  const ws = new WebSocket(target.webSocketDebuggerUrl);
  const pending = new Map();
  const events = [];
  let id = 0;
  const send = (method, params = {}) => new Promise((res) => {
    const i = ++id; pending.set(i, res);
    ws.send(JSON.stringify({ id: i, method, params }));
  });
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg.result || {}); pending.delete(msg.id); }
    else if (msg.method) events.push(msg);
  };
  await new Promise((r) => { ws.onopen = r; });

  await send("Page.enable");
  await send("Network.enable");
  await send("Runtime.enable");
  await send("Log.enable");
  await send("Page.navigate", { url });
  await new Promise((r) => setTimeout(r, waitMs));

  const shot = await send("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(out, Buffer.from(shot.data, "base64"));

  const failed = events.filter((e) => e.method === "Network.loadingFailed")
    .map((e) => `${e.params.errorText} (${e.params.type})`);
  const bad = events.filter((e) => e.method === "Network.responseReceived" && e.params.response.status >= 400)
    .map((e) => `${e.params.response.status} ${e.params.response.url.replace(/^http:\/\/[^/]+/, "")}`);
  const cons = events.filter((e) => e.method === "Runtime.consoleAPICalled")
    .map((e) => (e.params.args || []).map((a) => a.value === undefined ? a.type : a.value).join(" "));
  const log = events.filter((e) => e.method === "Log.entryAdded")
    .map((e) => `${e.params.entry.level}: ${e.params.entry.text}`);

  console.log(JSON.stringify({
    url, bytes: fs.existsSync(out) ? fs.statSync(out).size : 0,
    failed: [...new Set(failed)].slice(0, 10),
    http_errors: [...new Set(bad)].slice(0, 20),
    console: [...new Set(cons)].slice(0, 12),
    log: [...new Set(log)].slice(0, 12),
  }, null, 1));

  ws.close();
  proc.kill("SIGKILL");
  process.exit(0);
}
main();
