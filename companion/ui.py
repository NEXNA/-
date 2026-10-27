"""HTML/CSS for the companion workbench (no external assets)."""
from __future__ import annotations

import html
import json

CSS = r"""
:root{
  --bg:#f4f6f1; --panel:#ffffff; --ink:#17352f; --muted:#71837b;
  --line:#dde8e0; --green:#0b6b5c; --mint:#15b894; --mint-soft:#e0f6ef;
  --warm:#e9a35a; --danger:#b4473b; --sidebar:#082f2b;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:"Microsoft YaHei UI","Microsoft YaHei",system-ui,sans-serif}
a{color:var(--green)}
.shell{display:flex;min-height:100vh}
.sidebar{width:232px;background:var(--sidebar);color:#e9fbf5;flex:0 0 232px;
  display:flex;flex-direction:column;padding:22px 14px}
.brand{display:flex;align-items:center;gap:10px;padding:0 10px 22px}
.brand .mark{width:44px;height:44px;border-radius:14px;background:var(--mint);
  color:#fff;display:grid;place-items:center;font-size:25px;font-weight:800}
.brand b{font-size:16px;line-height:1.35}
.brand small{display:block;color:#8bc9bb;font-weight:400;font-size:11px}
.nav a{display:block;color:#cdeee5;text-decoration:none;padding:11px 14px;
  border-radius:10px;margin:4px 0;font-size:14px}
.nav a:hover{background:#0c443d;color:#fff}
.nav a.active{background:#0d554b;color:#fff;font-weight:700}
.sidebar .who{margin-top:auto;padding:14px 10px;border-top:1px solid #17554c;
  color:#a9d8cd;font-size:12px;line-height:1.7}
.main{flex:1;min-width:0;padding:30px 34px}
.top{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:22px}
.top h1{font-size:24px;margin:0}
.top p{margin:5px 0 0;color:var(--muted);font-size:12px}
.pill{background:var(--mint-soft);color:var(--green);border-radius:999px;
  padding:7px 13px;font-size:12px;font-weight:700;white-space:nowrap}
.action-card{display:block;color:var(--ink);text-decoration:none;transition:.15s}
.action-card:hover{transform:translateY(-2px);border-color:#9fd9c8}
.action-card b{display:block;font-size:16px;margin-bottom:7px}
.action-card span{display:block;color:var(--muted);font-size:12px;line-height:1.6}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:7px;
  border:0;border-radius:10px;padding:10px 16px;background:var(--mint);
  color:#fff;font-size:13px;font-weight:700;cursor:pointer;text-decoration:none}
.btn:hover{background:#0d9c7e}
.btn.secondary{background:#e8f2ed;color:var(--green)}
.btn.ghost{background:transparent;color:var(--muted);border:1px solid var(--line)}
.btn.danger{background:#fbe9e6;color:var(--danger)}
.btn:disabled{opacity:.45;cursor:not-allowed}
.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;
  padding:20px}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.grid.three{grid-template-columns:repeat(3,minmax(0,1fr))}
label{display:block;font-size:12px;color:var(--muted);margin:0 0 6px}
input,textarea,select{width:100%;border:1px solid var(--line);border-radius:10px;
  background:#fbfdfb;color:var(--ink);padding:10px 12px;font:inherit;font-size:13px;
  outline:none}
input:focus,textarea:focus,select:focus{border-color:var(--mint);
  box-shadow:0 0 0 3px #d8f4eb}
textarea{min-height:110px;resize:vertical}
.field{margin-bottom:15px}
.hint{font-size:11px;color:var(--muted);line-height:1.6}
.row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.between{display:flex;align-items:center;justify-content:space-between;gap:12px}
.check{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--ink)}
.check input{width:auto}
.muted{color:var(--muted)}
.status{display:inline-block;width:8px;height:8px;border-radius:50%;
  background:var(--mint);margin-right:7px}
.chat-wrap{display:grid;grid-template-columns:minmax(0,1fr) 270px;gap:16px;
  align-items:start}
.chat-card{display:flex;flex-direction:column;min-height:calc(100vh - 160px);
  padding:0;overflow:hidden}
.chat-head{padding:16px 20px;border-bottom:1px solid var(--line);
  display:flex;align-items:center;justify-content:space-between}
.chat-head b{font-size:15px}
.chat-log{flex:1;overflow:auto;padding:20px;background:
  radial-gradient(circle at 10% 10%,#eefaf5 0,transparent 35%),#fbfdfb}
.msg{display:flex;gap:10px;margin:0 0 16px;align-items:flex-start}
.msg .avatar{width:30px;height:30px;border-radius:10px;background:#e7f5ef;
  color:var(--green);display:grid;place-items:center;font-size:12px;font-weight:800;
  flex:0 0 30px}
.msg.user{flex-direction:row-reverse}
.msg.user .avatar{background:#fff0df;color:#a56528}
.bubble{max-width:min(680px,86%);padding:11px 14px;border-radius:14px;
  background:#fff;border:1px solid var(--line);font-size:13px;line-height:1.75;
  white-space:pre-wrap;word-break:break-word}
.msg.user .bubble{background:var(--mint);border-color:var(--mint);color:#fff}
.msg time{display:block;font-size:10px;color:#a5b4ae;margin-top:5px}
.msg.user time{color:#d9fff5;text-align:right}
.empty{margin:auto;text-align:center;color:var(--muted);font-size:13px;
  line-height:1.9;padding:40px}
.empty b{display:block;color:var(--ink);font-size:18px;margin-bottom:7px}
.composer{padding:14px 16px;border-top:1px solid var(--line);background:#fff;
  display:flex;gap:10px;align-items:flex-end}
.composer textarea{min-height:46px;height:46px;max-height:150px;resize:none}
.composer .btn{height:42px;min-width:76px}
.aside .card+.card{margin-top:14px}
.intimacy-number{font-size:30px;font-weight:800;color:var(--green);line-height:1}
.bar{height:8px;background:#e7efeb;border-radius:99px;overflow:hidden;margin:12px 0 7px}
.bar i{display:block;height:100%;background:linear-gradient(90deg,#77dbc5,#0b9b7f);
  border-radius:99px;transition:width .4s}
.mini-fortune{font-size:12px;color:var(--muted);line-height:1.7}
.stars{color:var(--warm);letter-spacing:2px}
.fortune-hero{background:linear-gradient(135deg,#083b35,#0b6b5c);color:#fff;
  border:0;border-radius:18px;padding:26px}
.fortune-hero h2{margin:0 0 6px;font-size:30px}
.fortune-hero p{color:#b9e6da;margin:0;font-size:13px;line-height:1.7}
.fortune-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:16px}
.fortune-item{background:rgba(255,255,255,.09);border-radius:12px;padding:12px}
.fortune-item span{display:block;color:#9bd3c6;font-size:11px;margin-bottom:4px}
.fortune-item b{font-size:15px}
.list{display:flex;flex-direction:column;gap:9px}
.memory{display:flex;gap:12px;align-items:flex-start;padding:12px 14px;
  border:1px solid var(--line);border-radius:12px;background:#fbfdfb}
.memory p{margin:0;font-size:13px;line-height:1.7;flex:1;word-break:break-word}
.memory small{color:var(--muted);font-size:10px}
.toast{position:fixed;right:24px;bottom:24px;background:#17352f;color:#fff;
  padding:12px 16px;border-radius:10px;font-size:12px;display:none;z-index:99}
.auth{min-height:100vh;display:grid;place-items:center;padding:24px;
  background:radial-gradient(circle at 15% 10%,#d9f7ec 0,transparent 35%),
  radial-gradient(circle at 90% 90%,#ffe8ce 0,transparent 30%),#f4f6f1}
.auth-card{width:min(420px,100%);background:#fff;border:1px solid var(--line);
  border-radius:22px;padding:32px;box-shadow:0 24px 60px rgba(7,59,54,.10)}
.auth-card .mark{width:54px;height:54px;border-radius:16px;background:var(--mint);
  color:#fff;display:grid;place-items:center;font-size:30px;font-weight:800;margin-bottom:18px}
.auth-card h1{font-size:24px;margin:0 0 7px}
.auth-card p{font-size:12px;color:var(--muted);line-height:1.7;margin:0 0 22px}
.error{background:#fbe9e6;color:var(--danger);padding:10px 12px;border-radius:9px;
  font-size:12px;margin-bottom:14px;line-height:1.6}
.section-title{font-size:15px;margin:0 0 4px}
.section-sub{font-size:11px;color:var(--muted);margin:0 0 16px}
.divider{height:1px;background:var(--line);margin:20px 0}
.persona-tabs{display:flex;gap:8px;flex-wrap:wrap;margin:4px 0 16px}
.persona-tab{border:1px solid var(--line);background:#fbfdfb;border-radius:12px;
  padding:10px 14px;cursor:pointer;font:inherit;font-size:13px;color:var(--ink);
  text-align:left;min-width:132px}
.persona-tab:hover{border-color:var(--mint)}
.persona-tab.active{border-color:var(--mint);background:var(--mint-soft);
  color:var(--green);font-weight:700}
.persona-tab small{display:block;color:var(--muted);font-size:10px;
  font-weight:400;margin-top:3px}
.persona-editor{display:none}
.persona-editor.active{display:block}
.persona-text{min-height:360px;font-size:12px;line-height:1.75}
.badge{display:inline-block;background:var(--mint-soft);color:var(--green);
  border-radius:999px;padding:3px 9px;font-size:10px;font-weight:700}
.code-box{margin-top:12px;background:#f2fbf7;border:1px dashed #9ad9c9;
  border-radius:12px;padding:14px;font-size:12px;color:var(--muted);line-height:1.8}
.code-box b{font-size:28px;letter-spacing:7px;color:var(--green);
  display:block;margin:5px 0 2px}
.persona-switch{margin-top:12px}
@media(max-width:900px){
  .shell{display:block}.sidebar{width:auto;flex:none;padding:14px}
  .brand{padding-bottom:10px}.nav{display:flex;gap:4px;overflow:auto}
  .nav a{white-space:nowrap}.sidebar .who{display:none}.main{padding:20px}
  .chat-wrap{grid-template-columns:1fr}.aside{display:grid;grid-template-columns:1fr 1fr;gap:12px}
  .aside .card+.card{margin-top:0}.grid{grid-template-columns:1fr}
}
"""


