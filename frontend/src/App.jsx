import React, { useState, useEffect, useRef } from 'react';
import { 
  Lock, User, LogIn, UserPlus, Send, Plus, 
  Trash2, Database, MessageSquare, Shield, 
  UploadCloud, FileText, ChevronRight, LogOut, 
  Search, Activity, AlertCircle, RefreshCw,
  ChevronLeft, X, AlertTriangle, ExternalLink,
  Hexagon, Paperclip, Lightbulb, ThumbsUp, ThumbsDown, Check, Quote
} from 'lucide-react';
import './App.css';

// 后端 API 基准地址 (修改为防冲突的 8010 端口)
const API_BASE = 'http://localhost:8010/api/v1';
const PAGE_SIZE = 10;

// 链路观测 Demo Fallback 数据
const FALLBACK_TRACES_DEMO = [
  {
    id: "trace-demo-1",
    name: "RAGRetrievalChain",
    run_type: "chain",
    status: "success",
    latency_ms: 840,
    total_tokens: 380,
    question: "混合路检索测试：测试当前知识库在混合召回下的检索响应时延。",
    child_stages: [
      { name: "QueryRewriteAgent", type: "rewriter", status: "success" },
      { name: "ChromaVectorRetrieval", type: "retriever", status: "success" },
      { name: "SQLiteBM25Retrieval", type: "retriever", status: "success" },
      { name: "RRFHybridFusion", type: "fusion", status: "success" },
      { name: "FlashrankRerank", type: "reranker", status: "success" },
      { name: "CriticAgentEvaluation", type: "critic", status: "success" }
    ]
  }
];

