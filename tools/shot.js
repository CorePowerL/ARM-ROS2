#!/usr/bin/env node
/**
 * 用 CDP（Chrome DevTools Protocol）打开页面 → 执行一段 JS → 截图。
 * 比 `msedge --headless --screenshot` 可靠（后者在新版 Edge 上经常不出文件）。
 *
 * 用法：
 *   node tools/shot.js <url> <输出png> [---js "<表达式>"] [--wait 3000] [--w 1400] [--h 900]
 *
 * 例：
 *   node tools/shot.js http://127.0.0.1:8777/k3b_arm_urdf/preview.html out.png \
 *        --js "document.querySelectorAll('#joints input')[5].value=0.01;document.querySelectorAll('#joints input')[5].dispatchEvent(new Event('input'))" \
 *        --wait 4000
 */

const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9333 + Math.floor(Math.random() * 200);

const argv = process.argv.slice(2);
const url = argv[0];
const out = argv[1];
const opt = { js: null, wait: 3000, w: 1400, h: 900 };
for (let i = 2; i < argv.length; i++) {
  if (argv[i] === '--js') opt.js = argv[++i];
  else if (argv[i] === '--wait') opt.wait = +argv[++i];
  else if (argv[i] === '--w') opt.w = +argv[++i];
  else if (argv[i] === '--h') opt.h = +argv[++i];
}
if (!url || !out) {
  console.error('用法: node tools/shot.js <url> <out.png> [--js expr] [--wait ms] [--w px] [--h px]');
  process.exit(2);
}

const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cdp-'));
const child = spawn(EDGE, [
  '--headless=new',
  '--disable-gpu-sandbox',
  '--no-first-run',
  '--no-default-browser-check',
  `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${profile}`,
  `--window-size=${opt.w},${opt.h}`,
  '--hide-scrollbars',
  'about:blank',
], { stdio: 'ignore' });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function targets() {
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/json/list`);
      const list = await r.json();
      const page = list.find((t) => t.type === 'page');
      if (page) return page;
    } catch { /* 端口还没起来 */ }
    await sleep(250);
  }
  throw new Error('CDP 端口未就绪');
}

class CDP {
  constructor(ws) { this.ws = ws; this.id = 0; this.pending = new Map(); this.logs = []; }
  static async open(wsUrl) {
    const ws = new WebSocket(wsUrl);
    await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
    const c = new CDP(ws);
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.id && c.pending.has(msg.id)) {
        const { res, rej } = c.pending.get(msg.id);
        c.pending.delete(msg.id);
        msg.error ? rej(new Error(msg.error.message)) : res(msg.result);
      } else if (msg.method === 'Runtime.consoleAPICalled') {
        c.logs.push(`[${msg.params.type}] ` + msg.params.args.map((a) => a.value ?? a.description ?? a.type).join(' '));
      } else if (msg.method === 'Runtime.exceptionThrown') {
        c.logs.push('[exception] ' + (msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text));
      }
    };
    return c;
  }
  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((res, rej) => {
      this.pending.set(id, { res, rej });
      this.ws.send(JSON.stringify({ id, method, params }));
      setTimeout(() => { if (this.pending.delete(id)) rej(new Error(method + ' 超时')); }, 25000);
    });
  }
}

(async () => {
  const page = await targets();
  const cdp = await CDP.open(page.webSocketDebuggerUrl);
  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('Emulation.setDeviceMetricsOverride',
    { width: opt.w, height: opt.h, deviceScaleFactor: 2, mobile: false });

  await cdp.send('Page.navigate', { url });
  await sleep(opt.wait);

  if (opt.js) {
    const r = await cdp.send('Runtime.evaluate', { expression: opt.js, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) console.error('JS 异常:', r.exceptionDetails.text);
    else if (r.result && r.result.value !== undefined) console.log('JS 返回:', JSON.stringify(r.result.value));
    await sleep(900);
  }

  const shot = await cdp.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
  fs.writeFileSync(out, Buffer.from(shot.data, 'base64'));
  console.log('截图已保存:', out);
  if (cdp.logs.length) console.log('页面日志:\n' + cdp.logs.join('\n'));

  cdp.ws.close();
  child.kill();
  await sleep(300);
  try { fs.rmSync(profile, { recursive: true, force: true }); } catch { /* ignore */ }
  process.exit(0);
})().catch((e) => {
  console.error('失败:', e.message);
  try { child.kill(); } catch { /* ignore */ }
  process.exit(1);
});