def esc(value: object) -> str:
    return html.escape(str(value or ""))


def json_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def layout(title: str, body: str, active: str, user: str, bot_name: str) -> str:
    nav = [
        ("chat", "/", "聊天"),
        ("panel", "/panel", "功能面板"),
        ("memories", "/memories", "记忆"),
        ("fortune", "/fortune", "今日运势"),
        ("design", "/design", "角色资料"),
        ("settings", "/settings", "机器人设定"),
    ]
    links = "".join(
        f'<a class="{"active" if key == active else ""}" href="{href}">{label}</a>'
        for key, href, label in nav
    )
    name = bot_name.strip() or "未命名机器人"
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} · 陪伴工作台</title><style>{CSS}</style></head>
<body><div id="toast" class="toast"></div>
<script>
function toast(t){{const e=document.getElementById('toast');e.textContent=t;e.style.display='block';setTimeout(()=>e.style.display='none',2200)}}
async function api(url,opts={{}}){{const r=await fetch(url,{{credentials:'same-origin',headers:{{'Content-Type':'application/json'}},...opts}});const d=await r.json().catch(()=>({{ok:false,error:'返回格式错误'}}));if(!r.ok||d.ok===false)throw new Error(d.error||'请求失败');return d}}
</script>
<div class="shell">
<aside class="sidebar">
  <div class="brand"><div class="mark">伴</div><div><b>陪伴工作台<br><small>COMPANION STUDIO</small></b></div></div>
  <nav class="nav">{links}<a href="/logout">退出登录</a></nav>
  <div class="who">已登录：{esc(user)}<br>{esc(name)}<br>设定由你定义</div>
