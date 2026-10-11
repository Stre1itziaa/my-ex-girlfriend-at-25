# -*- coding: utf-8 -*-
"""本地聊天 UI（纯 stdlib, 不接真微信）。启动: python ui/web.py -> http://127.0.0.1:8787"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))

HTML = """<!doctype html><html><head><meta charset=utf-8><title>{NAME}</title><style>
body{background:#f7f2ee;font-family:system-ui,'Microsoft YaHei';margin:0;display:flex;justify-content:center}
#app{width:420px;height:100vh;display:flex;flex-direction:column;background:#f2e9e4}
#log{flex:1;overflow-y:auto;padding:16px}
.msg{max-width:75%;padding:8px 12px;border-radius:14px;margin:4px 0;white-space:pre-wrap;font-size:15px;line-height:1.45}
img.sticker{max-width:150px;border-radius:8px}
.her{background:#fff;align-self:flex-start;border-top-left-radius:4px}
.me{background:#a8d8b9;align-self:flex-end;border-top-right-radius:4px}
.row{display:flex;flex-direction:column}.row.me{align-items:flex-end}
#bar{display:flex;padding:10px;background:#fff;border-top:1px solid #e5d8d0}
#inp{flex:1;border:none;outline:none;font-size:15px;padding:10px 12px;background:#f5f0ec;border-radius:20px}
button{border:none;background:#e8a2a2;color:#fff;border-radius:20px;padding:0 18px;margin-left:8px;font-size:15px}
</style></head><body><div id=app><div id=log></div><div id=bar>
<input id=inp placeholder="说点什么…"><button onclick=send()>发</button></div></div>
<script>
let hist=[];
function add(t,who){const d=document.createElement('div');d.className='row '+(who=='me'?'me':'');
if(/^\[表情包/.test(t)&&who=='her'){const n=(t.match(/\d+/)||[''])[0];
fetch('/api/sticker'+(n?'?n='+n:'')).then(r=>r.json()).then(j=>{
const m=document.createElement('img');m.className='msg sticker';d.appendChild(m);
if(j.url)m.src=j.url;log.appendChild(d);log.scrollTop=log.scrollHeight});return}
const m=document.createElement('div');m.className='msg '+who;m.textContent=t;d.appendChild(m);
log.appendChild(d);log.scrollTop=log.scrollHeight}
async function send(){const v=inp.value.trim();if(!v)return;inp.value='';add(v,'me');
const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({msg:v,history:hist})});const d=await r.json();
await new Promise(res=>setTimeout(res,1200+Math.random()*4000));
for(const b of d.bubbles){add(b,'her');hist.push(['assistant',b]);await new Promise(r=>setTimeout(r,400+Math.random()*900));}
hist.push(['user',v]);}
setInterval(async()=>{try{const r=await fetch('/api/poll');const d=await r.json();
for(const p of (d.proactive||[])){if(document.title.indexOf('')){
try{new Notification('{NAME}',{body:p.bubbles[0]||'…'})}catch(e){}
for(const b of p.bubbles){add(b,'her');hist.push(['assistant',b]);await new Promise(r=>setTimeout(r,600+Math.random()*1200));}
}}}catch(e){}},20000);
inp.addEventListener('keydown',e=>{if(e.key=='Enter')send()});
</script></body></html>"""

_comp = None


# ---- 身份配置（来自 config/persona.yaml，开源版零硬编码）----
def _persona_name():
    try:
        import yaml as _y
        _p = Path(__file__).resolve().parent.parent.parent / 'config' / 'persona.yaml'
        if _p.exists():
            return (_y.safe_load(_p.read_text(encoding='utf-8')) or {}).get('name', '她')
    except Exception:
        pass
    return '她'


persona_name = _persona_name()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/sticker"):
            import random as _rnd, json as _json
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            n = (qs.get("n") or [""])[0]
            mf = Path(__file__).resolve().parent.parent / "data" / "stickers" / "manifest.json"
            url = None
            if mf.exists():
                pool = _json.loads(mf.read_text(encoding="utf-8"))
                if pool:
                    if n.isdigit() and 1 <= int(n) <= len(pool):
                        pick = pool[int(n) - 1]["file"]
                    else:
                        pick = _rnd.choice(pool)["file"]
                    url = "/stickers/" + pick.replace("\\", "/").split("/")[-1]
            self._send(200, _json.dumps({"url": url}).encode("utf-8"))
            return
        if self.path.startswith("/stickers/"):
            name = Path(self.path).name  # 防目录穿越
            f = Path(__file__).resolve().parent.parent / "data" / "stickers" / name
            if f.exists():
                self._send(200, f.read_bytes(), "image/gif")
            else:
                self._send(404, b"no")
            return
        if self.path == "/api/poll":
            global _comp
            recs = []
            try:
                if _comp is None:
                    print("[ui] 加载检索索引与画像…")
                    _comp = __import__("chat").Companion()
                import proactive
                recs = proactive.poll_outbox()
            except Exception as e:
                self._send(500, json.dumps({"error": str(e)[:200]}, ensure_ascii=False).encode("utf-8"))
                return
            self._send(200, json.dumps({"proactive": recs}, ensure_ascii=False).encode("utf-8"))
            return
        self._send(200, HTML.replace("{NAME}", persona_name).encode("utf-8"), "text/html; charset=utf-8")

    def do_POST(self):
        global _comp
        try:
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if _comp is None:
                print("[ui] 加载检索索引与画像…")
                _comp = __import__("chat").Companion()
            bubbles = _comp.reply(data["msg"], [tuple(x) for x in data.get("history", [])])
            self._send(200, json.dumps({"bubbles": bubbles}, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self._send(500, json.dumps({"error": str(e)[:200]}, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    import threading
    import time as _time

    wh_hist = []  # 微信侧会话历史（与本地UI独立）

    def _bridge():
        """微信桥接适配器(channels/bridge_io.py): 存在则返回模块, 否则 None。"""
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "channels"))
        try:
            import bridge_io
            return bridge_io
        except Exception:
            return None

    def wechat_inbox_loop():
        """每2秒: 收微信消息 -> 她 -> 回。通道未绑定或 PAUSED 时待机。"""
        global _comp
        bridge = _bridge()
        if bridge is None:
            print("[wechat] 桥接适配器缺失，微信收发待机（详见 docs/wechat-bind.md）", flush=True)
            return
        paused_flag = Path(__file__).resolve().parent.parent.parent / "channels" / "agent2wechat" / "PAUSED"
        while True:
            try:
                if _comp is None:
                    print("[ui] 加载检索索引与画像…", flush=True)
                    _comp = __import__("chat").Companion()
                if paused_flag.exists():
                    # PAUSED 冷却: 只归档不回复(消息留在 inbox, 解冻后统一处理)
                    _time.sleep(3)
                    continue
                if bridge.wechat_bound():
                    msgs = bridge.poll_inbox()
                    if msgs:
                        # 连发聚合: 收到后追等两轮把快速连发聚齐(总延迟≤7s), 一次回复——真人不会逐条拆着回
                        for _ in range(2):
                            _time.sleep(3.5)
                            more = bridge.poll_inbox()
                            if not more:
                                break
                            msgs += more
                        imgs = []
                        for m in msgs:
                            imgs += [p for p in (m.get("images") or []) if p]
                        imgs = imgs[:2]
                        utext = "\n".join(m["text"] for m in msgs if m.get("text")).strip()
                        utext = utext or ("[对方发来一张照片]" if imgs else "")
                        bubbles = _comp.reply(utext, wh_hist, images=imgs)
                        bridge.send(bubbles, context_token=msgs[-1].get("ctx"), tag="reply")
                        wh_hist.append(("user", utext))
                        wh_hist.append(("assistant", "\n".join(bubbles)))
                        if len(wh_hist) > 24:
                            del wh_hist[:2]
            except Exception as e:
                print("[wechat]", str(e)[:150], flush=True)
            _time.sleep(2)

    def tick_loop():
        """每2分钟: 情绪衰减 + 掷骰子决定她是否主动发消息（本地UI + 微信双通道）。"""
        bridge = _bridge()
        while True:
            try:
                if _comp is not None:
                    import proactive
                    rec = proactive.tick(_comp.inner)
                    if rec and bridge is not None and bridge.wechat_bound():
                        bridge.send(rec["bubbles"], tag="proactive")
            except Exception as e:
                print("[tick]", str(e)[:120])
            _time.sleep(120)

    threading.Thread(target=tick_loop, daemon=True).start()
    threading.Thread(target=wechat_inbox_loop, daemon=True).start()
    print(f"{persona_name} 本地聊天页: http://127.0.0.1:8787 （她每2分钟掷骰子决定要不要找你）")
    ThreadingHTTPServer(("127.0.0.1", 8787), H).serve_forever()
