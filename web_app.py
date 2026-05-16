import os

import streamlit as st
import requests
import uuid
import pandas as pd

API_BASE = os.environ.get("API_BASE", "http://localhost:8000/api/v1")
PAGE_SIZE = 10



@st.cache_data(ttl=10)
def fetch_sessions():
    """缓存历史会话列表，10 秒内不重复请求。"""
    try:
        res = requests.get(f"{API_BASE}/sessions", timeout=5)
        if res.status_code == 200:
            return res.json().get("data", [])
    except Exception:
        pass
    return []


@st.cache_data(ttl=10)
def fetch_kb_list(page: int, page_size: int):
    """缓存知识库列表，10 秒内不重复请求。"""
    try:
        res = requests.get(
            f"{API_BASE}/list",
            params={"page": page, "page_size": page_size},
            timeout=10,
        )
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return None

st.set_page_config(
    page_title="智能知识库助手",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
/* ── 只隐藏必要元素，不动 header 结构 ── */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
.stDeployButton { display: none; }

/* ── 背景 ── */
.stApp { background-color: #f5f4ef; }
.main { background-color: #f5f4ef; }

/* ── 侧边栏 ── */
section[data-testid="stSidebar"] {
    background: #ffffff;
    border-right: 1px solid #e8e8e8;
}
section[data-testid="stSidebar"] > div:first-child {
    padding: 20px 14px;
}

/* ── 按钮 ── */
.stButton > button {
    border-radius: 10px;
    border: 1px solid #e5e5e5;
    background: white;
    color: #333;
    font-size: 13px;
    transition: all 0.15s;
    text-align: left;
}
.stButton > button:hover {
    background: #f5f5f5;
    border-color: #ccc;
}

/* ── 文本输入框 ── */
[data-testid="stTextInput"] input {
    background: white !important;
    border: 1px solid #e8e8e8 !important;
    border-radius: 8px !important;
    font-size: 13px !important;
    color: #333 !important;
    box-shadow: none !important;
}
[data-testid="stTextInput"] input:focus {
    border-color: #ccc !important;
    box-shadow: none !important;
}

/* ── 聊天输入框 ── */
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
[data-testid="stChatInput"] button svg {
    fill: white !important;
    color: white !important;
}

/* ── 聊天消息 ── */
[data-testid="stChatMessage"] {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    background: white !important;
    border: 1px solid #e8e8e8 !important;
    border-radius: 10px !important;
    box-shadow: none !important;
}
[data-testid="stExpander"] summary {
    color: #444 !important;
    font-size: 13px !important;
    font-weight: 500 !important;
}

/* ── Metric ── */
[data-testid="stMetric"] {
    background: white;
    border-radius: 10px;
    padding: 12px 16px;
    border: 1px solid #ebebeb;
}
[data-testid="stMetricValue"] { color: #1a1a1a !important; }
[data-testid="stMetricLabel"] { color: #999 !important; }

/* ── Dataframe ── */
[data-testid="stDataFrame"] {
    background: white;
    border-radius: 10px;
    border: 1px solid #ebebeb;
    overflow: hidden;
}

/* ── 通知消息 ── */
[data-testid="stAlert"] {
    border-radius: 10px !important;
    border: none !important;
    font-size: 13px !important;
}

/* ── 文件上传 ── */
[data-testid="stFileUploader"] {
    background: white;
    border-radius: 10px;
    border: 1px dashed #ddd;
    padding: 4px;
}
[data-testid="stFileUploader"] section {
    background: transparent !important;
    border: none !important;
}

/* ── Divider ── */
hr { border-color: #ebebeb !important; margin: 10px 0 !important; }

/* ── Caption ── */
.stCaption, [data-testid="stCaptionContainer"] {
    color: #bbb !important;
    font-size: 11px !important;
}

/* ── 主区域 ── */
.main .block-container {
    max-width: 860px;
    padding: 2rem 2rem 5rem;
    margin: 0 auto;
}

/* ── 侧边栏标签 ── */
.sidebar-label {
    font-size: 10px;
    font-weight: 700;
    color: #aaa;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin: 16px 0 8px 2px;
}

/* ── 功能卡片 ── */
.feature-card {
    background: white;
    border-radius: 16px;
    padding: 28px 24px;
    border: 1px solid #ebebeb;
    min-height: 140px;
}
</style>
""", unsafe_allow_html=True)

# ── Session State ─────────────────────────────────────────────────────────────
defaults = {
    "session_id": str(uuid.uuid4()),
    "messages": [],
    "show_clear_confirm": False,
    "show_kb_details": False,
    "kb_page": 1,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── 侧边栏 ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="display:flex;align-items:center;gap:10px;padding-bottom:16px;border-bottom:1px solid #f0f0f0;">
        <div style="width:28px;height:28px;background:linear-gradient(135deg,#ff6b9d,#c44dff);border-radius:50%;flex-shrink:0;"></div>
        <div>
            <div style="font-size:13px;font-weight:700;color:#1a1a1a;">智能知识库助手</div>
            <div style="font-size:11px;color:#666;">基于大模型的文档问答系统</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

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

    sessions = fetch_sessions()
    if search_query:
        sessions = [s for s in sessions if search_query.lower() in s.get("title", "").lower()]
    if not sessions:
        st.caption("暂无历史对话")
    else:
        for s in sessions:
            if st.button(s["title"], key=s["session_id"], use_container_width=True):
                st.session_state.session_id = s["session_id"]
                st.session_state.show_kb_details = False
                try:
                    history_res = requests.get(f"{API_BASE}/history/{s['session_id']}", timeout=5)
                    if history_res.status_code == 200:
                        st.session_state.messages = history_res.json().get("data", [])
                except Exception:
                    pass
                st.rerun()

    st.divider()

    with st.expander("管理选项"):
        st.markdown('<div class="sidebar-label">知识库</div>', unsafe_allow_html=True)
        uploaded_file = st.file_uploader(
            "上传文档",
            type=["pdf", "docx", "doc", "md", "txt"],
            label_visibility="collapsed"
        )
        st.caption("支持 PDF、DOC、MD、TXT 格式")
        if uploaded_file and st.button("上传入库", use_container_width=True):
            with st.spinner(f"正在上传 {uploaded_file.name}..."):
                try:
                    files = {"file": (uploaded_file.name, uploaded_file, uploaded_file.type)}
                    r = requests.post(f"{API_BASE}/upload", files=files, timeout=30)
                    if r.status_code == 200:
                        result = r.json()
                        if result.get("status") == "skipped":
                            st.warning(result["message"])
                        else:
                            st.success(f"{uploaded_file.name} 上传成功")
                    else:
                        st.error(f"上传失败: {r.status_code}")
                except requests.exceptions.Timeout:
                    st.error("上传超时")
                except Exception as e:
                    st.error(str(e))

        st.markdown('<div class="sidebar-label">数据库</div>', unsafe_allow_html=True)
        if st.button("查看知识库详情", use_container_width=True):
            st.session_state.show_kb_details = not st.session_state.show_kb_details
            st.rerun()

        if st.button("健康检查", use_container_width=True):
            with st.spinner("检查中..."):
                try:
                    r = requests.get(f"{API_BASE}/health", timeout=5)
                    if r.status_code == 200:
                        st.success("服务运行正常")
                        with st.expander("查看详情"):
                            st.json(r.json())
                    else:
                        st.error(f"服务异常: {r.status_code}")
                except Exception:
                    st.error("连接失败，请检查后端服务")

        if st.button("清空知识库", use_container_width=True):
            st.session_state.show_clear_confirm = True

        if st.session_state.show_clear_confirm:
            st.warning("此操作不可恢复，确认清空？")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("确认", key="confirm_clear"):
                    try:
                        r = requests.delete(f"{API_BASE}/clear", timeout=30)
                        if r.status_code == 200:
                            st.success("知识库已清空")
                            st.session_state.messages = []
                            st.session_state.show_clear_confirm = False
                            st.rerun()
                        else:
                            st.error(f"清空失败: {r.status_code}")
                    except Exception as e:
                        st.error(str(e))
            with c2:
                if st.button("取消", key="cancel_clear"):
                    st.session_state.show_clear_confirm = False
                    st.rerun()

# ── 主区域 ────────────────────────────────────────────────────────────────────
if st.session_state.show_kb_details:
    st.markdown("### 知识库详情")
    data = fetch_kb_list(st.session_state.kb_page, PAGE_SIZE)
    if data:
        kb_data = data.get("data", [])
        total_items = data.get("total", 0)
        total_pages = data.get("total_pages", 1)
        if total_items > 0:
            c1, c2, c3 = st.columns(3)
            c1.metric("文件总数", total_items)
            c2.metric("当前页码", f"{st.session_state.kb_page} / {total_pages}")
            c3.metric("本页数量", len(kb_data))
            st.dataframe(pd.DataFrame(kb_data), use_container_width=True, height=300)
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
                if st.button("收起"):
                    st.session_state.show_kb_details = False
                    st.rerun()
        else:
            st.info("知识库为空，请先上传文档")
            if st.button("收起"):
                st.session_state.show_kb_details = False
                st.rerun()
    else:
        st.error("加载失败，请检查后端服务")
    st.divider()

if not st.session_state.messages:
    st.markdown("""
    <div style="text-align:center;padding:120px 0 60px;">
        <h1 style="font-size:2.4rem;font-weight:700;color:#2d2d2d;margin-bottom:14px;letter-spacing:-0.5px;">智能知识库助手</h1>
    </div>
    """, unsafe_allow_html=True)
else:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

if prompt := st.chat_input("向知识库提问，或者和我聊聊天..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        full_response = ""
        try:
            payload = {"question": prompt, "session_id": st.session_state.session_id}
            response = requests.post(f"{API_BASE}/chat", json=payload, stream=True, timeout=60)
            for chunk in response.iter_content(chunk_size=1024, decode_unicode=True):
                if chunk:
                    full_response += chunk
                    placeholder.markdown(full_response + "▌")
            placeholder.markdown(full_response)
            st.session_state.messages.append({"role": "assistant", "content": full_response})
        except requests.exceptions.Timeout:
            st.error("请求超时，请稍后重试")
        except Exception as e:
            st.error(f"请求失败: {str(e)}")