</aside>
<main class="main">{body}</main>
</div></body></html>"""


def auth_page(mode: str, error: str = "") -> str:
    setup = mode == "setup"
    title = "第一次使用" if setup else "登录"
    subtitle = (
        "还没有管理员账号。先创建你的登录账号，再开始使用默认角色。"
        if setup else "登录后进入你的陪伴工作台。"
    )
    action = "/setup" if setup else "/login"
    extra = "" if setup else '<p class="hint">忘记密码：停止程序后删除 data/companion.db，重新创建账号。</p>'
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · 陪伴工作台</title><style>{CSS}</style></head>
<body><div class="auth"><div class="auth-card">
<div class="mark">伴</div><h1>{title}</h1><p>{subtitle}</p>
{('<div class="error">' + esc(error) + '</div>') if error else ''}
<form method="post" action="{action}">
<div class="field"><label>用户名</label><input name="username" autocomplete="username" required maxlength="32" placeholder="例如：主人"></div>
<div class="field"><label>密码</label><input type="password" name="password" autocomplete="{'new-password' if setup else 'current-password'}" required minlength="6" placeholder="至少 6 位"></div>
{('<div class="field"><label>确认密码</label><input type="password" name="password2" required minlength="6"></div>') if setup else ''}
<button class="btn" style="width:100%" type="submit">{'创建并进入' if setup else '登录'}</button>
</form>{extra}
<p class="hint" style="margin-top:18px">本地单管理员控制台。默认带两套可切换角色：诗寇蒂、伊邪那美（鸦越千羽）。角色设定、记忆和亲密度都由你控制。</p>
</div></div></body></html>"""