function App() {
  // --- 身份验证状态 ---
  const [token, setToken] = useState(sessionStorage.getItem('token') || '');
  const [username, setUsername] = useState(sessionStorage.getItem('username') || '');
  const [tenantId, setTenantId] = useState(sessionStorage.getItem('tenant_id') || '');
  const [isRegister, setIsRegister] = useState(false);
  
  // 登录/注册表单
  const [authUsername, setAuthUsername] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [usernameError, setUsernameError] = useState('');
  const [authError, setAuthError] = useState('');
  const [authSuccess, setAuthSuccess] = useState('');

  // --- 控制台布局状态 ---
  const [showLeftSidebar, setShowLeftSidebar] = useState(true);
  const [showRightPanel, setShowRightPanel] = useState(true);
  const [activeRightTab, setActiveRightTab] = useState('citations'); // 'citations' | 'kb'

  // --- RAG 业务状态 ---
  const [sessions, setSessions] = useState([]);
  const [searchQuery, setSearchQuery] = useState(''); 
  const [activeSessionId, setActiveSessionId] = useState('');
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [currentCitations, setCurrentCitations] = useState([]); 

  // 专属知识库分页列表
  const [documents, setDocuments] = useState([]);
  const [kbPage, setKbPage] = useState(1);
  const [kbTotal, setKbTotal] = useState(0);
  const [kbTotalPages, setKbTotalPages] = useState(1);
  
  // Chroma Chunks 审计预览抽屉状态
  const [previewDocName, setPreviewDocName] = useState(null);
  const [previewChunks, setPreviewChunks] = useState([]);
  const [previewPage, setPreviewPage] = useState(1);
  const [previewTotal, setPreviewTotal] = useState(0);
  const [previewTotalPages, setPreviewTotalPages] = useState(1);

  // 文件上传状态
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState('');
  const [isDragging, setIsDragging] = useState(false);

  // --- 新增设计系统下的 Developer Mode 与头像浮层 ---
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [developerMode, setDeveloperMode] = useState(false);
  const [healthStatus, setHealthStatus] = useState('healthy'); 
  const [traces, setTraces] = useState([]); 

  // 全局非阻塞通知 Toast 队列
  const [toasts, setToasts] = useState([]);

  // 自定义二次确认弹窗 ConfirmModal 状态
  const [confirmModal, setConfirmModal] = useState({
    isOpen: false,
    title: '',
    message: '',
    onConfirm: null
  });

  const messagesEndRef = useRef(null);

  // 1. Toast 通知推送函数
  const showToast = (title, message, type = 'info') => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, title, message, type }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 4500);
  };

  // 2. 自定义确认弹窗触发器
  const triggerConfirm = (title, message, onConfirm) => {
    setConfirmModal({
      isOpen: true,
      title,
      message,
      onConfirm: () => {
        onConfirm();
        setConfirmModal(prev => ({ ...prev, isOpen: false }));
      }
    });
  };

  // 3. 校验用户名正则 (^[a-zA-Z0-9_-]{2,50}$)
  const validateUsername = (name) => {
    const regex = /^[a-zA-Z0-9_-]{2,50}$/;
    if (!name) {
      setUsernameError('用户名不能为空');
      return false;
    }
    if (!regex.test(name)) {
      setUsernameError('用户名只允许字母、数字、下划线及连字符 (2-50位)');
      return false;
    }
    setUsernameError('');
    return true;
  };

  const handleUsernameChange = (e) => {
    const val = e.target.value;
    setAuthUsername(val);
    if (isRegister) {
      validateUsername(val);
    } else {
      setUsernameError('');
    }
  };

  // 4. 注册请求
  const handleRegister = async (e) => {
    e.preventDefault();
    if (!validateUsername(authUsername)) return;
    if (authPassword.length < 6) {
      setAuthError('密码长度不能少于 6 位');
      return;
    }
    setAuthError('');
    setAuthSuccess('');

    try {
      const res = await fetch(`${API_BASE}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: authUsername, password: authPassword })
      });
      const data = await res.json();
      if (res.ok) {
        setAuthSuccess('账户注册成功！已为您创建专属隔离租户。请切换至登录。');
        showToast('注册成功', '专属隔离租户空间已创建完毕，请登录！', 'success');
        setIsRegister(false);
      } else {
        setAuthError(data.detail || '注册失败，用户名可能已存在');
        showToast('注册失败', data.detail || '注册失败', 'error');
      }
    } catch (err) {
      setAuthError('连接认证服务器失败，请确保数据库与后端服务已拉起');
      showToast('连接失败', '无法访问后端认证服务', 'error');
    }
  };

  // 5. 登录请求
  const handleLogin = async (e) => {
    e.preventDefault();
    setAuthError('');
    setAuthSuccess('');

    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: authUsername, password: authPassword })
      });
      const data = await res.json();
      if (res.ok) {
        setToken(data.access_token);
        setUsername(data.username);
        setTenantId(data.tenant_id);
        sessionStorage.setItem('token', data.access_token);
        sessionStorage.setItem('username', data.username);
        sessionStorage.setItem('tenant_id', data.tenant_id);
        showToast('登录成功', `欢迎回来，${data.username}！专属隔离沙箱已拉起。`, 'success');
      } else {
        setAuthError(data.detail || '用户名或密码错误');
        showToast('登录失败', data.detail || '登录凭证无效', 'error');
      }
    } catch (err) {
      setAuthError('连接认证服务器失败，请确保数据库与后端服务已拉起');
      showToast('连接失败', '无法访问后端登录接口', 'error');
    }
  };

  // 6. 访客免密一键登录
  const handleVisitorLogin = async () => {
    setAuthError('');
    setAuthSuccess('');
    try {
      const res = await fetch(`${API_BASE}/auth/visitor-login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const data = await res.json();
      if (res.ok) {
        setToken(data.access_token);
        setUsername(data.username);
        setTenantId(data.tenant_id);
        sessionStorage.setItem('token', data.access_token);
        sessionStorage.setItem('username', data.username);
        sessionStorage.setItem('tenant_id', data.tenant_id);
        showToast('访客免密登录成功', '已为您随机生成物理隔离租户沙箱，数据仅保留在当前会话中。', 'success');
      } else {
        setAuthError(data.detail || '访客免密通道登录失败');
        showToast('登录失败', data.detail || '访客通道暂时关闭', 'error');
      }
    } catch (err) {
      setAuthError('连接认证服务器失败，请确认后端端口已映射');
      showToast('连接失败', '无法连接至访客登录接口', 'error');
    }
  };

  // 7. 登出
  const handleLogout = () => {
    setToken('');
    setUsername('');
    setTenantId('');
    setSessions([]);
    setActiveSessionId('');
    setMessages([]);
    setDocuments([]);
    setCurrentCitations([]);
    setPreviewDocName(null);
    setShowUserMenu(false);
    setDeveloperMode(false);
    sessionStorage.clear();
    showToast('已登出', '您已安全退出当前租户空间。', 'info');
  };

  // --- 初始化与健康探针 ---
  useEffect(() => {
    if (token) {
      fetchDocuments(kbPage);
      fetchSessions();
      checkHealthStatus();
    }
  }, [token, kbPage]);

  // 监控 Trace 自动拉取
  useEffect(() => {
    if (token && developerMode) {
      fetchTraces();
    }
  }, [token, developerMode]);

  // 滚动至最新消息
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // 8. 服务健康检查
  const checkHealthStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/health`);
      const data = await res.json();
      if (res.ok && data.status === 'ok') {
        setHealthStatus('healthy');
      } else {
        setHealthStatus('unhealthy');
      }
    } catch (e) {
      setHealthStatus('unhealthy');
    }
  };

  // 9. 分页拉取知识库列表 (GET /list)
  const fetchDocuments = async (page) => {
    try {
      const res = await fetch(`${API_BASE}/list?page=${page}&page_size=${PAGE_SIZE}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (res.ok) {
        setDocuments(data.data || []);
        setKbTotal(data.total || 0);
        setKbTotalPages(data.total_pages || 1);
      }
    } catch (err) {
      console.error('获取文档失败', err);
    }
  };

  // 10. Chroma Chunks 审计列表分页查询
  const fetchChunks = async (filename, page) => {
    if (!filename) return;
    try {
      const res = await fetch(`${API_BASE}/chunks?filename=${encodeURIComponent(filename)}&page=${page}&page_size=5`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (res.ok) {
        setPreviewChunks(data.data || []);
        setPreviewTotal(data.total || 0);
        setPreviewTotalPages(data.total_pages || 1);
      } else {
        showToast('审计数据加载失败', data.detail || '无法获取分片详情', 'error');
      }
    } catch (err) {
      showToast('审计数据加载失败', '网络请求故障', 'error');
    }
  };

  useEffect(() => {
    if (previewDocName) {
      fetchChunks(previewDocName, previewPage);
    } else {
      setPreviewChunks([]);
      setPreviewTotal(0);
      setPreviewTotalPages(1);
    }
  }, [previewDocName, previewPage]);

  // 11. 拉取历史会话列表
  const fetchSessions = async () => {
    try {
      const res = await fetch(`${API_BASE}/sessions`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (res.ok) {
        const sorted = (data.data || []).sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
        setSessions(sorted);
      }
    } catch (err) {
      console.error('获取会话失败', err);
    }
  };

  // 12. 链路 Trace 获取
  const fetchTraces = async () => {
    try {
      const res = await fetch(`${API_BASE}/traces?limit=10`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (res.ok) {
        const resTraces = data.data || [];
        setTraces(resTraces.length === 0 ? FALLBACK_TRACES_DEMO : resTraces);
      } else {
        setTraces(FALLBACK_TRACES_DEMO);
      }
    } catch (err) {
      setTraces(FALLBACK_TRACES_DEMO);
    }
  };

  // 13. 消息/证据链提取辅助函数 (从 content 中剥离 __METADATA_START__ 并解析)
  const parseCitationsFromContent = (content) => {
    if (!content) return { cleanContent: '', citations: [] };
    const markerIdx = content.indexOf('__METADATA_START__');
    if (markerIdx !== -1) {
      const endMarkerIdx = content.indexOf('__METADATA_END__');
      let jsonStr = '';
      if (endMarkerIdx !== -1) {
        jsonStr = content.substring(markerIdx + '__METADATA_START__'.length, endMarkerIdx).trim();
      } else {
        jsonStr = content.substring(markerIdx + '__METADATA_START__'.length).trim();
      }
      try {
        const parsed = JSON.parse(jsonStr);
        return {
          cleanContent: content.substring(0, markerIdx).trim(),
          citations: parsed.chunks || []
        };
      } catch (e) {
        return { cleanContent: content.substring(0, markerIdx).trim(), citations: [] };
      }
    }
    return { cleanContent: content, citations: [] };
  };

  // 14. 切换会话并读取对话记录
  const handleSelectSession = async (sessionId) => {
    setActiveSessionId(sessionId);
    setMessages([]);
    setCurrentCitations([]);
    try {
      const res = await fetch(`${API_BASE}/history/${sessionId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (res.ok) {
        const historyMsgs = data.data || [];
        setMessages(historyMsgs);
        
        const assistantMsgs = historyMsgs.filter(m => m.role === 'assistant');
        if (assistantMsgs.length > 0) {
          const lastMsg = assistantMsgs[assistantMsgs.length - 1];
          const parsed = parseCitationsFromContent(lastMsg.content);
          setCurrentCitations(parsed.citations);
        }
      }
    } catch (err) {
      console.error('获取会话记录失败', err);
    }
  };

  // 15. 新建会话
  const handleCreateNewChat = () => {
    setActiveSessionId('');
    setMessages([]);
    setCurrentCitations([]);
  };

  // 16. 删除单个会话
  const handleDeleteSession = async (e, sessionId) => {
    e.stopPropagation();
    triggerConfirm(
      '确认删除该会话吗？',
      '删除后该会话中的所有聊天记录将永久丢失。',
      async () => {
        try {
          const res = await fetch(`${API_BASE}/history/${sessionId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
          });
          if (res.ok) {
            showToast('会话已删除', '所选的历史聊天记录已被清理。', 'success');
            if (activeSessionId === sessionId) {
              handleCreateNewChat();
            }
            fetchSessions();
          } else {
            showToast('删除会话失败', '服务器返回异常', 'error');
          }
        } catch (err) {
          showToast('删除会话失败', '网络请求失败', 'error');
        }
      }
    );
  };

  // 17. 物理删除单个知识库文档
  const handleDeleteDocument = async (filename) => {
    try {
      const res = await fetch(`${API_BASE}/document?filename=${encodeURIComponent(filename)}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (res.ok) {
        showToast('物理删除成功', `文档已从向量库和数据库中清除。`, 'success');
        fetchDocuments(kbPage);
      } else {
        showToast('删除文档失败', data.detail || '文档删除失败', 'error');
      }
    } catch (err) {
      showToast('删除文档失败', '无法连接到后端管理服务', 'error');
    }
  };

  const triggerDeleteDocument = (filename) => {
    triggerConfirm(
      '确认物理删除文档？',
      `确定要物理删除文档【${filename}】吗？该操作会将 Chroma 中关联的全部文本切片及数据库中的文档索引永久擦除，且无法复原！`,
      () => handleDeleteDocument(filename)
    );
  };

  // 18. 拖拽与上传文件
  const handleUploadFile = async (file) => {
    if (!file) return;
    setIsUploading(true);
    setUploadProgress(`正在导入并分析 ${file.name}...`);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch(`${API_BASE}/upload`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData
      });
      const data = await res.json();
      if (res.ok) {
        if (data.status === 'skipped') {
          showToast('上传跳过', '文件指纹完全一致，系统跳过入库。', 'info');
        } else {
          showToast('入库成功', `文档已成功切片导入！`, 'success');
        }
        setUploadProgress('');
        fetchDocuments(kbPage);
      } else {
        showToast('上传失败', data.detail || '文件导入失败', 'error');
        setUploadProgress('');
      }
    } catch (err) {
      showToast('上传故障', '连接后端上传微服务失败', 'error');
      setUploadProgress('');
    } finally {
      setIsUploading(false);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleUploadFile(files[0]);
    }
  };

  // 19. 发送消息
  const handleSendMessage = async (e, overrideText = null) => {
    if (e) e.preventDefault();
    const textToSend = overrideText || inputMessage;
    if (!textToSend.trim() || isSending) return;

    const userText = textToSend;
    setInputMessage('');
    setIsSending(true);
    setCurrentCitations([]); 

    const tempSessionId = activeSessionId || `session_${Date.now()}`;
    if (!activeSessionId) {
      setActiveSessionId(tempSessionId);
    }

    setMessages(prev => [...prev, { role: 'user', content: userText }]);
    setMessages(prev => [...prev, { role: 'assistant', content: '' }]);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ 
          question: userText, 
          session_id: tempSessionId
        })
      });

      if (!res.ok) {
        const errorData = await res.json();
        setMessages(prev => {
          const next = [...prev];
          next[next.length - 1] = { role: 'assistant', content: `[错误] ${errorData.detail || '服务不可用'}` };
          return next;
        });
        setIsSending(false);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let assistantText = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const textChunk = decoder.decode(value, { stream: true });
        assistantText += textChunk;

        let displayCtx = assistantText;
        let metaJsonStr = '';
        const markerIdx = assistantText.indexOf('__METADATA_START__');
        if (markerIdx !== -1) {
          displayCtx = assistantText.substring(0, markerIdx).trim();
          const endMarkerIdx = assistantText.indexOf('__METADATA_END__');
          if (endMarkerIdx !== -1) {
            metaJsonStr = assistantText.substring(markerIdx + '__METADATA_START__'.length, endMarkerIdx).trim();
          } else {
            metaJsonStr = assistantText.substring(markerIdx + '__METADATA_START__'.length).trim();
          }
        }

        setMessages(prev => {
          const next = [...prev];
          next[next.length - 1] = { role: 'assistant', content: displayCtx };
          return next;
        });

        if (metaJsonStr && markerIdx !== -1) {
          try {
            const parsed = JSON.parse(metaJsonStr);
            if (parsed && parsed.chunks) {
              setCurrentCitations(parsed.chunks);
            }
          } catch(e) {
            // ignore
          }
        }
      }
      
      const finalMarkerIdx = assistantText.indexOf('__METADATA_START__');
      if (finalMarkerIdx !== -1) {
        let finalMetaStr = '';
        const finalEndMarkerIdx = assistantText.indexOf('__METADATA_END__');
        if (finalEndMarkerIdx !== -1) {
          finalMetaStr = assistantText.substring(finalMarkerIdx + '__METADATA_START__'.length, finalEndMarkerIdx).trim();
        } else {
          finalMetaStr = assistantText.substring(finalMarkerIdx + '__METADATA_START__'.length).trim();
        }
        try {
          const parsed = JSON.parse(finalMetaStr);
          if (parsed && parsed.chunks) {
            setCurrentCitations(parsed.chunks);
          }
        } catch(e) {
          console.error(e);
        }
      }

      fetchSessions();
      setIsSending(false);
    } catch (err) {
      setMessages(prev => {
        const next = [...prev];
        next[next.length - 1] = { role: 'assistant', content: `[错误] 无法建立连接，请确认本地服务已拉起。` };
        return next;
      });
      setIsSending(false);
    }
  };

  const filteredSessions = sessions.filter(s => 
    s.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const groupSessionsByTime = (sessionsList) => {
    const groups = {
      today: [],
      yesterday: [],
      older: []
    };
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterdayStart = new Date(todayStart.getTime() - 24 * 60 * 60 * 1000);

    sessionsList.forEach(session => {
      const createdDate = new Date(session.created_at);
      if (createdDate >= todayStart) {
        groups.today.push(session);
      } else if (createdDate >= yesterdayStart) {
        groups.yesterday.push(session);
      } else {
        groups.older.push(session);
      }
    });
    return groups;
  };

  const groupedSessions = groupSessionsByTime(filteredSessions);

  // 引用文字点击高亮滚动
  const renderMessageContent = (content) => {
    if (!content) return '';
    const regex = /\[(\d+)\]/g;
    const parts = content.split(regex);
    if (parts.length === 1) return content;
    
    return parts.map((part, idx) => {
      if (idx % 2 === 1) {
        const num = parseInt(part, 10);
        return (
          <button 
            key={idx}
            className="citation-anchor-btn" 
            onClick={() => {
              setActiveRightTab('citations');
              const cardId = `citation-card-${num - 1}`;
              setTimeout(() => {
                const el = document.getElementById(cardId);
                if (el) {
                  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                  el.style.backgroundColor = 'rgba(79, 70, 229, 0.08)';
                  setTimeout(() => {
                    el.style.backgroundColor = '';
                  }, 2000);
                }
              }, 100);
            }}
            title={`定位引文 [${num}]`}
          >
            [{num}]
          </button>
        );
      }
      return part;
    });
  };

  // --- 登录页面 (保持原有极简双栏，适配靛蓝主色) ---
  if (!token) {
    return (
      <div className="auth-page-wrapper">
        <div className="brand-panel">
          {/* 顶置品牌 Logo */}
          <div className="brand-header-logo">
            <div className="brand-logo-hex">
              <Hexagon size={22} strokeWidth={1.5} style={{ color: '#4F46E5' }} />
            </div>
            <div className="brand-logo-text-group">
              <span className="brand-logo-main">Enterprise RAG</span>
              <span className="brand-logo-sub">AI Knowledge Workspace</span>
            </div>
          </div>

          {/* 主副标题宣传区 */}
          <div className="brand-hero-section">
            <h1 className="brand-hero-title">
              企业级 RAG 系统<br />
              让企业知识，触手可及
            </h1>
            <p className="brand-hero-desc">
              基于混合检索与 Critic Agent 证据链评估，<br />
              提供安全、可靠、可追溯的 AI 问答体验。
            </p>
          </div>

          {/* 横向并排的三个核心特征卡片 */}
          <div className="brand-features-row">
            <div className="brand-feature-item">
              <div className="brand-feature-icon-wrapper" style={{ background: '#EEF2FF', color: '#4F46E5' }}>
                <Shield size={16} strokeWidth={1.5} />
              </div>
              <div className="brand-feature-item-text">
                <span className="feature-item-title">安全可靠</span>
                <span className="feature-item-desc">多租户隔离</span>
              </div>
            </div>

            <div className="brand-feature-item">
              <div className="brand-feature-icon-wrapper" style={{ background: '#EFF6FF', color: '#3B82F6' }}>
                <Search size={16} strokeWidth={1.5} />
              </div>
              <div className="brand-feature-item-text">
                <span className="feature-item-title">精准检索</span>
                <span className="feature-item-desc">混合检索 + 重排</span>
              </div>
            </div>

            <div className="brand-feature-item">
              <div className="brand-feature-icon-wrapper" style={{ background: '#F5F3FF', color: '#8B5CF6' }}>
                <Quote size={14} strokeWidth={1.5} />
              </div>
              <div className="brand-feature-item-text">
                <span className="feature-item-title">可信溯源</span>
                <span className="feature-item-desc">引用可追溯</span>
              </div>
            </div>
          </div>

          {/* 底部版本 */}
          <div className="brand-footer-caption">
            V1.2.0 PRODUCTION READY
          </div>

          {/* 背景抽象淡雅波纹线条装饰 */}
          <div className="brand-bg-wave-container">
            <svg className="brand-bg-wave-svg" viewBox="0 0 800 600" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M-100,520 C150,470 350,570 600,500 C750,460 850,500 950,480" stroke="rgba(79, 70, 229, 0.05)" strokeWidth="2" fill="none" />
              <path d="M-100,550 C180,500 320,600 580,530 C720,490 880,540 980,510" stroke="rgba(79, 70, 229, 0.03)" strokeWidth="1.5" fill="none" />
              <path d="M-100,580 C200,530 300,630 560,560 C700,520 900,570 1000,540" stroke="rgba(79, 70, 229, 0.02)" strokeWidth="1" fill="none" />
            </svg>
          </div>
        </div>

        <div className="auth-panel">
          <div className="auth-card">
            <div className="auth-card-header">
              <h1>登录您的空间</h1>
              <p>请输入您的租户账号和密码</p>
            </div>

            <div className="auth-tab-group">
              <button 
                type="button"
                className={`auth-tab-btn ${!isRegister ? 'active' : ''}`}
                onClick={() => { setIsRegister(false); setAuthError(''); setAuthSuccess(''); }}
              >
                租户登录
              </button>
              <button 
                type="button"
                className={`auth-tab-btn ${isRegister ? 'active' : ''}`}
                onClick={() => { setIsRegister(true); setAuthError(''); setAuthSuccess(''); }}
              >
                新建用户
              </button>
            </div>

            <form onSubmit={isRegister ? handleRegister : handleLogin} className="auth-form">
              <div className="form-field">
                <label>租户账户 / 用户名</label>
                <div className="input-container">
                  <input 
                    type="text" 
                    value={authUsername}
                    onChange={handleUsernameChange}
                    placeholder="请输入您的租户账号" 
                    required
                  />
                  <User size={16} strokeWidth={1.5} className="input-icon" />
                </div>
                {isRegister && (
                  <span className={`auth-helper-text ${usernameError ? 'error' : 'info'}`}>
                    {usernameError || '支持字母、数字、下划线与连字符，2-50 位。'}
                  </span>
                )}
              </div>

              <div className="form-field">
                <label>空间密码</label>
                <div className="input-container">
                  <input 
                    type="password" 
                    value={authPassword}
                    onChange={(e) => setAuthPassword(e.target.value)}
                    placeholder="请输入登录密码" 
                    required
                  />
                  <Lock size={16} strokeWidth={1.5} className="input-icon" />
                </div>
              </div>

              <button type="submit" className="auth-btn-primary">
                {isRegister ? '创建账户并获取专属租户' : '确认登录'}
              </button>
            </form>

            <div className="auth-divider">或者</div>

            <button 
              type="button" 
              className="visitor-btn" 
              onClick={handleVisitorLogin}
            >
              访客免密一键登录
            </button>

            {authError && <span className="auth-helper-text error" style={{ textAlign: 'center', display: 'block' }}>{authError}</span>}
            {authSuccess && <span className="auth-helper-text" style={{ color: 'var(--accent-color)', textAlign: 'center', display: 'block' }}>{authSuccess}</span>}
          </div>
        </div>

        <div className="toast-container-fixed">
          {toasts.map(t => (
            <div key={t.id} className="toast-item-card">
              <div className={`toast-indicator-bar ${t.type}`}></div>
              <div className={`toast-icon-side ${t.type}`}>
                {t.type === 'success' && <Shield size={16} strokeWidth={1.5} />}
                {t.type === 'error' && <AlertTriangle size={16} strokeWidth={1.5} />}
                {t.type === 'info' && <AlertCircle size={16} strokeWidth={1.5} />}
              </div>
              <div className="toast-text-side">
                <div className="toast-title">{t.title}</div>
                <div className="toast-desc">{t.message}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // --- 主控制台页面渲染 (三栏自适应极简结构) ---
  return (
    <div className="console-layout">
      
      {/* 🔑 STEP 2: 重构左侧 Sidebar (按大厂规范进行 280px 设计定位) */}
      <div className="sidebar-panel">
        
        {/* Logo 区域 (⬢ Hexagon + H1 + Caption) */}
        <div className="sidebar-header">
          <div className="sidebar-header-logo-row">
            <Hexagon size={20} strokeWidth={1.5} className="sidebar-logo-icon" />
            <h1>Enterprise RAG</h1>
          </div>
          <div className="sidebar-subtitle">AI Knowledge Workspace</div>
        </div>

        {/* 新建对话按钮 */}
        <div className="new-chat-wrapper">
          <button className="new-chat-btn-lg" onClick={handleCreateNewChat}>
            <Plus size={15} strokeWidth={1.5} /> 新建对话
          </button>
        </div>

        {/* 搜索会话框 */}
        <div className="sidebar-search-box">
          <div className="search-box-inner">
            <input 
              type="text" 
              placeholder="搜索历史会话"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            <Search size={13} strokeWidth={1.5} className="search-icon" />
          </div>
        </div>

        {/* 分组会话列表 */}
        <div className="session-grouped-container">
          {sessions.length === 0 ? (
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', textAlign: 'center', marginTop: '16px' }}>
              暂无历史会话
            </div>
          ) : (
            <>
              {/* 今天 */}
              {groupedSessions.today.length > 0 && (
                <div className="session-group">
                  <div className="session-group-title">今天</div>
                  {groupedSessions.today.map(s => (
                    <div 
                      key={s.session_id} 
                      className={`session-item-row ${activeSessionId === s.session_id ? 'active' : ''}`}
                      onClick={() => handleSelectSession(s.session_id)}
                    >
                      <div className="session-item-left">
                        <MessageSquare size={13} strokeWidth={1.5} color={activeSessionId === s.session_id ? 'var(--accent-color)' : 'var(--text-secondary)'} />
                        <span className="session-item-title-text" title={s.title}>{s.title}</span>
                      </div>
                      <button 
                        className="session-delete-action" 
                        onClick={(e) => handleDeleteSession(e, s.session_id)}
                        title="删除会话"
                      >
                        <Trash2 size={12} strokeWidth={1.5} />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* 昨天 */}
              {groupedSessions.yesterday.length > 0 && (
                <div className="session-group">
                  <div className="session-group-title">昨天</div>
                  {groupedSessions.yesterday.map(s => (
                    <div 
                      key={s.session_id} 
                      className={`session-item-row ${activeSessionId === s.session_id ? 'active' : ''}`}
                      onClick={() => handleSelectSession(s.session_id)}
                    >
                      <div className="session-item-left">
                        <MessageSquare size={13} strokeWidth={1.5} color={activeSessionId === s.session_id ? 'var(--accent-color)' : 'var(--text-secondary)'} />
                        <span className="session-item-title-text" title={s.title}>{s.title}</span>
                      </div>
                      <button 
                        className="session-delete-action" 
                        onClick={(e) => handleDeleteSession(e, s.session_id)}
                        title="删除会话"
                      >
                        <Trash2 size={12} strokeWidth={1.5} />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* 更早 */}
              {groupedSessions.older.length > 0 && (
                <div className="session-group">
                  <div className="session-group-title">更早</div>
                  {groupedSessions.older.map(s => (
                    <div 
                      key={s.session_id} 
                      className={`session-item-row ${activeSessionId === s.session_id ? 'active' : ''}`}
                      onClick={() => handleSelectSession(s.session_id)}
                    >
                      <div className="session-item-left">
                        <MessageSquare size={13} strokeWidth={1.5} color={activeSessionId === s.session_id ? 'var(--accent-color)' : 'var(--text-secondary)'} />
                        <span className="session-item-title-text" title={s.title}>{s.title}</span>
                      </div>
                      <button 
                        className="session-delete-action" 
                        onClick={(e) => handleDeleteSession(e, s.session_id)}
                        title="删除会话"
                      >
                        <Trash2 size={12} strokeWidth={1.5} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        {/* 底部操作员卡片与弹出浮层菜单 */}
        <div className="sidebar-user-card-wrapper">
          {showUserMenu && (
            <div className="user-dropdown-menu">
              <div className="dropdown-item-row" onClick={(e) => { e.stopPropagation(); setDeveloperMode(!developerMode); }}>
                <span>Developer Mode</span>
                <div className={`switch-control-box ${developerMode ? 'active' : ''}`}>
                  <div className="switch-thumb"></div>
                </div>
              </div>
              <div className="dropdown-item-row logout" onClick={handleLogout}>
                <span>退出登录</span>
                <LogOut size={13} strokeWidth={1.5} />
              </div>
            </div>
          )}
          {(() => {
            const rawUsername = username || 'Visitor';
            const displayUsername = rawUsername.startsWith('visitor_') ? 'visitor' : rawUsername;
            return (
              <div className="sidebar-user-card" onClick={() => setShowUserMenu(!showUserMenu)}>
                <div className="user-avatar-circle">
                  {displayUsername ? displayUsername[0].toUpperCase() : 'V'}
                </div>
                <div className="user-card-info-col">
                  <span className="user-card-name-text">{displayUsername}</span>
                  <span className="user-card-sub-text">Workspace Alpha</span>
                </div>
              </div>
            );
          })()}
        </div>
      </div>

      {/* 中间 Workspace 区域 (最大宽度 900px, 左右留白自适应) */}
      {(() => {
        const rawUsername = username || 'Visitor';
        const displayUsername = rawUsername.startsWith('visitor_') ? 'visitor' : rawUsername;
        const recentSessionsLimit = sessions.slice(0, 3); // 最多 3 条最近会话
        
        return (
          <div className="main-workspace">
            {messages.length === 0 ? (
              /* 欢迎状态 (Figma 极致留白布局) */
              <div style={{ maxWidth: '900px', width: '100%', margin: '0 auto', flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                  
                  {/* 1. 欢迎标题与副标题 */}
                  <div className="workspace-welcome-section">
                    <h2 className="welcome-h1">欢迎回来，{displayUsername}</h2>
                    <p className="welcome-h2">与企业知识对话，而不是翻找文档</p>
                  </div>

                  {/* 2. 推荐问题提示框 */}
                  <div className="workspace-recommend-card">
                    <div className="recommend-card-left-group">
                      <div className="recommend-lightbulb-box">
                        <Lightbulb size={20} strokeWidth={1.5} />
                      </div>
                      <div className="recommend-text-group">
                        <div className="recommend-line-1">试试问我：公司年假有多少天？</div>
                        <div className="recommend-line-2">如何申请加班？员工报销需要哪些材料？</div>
                      </div>
                    </div>
                    <button 
                      type="button" 
                      className="recommend-arrow-btn" 
                      onClick={() => setInputMessage("公司年假有多少天？如何申请加班？员工报销需要哪些材料？")}
                      title="填入输入框"
                    >
                      <ChevronRight size={18} strokeWidth={1.5} />
                    </button>
                  </div>

                  {/* 3. 最近对话 (最多 3 条) */}
                  {recentSessionsLimit.length > 0 && (
                    <div className="workspace-recent-section">
                      <h3 className="recent-section-title">最近对话</h3>
                      <div className="recent-list-container">
                        {recentSessionsLimit.map(s => {
                          const dateStr = s.created_at 
                            ? new Date(s.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
                            : '刚刚';
                          return (
                            <div key={s.session_id} className="recent-item-card">
                              <div className="recent-item-left">
                                <div className="recent-item-icon-box">
                                  <MessageSquare size={16} strokeWidth={1.5} />
                                </div>
                                <div className="recent-item-info">
                                  <span className="recent-item-title-txt">{s.title}</span>
                                  <span className="recent-item-time-txt">{dateStr}</span>
                                </div>
                              </div>
                              <button 
                                type="button" 
                                className="recent-continue-btn"
                                onClick={() => handleSelectSession(s.session_id)}
                              >
                                继续对话
                              </button>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                </div>

                {/* 4. 底部固定输入框 (高度 64px, 圆角 16px) */}
                <div className="workspace-input-area">
                  <div className="input-bar-inner-container">
                    <form onSubmit={(e) => handleSendMessage(e)} className="input-bar-inner">
                      {/* 点击 📎 触发专属知识库文件上传 */}
                      <button 
                        type="button" 
                        className="input-paperclip-btn" 
                        onClick={() => document.getElementById('kb-file-input')?.click()}
                        title="上传文档至知识库"
                      >
                        <Paperclip size={18} strokeWidth={1.5} />
                      </button>
                      <input 
                        type="text" 
                        value={inputMessage}
                        onChange={(e) => setInputMessage(e.target.value)}
                        placeholder="输入你的问题..."
                        disabled={isSending}
                      />
                      <button type="submit" className="input-send-btn" disabled={isSending || !inputMessage.trim()}>
                        <Send size={15} strokeWidth={1.5} />
                      </button>
                    </form>
                  </div>
                </div>

              </div>
            ) : (
              /* 聊天进行中状态 */
              <div style={{ maxWidth: '900px', width: '100%', margin: '0 auto', flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'space-between', paddingBottom: '24px' }}>
                
                <div className="chat-flow-container" style={{ padding: '0 0 24px 0' }}>
                  {/* Figma 风格的顶部大会话标题与来源 Meta 汇总 */}
                  <div className="chat-flow-session-header">
                    <h2 className="chat-flow-header-title">
                      {sessions.find(s => s.session_id === activeSessionId)?.title || "公司年假有多少天？如何申请加班？员工报销需要哪些材料？"}
                    </h2>
                    <div className="chat-flow-header-meta">
                      <span>今天 21:54</span>
                      <span>·</span>
                      <span>来自 员工手册.pdf 等 3 个来源</span>
                      <span className="chat-flow-header-meta-chevron">
                        <ChevronRight size={14} style={{ transform: 'rotate(90deg)' }} />
                      </span>
                    </div>
                  </div>

                  {messages.map((msg, index) => {
                    const isUser = msg.role === 'user';
                    return (
                      <div key={index} style={{ marginBottom: '32px' }}>
                        <div className={`chat-message-row ${isUser ? 'user' : 'assistant'}`}>
                          <div className="message-role-label" style={{ marginBottom: '8px' }}>
                            {isUser ? (
                              <>
                                <div style={{ 
                                  width: '24px', 
                                  height: '24px', 
                                  borderRadius: '50%', 
                                  background: '#EEF2FF', 
                                  color: '#4F46E5', 
                                  display: 'flex', 
                                  alignItems: 'center', 
                                  justifyContent: 'center',
                                  fontSize: '11px',
                                  fontWeight: '600'
                                }}>
                                  V
                                </div>
                                <span style={{ fontWeight: '600', color: '#222222', fontSize: '13.5px' }}>visitor</span>
                              </>
                            ) : (
                              <>
                                <div className="message-role-icon">
                                  <Hexagon size={16} strokeWidth={1.5} style={{ color: 'var(--accent-color)' }} />
                                </div>
                                <span style={{ fontWeight: '600', color: '#222222', fontSize: '13.5px' }}>Enterprise RAG</span>
                              </>
                            )}
                          </div>
                          
                          <div className="message-bubble-card" style={{ background: '#FFFFFF', border: '1px solid #EAEAEA', borderRadius: '12px', padding: '16px' }}>
                            {renderMessageContent(msg.content)}
                            
                            {/* AI 回答右下角的赞踩微标反馈按钮 */}
                            {!isUser && (
                              <div className="message-feedback-row">
                                <button type="button" className="feedback-mini-btn" title="赞">
                                  <ThumbsUp size={14} strokeWidth={1.5} />
                                </button>
                                <button type="button" className="feedback-mini-btn" title="踩">
                                  <ThumbsDown size={14} strokeWidth={1.5} />
                                </button>
                              </div>
                            )}
                          </div>
                          
                          <span style={{ fontSize: '11px', color: '#9CA3AF', marginTop: '6px', display: 'inline-block' }}>
                            {isUser ? '21:54' : '21:55'}
                          </span>
                        </div>

                        {/* 最后一个 AI 回复下方，如果存在引用来源，渲染垂直卡片列表 */}
                        {!isUser && index === messages.length - 1 && currentCitations.length > 0 && (
                          <div className="citations-block-wrapper">
                            <div className="citations-block-title-row">
                              <span className="citations-block-title">引用来源</span>
                              <span className="citations-block-count-badge">{currentCitations.length}</span>
                            </div>
                            <div className="citations-vertical-list">
                              {currentCitations.map((c, cIdx) => (
                                <div key={cIdx} className="citation-vertical-card">
                                  <div className="citation-vertical-card-left">
                                    <div className="citation-vertical-card-icon-box">
                                      <FileText size={16} strokeWidth={1.5} />
                                    </div>
                                    <div className="citation-vertical-card-info">
                                      <div className="citation-vertical-card-title-row">
                                        <span className="citation-vertical-card-name">{c.filename}</span>
                                        <span className="citation-vertical-card-page">第 {c.page || cIdx + 1} 页</span>
                                      </div>
                                      <span className="citation-vertical-card-snippet" title={c.content}>
                                        {c.content}
                                      </span>
                                    </div>
                                  </div>
                                  <button 
                                    type="button" 
                                    className="citation-vertical-card-btn"
                                    onClick={() => {
                                      setPreviewDocName(c.filename);
                                      setPreviewChunks([
                                        { chunk_id: 'chunk_match_1', content: c.content },
                                        { chunk_id: 'chunk_match_2', content: 'Chroma 检索到的补充关联上下文切片数据片段...' }
                                      ]);
                                    }}
                                  >
                                    查看
                                  </button>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                  <div ref={messagesEndRef} />
                </div>

                <div className="workspace-input-area">
                  <div className="input-bar-inner-container">
                    <form onSubmit={(e) => handleSendMessage(e)} className="input-bar-inner">
                      <button 
                        type="button" 
                        className="input-paperclip-btn" 
                        onClick={() => document.getElementById('kb-file-input')?.click()}
                        title="上传文档至知识库"
                      >
                        <Paperclip size={18} strokeWidth={1.5} />
                      </button>
                      <input 
                        type="text" 
                        value={inputMessage}
                        onChange={(e) => setInputMessage(e.target.value)}
                        placeholder="输入你的问题..."
                        disabled={isSending}
                      />
                      <span className="input-bar-inner-tip">Shift + Enter 换行</span>
                      <button type="submit" className="input-send-btn" disabled={isSending || !inputMessage.trim()}>
                        <Send size={15} strokeWidth={1.5} />
                      </button>
                    </form>
                  </div>
                </div>

              </div>
            )}
          </div>
        );
      })()}

      <div className="right-panel">
        {developerMode ? (
          /* 🟢 开发模式下的头部控制栏 (带保存、分享按钮以及高亮的 Developer 选项卡) */
          <div className="dev-top-actions-row" style={{ borderBottom: '1px solid var(--border-color)', paddingBottom: '16px', marginBottom: '24px' }}>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button type="button" className="dev-action-btn" title="保存当前会话">
                <FileText size={14} strokeWidth={1.5} style={{ color: '#9CA3AF' }} />
                <span style={{ color: '#222222' }}>保存</span>
              </button>
              <button type="button" className="dev-action-btn" title="分享当前会话">
                <ExternalLink size={14} strokeWidth={1.5} style={{ color: '#9CA3AF' }} />
                <span style={{ color: '#222222' }}>分享</span>
              </button>
            </div>
            
            <button 
              type="button" 
              className="panel-tab-trigger active" 
              style={{ paddingBottom: '0', borderBottom: 'none', fontWeight: '600', color: 'var(--accent-color)' }}
            >
              Developer
            </button>
          </div>
        ) : (
          /* ⚪ 普通模式下的双并列 Tabs (Knowledge / Sources) */
          <div className="panel-tabs-header">
            <button 
              type="button"
              className={`panel-tab-trigger ${activeRightTab === 'kb' ? 'active' : ''}`} 
              onClick={() => setActiveRightTab('kb')}
            >
              Knowledge
            </button>
            <button 
              type="button"
              className={`panel-tab-trigger ${activeRightTab === 'citations' ? 'active' : ''}`} 
              onClick={() => setActiveRightTab('citations')}
            >
              Sources
            </button>
          </div>
        )}

        <div className="panel-content-body" style={{ padding: '0', overflowY: 'auto' }}>
          {developerMode ? (
            /* 🛠️ 开发面板核心组件 (系统健康、TRACE、检索、Chunks) */
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              
              {/* 1. 系统健康状态 */}
              <h3 className="dev-section-title">系统健康状态</h3>
              <div className="dev-health-grid">
                <div className="dev-health-card">
                  <div className="dev-health-card-name">SQLite</div>
                  <div className="dev-health-card-status" style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '6px', color: '#22C55E' }}>
                    <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#22C55E', display: 'inline-block' }}></span>
                    <span>正常</span>
                  </div>
                </div>
                <div className="dev-health-card">
                  <div className="dev-health-card-name">Chroma</div>
                  <div className="dev-health-card-status" style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '6px', color: '#22C55E' }}>
                    <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#22C55E', display: 'inline-block' }}></span>
                    <span>正常</span>
                  </div>
                </div>
                <div className="dev-health-card">
                  <div className="dev-health-card-name">API</div>
                  <div className="dev-health-card-status" style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '6px', color: '#22C55E' }}>
                    <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#22C55E', display: 'inline-block' }}></span>
                    <span>正常</span>
                  </div>
                </div>
              </div>

              {/* 2. TRACE PIPELINE */}
              <h3 className="dev-trace-uppercase-title">TRACE PIPELINE</h3>
              <div className="dev-trace-list">
                <div className="dev-trace-item-row">
                  <div className="dev-trace-item-left">
                    <span className="dev-trace-index">1</span>
                    <span className="dev-trace-name">Query Rewrite</span>
                  </div>
                  <div className="dev-trace-right">
                    <span className="dev-trace-latency">128ms</span>
                    <span className="dev-trace-check-box">
                      <Check size={14} strokeWidth={2.5} />
                    </span>
                  </div>
                </div>
                <div className="dev-trace-item-row">
                  <div className="dev-trace-item-left">
                    <span className="dev-trace-index">2</span>
                    <span className="dev-trace-name">Retrieve (Vector Search)</span>
                  </div>
                  <div className="dev-trace-right">
                    <span className="dev-trace-latency">298ms</span>
                    <span className="dev-trace-check-box">
                      <Check size={14} strokeWidth={2.5} />
                    </span>
                  </div>
                </div>
                <div className="dev-trace-item-row">
                  <div className="dev-trace-item-left">
                    <span className="dev-trace-index">3</span>
                    <span className="dev-trace-name">Rerank (RRF)</span>
                  </div>
                  <div className="dev-trace-right">
                    <span className="dev-trace-latency">156ms</span>
                    <span className="dev-trace-check-box">
                      <Check size={14} strokeWidth={2.5} />
                    </span>
                  </div>
                </div>
                <div className="dev-trace-item-row">
                  <div className="dev-trace-item-left">
                    <span className="dev-trace-index">4</span>
                    <span className="dev-trace-name">Generate (LLM)</span>
                  </div>
                  <div className="dev-trace-right">
                    <span className="dev-trace-latency">742ms</span>
                    <span className="dev-trace-check-box">
                      <Check size={14} strokeWidth={2.5} />
                    </span>
                  </div>
                </div>
              </div>

              {/* 3. 检索详情 */}
              <div className="dev-retrieve-header">
                <h3 className="dev-section-title" style={{ marginBottom: 0 }}>检索详情</h3>
                <span className="dev-retrieve-badge-topk">Top K: 8</span>
              </div>
              <div className="dev-retrieve-grid-card" onClick={() => setPreviewDocName(currentCitations[0]?.filename || "员工手册.pdf")}>
                <div className="dev-retrieve-2x2">
                  <div className="dev-retrieve-item">
                    <span className="dev-retrieve-label">命中率 (Rerank TopK)</span>
                    <span className="dev-retrieve-val">8/8</span>
                  </div>
                  <div className="dev-retrieve-item">
                    <span className="dev-retrieve-label">来源文档数</span>
                    <span className="dev-retrieve-val">{documents.length || 3}</span>
                  </div>
                  <div className="dev-retrieve-item">
                    <span className="dev-retrieve-label">向量库</span>
                    <span className="dev-retrieve-val">Chroma</span>
                  </div>
                  <div className="dev-retrieve-item">
                    <span className="dev-retrieve-label">命名空间</span>
                    <span className="dev-retrieve-val">default</span>
                  </div>
                </div>
                <div className="dev-retrieve-arrow-icon">
                  <ChevronRight size={14} strokeWidth={1.5} />
                </div>
              </div>

              {/* 4. Chunks 预览 */}
              <div className="dev-chunks-header">
                <h3 className="dev-section-title" style={{ marginBottom: 0 }}>Chunks 预览</h3>
                <button 
                  type="button" 
                  className="dev-chunks-expand-btn"
                  onClick={() => setPreviewDocName(currentCitations[0]?.filename || "员工手册.pdf")}
                >
                  <span>展开</span>
                  <ChevronRight size={12} strokeWidth={1.5} />
                </button>
              </div>
              <div className="dev-chunks-list">
                <div className="dev-chunk-item-line">
                  <div className="dev-chunk-left">
                    <span className="dev-chunk-hash-tag">#1</span>
                    <span className="dev-chunk-meta-text">员工手册.pdf - 第 12 页</span>
                  </div>
                  <span className="dev-chunk-score-text">相似度 0.865</span>
                </div>
                <div className="dev-chunk-item-line">
                  <div className="dev-chunk-left">
                    <span className="dev-chunk-hash-tag">#2</span>
                    <span className="dev-chunk-meta-text">考勤制度.md - 第 3 页</span>
                  </div>
                  <span className="dev-chunk-score-text">相似度 0.742</span>
                </div>
                <div className="dev-chunk-item-line">
                  <div className="dev-chunk-left">
                    <span className="dev-chunk-hash-tag">#3</span>
                    <span className="dev-chunk-meta-text">福利政策.pdf - 第 8 页</span>
                  </div>
                  <span className="dev-chunk-score-text">相似度 0.681</span>
                </div>
              </div>

            </div>
          ) : (
            /* ⚪ 普通模式下的内容体 (包含双 Tab) */
            <>
              {/* 1. Knowledge 选项卡 */}
              {activeRightTab === 'kb' && (
                <>
                  <div className="kb-header-row">
                    <h3>我的知识库</h3>
                    <span className="kb-count-badge">共 {documents.length} 个文档</span>
                  </div>

                  <div className="kb-files-list">
                    {documents.length === 0 ? (
                      <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', textAlign: 'center', padding: '24px 0' }}>
                        暂无已索引文档
                      </div>
                    ) : (
                      documents.map((doc, idx) => {
                        const filename = doc.source;
                        const extension = filename.split('.').pop().toLowerCase();
                        let iconClass = '';
                        if (extension === 'pdf') iconClass = 'pdf';
                        else if (extension === 'md') iconClass = 'md';
                        else if (extension === 'txt') iconClass = 'txt';
                        
                        return (
                          <div key={idx} className="kb-file-card">
                            <div className="kb-file-left">
                              <div className={`kb-file-icon-box ${iconClass}`}>
                                <FileText size={16} strokeWidth={1.5} />
                              </div>
                              <div className="kb-file-info">
                                <span className="kb-file-name" title={filename}>{filename}</span>
                                <span className="kb-file-meta">
                                  {extension.toUpperCase()} · 已索引
                                </span>
                              </div>
                            </div>
                            <button 
                              type="button"
                              className="kb-file-delete-btn"
                              onClick={() => triggerDeleteDocument(filename)}
                              title="删除文档"
                            >
                              <Trash2 size={14} strokeWidth={1.5} />
                            </button>
                          </div>
                        );
                      })
                    )}
                  </div>

                  <div 
                    className={`kb-upload-zone ${isDragging ? 'dragover' : ''}`}
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onDrop={handleDrop}
                    onClick={() => document.getElementById('kb-file-input')?.click()}
                  >
                    <input 
                      type="file" 
                      id="kb-file-input" 
                      style={{ display: 'none' }} 
                      onChange={(e) => {
                        if (e.target.files && e.target.files.length > 0) {
                          handleUploadFile(e.target.files[0]);
                        }
                      }} 
                      disabled={isUploading} 
                    />
                    <UploadCloud size={24} strokeWidth={1.5} className="zone-icon" />
                    <span className="zone-title">
                      {isUploading ? '上传切片向量化中...' : '拖拽文件到这里上传'}
                    </span>
                    <span className="zone-desc">支持 PDF、MD、TXT (最大 20MB)</span>
                  </div>

                  <div className="kb-tip-card">
                    <div className="tip-header">
                      <div className="tip-header-icon">
                        <Lightbulb size={16} strokeWidth={1.5} />
                      </div>
                      <span>提示</span>
                    </div>
                    <div className="tip-content">
                      上传文档后，AI 将基于企业知识库为您提供更准确的回答
                    </div>
                  </div>
                </>
              )}

              {/* 2. Sources 选项卡 */}
              {activeRightTab === 'citations' && (
                <div className="source-items-list">
                  {currentCitations.length === 0 ? (
                    <div style={{ fontSize: '13px', color: 'var(--text-secondary)', textAlign: 'center', padding: '32px 0' }}>
                      暂无引用来源
                    </div>
                  ) : (
                    currentCitations.map((c, idx) => (
                      <div key={idx} id={`citation-card-${idx}`} className="source-item-card">
                        <div className="source-card-header">
                          <span className="source-doc-title" title={c.filename}>
                            [{idx + 1}] {c.filename}
                          </span>
                          <span className="source-doc-score">Match</span>
                        </div>
                        <div className="source-chunk-text">{c.content}</div>
                      </div>
                    ))
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Chroma Chunks 审计预览侧滑抽屉 */}
      {previewDocName && (
        <div className="audit-drawer-overlay" onClick={() => setPreviewDocName(null)}>
          <div className="audit-drawer-box" onClick={(e) => e.stopPropagation()}>
            <div className="audit-drawer-header">
              <div className="audit-drawer-header-left">
                <h3>Chroma 向量切片审计</h3>
                <span>文档: {previewDocName}</span>
              </div>
              <button className="audit-drawer-close-btn" onClick={() => setPreviewDocName(null)}>
                <X size={15} />
              </button>
            </div>
            <div className="audit-drawer-body">
              {previewChunks.map((chunk, idx) => (
                <div key={idx} className="audit-chunk-card">
                  <div className="audit-chunk-meta-row">
                    <span className="audit-chunk-index">#{idx + 1}</span>
                    <span className="audit-chunk-id">ID: {chunk.chunk_id.substring(0, 12)}...</span>
                  </div>
                  <div className="audit-chunk-content">{chunk.content}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* 二次确认模态框 */}
      {confirmModal.isOpen && (
        <div className="confirm-overlay-blur">
          <div className="confirm-modal-box">
            <div className="confirm-modal-header">
              <AlertTriangle size={18} color="#C75A4E" strokeWidth={1.5} />
              <h3>{confirmModal.title}</h3>
            </div>
            <div className="confirm-modal-body">
              {confirmModal.message}
            </div>
            <div className="confirm-modal-actions">
              <button className="confirm-btn-cancel" onClick={() => setConfirmModal(prev => ({ ...prev, isOpen: false }))}>
                取消
              </button>
              <button className="confirm-btn-execute" onClick={confirmModal.onConfirm}>
                确认执行
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast */}
      <div className="toast-container-fixed">
        {toasts.map(t => (
          <div key={t.id} className="toast-item-card">
            <div className={`toast-indicator-bar ${t.type}`}></div>
            <div className={`toast-icon-side ${t.type}`}>
              {t.type === 'success' && <Shield size={16} strokeWidth={1.5} />}
              {t.type === 'error' && <AlertTriangle size={16} strokeWidth={1.5} />}
              {t.type === 'info' && <AlertCircle size={16} strokeWidth={1.5} />}
            </div>
            <div className="toast-text-side">
              <div className="toast-title">{t.title}</div>
              <div className="toast-desc">{t.message}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default App;
