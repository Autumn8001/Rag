import os
import streamlit as st
import requests
import uuid
import pandas as pd

API_BASE = os.environ.get("API_BASE", "http://localhost:8000/api/v1")
PAGE_SIZE = 10


@st.cache_data(ttl=10)
def fetch_sessions(jwt_token: str | None):
    """缓存历史会话列表，基于 jwt_token 隔离缓存。"""
    if not jwt_token:
        return []
    try:
        headers = {"Authorization": f"Bearer {jwt_token}"}
        res = requests.get(f"{API_BASE}/sessions", headers=headers, timeout=5)
        if res.status_code == 200:
            return res.json().get("data", [])
    except Exception:
        pass
    return []


@st.cache_data(ttl=10)
def fetch_kb_list(page: int, page_size: int, jwt_token: str | None):
    """缓存知识库列表，基于 jwt_token 隔离缓存。"""
    if not jwt_token:
        return None
    try:
        headers = {"Authorization": f"Bearer {jwt_token}"}
        res = requests.get(
            f"{API_BASE}/list",
            params={"page": page, "page_size": page_size},
            headers=headers,
            timeout=10,
        )
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return None

st.set_page_config(
    page_title="企业多租户智能知识库",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
/* ── 隐藏必要多余元素，保持精美 ── */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
.stDeployButton { display: none; }

/* ── 极简 Claude 质感背景底色 ── */
.stApp { background-color: #f5f4ef; }
.main { background-color: #f5f4ef; }

/* ── 侧边栏（Sidebar）美化 ── */
section[data-testid="stSidebar"] {
    background: #ffffff;
    border-right: 1px solid #e8e8e8;
}
section[data-testid="stSidebar"] > div:first-child {
    padding: 20px 14px;
}

/* ── 按钮样式重构（圆角、过渡） ── */
.stButton > button {
    border-radius: 10px;
    border: 1px solid #e5e5e5;
    background: white;
    color: #333;
    font-size: 13px;
    transition: all 0.15s;
    text-align: left;
    padding: 8px 12px;
}
.stButton > button:hover {
    background: #f5f5f5;
    border-color: #ccc;
}

/* ── 输入框美化 ── */
[data-testid="stTextInput"] input, [data-testid="stPasswordInput"] input {
    background: white !important;
    border: 1px solid #e8e8e8 !important;
    border-radius: 8px !important;
    font-size: 13px !important;
    color: #333 !important;
    box-shadow: none !important;
}

/* ── 底部聊天输入框扁平化 ── */
[data-testid="stChatInput"] {
    background: #efefef !important;
    border-radius: 16px !important;
    border: none !important;
    padding: 6px 6px 6px 4px !important;
    box-shadow: none !important;
}
[data-testid="stChatInput"] textarea {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    font-size: 14px !important;
    color: #333 !important;
    padding: 10px 14px !important;
}
[data-testid="stChatInput"] button {
    background: #3d3d3d !important;
    border-radius: 10px !important;
    border: none !important;
    width: 38px !important;
    height: 38px !important;
    margin: auto 2px !important;
    transition: background 0.15s !important;
}
[data-testid="stChatInput"] button:hover {
    background: #1a1a1a !important;
}

/* ── 隐藏原生消息卡片边框 ── */
[data-testid="stChatMessage"] {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

/* ── 展开/折叠面板 ── */
[data-testid="stExpander"] {
    background: white !important;
    border: 1px solid #e8e8e8 !important;
    border-radius: 10px !important;
    box-shadow: none !important;
}

/* ── 指标卡片 ── */
[data-testid="stMetric"] {
    background: white;
    border-radius: 10px;
    padding: 12px 16px;
    border: 1px solid #ebebeb;
}
[data-testid="stMetricValue"] { color: #1a1a1a !important; }
[data-testid="stMetricLabel"] { color: #999 !important; }

/* ── 侧边栏字体标签 ── */
.sidebar-label {
    font-size: 10px;
    font-weight: 700;
    color: #aaa;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin: 16px 0 8px 2px;
}

/* ── 主阅读区居中宽度 ── */
.main .block-container {
    max-width: 860px;
    padding: 2rem 2rem 5rem;
    margin: 0 auto;
}

/* ── 认证卡片美化 ── */
.auth-container {
    background-color: white;
    border-radius: 16px;
    padding: 40px;
    border: 1px solid #ebebeb;
    max-width: 420px;
    margin: 80px auto 0;
    box-shadow: 0 4px 12px rgba(0,0,0,0.02);
}
</style>
""", unsafe_allow_html=True)

# ── Session State 初始化 ──────────────────────────────────────────────────────
defaults = {
    "session_id": str(uuid.uuid4()),
    "messages": [],
    "show_clear_confirm": False,
    "show_kb_details": False,
    "kb_page": 1,
    "jwt_token": None,
    "username": None,
    "tenant_id": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

def get_auth_headers():
    if st.session_state.jwt_token:
        return {"Authorization": f"Bearer {st.session_state.jwt_token}"}
    return {}

# ── 1. 登录/注册拦截机制 ──────────────────────────────────────────────────────
if not st.session_state.jwt_token:
    st.markdown("<div style='text-align:center;padding-top:40px;'><h2>📚 欢迎使用企业级多租户 RAG 知识库</h2><p style='color:#666;'>请登录或注册以获得隔离的专属租户空间</p></div>", unsafe_allow_html=True)
    
    # 居中认证表单
    c1, c2, c3 = st.columns([1, 1.5, 1])
    with c2:
        st.markdown("<div class='auth-container'>", unsafe_allow_html=True)
        tab1, tab2 = st.tabs(["🔑 租户登录", "👤 新建用户"])
        
        with tab1:
            login_username = st.text_input("用户名", key="login_user")
            login_password = st.text_input("密码", type="password", key="login_pwd")
            if st.button("立即登录", use_container_width=True, key="login_btn"):
                if not login_username or not login_password:
                    st.error("请输入用户名和密码。")
                else:
                    try:
                        r = requests.post(
                            f"{API_BASE}/auth/login",
                            json={"username": login_username, "password": login_password},
                            timeout=5
                        )
                        if r.status_code == 200:
                            data = r.json()
                            st.session_state.jwt_token = data["access_token"]
                            st.session_state.username = data["username"]
                            st.session_state.tenant_id = data["tenant_id"]
                            st.session_state.session_id = str(uuid.uuid4())
                            st.session_state.messages = []
                            st.success("登录成功，正在进入工作空间...")
                            st.rerun()
                        else:
                            st.error(f"登录失败: {r.json().get('detail', '未知错误')}")
                    except Exception as e:
                        st.error(f"连接认证服务失败: {e}")
                        
        with tab2:
            reg_username = st.text_input("注册用户名", key="reg_user")
            reg_password = st.text_input("设置登录密码 (≥6位)", type="password", key="reg_pwd")
            if st.button("创建账户并获取专属租户", use_container_width=True, key="reg_btn"):
                if not reg_username or not reg_password:
                    st.error("请输入欲注册的用户名及密码。")
                elif len(reg_password) < 6:
                    st.error("密码长度必须在 6 位以上。")
                else:
                    try:
                        r = requests.post(
                            f"{API_BASE}/auth/register",
                            json={"username": reg_username, "password": reg_password},
                            timeout=5
                        )
                        if r.status_code == 201:
                            st.success("注册成功！请切换到【租户登录】页签登录您的专属空间。")
                        else:
                            st.error(f"注册失败: {r.json().get('detail', '账号已被占用')}")
                    except Exception as e:
                        st.error(f"连接认证服务失败: {e}")
        st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# ── 2. 已登录 - 侧边栏布局与会话切换 ───────────────────────────────────────────
with st.sidebar:
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:10px;padding-bottom:16px;border-bottom:1px solid #f0f0f0;">
        <div style="width:28px;height:28px;background:linear-gradient(135deg,#4caf50,#81c784);border-radius:50%;flex-shrink:0;"></div>
        <div>
            <div style="font-size:13px;font-weight:700;color:#1a1a1a;">已登录：{st.session_state.username}</div>
            <div style="font-size:10px;color:#888;">租户: {st.session_state.tenant_id[:16]}...</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("🚪 退出登录", use_container_width=True):
        st.session_state.jwt_token = None
        st.session_state.username = None
        st.session_state.tenant_id = None
        st.session_state.messages = []
        st.rerun()

    if st.button("+ 新对话", use_container_width=True):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.show_kb_details = False
        st.session_state.kb_page = 1
        st.rerun()

    st.markdown('<div class="sidebar-label">历史对话</div>', unsafe_allow_html=True)
    search_query = st.text_input(
        "", placeholder="搜索对话...",
        label_visibility="collapsed", key="history_search"
    )

    sessions = fetch_sessions(st.session_state.jwt_token)
    if search_query:
        sessions = [s for s in sessions if search_query.lower() in s.get("title", "").lower()]
    if not sessions:
        st.caption("暂无历史对话")
    else:
        for s in sessions:
            title = s["title"]
            is_active = s["session_id"] == st.session_state.session_id
            btn_label = f"💬 {title}"
            if is_active:
                btn_label = f"📝 {title} (当前)"
            if st.button(btn_label, key=s["session_id"], use_container_width=True):
                st.session_state.session_id = s["session_id"]
                st.session_state.show_kb_details = False
                try:
                    history_res = requests.get(
                        f"{API_BASE}/history/{s['session_id']}",
                        headers=get_auth_headers(),
                        timeout=5
                    )
                    if history_res.status_code == 200:
                        st.session_state.messages = history_res.json().get("data", [])
                except Exception:
                    pass
                st.rerun()

    st.divider()

    with st.expander("🛠️ 管理选项"):
        st.markdown('<div class="sidebar-label">专属知识库</div>', unsafe_allow_html=True)
        uploaded_file = st.file_uploader(
            "上传文档",
            type=["pdf", "docx", "doc", "md", "txt"],
            label_visibility="collapsed"
        )
        st.caption("支持 PDF、DOC、MD、TXT 格式")
        if uploaded_file and st.button("上传入库", use_container_width=True):
            with st.spinner(f"正在上传并做租户级隔离切片 {uploaded_file.name}..."):
                try:
                    files = {"file": (uploaded_file.name, uploaded_file, uploaded_file.type)}
                    r = requests.post(
                        f"{API_BASE}/upload",
                        files=files,
                        headers=get_auth_headers(),
                        timeout=30
                    )
                    if r.status_code == 200:
                        result = r.json()
                        if result.get("status") == "skipped":
                            st.warning(result["message"])
                        else:
                            st.success(f"{uploaded_file.name} 已隔离上传成功")
                            fetch_kb_list.clear()
                    else:
                        st.error(f"上传失败: {r.status_code}")
                except requests.exceptions.Timeout:
                    st.error("上传超时")
                except Exception as e:
                    st.error(str(e))

        st.markdown('<div class="sidebar-label">隔离审计</div>', unsafe_allow_html=True)
        if st.button("查看当前租户已存文档", use_container_width=True):
            st.session_state.show_kb_details = not st.session_state.show_kb_details
            st.rerun()

        if st.button("运行状态探测", use_container_width=True):
            with st.spinner("检查中..."):
                try:
                    r = requests.get(
                        f"{API_BASE}/health",
                        headers=get_auth_headers(),
                        timeout=5
                    )
                    if r.status_code == 200:
                        st.success("服务连接正常")
                        with st.expander("查看详情"):
                            st.json(r.json())
                    else:
                        st.error(f"服务异常: {r.status_code}")
                except Exception:
                    st.error("连接失败，请检查后端服务")

        if st.button("清空知识库", use_container_width=True):
            st.session_state.show_clear_confirm = True

        if st.session_state.show_clear_confirm:
            st.warning("此操作不可恢复，确认物理清空您租户空间下的所有数据？")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("确认", key="confirm_clear"):
                    try:
                        r = requests.delete(
                            f"{API_BASE}/clear",
                            headers=get_auth_headers(),
                            timeout=30
                        )
                        if r.status_code == 200:
                            st.success("租户数据已全部物理清空")
                            st.session_state.messages = []
                            st.session_state.show_clear_confirm = False
                            fetch_kb_list.clear()
                            st.rerun()
                        else:
                            st.error(f"清空失败: {r.status_code}")
                    except Exception as e:
                        st.error(str(e))
            with c2:
                if st.button("取消", key="cancel_clear"):
                    st.session_state.show_clear_confirm = False
                    st.rerun()

# ── 3. 主区域内容展示 ──────────────────────────────────────────────────────────
if st.session_state.show_kb_details:
    st.markdown("### 🔍 专属隔离知识库清单")
    data = fetch_kb_list(
        st.session_state.kb_page,
        PAGE_SIZE,
        st.session_state.jwt_token
    )
    if data:
        kb_data = data.get("data", [])
        total_items = data.get("total", 0)
        total_pages = data.get("total_pages", 1)
        if total_items > 0:
            c1, c2, c3 = st.columns(3)
            c1.metric("文件总数 (当前租户)", total_items)
            c2.metric("分页列表", f"{st.session_state.kb_page} / {total_pages}")
            c3.metric("本页载入行", len(kb_data))
            st.dataframe(pd.DataFrame(kb_data), use_container_width=True, height=250)
            b1, b2, b3 = st.columns([1, 1, 2])
            with b1:
                if st.button("上一页", disabled=st.session_state.kb_page <= 1):
                    st.session_state.kb_page -= 1
                    fetch_kb_list.clear()
                    st.rerun()
            with b2:
                if st.button("下一页", disabled=st.session_state.kb_page >= total_pages):
                    st.session_state.kb_page += 1
                    fetch_kb_list.clear()
                    st.rerun()
            with b3:
                if st.button("收起面板"):
                    st.session_state.show_kb_details = False
                    st.rerun()
        else:
            st.info("您专属的知识库暂时为空，请在侧边栏上传文档。")
            if st.button("收起面板"):
                st.session_state.show_kb_details = False
                st.rerun()
    else:
        st.error("加载列表失败，请检查后端服务")
    st.divider()

if not st.session_state.messages:
    st.markdown(f"""
    <div style="text-align:center;padding:120px 0 60px;">
        <h1 style="font-size:2.4rem;font-weight:700;color:#2d2d2d;margin-bottom:14px;letter-spacing:-0.5px;">智能知识库助手</h1>
        <p style="color:#666;font-size:14px;">已为租户 <span style="font-family:monospace;color:#1e88e5;font-weight:600;">{st.session_state.tenant_id}</span> 建立专属加密沙箱通道</p>
    </div>
    """, unsafe_allow_html=True)
else:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

if prompt := st.chat_input("向专属知识库提问，或者和 AI 聊聊天..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        full_response = ""
        try:
            payload = {"question": prompt, "session_id": st.session_state.session_id}
            response = requests.post(
                f"{API_BASE}/chat",
                json=payload,
                headers=get_auth_headers(),
                stream=True,
                timeout=60
            )
            for chunk in response.iter_content(chunk_size=1024, decode_unicode=True):
                if chunk:
                    full_response += chunk
                    placeholder.markdown(full_response + "▌")
            placeholder.markdown(full_response)
            st.session_state.messages.append({"role": "assistant", "content": full_response})
            fetch_sessions.clear()
        except requests.exceptions.Timeout:
            st.error("RAG 后端检索答复超时")
        except Exception as e:
            st.error(f"网络异常，请求失败: {str(e)}")