def chat_page(settings: dict, user: str, history: list[dict],
              intimacy: int, fortune: dict | None, persona: dict,
              personas: list[dict]) -> str:
    bot_name = persona.get("name") or "未命名角色"
    greeting = persona.get("greeting") or "这个角色还没有写开场白。去「机器人设定」补上，然后从第一句话开始。"
    active_key = str(persona.get("key") or "")
    options = "".join(
        f'<option value="{esc(item["key"])}" '
        f'{"selected" if item["key"] == active_key else ""}>'
        f'{esc(item["name"])}</option>'
        for item in personas
    )
    history_html = ""
    for item in history:
        role = item.get("role")
        if role not in ("user", "assistant"):
            continue
        cls = "user" if role == "user" else "bot"
        who = "你" if role == "user" else bot_name
        history_html += (
            f'<div class="msg {cls}"><div class="avatar">{esc(who[:1])}</div>'
            f'<div class="bubble">{esc(item.get("content", ""))}'
            f'<time>{esc(who)}</time></div></div>'
        )
    if not history_html:
        history_html = (
            f'<div class="empty"><b>{esc(bot_name)}</b>{esc(greeting)}</div>'
        )
    fortune_text = ""
    if fortune:
        fortune_text = (
            f'<div class="stars">{"★" * int(fortune["overall"])}'
            f'{"☆" * (5 - int(fortune["overall"]))}</div>'
            f'<div class="mini-fortune">今日：{esc(fortune["summary"])}</div>'
        )
    else:
        fortune_text = '<div class="mini-fortune">还没有生成今日运势。</div>'
    intimacy_html = ""
    if settings.get("intimacy_enabled", 1):
        intimacy_html = f"""
        <div class="card aside-card">
          <div class="between"><span class="muted" style="font-size:12px">亲密度</span>
            <span class="pill">{intimacy} / 100</span></div>
          <div class="intimacy-number" id="intimacyNum">{intimacy}</div>
          <div class="bar"><i id="intimacyBar" style="width:{intimacy}%"></i></div>
          <div class="hint" id="intimacyLabel">每聊一次，慢慢靠近一点。</div>
        </div>"""
    persona_switch = ""
    if personas:
        persona_switch = f"""
    <div class="card">
      <div class="between"><b style="font-size:13px">当前角色</b><span class="badge">{esc(bot_name)}</span></div>
      <select class="persona-switch" id="personaSwitch">{options}</select>
      <p class="hint" style="margin:8px 0 0">切换角色不会清空记忆、亲密度和历史。</p>
    </div>"""
    body = f"""
<div class="top"><div><h1>{esc(bot_name)}</h1><p>和{esc(bot_name)}聊天。角色、记忆和亲密度都由你控制。</p></div>
<span class="pill"><span class="status"></span>本地在线</span></div>
<div class="chat-wrap">
  <section class="card chat-card">
    <div class="chat-head"><b>{esc(bot_name)}</b><span class="hint">按当前角色设定回应</span></div>
    <div class="chat-log" id="chatLog">{history_html}</div>
    <div class="composer">
      <textarea id="input" placeholder="说点什么…  Enter 发送，Shift+Enter 换行"></textarea>
      <button class="btn" id="send">发送</button>
    </div>
  </section>
  <aside class="aside">
    {intimacy_html}
    {persona_switch}
    <div class="card">
      <div class="between"><b style="font-size:13px">今日运势</b><a href="/fortune" style="font-size:11px">详情</a></div>
      {fortune_text}
    </div>
    <div class="card">
      <div class="between"><b style="font-size:13px">记忆</b><a href="/memories" style="font-size:11px">管理</a></div>
      <p class="hint" style="margin:8px 0 0">记忆会让对话更连续；不想留的可以随时删除。</p>
    </div>
  </aside>
</div>
<script>
const log=document.getElementById('chatLog'),input=document.getElementById('input'),send=document.getElementById('send');
const botName={json_script(bot_name)};
function add(role,text){{
  const wrap=document.createElement('div');wrap.className='msg '+(role==='user'?'user':'bot');
  const av=document.createElement('div');av.className='avatar';av.textContent=(role==='user'?'你':botName).slice(0,1);
  const b=document.createElement('div');b.className='bubble';b.textContent=text;
  const t=document.createElement('time');t.textContent=role==='user'?'你':botName;b.appendChild(t);
  wrap.appendChild(av);wrap.appendChild(b);log.appendChild(wrap);log.scrollTop=log.scrollHeight;
}}
function updateIntimacy(v){{
  const n=document.getElementById('intimacyNum'),bar=document.getElementById('intimacyBar'),lab=document.getElementById('intimacyLabel');
  if(!n)return;n.textContent=v;if(bar)bar.style.width=v+'%';
  if(lab)lab.textContent=v<20?'刚认识，慢慢来。':v<40?'开始熟悉了。':v<60?'已经会惦记对方。':v<80?'很信赖彼此。':'很重要的人。';
}}
async function submit(){{
  const text=input.value.trim();if(!text||send.disabled)return;
  input.value='';input.style.height='46px';send.disabled=true;add('user',text);
  const typing=document.createElement('div');typing.className='msg bot';typing.innerHTML='<div class="avatar">·</div><div class="bubble">正在想…</div>';log.appendChild(typing);log.scrollTop=log.scrollHeight;
  try{{
    const d=await api('/api/chat',{{method:'POST',body:JSON.stringify({{message:text}})}});
    typing.remove();add('assistant',d.reply);if(d.intimacy!==null)updateIntimacy(d.intimacy);
  }}catch(e){{typing.remove();add('assistant','（出错了）'+e.message)}}
  send.disabled=false;input.focus();
}}
send.onclick=submit;
input.addEventListener('keydown',e=>{{if(e.key==='Enter'&&!e.shiftKey){{e.preventDefault();submit()}}}});
input.addEventListener('input',()=>{{input.style.height='46px';input.style.height=Math.min(150,input.scrollHeight)+'px'}});
const personaSwitch=document.getElementById('personaSwitch');
if(personaSwitch){{personaSwitch.onchange=async()=>{{
  personaSwitch.disabled=true;
  try{{await api('/api/persona/switch',{{method:'POST',body:JSON.stringify({{key:personaSwitch.value}})}});location.reload();}}
  catch(e){{toast(e.message);personaSwitch.disabled=false;}}
}};}}
updateIntimacy({intimacy});input.focus();
</script>"""
    return layout("聊天", body, "chat", user, bot_name)


