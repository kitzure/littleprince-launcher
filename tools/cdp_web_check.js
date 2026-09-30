// Check the accounts page's tab visibility and greeting by driving it and reading
// the DOM - stronger than eyeballing a screenshot, and it proves the signed-out and
// signed-in states separately.
const fs = require("fs");
const { spawn } = require("child_process");

const CH = process.argv[2];
const URL = process.argv[3];
const SHOTS = process.argv[4] || "/tmp/p2";
const EMAIL = "webtest@local.test";
const PASS = "test1234";

async function main() {
  const port = 9400 + Math.floor(Math.random() * 400);
  const proc = spawn(CH, ["--headless=new", "--disable-gpu", "--no-sandbox",
    "--hide-scrollbars", "--window-size=900,900",
    `--remote-debugging-port=${port}`, "about:blank"], { stdio: "ignore" });
  let target = null;
  for (let i = 0; i < 100 && !target; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      target = list.find((t) => t.type === "page");
    } catch (e) { /* not up yet */ }
    if (!target) await new Promise((r) => setTimeout(r, 250));
  }
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
  await send("Page.enable");
  await send("Runtime.enable");

  const evaluate = async (expr) => {
    const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true,
                                               returnByValue: true });
    return r.result ? r.result.value : undefined;
  };
  const shot = async (name) => {
    const png = await send("Page.captureScreenshot", { format: "png" });
    fs.writeFileSync(`${SHOTS}/${name}.png`, Buffer.from(png.data, "base64"));
  };

  const state = () => evaluate(`(() => {
    const vis = (id) => { const el = document.getElementById(id);
      return el ? !el.classList.contains('hide') : null; };
    const tabVisible = (t) => { const b = document.querySelector('#tabs [data-tab="' + t + '"]');
      return b ? !b.classList.contains('hide') : null; };
    return JSON.stringify({
      tabs: { signin: tabVisible('login'), register: tabVisible('register'),
              account: tabVisible('panel') },
      sections: { panel: vis('tab-panel'), home: vis('tab-panel-home'),
                  profile: vis('tab-panel-personal'), account: vis('tab-panel-account'),
                  worlds: vis('tab-panel-worlds'), stats: vis('tab-panel-stats'),
                  list: vis('tab-panel-list') },
      subnav: vis('subnav'),
      onSub: (document.querySelector('#subnav button.on') || {}).textContent,
      hello: (document.getElementById('home-hello') || {}).textContent,
      who: (document.getElementById('home-email') || {}).textContent,
      signedOutToasts: (document.getElementById('li-msg') || {}).textContent
    });
  })()`);

  await send("Page.navigate", { url: URL });
  await new Promise((r) => setTimeout(r, 2500));
  console.log("SIGNED OUT:", await state());
  await shot("web_signedout");

  // register through the page itself, exactly as a user would
  await evaluate(`(() => {
    document.querySelector('#tabs [data-tab="register"]').click();
    document.getElementById('rg-email').value = ${JSON.stringify(EMAIL)};
    document.getElementById('rg-pass').value = ${JSON.stringify(PASS)};
    document.getElementById('rg-pass2').value = ${JSON.stringify(PASS)};
    document.getElementById('rg-name').value = 'Web Tester';
    register();
  })()`);
  await new Promise((r) => setTimeout(r, 2000));
  console.log("REGISTERED:", await state());
  await shot("web_signedin");

  await evaluate("Promise.all([showSub('worlds')]).then(()=>1)");
  await new Promise((r) => setTimeout(r, 500));
  console.log("AFTER SUB-TAB CLICK:", await state());

  await evaluate("signOut()");
  await new Promise((r) => setTimeout(r, 1500));
  console.log("SIGNED OUT AGAIN:", await state());

  ws.close();
  proc.kill("SIGKILL");
  process.exit(0);
}
main();
