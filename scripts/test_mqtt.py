"""启动 uvicorn + MQTT bridge, 生成测试链接"""
import sys, os, time, base64
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

API_KEY = os.environ.get("VC_WEB_API_KEY", "")
if not API_KEY:
    print("❌ 请先设置环境变量 VC_WEB_API_KEY")
    sys.exit(1)
os.environ["VC_WEB_API_KEY"] = API_KEY

MQTT_BROKER = os.environ.get("VC_MQTT_BROKER", "broker.emqx.io")
MQTT_BROKER_PORT = os.environ.get("VC_MQTT_BROKER_PORT", "8084")

# 极简 mobile.html — 压到二维码里的 data URI (QR code 版本 40 最多 2953 chars)
MINIMAL_HTML = """<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>
<title>VideoCrawler</title>
<script src=https://unpkg.com/mqtt@5.10.1/dist/mqtt.min.js></script>
<style>*{box-sizing:border-box}body{margin:0;background:#0f0f14;color:#d4d4d8;font-family:system-ui;padding:16px}h3{margin:0 0 12px;font-size:14px;color:#f4f4f5}button{width:100%;padding:14px;border:none;border-radius:8px;font-size:15px;font-weight:600;cursor:pointer;margin-bottom:8px}.b1{background:#22c55e;color:#000}.b2{background:#ef4444;color:#000}.b3{background:#f59e0b;color:#000}#log{background:#18181b;border:1px solid #27272a;border-radius:8px;padding:10px;font-family:monospace;font-size:12px;min-height:100px;max-height:280px;overflow-y:auto;white-space:pre-wrap;margin-top:12px}.bd{padding:2px 8px;border-radius:4px;font-size:11px;margin-left:8px}.on{background:#22c55e;color:#000}.off{background:#71717a;color:#000}</style>
<h3>VideoCrawler <span class=bd id=st>连接中</span></h3>
<button class=b1 onclick=send('status')>📡 设备状态</button>
<button class=b3 onclick=send('pipeline')>🎬 开始流水线</button>
<button class=b2 onclick=send('stop')>🛑 停止</button>
<div id=log>等待指令...</div>
<script>
const u=new URLSearchParams(location.search),d=u.get('device'),t=u.get('token');
const c=mqtt.connect('wss://broker.emqx.io:8084/mqtt');
const tc='user/'+d+'/cmd',tl='user/'+d+'/log',tr='user/'+d+'/resp';
const st=document.getElementById('st'),lg=document.getElementById('log');
function send(a,p){c.publish(tc,JSON.stringify({token:t,action:a,params:p||{}}))}
function log(m){lg.textContent='['+new Date().toLocaleTimeString()+'] '+m+'\\n'+lg.textContent}
c.on('connect',()=>{st.textContent='MQTT 在线';st.className='bd on';c.subscribe(tl);c.subscribe(tr);log('已连接 broker.emqx.io')});
c.on('disconnect',()=>{st.textContent='MQTT 离线';st.className='bd off'});
c.on('message',(tp,p)=>{const m=p.toString();if(tp===tl)log(m);else log('📥 '+m)});
</script>"""

MINIMAL_HTML = MINIMAL_HTML.replace(
    "wss://broker.emqx.io:8084/mqtt",
    f"wss://{MQTT_BROKER}:{MQTT_BROKER_PORT}/mqtt",
)
MINIMAL_HTML = MINIMAL_HTML.replace(
    "已连接 broker.emqx.io",
    f"已连接 {MQTT_BROKER}",
)

print(f"极简 HTML: {len(MINIMAL_HTML)} chars")
b64 = base64.b64encode(MINIMAL_HTML.encode()).decode()
print(f"base64: {len(b64)} chars")
data_uri = f"data:text/html;base64,{b64}"
print(f"data URI: {len(data_uri)} chars (QR code v40 最大 2953)")

# 启动
from gui.web_host import GuiWebHost
host = GuiWebHost(port=8000)
info = host.start_all()
time.sleep(3)

mqtt = info.get("mqtt", {})
print(f"\n=== MQTT 状态 ===")
print(f"connected={mqtt.get('connected')}")
print(f"device_id={mqtt.get('device_id')}")
print(f"token={mqtt.get('token')}")

d = mqtt.get("device_id", "")
tok = mqtt.get("token", "")

# 用 data URI 拼完整链接 (手机扫码直接打开, 内嵌 HTML + device/token 参数)
# 实际上 data URI 里不需要 device/token — 已经嵌在 HTML 里了
# 但 data URI 太长了 QR code 装不下... 所以换方案:
# 二维码里放 LAN URL (同 WiFi 直连), 远程用户部署到 CF Pages 后设 VC_MQTT_WEB_URL
print(f"\n=== 测试方式 ===")
print(f"同 WiFi 手机 → http://192.168.31.167:8000/static/mobile.html?device={d}&token={tok}")
print(f"局域网 LAN    → http://localhost:8000/static/mobile.html?device={d}&token={tok}")
print(f"\n(data URI 太长={len(data_uri)}, 超过 QR code 容量, 不用它)")

import urllib.request
try:
    r = urllib.request.urlopen(f"http://127.0.0.1:8000/api/mqtt/status?key={API_KEY}", timeout=5)
    print(f"\n✅ uvicorn + MQTT bridge OK (status={r.status})")
except Exception as e:
    print(f"\n❌ MQTT status 异常: {e}")