def settings_page(settings: dict, user: str, personas: list[dict],
                  active_key: str, qq: str, napcat_enabled: bool,
                  bot_qq: str = "", whitelist: list[dict] | None = None,
                  whitelist_enabled: bool = False,
                  napcat_accounts: list[str] | None = None) -> str:
    whitelist = whitelist or []
    napcat_accounts = napcat_accounts or []
    active = next(
        (item for item in personas if item.get("key") == active_key),
        personas[0] if personas else {},
    )
    bot_name = active.get("name") or "未命名角色"
    tabs = ""
    editors = ""
    for item in personas:
        key = str(item["key"])
        selected = key == active_key
        tabs += (
            f'<button type="button" class="persona-tab '
            f'{"active" if selected else ""}" data-key="{esc(key)}" '
            f'onclick="showPersona(\'{esc(key)}\')">'
            f'{esc(item["name"])}<small>{esc(key)}</small></button>'
        )
        options = "".join(
            f'<option value="{model}" '
            f'{"selected" if model == item.get("model", "deepseek-chat") else ""}>'
            f'{model}</option>'
            for model in ("deepseek-chat", "deepseek-reasoner", "deepseek-flash")
        )
        editors += f"""
<div class="persona-editor {"active" if selected else ""}" id="editor_{esc(key)}" data-key="{esc(key)}">
  <div class="grid">
    <div class="field"><label>名字</label>
      <input id="name_{esc(key)}" maxlength="40" value="{esc(item.get('name', ''))}"></div>
    <div class="field"><label>开场白</label>
      <textarea id="greeting_{esc(key)}" placeholder="第一次打开聊天时显示的话">{esc(item.get('greeting', ''))}</textarea></div>
  </div>
  <div class="field"><label>人设 / system prompt（越详细越稳）</label>
    <textarea id="persona_{esc(key)}" class="persona-text" placeholder="角色身份、经历、性格、说话方式、关系、边界……">{esc(item.get('persona', ''))}</textarea></div>
  <div class="grid" style="grid-template-columns:repeat(3,minmax(0,1fr))">
    <div class="field"><label>模型</label><select id="model_{esc(key)}">{options}</select></div>
    <div class="field"><label>最大回复 token</label>
      <input id="max_tokens_{esc(key)}" type="number" min="64" max="4096" value="{int(item.get('max_tokens', 600))}"></div>
    <div class="field"><label>温度 <span id="tempVal_{esc(key)}">{float(item.get('temperature', .9)):.2f}</span></label>
      <input id="temperature_{esc(key)}" type="range" min="0" max="1.5" step="0.05" value="{float(item.get('temperature', .9))}"></div>
  </div>
  <div class="row" style="margin-top:10px">
    <button class="btn" type="button" onclick="savePersona('{esc(key)}')">保存这套设定</button>
    <button class="btn secondary" type="button" onclick="switchPersona('{esc(key)}')">在网页聊天使用</button>
    <span class="hint">保存只改这套角色；切换只改当前账号使用的那一套。</span>
  </div>
</div>"""
    if qq:
        qq_html = f"""
  <p class="section-sub">当前绑定：<b>{esc(qq)}</b>。这个 QQ 私聊机器人时，会自动使用本账号的角色和记忆。</p>
  <button class="btn danger" type="button" onclick="unbindQQ()">解除绑定</button>"""
    else:
        qq_html = f"""
  <p class="section-sub">机器人 QQ：<b>{esc(bot_qq or '未填写')}</b>。在网页生成 6 位绑定码，然后用这个 QQ 私聊机器人发送 <code>/bind 验证码</code>。</p>
  <button class="btn" type="button" onclick="makeBindCode()">生成 6 位绑定码</button>
  <div id="bindCode"></div>"""
    napcat_note = "" if napcat_enabled else (
        '<p class="hint" style="margin-top:12px">NapCat 还没有启用：'
        '先运行 setup_napcat.py，或在 .env 填好 NAPCAT_* 配置后重启。</p>'
    )
    whitelist_rows = "".join(
        f'<div class="memory"><div style="flex:1"><p><b>{esc(item["qq"])}</b>'
        f'{" · " + esc(item["note"]) if item.get("note") else ""}</p>'
        f'<small>加入于 {esc(item.get("created_at", ""))}</small></div>'
        f'<button class="btn danger" type="button" '
        f'onclick="removeWhitelist(\'{esc(item["qq"])}\')">移出</button></div>'
        for item in whitelist
    ) or (
        '<div class="empty" style="padding:20px">白名单还是空的。'
        '绑定成功会自动加入；也可以在上面手动添加。'
        '开启白名单但列表为空时，普通 QQ 都会被拒绝。</div>'
    )
    account_options = "".join(
        f'<option value="{esc(item)}"></option>' for item in napcat_accounts
    )
    whitelist_html = f"""
<div class="card" style="margin-top:16px">
  <div class="between">
    <div><h3 class="section-title">QQ 白名单</h3>
      <p class="section-sub" style="margin:0">开启后，只有列表里的 QQ 能私聊机器人；绑定成功会自动加入。把已绑定的 QQ 移出后，它也会立即被拦截。</p></div>
    <label class="check" style="margin:0"><input type="checkbox" id="whitelistEnabled"
      {'checked' if whitelist_enabled else ''} onchange="toggleWhitelist(this.checked)"> 启用白名单</label>
  </div>
  <div class="list" style="margin-top:14px">{whitelist_rows}</div>
  <div class="divider"></div>
  <div class="grid" style="grid-template-columns:1fr 1.4fr auto;align-items:end">
    <div class="field" style="margin:0"><label>QQ 号</label>
      <input id="whitelistQQ" inputmode="numeric" placeholder="例如 123456789"></div>
    <div class="field" style="margin:0"><label>备注（可选）</label>
      <input id="whitelistNote" maxlength="100" placeholder="例如：我的小号"></div>
    <button class="btn" type="button" onclick="addWhitelist()">加入白名单</button>
  </div>
</div>"""
    body = f"""
<div class="top"><div><h1>机器人设定</h1><p>两套角色各自独立，可随时切换；记忆和亲密度跟着账号走。</p></div>
<a class="btn secondary" href="/">回到聊天</a></div>
<section class="card" style="margin-bottom:16px">
  <div class="between" style="margin-bottom:12px">
    <div><h3 class="section-title">角色设定</h3><p class="section-sub" style="margin:0">当前使用：{esc(bot_name)}</p></div>
    <span class="pill">共 {len(personas)} 套</span>
  </div>
  <div class="persona-tabs">{tabs}</div>
  {editors}
</section>
<form class="card" id="settingsForm">
  <div class="between" style="margin-bottom:12px"><div><h3 class="section-title">全局开关</h3><p class="section-sub" style="margin:0">两套角色共用这些开关。</p></div></div>
  <div class="grid">
    <div class="card" style="box-shadow:none;background:#fbfdfb">
      <div class="check"><input type="checkbox" id="memory_enabled" {'checked' if settings.get('memory_enabled', 1) else ''}><label for="memory_enabled" style="margin:0">启用长期记忆</label></div>
      <div class="check" style="margin-top:10px"><input type="checkbox" id="auto_memory" {'checked' if settings.get('auto_memory', 1) else ''}><label for="auto_memory" style="margin:0">自动记住自述</label></div>
      <div class="check" style="margin-top:10px"><input type="checkbox" id="fortune_enabled" {'checked' if settings.get('fortune_enabled', 1) else ''}><label for="fortune_enabled" style="margin:0">启用今日运势</label></div>
      <div class="check" style="margin-top:10px"><input type="checkbox" id="intimacy_enabled" {'checked' if settings.get('intimacy_enabled', 1) else ''}><label for="intimacy_enabled" style="margin:0">启用亲密度</label></div>
    </div>
    <div>
      <div class="field"><label>初始亲密度（0-100）</label><input id="intimacy_start" type="number" min="0" max="100" value="{int(settings.get('intimacy_start', 10))}"></div>
      <p class="hint">只影响还没有聊天记录的新账号；已有账号请用下面的“当前亲密度”单独调整。</p>
    </div>
  </div>
  <div class="row" style="margin-top:8px"><button class="btn" type="submit">保存全局设置</button></div>
</form>
<div class="grid" style="margin-top:16px">
  <div class="card"><h3 class="section-title">当前亲密度</h3><p class="section-sub">单独调整当前值，不会改变初始值。</p>
    <div class="row"><input id="currentIntimacy" type="number" min="0" max="100" value="10" style="max-width:120px"><button class="btn secondary" type="button" onclick="setIntimacy()">设置</button></div></div>
  <div class="card"><h3 class="section-title">清空对话</h3><p class="section-sub">只删聊天记录，不删记忆和角色设定。</p>
    <button class="btn danger" type="button" onclick="clearHistory()">清空聊天记录</button></div>
</div>
<script>
function showPersona(key){{
  document.querySelectorAll('.persona-editor').forEach(el=>el.classList.toggle('active',el.dataset.key===key));
  document.querySelectorAll('.persona-tab').forEach(el=>el.classList.toggle('active',el.dataset.key===key));
}}
document.querySelectorAll('input[type=range][id^="temperature_"]').forEach(el=>{{
  el.addEventListener('input',()=>{{
    const key=el.id.slice('temperature_'.length);
    const label=document.getElementById('tempVal_'+key);
    if(label)label.textContent=parseFloat(el.value).toFixed(2);
  }});
}});
async function savePersona(key){{
  const get=id=>document.getElementById(id);
  const body={{key:key,
    name:get('name_'+key).value,
    greeting:get('greeting_'+key).value,
    persona:get('persona_'+key).value,
    model:get('model_'+key).value,
    temperature:parseFloat(get('temperature_'+key).value),
    max_tokens:parseInt(get('max_tokens_'+key).value||'600')}};
  try{{await api('/api/personas/save',{{method:'POST',body:JSON.stringify(body)}});toast('这套角色已保存');}}
  catch(e){{toast(e.message);}}
}}
async function switchPersona(key){{
  try{{await api('/api/persona/switch',{{method:'POST',body:JSON.stringify({{key:key}})}});toast('已切换');setTimeout(()=>location.reload(),350);}}
  catch(e){{toast(e.message);}}
}}
const form=document.getElementById('settingsForm');
form.addEventListener('submit',async e=>{{e.preventDefault();
 const body={{memory_enabled:document.getElementById('memory_enabled').checked?1:0,auto_memory:document.getElementById('auto_memory').checked?1:0,fortune_enabled:document.getElementById('fortune_enabled').checked?1:0,intimacy_enabled:document.getElementById('intimacy_enabled').checked?1:0,intimacy_start:parseInt(document.getElementById('intimacy_start').value||'10')}};
 try{{await api('/api/settings',{{method:'POST',body:JSON.stringify(body)}});toast('全局设置已保存');}}
 catch(err){{toast(err.message);}}
}});
async function setIntimacy(){{try{{const v=parseInt(document.getElementById('currentIntimacy').value||'0');await api('/api/intimacy',{{method:'POST',body:JSON.stringify({{intimacy:v}})}});toast('亲密度已设置');}}catch(e){{toast(e.message);}}}}
async function clearHistory(){{if(!confirm('清空聊天记录？'))return;try{{await api('/api/history/clear',{{method:'POST',body:'{{}}'}});toast('已清空');}}catch(e){{toast(e.message);}}}}
api('/api/state').then(d=>{{const el=document.getElementById('currentIntimacy');if(el&&d.intimacy!==undefined)el.value=d.intimacy;}}).catch(()=>{{}});
</script>"""
    return layout("机器人设定", body, "settings", user, bot_name)


def memories_page(settings: dict, user: str, memories: list[dict],
                  persona: dict) -> str:
    bot_name = persona.get("name") or "未命名角色"
    rows = "".join(
        f'<div class="memory"><div style="flex:1"><p>{esc(m["text"])}</p>'
        f'<small>{esc(m["source"])} · {esc(m["created_at"])}</small></div>'
        f'<button class="btn danger" onclick="delMemory({int(m["id"])})">删除</button></div>'
        for m in memories
    ) or '<div class="empty" style="padding:26px">还没有记忆。聊到关于你的事时，可以手动添加，也可以打开自动记忆。</div>'
    body = f"""
<div class="top"><div><h1>长期记忆</h1><p>它会跟着这个账号，在每次聊天时被参考。</p></div><a class="btn secondary" href="/">回到聊天</a></div>
<div class="grid" style="grid-template-columns:minmax(0,1.5fr) minmax(280px,.8fr)">
  <section class="card"><div class="between"><h3 class="section-title">记忆列表</h3><span class="pill">{len(memories)} 条</span></div>
    <div class="list" style="margin-top:14px">{rows}</div></section>
  <aside class="card"><h3 class="section-title">添加一条</h3><p class="section-sub">只记你自己的事，不要写别人的隐私。</p>
    <div class="field"><label>内容</label><textarea id="memoryText" placeholder="例如：我喜欢下雨天，生日是 5 月 20 日"></textarea></div>
    <button class="btn" onclick="addMemory()">保存记忆</button>
    <div class="divider"></div><button class="btn danger" onclick="clearMemories()">清空全部记忆</button>
  </aside>
</div>
<script>
async function addMemory(){{const t=document.getElementById('memoryText').value.trim();if(!t)return;try{{await api('/api/memories',{{method:'POST',body:JSON.stringify({{text:t}})}});location.reload()}}catch(e){{toast(e.message)}}}}
async function delMemory(id){{if(!confirm('删除这条记忆？'))return;try{{await api('/api/memories/delete',{{method:'POST',body:JSON.stringify({{id}})}});location.reload()}}catch(e){{toast(e.message)}}}}
async function clearMemories(){{if(!confirm('清空全部记忆？'))return;try{{await api('/api/memories/clear',{{method:'POST',body:'{{}}'}});location.reload()}}catch(e){{toast(e.message)}}}}
</script>"""
    return layout("长期记忆", body, "memories", user, bot_name)


def fortune_page(settings: dict, user: str, fortune: dict | None,
                 persona: dict) -> str:
    bot_name = persona.get("name") or "未命名角色"
    if not fortune:
        fortune = {
            "date": "", "overall": 3, "love": 3, "work": 3, "wealth": 3,
            "summary": "还没有生成今天的运势。", "lucky_color": "—",
            "lucky_number": 0, "good": "—", "bad": "—", "note": "",
        }
    body = f"""
<div class="top"><div><h1>今日运势</h1><p>每天按日期固定生成，只当娱乐。</p></div><a class="btn secondary" href="/">回到聊天</a></div>
<section class="fortune-hero">
  <div class="between"><div><h2>{esc(fortune.get('date', ''))}</h2><p>{esc(fortune.get('summary', ''))}</p></div><div class="stars" style="font-size:26px">{'★' * int(fortune.get('overall', 3))}{'☆' * (5 - int(fortune.get('overall', 3)))}</div></div>
  <div class="fortune-grid">
    <div class="fortune-item"><span>感情</span><b>{'★' * int(fortune.get('love', 3))}</b></div>
    <div class="fortune-item"><span>学习 / 工作</span><b>{'★' * int(fortune.get('work', 3))}</b></div>
    <div class="fortune-item"><span>财运</span><b>{'★' * int(fortune.get('wealth', 3))}</b></div>
  </div>
</section>
<div class="grid three" style="margin-top:16px">
  <div class="card"><div class="muted" style="font-size:11px">幸运色</div><div style="font-size:22px;font-weight:800;margin-top:7px">{esc(fortune.get('lucky_color', '—'))}</div></div>
  <div class="card"><div class="muted" style="font-size:11px">幸运数字</div><div style="font-size:22px;font-weight:800;margin-top:7px">{esc(fortune.get('lucky_number', '—'))}</div></div>
  <div class="card"><div class="muted" style="font-size:11px">今天适合</div><div style="font-size:17px;font-weight:700;margin-top:7px">{esc(fortune.get('good', '—'))}</div></div>
</div>
<div class="card" style="margin-top:16px"><div class="muted" style="font-size:11px">今天不太适合</div><div style="font-size:17px;font-weight:700;margin-top:7px">{esc(fortune.get('bad', '—'))}</div>
<p class="hint" style="margin-top:14px">{esc(fortune.get('note', ''))}</p></div>"""
    return layout("今日运势", body, "fortune", user, bot_name)


def panel_page(settings: dict, user: str, persona: dict, state: dict,
               memory_count: int, qq: str, fortune: dict | None,
               bot_qq: str = "") -> str:
    name = persona.get("name") or "未命名角色"
    intimacy = int(state.get("intimacy", 0))
    summary = (fortune or {}).get("summary") or "今天还没有生成运势。"
    bot_line = (
        f'<p class="hint" style="margin:10px 0 0">陪伴 QQ：'
        f'<a href="https://wpa.qq.com/msgrd?v=3&uin={esc(bot_qq)}&site=qq&menu=yes" '
        f'target="_blank" rel="noreferrer">{esc(bot_qq)}</a>'
        f' —— 私聊请确认发的是这个号，不是摩卡的 3826300285。</p>'
        if bot_qq else ""
    )
    body = f"""
<div class="top"><div><h1>功能面板</h1><p>私聊和网页都能用的快捷入口。</p></div><a class="btn secondary" href="/">回到聊天</a></div>
<section class="card">
  <div class="between"><div><h2 style="margin:0">{esc(name)}</h2><p class="muted" style="margin:6px 0 0">当前角色 · 亲密度 {intimacy}/100 · 记忆 {memory_count} 条</p></div><span class="pill">{esc(user)}</span></div>
  <p style="margin:14px 0 0"><b>今日运势：</b>{esc(summary)}</p>
  {bot_line}
</section>
<div class="grid three" style="margin-top:16px">
  <a class="card action-card" href="/"><b>继续聊天</b><span>和当前角色说话</span></a>
  <a class="card action-card" href="/settings"><b>切换角色 / 改人设</b><span>诗蔻蒂、伊邪那美</span></a>
  <a class="card action-card" href="/fortune"><b>今日运势</b><span>感情、工作、财运</span></a>
  <a class="card action-card" href="/memories"><b>长期记忆</b><span>查看、添加、删除</span></a>
  <a class="card action-card" href="/design"><b>角色资料</b><span>经历、行为、语言设计</span></a>
  <a class="card action-card" href="/settings"><b>QQ 绑定</b><span>私聊身份和绑定码</span></a>
</div>
<section class="card" style="margin-top:16px">
  <h3 class="section-title">私聊里的面板</h3>
  <p class="hint" style="margin:0 0 8px">在 QQ 私聊发送：</p>
  <pre style="white-space:pre-wrap;font:13px/1.8 'Microsoft YaHei UI',sans-serif;margin:0">/面板
/切换 诗蔻蒂
/运势
/记忆
/亲密度
/搜 关键词
/状态
/bind 123456</pre>
  <p class="hint" style="margin:10px 0 0">绑定 QQ：{esc(qq or '未绑定')}</p>
</section>"""
    return layout("功能面板", body, "panel", user, name)


def design_page(user: str, bot_name: str, content: str) -> str:
    body = f"""
<div class="top"><div><h1>角色资料</h1><p>诗蔻蒂 / 伊邪那美 / 青叶摩卡；摩卡只作对照，不在本项目里改。</p></div><a class="btn secondary" href="/settings">去改人设</a></div>
<section class="card">
  <div class="between" style="margin-bottom:10px"><div><h3 class="section-title">角色设计库</h3><p class="section-sub" style="margin:0">资料、经历、行为细节、正常人口语规则和示例。</p></div><span class="pill">design/character_bible.md</span></div>
  <pre style="white-space:pre-wrap;word-break:break-word;font:13px/1.8 'Microsoft YaHei UI',sans-serif;margin:0;color:var(--ink)">{esc(content)}</pre>
</section>"""
    return layout("角色资料", body, "design", user, bot_name)
