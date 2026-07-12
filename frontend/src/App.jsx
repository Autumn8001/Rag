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

const DEFAULT_API_BASE = `${window.location.protocol}//${window.location.hostname}:8010/api/v1`;
const API_BASE = (import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE).replace(/\/$/, '');
const PAGE_SIZE = 10;
const VISITOR_SESSION_TTL_MINUTES = 120;
const DEFAULT_HEALTH_COMPONENTS = [
  { key: 'database', name: 'PostgreSQL', status: 'unknown' },
  { key: 'vectorstore', name: 'Chroma', status: 'unknown' },
  { key: 'api', name: 'API', status: 'unknown' }
];

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
      { name: "PostgreSQLBM25Retrieval", type: "retriever", status: "success" },
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
  const [sessionExpiresAt, setSessionExpiresAt] = useState(sessionStorage.getItem('session_expires_at') || '');
  const [visitorSessionStartedAt, setVisitorSessionStartedAt] = useState(sessionStorage.getItem('visitor_session_started_at') || '');
  const [isTemporaryVisitor, setIsTemporaryVisitor] = useState(sessionStorage.getItem('is_temporary') === 'true');
  const [nowTick, setNowTick] = useState(Date.now());
  const [isRegister, setIsRegister] = useState(false);
  
  // 登录/注册表单
  const [authUsername, setAuthUsername] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [usernameError, setUsernameError] = useState('');
  const [authError, setAuthError] = useState('');
  const [authSuccess, setAuthSuccess] = useState('');

  // --- 控制台布局状态与自定义拖拽拉伸 ---
  const [sidebarWidth, setSidebarWidth] = useState(260); // 默认 260px
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [rightPanelWidth, setRightPanelWidth] = useState(360); // 默认 360px
  const [rightPanelCollapsed, setRightPanelCollapsed] = useState(false);
  const [activeRightTab, setActiveRightTab] = useState('kb'); // 'citations' | 'kb'

  // --- Wiki 工作台与检索路由状态 ---
  const [activeTab, setActiveTab] = useState('chat'); // 'chat' | 'wiki'
  const [searchMode, setSearchMode] = useState('RAG_ONLY'); // 'RAG_ONLY' | 'WIKI_ONLY'
  const [wikiDocs, setWikiDocs] = useState([]); // 已编译的 Wiki 文档列表
  const [selectedWikiDocId, setSelectedWikiDocId] = useState(null); // 当前选中的 Wiki 文档 ID
  const [selectedWiki, setSelectedWiki] = useState(null); // 当前选中的 Wiki 编译结构化详情对象
  const [isLoadingWiki, setIsLoadingWiki] = useState(false); // 加载 Wiki 状态

  // 获取已编译的 Wiki 列表
  const fetchWikis = async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/wiki/list`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (res.ok) {
        setWikiDocs(data.wikis || []);
      }
    } catch (err) {
      console.error('获取Wiki列表失败', err);
    }
  };

  // 获取单个 Wiki 详情
  const fetchWikiDetail = async (documentId) => {
    if (!documentId) return;
    setIsLoadingWiki(true);
    try {
      const res = await fetch(`${API_BASE}/wiki/detail?document_id=${documentId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (res.ok) {
        setSelectedWiki(data.wiki || null);
      } else {
        showToast('获取Wiki详情失败', data.detail || '无法获取Wiki内容', 'error');
      }
    } catch (err) {
      console.error('获取Wiki详情失败', err);
      showToast('获取Wiki详情失败', '网络请求错误', 'error');
    } finally {
      setIsLoadingWiki(false);
    }
  };

  // 左侧边栏拖拽拉伸
  const handleLeftResizeMouseDown = (e) => {
    e.preventDefault();
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';
    
    const handleMouseMove = (moveEvent) => {
      const newWidth = moveEvent.clientX;
      if (newWidth >= 180 && newWidth <= 400) {
        setSidebarWidth(newWidth);
      }
    };
    
    const handleMouseUp = () => {
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
    
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  };

  // 右侧面板拖拽拉伸
  const handleRightResizeMouseDown = (e) => {
    e.preventDefault();
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';
    
    const handleMouseMove = (moveEvent) => {
      const newWidth = window.innerWidth - moveEvent.clientX;
      if (newWidth >= 280 && newWidth <= 600) {
        setRightPanelWidth(newWidth);
      }
    };
    
    const handleMouseUp = () => {
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
    
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  };

  // --- RAG 业务状态 ---
  const [sessions, setSessions] = useState([]);
  const [searchQuery, setSearchQuery] = useState(''); 
  const [activeSessionId, setActiveSessionId] = useState('');
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [currentCitations, setCurrentCitations] = useState([]); 
  const [currentStep, setCurrentStep] = useState(-1);
  const [isCitationsExpanded, setIsCitationsExpanded] = useState(false);

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
  const [healthComponents, setHealthComponents] = useState(DEFAULT_HEALTH_COMPONENTS);
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
  const activeChatAbortRef = useRef(null);
  const isMountedRef = useRef(true);

  useEffect(() => {
    const timer = setInterval(() => {
      setNowTick(Date.now());
    }, 30000);
    return () => {
      clearInterval(timer);
      isMountedRef.current = false;
      activeChatAbortRef.current?.abort?.();
    };
  }, []);

  const formatDurationLabel = (milliseconds) => {
    if (!milliseconds || milliseconds <= 0) return '0 分钟';
    const totalMinutes = Math.max(1, Math.floor(milliseconds / 60000));
    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;
    if (hours <= 0) return `${minutes} 分钟`;
    if (minutes === 0) return `${hours} 小时`;
    return `${hours} 小时 ${minutes} 分钟`;
  };

  const parseUtcTimestampMs = (value) => {
    if (!value) return NaN;
    if (value instanceof Date) return value.getTime();
    if (typeof value !== 'string') return NaN;
    const normalized = value.includes('T') && !/[zZ]|[+-]\d{2}:?\d{2}$/.test(value)
      ? `${value}Z`
      : value;
    return new Date(normalized).getTime();
  };
  const updateVisitorLifecycleCache = (data) => {
    if (!data) return;
    if (typeof data.is_temporary === 'boolean') {
      setIsTemporaryVisitor(data.is_temporary);
      sessionStorage.setItem('is_temporary', String(data.is_temporary));
    }
    if (data.expires_at) {
      setSessionExpiresAt(data.expires_at);
      sessionStorage.setItem('session_expires_at', data.expires_at);
    }

    const startedAt = data.created_at || data.last_active_at || '';
    if (startedAt) {
      setVisitorSessionStartedAt(startedAt);
      sessionStorage.setItem('visitor_session_started_at', startedAt);
    }
  };

  const isVisitorSession = () => {
    const rawUsername = username || sessionStorage.getItem('username') || '';
    return Boolean(
      isTemporaryVisitor ||
      rawUsername.startsWith('visitor_') ||
      sessionExpiresAt ||
      visitorSessionStartedAt
    );
  };

  const getVisitorRemainingMs = () => {
    const expiresTs = parseUtcTimestampMs(sessionExpiresAt);
    if (Number.isFinite(expiresTs)) {
      return Math.max(0, expiresTs - nowTick);
    }

    const startedTs = parseUtcTimestampMs(visitorSessionStartedAt);
    if (Number.isFinite(startedTs)) {
      const fallbackExpiresTs = startedTs + VISITOR_SESSION_TTL_MINUTES * 60 * 1000;
      return Math.max(0, fallbackExpiresTs - nowTick);
    }
    return 0;
  };

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
        updateVisitorLifecycleCache(data);
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
        updateVisitorLifecycleCache(data);
        showToast('访客免密登录成功', '已为您随机生成独立租户空间，数据将在会话过期后自动清理。', 'success');
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
    activeChatAbortRef.current?.abort?.();
    setToken('');
    setUsername('');
    setTenantId('');
    setSessionExpiresAt('');
    setVisitorSessionStartedAt('');
    setIsTemporaryVisitor(false);
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

  const syncCurrentUserSession = async (authToken) => {
    if (!authToken) return;
    try {
      const res = await fetch(`${API_BASE}/auth/me`, {
        headers: { 'Authorization': `Bearer ${authToken}` }
      });
      if (!res.ok) return;
      const data = await res.json();
      if (!isMountedRef.current) return;

      if (data?.username) {
        setUsername(data.username);
        sessionStorage.setItem('username', data.username);
      }
      if (data?.tenant_id) {
        setTenantId(data.tenant_id);
        sessionStorage.setItem('tenant_id', data.tenant_id);
      }
      if (typeof data?.is_temporary === 'boolean') {
        setIsTemporaryVisitor(data.is_temporary);
      }
      updateVisitorLifecycleCache(data);
    } catch (err) {
      // ignore sync failure and keep local session state
    }
  };

  const getCitationFilename = (citation) => citation?.filename || citation?.source || '';
  const getCitationScore = (citation) => citation?.rrf_score || citation?.score || citation?.similarity || null;
  const latestTrace = traces[0] || null;
  const traceStages = latestTrace?.child_stages || [];
  const firstPreviewDocName = getCitationFilename(currentCitations[0]) || documents[0]?.source || null;
  const chunkPreviewRows = currentCitations.length > 0
    ? currentCitations.slice(0, 4).map((citation, index) => ({
        id: index + 1,
        filename: getCitationFilename(citation),
        page: citation.page,
        score: getCitationScore(citation),
      }))
    : documents.slice(0, 4).map((document, index) => ({
        id: index + 1,
        filename: document.source,
        page: null,
        score: null,
      }));
  const retrievalHitCount = currentCitations.length;

  const openChunkPreview = (filename = firstPreviewDocName) => {
    if (!filename) {
      showToast('暂无切片', '请先上传文档或执行一次带引用的问答。', 'info');
      return;
    }
    setPreviewPage(1);
    setPreviewDocName(filename);
  };

  const handleSaveConversation = () => {
    if (!activeSessionId || messages.length === 0) {
      showToast('暂无可保存会话', '请先开始一段对话。', 'info');
      return;
    }
    fetchSessions();
    showToast('已保存', '当前会话已由后端历史记录持久化。', 'success');
  };

  // --- 初始化与健康探针 ---
  useEffect(() => {
    if (token) {
      fetchDocuments(kbPage);
      fetchSessions();
      fetchWikis();
      checkHealthStatus();
      syncCurrentUserSession(token);
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
      if (res.ok && (data.status === 'ok' || data.status === 'degraded')) {
        setHealthStatus('healthy');
        if (data.components) {
          setHealthComponents(
            DEFAULT_HEALTH_COMPONENTS.map((component) => {
              const source = data.components[component.key];
              return source
                ? { ...component, name: source.name || component.name, status: source.status || 'unknown' }
                : component;
            })
          );
        }
      } else {
        setHealthStatus('unhealthy');
        setHealthComponents(DEFAULT_HEALTH_COMPONENTS.map((component) => ({ ...component, status: 'error' })));
      }
    } catch (e) {
      setHealthStatus('unhealthy');
      setHealthComponents(DEFAULT_HEALTH_COMPONENTS.map((component) => ({ ...component, status: 'error' })));
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
        setTraces(resTraces);
      } else {
        setTraces([]);
      }
    } catch (err) {
      setTraces([]);
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
    activeChatAbortRef.current?.abort?.();
    activeChatAbortRef.current = null;
    setIsSending(false);
    setCurrentStep(-1);
    setActiveSessionId(sessionId);
    setMessages([]);
    setCurrentCitations([]);
    setIsCitationsExpanded(false);
    try {
      const res = await fetch(`${API_BASE}/history/${sessionId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
        if (res.ok) {
          const rawHistoryMsgs = data.data || [];
          const assistantMsgs = rawHistoryMsgs.filter(m => m.role === 'assistant');
          if (assistantMsgs.length > 0) {
            const lastMsg = assistantMsgs[assistantMsgs.length - 1];
            const parsed = parseCitationsFromContent(lastMsg.content);
            setCurrentCitations(parsed.citations);
          }
          
          const cleanHistoryMsgs = rawHistoryMsgs.map(m => {
            if (m.role === 'assistant') {
              const parsed = parseCitationsFromContent(m.content);
              return { ...m, content: parsed.cleanContent };
            }
            return m;
          });
          setMessages(cleanHistoryMsgs);
        }
    } catch (err) {
      console.error('获取会话记录失败', err);
    }
  };

  // 15. 新建会话
  const handleCreateNewChat = () => {
    activeChatAbortRef.current?.abort?.();
    activeChatAbortRef.current = null;
    setIsSending(false);
    setCurrentStep(-1);
    setActiveSessionId('');
    setMessages([]);
    setIsCitationsExpanded(false);
    setCurrentCitations([]);
    fetchSessions();
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
        fetchWikis();
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

    activeChatAbortRef.current?.abort?.();
    const abortController = new AbortController();
    activeChatAbortRef.current = abortController;
    const isCurrentChatRequest = () => activeChatAbortRef.current === abortController;

    const userText = textToSend;
    setInputMessage('');
    setIsSending(true);
    setCurrentCitations([]); 
    setIsCitationsExpanded(false); 

    const tempSessionId = activeSessionId || `session_${Date.now()}`;
    if (!activeSessionId) {
      setActiveSessionId(tempSessionId);
    }

    setMessages(prev => [...prev, { role: 'user', content: userText }]);
    setMessages(prev => [...prev, { role: 'assistant', content: '' }]);

    // 初始化 Thinking Pipeline 状态与计时器
    setCurrentStep(0);
    let stepStartTimeVal = Date.now();
    let parsedBackendStageVal = -1;
    let hasBackendEventsVal = false;
    let hasRealTextReceivedVal = false;

    const intervalId = setInterval(() => {
      const now = Date.now();
      const elapsed = now - stepStartTimeVal;

      setCurrentStep(curr => {
        if (curr === -1 || curr >= 5) {
          clearInterval(intervalId);
          return curr;
        }

        if (curr < 4) {
          if (hasBackendEventsVal) {
            const nextStage = parsedBackendStageVal;
            if (nextStage > curr && elapsed >= 350) {
              stepStartTimeVal = now;
              return curr + 1;
            }
          } else {
            if (elapsed >= 400) {
              stepStartTimeVal = now;
              return curr + 1;
            }
          }
        } else if (curr === 4) {
          const isReady = hasBackendEventsVal
            ? (parsedBackendStageVal === 5 && elapsed >= 350)
            : (elapsed >= 400 && hasRealTextReceivedVal);
          if (isReady) {
            clearInterval(intervalId);
            return 5;
          }
        }
        return curr;
      });
    }, 50);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        signal: abortController.signal,
        body: JSON.stringify({ 
          question: userText, 
          session_id: tempSessionId,
          search_mode: searchMode
        })
      });

      if (!res.ok) {
        const errorData = await res.json();
        if (isCurrentChatRequest()) {
          setMessages(prev => {
            const next = [...prev];
            next[next.length - 1] = { role: 'assistant', content: `[错误] ${errorData.detail || '服务不可用'}` };
            return next;
          });
          clearInterval(intervalId);
          setCurrentStep(5);
          setIsSending(false);
        }
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let assistantText = '';

      while (true) {
        if (abortController.signal.aborted) {
          break;
        }
        const { value, done } = await reader.read();
        if (done) break;

        const textChunk = decoder.decode(value, { stream: true });
        assistantText += textChunk;

        // 检测后端步骤事件
        if (assistantText.includes('__STAGE__:UNDERSTANDING')) {
          hasBackendEventsVal = true;
          parsedBackendStageVal = Math.max(parsedBackendStageVal, 0);
        }
        if (assistantText.includes('__STAGE__:REWRITE')) {
          hasBackendEventsVal = true;
          parsedBackendStageVal = Math.max(parsedBackendStageVal, 1);
        }
        if (assistantText.includes('__STAGE__:RETRIEVING')) {
          hasBackendEventsVal = true;
          parsedBackendStageVal = Math.max(parsedBackendStageVal, 2);
        }
        if (assistantText.includes('__STAGE__:RERANKING')) {
          hasBackendEventsVal = true;
          parsedBackendStageVal = Math.max(parsedBackendStageVal, 3);
        }
        if (assistantText.includes('__STAGE__:GENERATING')) {
          hasBackendEventsVal = true;
          parsedBackendStageVal = Math.max(parsedBackendStageVal, 4);
        }

        // 清洗步骤标记
        const cleanCtx = assistantText.replace(/__STAGE__:[A-Z_]+\n?/g, '');

        // 判断是否收到了真实的流式输出内容
        const checkContent = cleanCtx.replace(/__METADATA_START__[\s\S]*/, '').trim();
        if (checkContent.length > 0) {
          hasRealTextReceivedVal = true;
          if (hasBackendEventsVal) {
            parsedBackendStageVal = 5;
          }
          setCurrentStep(5);
        }

        let displayCtx = cleanCtx;
        let metaJsonStr = '';
        const markerIdx = cleanCtx.indexOf('__METADATA_START__');
        if (markerIdx !== -1) {
          displayCtx = cleanCtx.substring(0, markerIdx).trim();
          const endMarkerIdx = cleanCtx.indexOf('__METADATA_END__');
          if (endMarkerIdx !== -1) {
            metaJsonStr = cleanCtx.substring(markerIdx + '__METADATA_START__'.length, endMarkerIdx).trim();
          } else {
            metaJsonStr = cleanCtx.substring(markerIdx + '__METADATA_START__'.length).trim();
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
      
      const finalCleanText = assistantText.replace(/__STAGE__:[A-Z_]+\n?/g, '');
      const finalMarkerIdx = finalCleanText.indexOf('__METADATA_START__');
      if (finalMarkerIdx !== -1) {
        let finalMetaStr = '';
        const finalEndMarkerIdx = finalCleanText.indexOf('__METADATA_END__');
        if (finalEndMarkerIdx !== -1) {
          finalMetaStr = finalCleanText.substring(finalMarkerIdx + '__METADATA_START__'.length, finalEndMarkerIdx).trim();
        } else {
          finalMetaStr = finalCleanText.substring(finalMarkerIdx + '__METADATA_START__'.length).trim();
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

      if (!abortController.signal.aborted && isMountedRef.current) {
        await fetchSessions();
        window.setTimeout(() => {
          if (isMountedRef.current) {
            fetchSessions();
          }
        }, 350);
      }
    } catch (err) {
      if (err?.name === 'AbortError') {
        return;
      }
      if (isCurrentChatRequest()) {
        setMessages(prev => {
          const next = [...prev];
          next[next.length - 1] = { role: 'assistant', content: `[错误] 无法建立连接，请确认本地服务已拉起。` };
          return next;
        });
      }
    } finally {
      clearInterval(intervalId);
      const wasCurrentChatRequest = isCurrentChatRequest();
      if (wasCurrentChatRequest) {
        activeChatAbortRef.current = null;
      }
      if (isMountedRef.current && wasCurrentChatRequest) {
        setCurrentStep(5);
        setIsSending(false);
      }
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

  // 引用文字点击高亮滚动与 Markdown 块级解析器 (带自动元数据清洗)
  const renderMessageContent = (rawContent) => {
    if (!rawContent) return '';

    // 剔除 __METADATA_START__ 及其之后的内容以及 stage 步骤标签，防止在气泡中直出
    let content = rawContent;
    const markerIdx = rawContent.indexOf('__METADATA_START__');
    if (markerIdx !== -1) {
      content = rawContent.substring(0, markerIdx);
    }
    content = content.replace(/__STAGE__:[A-Z_]+\n?/g, '').trim();

    if (!content) return '';

    // 解析单行内的加粗与引文超链接
    const renderInlineText = (text) => {
      const citationRegex = /\[(\d+)\]/g;
      const parts = text.split(citationRegex);
      return parts.map((part, idx) => {
        if (idx % 2 === 1) {
          const num = parseInt(part, 10);
          return (
            <button 
              key={`citation-${idx}`}
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
        
        // 解析 **加粗**
        const boldRegex = /\*\*([^*]+)\*\*/g;
        const boldParts = part.split(boldRegex);
        if (boldParts.length > 1) {
          return boldParts.map((subPart, subIdx) => {
            if (subIdx % 2 === 1) {
              return <strong key={`bold-${subIdx}`}>{subPart}</strong>;
            }
            return subPart;
          });
        }
        return part;
      });
    };

    // 按换行符拆分块级元素
    const lines = content.split('\n');
    const elements = [];
    let listItems = [];
    let listType = null; // 'ul' or 'ol'

    const pushListIfExist = () => {
      if (listItems.length > 0) {
        const key = `list-${elements.length}`;
        if (listType === 'ol') {
          elements.push(
            <ol key={key} style={{ margin: '8px 0', paddingLeft: '20px', listStyleType: 'decimal' }}>
              {listItems}
            </ol>
          );
        } else {
          elements.push(
            <ul key={key} style={{ margin: '8px 0', paddingLeft: '20px', listStyleType: 'disc' }}>
              {listItems}
            </ul>
          );
        }
        listItems = [];
        listType = null;
      }
    };

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const trimmed = line.trim();

      // 标题语法 (支持 1 到 6 级标头)
      const headingMatch = trimmed.match(/^(#{1,6})\s+(.*)$/);
      if (headingMatch) {
        pushListIfExist();
        const level = headingMatch[1].length;
        const text = headingMatch[2];
        const headingStyles = {
          1: { fontSize: '17px', margin: '14px 0 8px', fontWeight: '700' },
          2: { fontSize: '15px', margin: '12px 0 6px', fontWeight: '600' },
          3: { fontSize: '14px', margin: '10px 0 4px', fontWeight: '600' },
          4: { fontSize: '13px', margin: '8px 0 4px', fontWeight: '600' },
          5: { fontSize: '12px', margin: '6px 0 2px', fontWeight: '600' },
          6: { fontSize: '11px', margin: '6px 0 2px', fontWeight: '600' }
        };
        const HeadingTag = `h${Math.min(level + 1, 6)}`;
        elements.push(
          <HeadingTag key={i} style={{ ...headingStyles[level], color: '#111827' }}>
            {renderInlineText(text)}
          </HeadingTag>
        );
      } 
      // 无序列表
      else if (/^[\*\-\+]\s+/.test(trimmed)) {
        if (listType !== 'ul') {
          pushListIfExist();
          listType = 'ul';
        }
        const text = trimmed.replace(/^[\*\-\+]\s+/, '');
        listItems.push(<li key={`li-${i}`} style={{ marginBottom: '4px', lineHeight: '1.6' }}>{renderInlineText(text)}</li>);
      }
      // 有序列表
      else if (/^\d+\.\s+/.test(trimmed)) {
        if (listType !== 'ol') {
          pushListIfExist();
          listType = 'ol';
        }
        const text = trimmed.replace(/^\d+\.\s+/, '');
        listItems.push(<li key={`li-${i}`} style={{ marginBottom: '4px', lineHeight: '1.6' }}>{renderInlineText(text)}</li>);
      }
      // 空白行隔断
      else if (trimmed === '') {
        pushListIfExist();
      }
      // 普通段落
      else {
        pushListIfExist();
        elements.push(<p key={i} style={{ margin: '6px 0', lineHeight: '1.6' }}>{renderInlineText(line)}</p>);
      }
    }
    pushListIfExist();

    return <div className="markdown-rendered-content">{elements}</div>;
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
      <input
        type="file"
        id="kb-file-input"
        style={{ display: 'none' }}
        onChange={(e) => {
          if (e.target.files && e.target.files.length > 0) {
            handleUploadFile(e.target.files[0]);
            e.target.value = '';
          }
        }}
        disabled={isUploading}
      />
      
      {/* 🔑 STEP 2: 重构左侧 Sidebar (按大厂规范进行 280px 设计定位) */}
      <div 
        className={`sidebar-panel ${sidebarCollapsed ? 'collapsed' : ''}`}
        style={{ width: sidebarCollapsed ? 0 : `${sidebarWidth}px` }}
      >
        
        {/* Logo 区域 (⬢ Hexagon + H1 + Caption) */}
        <div className="sidebar-header">
          <div className="sidebar-header-logo-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Hexagon size={20} strokeWidth={1.5} className="sidebar-logo-icon" />
              <h1>Enterprise RAG</h1>
            </div>
            <button 
              type="button" 
              className="panel-collapse-btn" 
              onClick={() => setSidebarCollapsed(true)} 
              title="收起侧边栏"
              style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: '4px', display: 'flex', alignItems: 'center', color: '#9CA3AF' }}
            >
              <ChevronLeft size={16} strokeWidth={1.5} />
            </button>
          </div>
          <div className="sidebar-subtitle">AI Knowledge Workspace</div>
        </div>

        {/* 工作台功能模式切换 Tabs */}
        <div className="sidebar-mode-tabs" style={{ display: 'flex', gap: '4px', padding: '12px 16px 8px', borderBottom: '1px solid var(--border-color, #E5E7EB)' }}>
          <button 
            type="button"
            onClick={() => setActiveTab('chat')}
            style={{
              flex: 1,
              padding: '6px 12px',
              fontSize: '12px',
              fontWeight: '600',
              borderRadius: '6px',
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
              background: activeTab === 'chat' ? '#EEF2FF' : 'transparent',
              color: activeTab === 'chat' ? '#4F46E5' : '#4B5563',
              transition: 'all 0.2s'
            }}
          >
            <MessageSquare size={13} />
            智能问答
          </button>
          <button 
            type="button"
            onClick={() => setActiveTab('wiki')}
            style={{
              flex: 1,
              padding: '6px 12px',
              fontSize: '12px',
              fontWeight: '600',
              borderRadius: '6px',
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
              background: activeTab === 'wiki' ? '#EEF2FF' : 'transparent',
              color: activeTab === 'wiki' ? '#4F46E5' : '#4B5563',
              transition: 'all 0.2s'
            }}
          >
            <FileText size={13} />
            知识 Wiki
          </button>
        </div>

        {activeTab === 'chat' ? (
          <>
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
          </>
        ) : (
          /* 已编译文档 WIKI 列表 */
          <div className="session-grouped-container">
            <div style={{ fontSize: '11px', fontWeight: '600', color: '#9CA3AF', padding: '8px 16px 4px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              已编译的文档 Wiki ({wikiDocs.length})
            </div>
            {wikiDocs.length === 0 ? (
              <div style={{ fontSize: '12px', color: '#9CA3AF', textAlign: 'center', marginTop: '24px', padding: '0 16px', lineHeight: '1.5' }}>
                暂无编译文档。在右侧上传 PDF/MD 文档，AI 会自动对其编译。
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', padding: '4px 8px' }}>
                {wikiDocs.map(s => (
                  <div 
                    key={s.document_id} 
                    className={`session-item-row ${selectedWikiDocId === s.document_id ? 'active' : ''}`}
                    onClick={() => { setSelectedWikiDocId(s.document_id); fetchWikiDetail(s.document_id); }}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '8px 12px',
                      borderRadius: '8px',
                      cursor: 'pointer',
                      background: selectedWikiDocId === s.document_id ? '#EEF2FF' : 'transparent',
                      color: selectedWikiDocId === s.document_id ? '#4F46E5' : '#374151',
                      transition: 'all 0.2s'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden', width: '100%' }}>
                      <FileText size={13} strokeWidth={1.5} style={{ flexShrink: 0, color: selectedWikiDocId === s.document_id ? '#4F46E5' : '#6B7280' }} />
                      <span style={{ fontSize: '12px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: selectedWikiDocId === s.document_id ? '600' : '400' }} title={s.title}>
                        {s.title}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

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
            const rawUsername = username || '访客';
            const displayUsername = isVisitorSession() ? '访客' : rawUsername;
            const remainingMs = isVisitorSession() ? getVisitorRemainingMs() : 0;
            const remainingMinutes = Math.floor(remainingMs / 60000);
            const remainingClass = isVisitorSession() && remainingMinutes <= 15 ? 'is-expiring' : ''; 
            const userSubText = isVisitorSession()
              ? `剩余体验 ${formatDurationLabel(remainingMs)}`
              : '当前工作区';
            return (
              <div className={`sidebar-user-card ${remainingClass}`} onClick={() => setShowUserMenu(!showUserMenu)}>
                <div className="user-avatar-circle">
                  {displayUsername ? displayUsername[0].toUpperCase() : '访'}
                </div>
                <div className="user-card-info-col">
                  <span className="user-card-name-text">{displayUsername}</span>
                  <span className="user-card-sub-text">{userSubText}</span>
                </div>
              </div>
            );
          })()}
        </div>
      </div>
      {!sidebarCollapsed && (
        <div className="resizer-bar vertical-resizer" onMouseDown={handleLeftResizeMouseDown} />
      )}

      {/* 中间 Workspace 区域 (最大宽度 900px, 左右留白自适应) */}
      {activeTab === 'wiki' ? (
        /* Wiki 编译工作台渲染 */
        <div className="main-workspace" style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, overflow: 'hidden' }}>
          {!selectedWikiDocId ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-secondary)', padding: '24px' }}>
              <FileText size={48} strokeWidth={1} style={{ marginBottom: '16px', color: 'var(--accent-color)' }} />
              <h3 style={{ fontSize: '16px', fontWeight: '600', color: 'var(--text-main)' }}>请在左侧选择已编译文档以查看结构化 Wiki</h3>
              <p style={{ fontSize: '13px', marginTop: '8px', textAlign: 'center', maxWidth: '400px', lineHeight: '1.6' }}>
                大模型知识编译器会自动对上传的文档做智能摘要、核心概念、关键条款以及典型问答的提炼，并为您保留引用的出处与片段。
              </p>
            </div>
          ) : isLoadingWiki ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-secondary)' }}>
              <RefreshCw className="animate-spin" size={32} style={{ marginBottom: '16px', color: 'var(--accent-color)' }} />
              <p style={{ fontSize: '13px' }}>智能知识编译器正在编译该文档的 Wiki 结构化视图...</p>
            </div>
          ) : selectedWiki ? (
            <div className="wiki-detail-workspace" style={{ flex: 1, overflowY: 'auto', padding: '24px 32px' }}>
              <div style={{ maxWidth: '840px', margin: '0 auto', width: '100%', paddingBottom: '40px' }}>
                
                {/* 顶部标题与摘要卡片 */}
                <div style={{ borderBottom: '1px solid var(--border-color)', paddingBottom: '20px', marginBottom: '24px' }}>
                  <h1 style={{ fontSize: '20px', fontWeight: '700', color: 'var(--text-main)', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <FileText size={20} style={{ color: 'var(--accent-color)' }} />
                    {selectedWiki.title}
                  </h1>
                  <div style={{ background: 'var(--bg-card-header, #F9FAFB)', border: '1px solid var(--border-color)', borderRadius: '12px', padding: '16px', fontSize: '13px', color: 'var(--text-main)', lineHeight: '1.6' }}>
                    <div style={{ fontWeight: '600', color: 'var(--text-main)', marginBottom: '6px', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Activity size={13} style={{ color: 'var(--accent-color)' }} /> AI 自动生成全局摘要
                    </div>
                    {selectedWiki.summary || '暂无文档摘要。'}
                  </div>
                </div>

                {/* 核心概念与专有名词 */}
                <div style={{ marginBottom: '32px' }}>
                  <h3 style={{ fontSize: '14px', fontWeight: '600', color: 'var(--text-main)', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Hexagon size={14} style={{ color: 'var(--accent-color)' }} /> 核心概念与专有名词 ({selectedWiki.concepts ? selectedWiki.concepts.length : 0})
                  </h3>
                  {!selectedWiki.concepts || selectedWiki.concepts.length === 0 ? (
                    <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>未提取到核心名词。</p>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      {selectedWiki.concepts.map((c, idx) => (
                        <div key={idx} style={{ background: '#FFF', border: '1px solid var(--border-color)', borderRadius: '12px', padding: '16px', boxShadow: '0 1px 2px rgba(0,0,0,0.01)' }}>
                          <div style={{ fontWeight: '600', color: 'var(--text-main)', fontSize: '13px', marginBottom: '4px' }}>
                            {c.key}
                          </div>
                          <div style={{ fontSize: '13px', color: '#4B5563', lineHeight: '1.5', marginBottom: '8px' }}>
                            {c.value}
                          </div>
                          {c.citation && (
                            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', background: '#F9FAFB', padding: '10px 12px', borderLeft: '3px solid var(--accent-light, #EEF2FF)', borderRadius: '4px' }}>
                              <span style={{ fontWeight: '500', color: '#4B5563' }}>原文依据:</span> “{c.citation}”
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* 关键条款与合规规则 */}
                <div style={{ marginBottom: '32px' }}>
                  <h3 style={{ fontSize: '14px', fontWeight: '600', color: 'var(--text-main)', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Shield size={14} style={{ color: '#10B981' }} /> 关键条款与合规规则 ({selectedWiki.clauses ? selectedWiki.clauses.length : 0})
                  </h3>
                  {!selectedWiki.clauses || selectedWiki.clauses.length === 0 ? (
                    <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>未提取到关键条款。</p>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      {selectedWiki.clauses.map((c, idx) => (
                        <div key={idx} style={{ background: '#FFF', border: '1px solid var(--border-color)', borderRadius: '12px', padding: '16px', boxShadow: '0 1px 2px rgba(0,0,0,0.01)' }}>
                          <div style={{ fontWeight: '600', color: 'var(--text-main)', fontSize: '13px', marginBottom: '4px' }}>
                            {c.key}
                          </div>
                          <div style={{ fontSize: '13px', color: '#4B5563', lineHeight: '1.5', marginBottom: '8px' }}>
                            {c.value}
                          </div>
                          {c.citation && (
                            <div style={{ fontSize: '12px', color: '#6B7280', background: '#F9FAFB', padding: '10px 12px', borderLeft: '3px solid #D1FAE5', borderRadius: '4px' }}>
                              <span style={{ fontWeight: '500', color: '#047857' }}>原文依据:</span> “{c.citation}”
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* 典型问答 FAQs */}
                <div style={{ marginBottom: '32px' }}>
                  <h3 style={{ fontSize: '14px', fontWeight: '600', color: 'var(--text-main)', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Lightbulb size={14} style={{ color: '#F59E0B' }} /> 典型问答 FAQs ({selectedWiki.faqs ? selectedWiki.faqs.length : 0})
                  </h3>
                  {!selectedWiki.faqs || selectedWiki.faqs.length === 0 ? (
                    <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>未提取到常见问答。</p>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      {selectedWiki.faqs.map((f, idx) => (
                        <div key={idx} style={{ background: '#FFF', border: '1px solid var(--border-color)', borderRadius: '12px', padding: '16px', boxShadow: '0 1px 2px rgba(0,0,0,0.01)' }}>
                          <div style={{ fontWeight: '600', color: 'var(--text-main)', fontSize: '13px', marginBottom: '6px', display: 'flex', alignItems: 'flex-start', gap: '6px' }}>
                            <span style={{ color: '#D97706', fontWeight: '700' }}>Q:</span>
                            <span>{f.key}</span>
                          </div>
                          <div style={{ fontSize: '13px', color: '#4B5563', lineHeight: '1.5', marginBottom: '8px', paddingLeft: '20px', display: 'flex', alignItems: 'flex-start', gap: '6px' }}>
                            <span style={{ color: '#059669', fontWeight: '700' }}>A:</span>
                            <span>{f.value}</span>
                          </div>
                          {f.citation && (
                            <div style={{ marginLeft: '20px', fontSize: '12px', color: '#6B7280', background: '#F9FAFB', padding: '10px 12px', borderLeft: '3px solid #FEF3C7', borderRadius: '4px' }}>
                              <span style={{ fontWeight: '500', color: '#B45309' }}>原文依据:</span> “{f.citation}”
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* 完整编译 Wiki 全文 */}
                {selectedWiki.markdown_content && (
                  <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: '24px', marginTop: '12px' }}>
                    <h3 style={{ fontSize: '14px', fontWeight: '600', color: 'var(--text-main)', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <FileText size={14} style={{ color: 'var(--accent-color)' }} /> 完整编译 Wiki 全文
                    </h3>
                    <div style={{ background: '#FFF', border: '1px solid var(--border-color)', borderRadius: '12px', padding: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
                      {renderMessageContent(selectedWiki.markdown_content)}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div style={{ textAlign: 'center', color: '#EF4444', marginTop: '40px', fontSize: '13px' }}>
              暂无该文档的 Wiki 视图。
            </div>
          )}
        </div>
      ) : (
        /* 智能对话工作台 */
        (() => {
          const rawUsername = username || '访客';
          const displayUsername = isVisitorSession() ? '访客' : rawUsername;
          const recentSessionsLimit = sessions.slice(0, 3); // 最多 3 条最近会话
          
          return (
            <div className="main-workspace">
            {messages.length === 0 ? (
              /* 欢迎状态 (Figma 极致留白布局) */
              <div style={{ maxWidth: '900px', width: '100%', margin: '0 auto', flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'space-between', minHeight: 0, height: '100%' }}>
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
              <div style={{ maxWidth: '900px', width: '100%', margin: '0 auto', flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'space-between', paddingBottom: '24px', minHeight: 0, height: '100%' }}>
                
                <div className="chat-flow-container" style={{ padding: '0 0 24px 0', flex: 1, overflowY: 'auto' }}>
                  {/* Figma 风格的顶部大会话标题与来源 Meta 汇总 */}
                  <div className="chat-flow-session-header">
                    <h2 className="chat-flow-header-title">
                      {(() => {
                        const matched = sessions.find(s => s.session_id === activeSessionId);
                        if (matched && matched.title) return matched.title;
                        const firstUserMsg = messages.find(m => m.role === 'user');
                        if (firstUserMsg && firstUserMsg.content) {
                          return firstUserMsg.content.length > 24 
                            ? firstUserMsg.content.substring(0, 24) + '...'
                            : firstUserMsg.content;
                        }
                        return "新对话";
                      })()}
                    </h2>
                    <div className="chat-flow-header-meta">
                      <span>
                        {(() => {
                          const matched = sessions.find(s => s.session_id === activeSessionId);
                          return matched && matched.created_at ? matched.created_at : "刚刚";
                        })()}
                      </span>
                      <span>·</span>
                      <span>{currentCitations.length ? `来自 ${currentCitations.length} 个参考来源` : `已关联知识库`}</span>
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
                                <span style={{ fontWeight: '600', color: '#222222', fontSize: '13.5px' }}>访客</span>
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
                          
                          {!isUser && index === messages.length - 1 && currentStep >= 0 && currentStep <= 5 ? (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', width: '100%' }}>
                              {currentStep <= 5 && (
                                <div className={`thinking-card-wrapper ${currentStep === 5 ? 'fade-out' : ''}`}>
                                  <div className="thinking-card-header">
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                      <Hexagon size={14} strokeWidth={1.5} className="thinking-logo-icon" />
                                      <span className="thinking-card-title">深度思考中</span>
                                    </div>
                                  </div>
                                  <div className="thinking-card-steps">
                                    {[
                                      { id: 'UNDERSTANDING', text: '理解当前问题...' },
                                      { id: 'REWRITE', text: '多轮对话查询重写...' },
                                      { id: 'RETRIEVING', text: '正在检索知识库...' },
                                      { id: 'RERANKING', text: '正在重排检索文档...' },
                                      { id: 'GENERATING', text: '正在生成流式回答...' }
                                    ].map((step, idx) => {
                                      const isCompleted = idx < currentStep || currentStep === 5;
                                      const isActive = idx === currentStep && currentStep < 5;
                                      const isPending = idx > currentStep && currentStep < 5;

                                      return (
                                        <div key={step.id} className={`thinking-step-row ${isCompleted ? 'completed' : isActive ? 'active' : 'pending'}`}>
                                          <div className="thinking-step-indicator">
                                            {isCompleted ? (
                                              <Check size={10} strokeWidth={3} className="check-icon" />
                                            ) : isActive ? (
                                              <span className="thinking-step-dot active"></span>
                                            ) : (
                                              <span className="thinking-step-dot pending"></span>
                                            )}
                                          </div>
                                          <span className="thinking-step-text">{step.text}</span>
                                        </div>
                                      );
                                    })}
                                  </div>
                                </div>
                              )}
                              {currentStep === 5 && (
                                <div className="message-bubble-card fade-in" style={{ background: '#FFFFFF', border: '1px solid #EAEAEA', borderRadius: '12px', padding: '16px' }}>
                                  {renderMessageContent(msg.content)}
                                </div>
                              )}
                            </div>
                          ) : (
                            <div className="message-bubble-card" style={{ background: '#FFFFFF', border: '1px solid #EAEAEA', borderRadius: '12px', padding: '16px' }}>
                              {renderMessageContent(msg.content)}
                            </div>
                          )}
                          
                          <span style={{ fontSize: '11px', color: '#9CA3AF', marginTop: '6px', display: 'inline-block' }}>
                            {isUser ? '21:54' : '21:55'}
                          </span>
                        </div>

                        {/* 最后一个 AI 回复下方，如果存在引用来源，渲染垂直卡片列表 */}
                        {!isUser && index === messages.length - 1 && currentCitations.length > 0 && (
                          <div className="citations-block-wrapper">
                            <div 
                              className="citations-toggle-header" 
                              onClick={() => setIsCitationsExpanded(!isCitationsExpanded)}
                              style={{ 
                                cursor: 'pointer', 
                                display: 'inline-flex', 
                                alignItems: 'center', 
                                gap: '6px',
                                padding: '4px 0',
                                userSelect: 'none'
                              }}
                            >
                              <span className="citations-block-title" style={{ fontSize: '13px', fontWeight: '600', color: '#4F46E5' }}>
                                引用来源 ({currentCitations.length})
                              </span>
                              <ChevronRight 
                                size={14} 
                                style={{ 
                                  transform: isCitationsExpanded ? 'rotate(90deg)' : 'rotate(0deg)', 
                                  transition: 'transform 0.2s ease',
                                  color: '#4F46E5'
                                }} 
                              />
                            </div>
                            
                            {isCitationsExpanded && (
                              <div className="citations-list-compact" style={{ 
                                maxHeight: '120px', 
                                overflowY: 'auto', 
                                marginTop: '8px', 
                                display: 'flex', 
                                flexDirection: 'column', 
                                gap: '6px',
                                paddingRight: '4px'
                              }}>
                                {currentCitations.map((c, cIdx) => (
                                  <div 
                                    key={cIdx} 
                                    className="citation-compact-item"
                                    onClick={() => openChunkPreview(getCitationFilename(c))}
                                    style={{ 
                                      display: 'flex', 
                                      alignItems: 'center', 
                                      justifyContent: 'space-between',
                                      padding: '6px 10px',
                                      background: '#F9FAFB',
                                      border: '1px solid #F3F4F6',
                                      borderRadius: '6px',
                                      cursor: 'pointer',
                                      transition: 'background 0.2s ease'
                                    }}
                                    onMouseEnter={(e) => e.currentTarget.style.background = '#EEF2FF'}
                                    onMouseLeave={(e) => e.currentTarget.style.background = '#F9FAFB'}
                                  >
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden' }}>
                                      <span style={{ fontSize: '11px', fontWeight: '600', color: '#4F46E5', background: '#EEF2FF', padding: '1px 5px', borderRadius: '4px', flexShrink: 0 }}>
                                        [{cIdx + 1}]
                                      </span>
                                      <span style={{ fontSize: '12px', color: '#374151', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                                        {getCitationFilename(c)}
                                      </span>
                                      {c.page && (
                                        <span style={{ fontSize: '11px', color: '#6B7280', flexShrink: 0 }}>
                                          (第 {c.page} 页)
                                        </span>
                                      )}
                                    </div>
                                    <span style={{ fontSize: '11px', color: '#4F46E5', fontWeight: '500', flexShrink: 0 }}>
                                      点击预览 ➔
                                    </span>
                                  </div>
                                ))}
                              </div>
                            )}
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
      })()
      )}

      {!rightPanelCollapsed && (
        <div className="resizer-bar vertical-resizer" onMouseDown={handleRightResizeMouseDown} />
      )}

      <div 
        className={`right-panel ${rightPanelCollapsed ? 'collapsed' : ''}`}
        style={{ width: rightPanelCollapsed ? 0 : `${rightPanelWidth}px` }}
      >
        {developerMode ? (
          /* 🟢 开发模式下的头部控制栏 (带保存、分享按钮以及高亮的 Developer 选项卡) */
          <div className="dev-top-actions-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-color)', paddingBottom: '16px', marginBottom: '24px' }}>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button type="button" className="dev-action-btn" title="保存当前会话" onClick={handleSaveConversation}>
                <FileText size={14} strokeWidth={1.5} style={{ color: '#9CA3AF' }} />
                <span style={{ color: '#222222' }}>保存</span>
              </button>
              <button type="button" className="dev-action-btn" title="分享功能暂未接入" disabled>
                <ExternalLink size={14} strokeWidth={1.5} style={{ color: '#9CA3AF' }} />
                <span style={{ color: '#222222' }}>分享</span>
              </button>
            </div>
            
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <button 
                type="button" 
                className="panel-tab-trigger active" 
                style={{ paddingBottom: '0', borderBottom: 'none', fontWeight: '600', color: 'var(--accent-color)' }}
              >
                Developer
              </button>
              <button 
                type="button" 
                className="panel-collapse-btn" 
                onClick={() => setRightPanelCollapsed(true)} 
                title="收起右面板"
                style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: '4px', display: 'flex', alignItems: 'center', color: '#9CA3AF' }}
              >
                <ChevronRight size={16} strokeWidth={1.5} />
              </button>
            </div>
          </div>
        ) : (
          /* ⚪ 普通模式下的双并列 Tabs (Knowledge / Sources) */
          <div className="panel-tabs-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', gap: '24px' }}>
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
            <button 
              type="button" 
              className="panel-collapse-btn" 
              onClick={() => setRightPanelCollapsed(true)} 
              title="收起右面板"
              style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: '4px', display: 'flex', alignItems: 'center', color: '#9CA3AF' }}
            >
              <ChevronRight size={16} strokeWidth={1.5} />
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
                {healthComponents.map((component) => {
                  const isOk = component.status === 'ok';
                  const statusColor = isOk ? '#22C55E' : component.status === 'unknown' ? '#9CA3AF' : '#EF4444';
                  return (
                    <div key={component.key} className="dev-health-card">
                      <div className="dev-health-card-name">{component.name}</div>
                      <div className="dev-health-card-status" style={{ color: statusColor }}>
                        <span style={{ background: statusColor }}></span>
                        <span>{isOk ? 'OK' : component.status === 'unknown' ? 'Pending' : 'Error'}</span>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* 1.5 MCP Tools 服务层 */}
              <h3 className="dev-section-title" style={{ marginTop: '16px', marginBottom: '8px' }}>MCP Tools 服务层</h3>
              <div className="dev-health-card" style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '12px', background: 'var(--panel-bg-dark, #F9FAFB)', border: '1px solid var(--border-color)', borderRadius: '8px', marginBottom: '16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '13px', fontWeight: '600', color: '#111827' }}>MCP-ready stdio 服务</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', color: '#22C55E', fontWeight: '500' }}>
                    <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#22C55E', display: 'inline-block' }}></span>
                    Ready
                  </span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', borderTop: '1px dashed var(--border-color)', paddingTop: '8px' }}>
                  <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '4px' }}>
                    <code style={{ fontSize: '11px', background: '#E0F2FE', color: '#0369A1', padding: '2px 6px', borderRadius: '4px' }}>search_documents</code>
                    <code style={{ fontSize: '11px', background: '#E0F2FE', color: '#0369A1', padding: '2px 6px', borderRadius: '4px' }}>answer_with_citations</code>
                    <code style={{ fontSize: '11px', background: '#E0F2FE', color: '#0369A1', padding: '2px 6px', borderRadius: '4px' }}>list_documents</code>
                  </div>
                  <span style={{ fontSize: '11px', color: '#6B7280', lineHeight: '1.4' }}>
                    已导出当前租户的 RAG 核心工具集，可直接在 Cursor / Claude Desktop 等 IDE Agent 中挂载与调用。
                  </span>
                </div>
              </div>

              {/* 2. TRACE PIPELINE */}
              <h3 className="dev-trace-uppercase-title">TRACE PIPELINE</h3>
              <div className="dev-trace-list">
                {traceStages.length === 0 ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', width: '100%' }}>
                    <div style={{ fontSize: '11px', color: '#6B7280', marginBottom: '4px' }}>租户流式链路监听中 (静态预览模式)：</div>
                    {[
                      { name: "1. Query Rewrite (指代消解与多路分词)", desc: "意图重写 Agent" },
                      { name: "2. Hybrid Retrieval (混合多路检索)", desc: "Chroma 向量检索 + 租户隔离 BM25" },
                      { name: "3. RRF Ensemble (多路召回融合)", desc: "Reciprocal Rank Fusion 多路融合" },
                      { name: "4. Flashrank Rerank (重排精选)", desc: "轻量级本地交叉编码器重排" },
                      { name: "5. Critic Agent Guard (证据评估)", desc: "相关性打分与超纲拒答判定" },
                      { name: "6. SSE Answer Generator (流式响应)", desc: "大模型 SSE 流式输出与历史落库" }
                    ].map((step, idx) => (
                      <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#FFFFFF', border: '1px solid var(--border-color)', borderRadius: '6px', padding: '8px 10px' }}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                          <span style={{ fontSize: '12px', fontWeight: '500', color: '#374151' }}>{step.name}</span>
                          <span style={{ fontSize: '11px', color: '#9CA3AF' }}>{step.desc}</span>
                        </div>
                        <span style={{ fontSize: '10px', color: '#3B82F6', background: '#EFF6FF', border: '1px solid #BFDBFE', padding: '1px 6px', borderRadius: '4px', whiteSpace: 'nowrap' }}>监听中</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  traceStages.map((stage, stageIndex) => (
                    <div key={`${stage.name}-${stageIndex}`} className="dev-trace-item-row">
                      <div className="dev-trace-item-left">
                        <span className="dev-trace-index">{stageIndex + 1}</span>
                        <span className="dev-trace-name">{stage.name}</span>
                      </div>
                      <div className="dev-trace-right">
                        <span className="dev-trace-latency">{stage.latency_ms ? `${stage.latency_ms}ms` : 'live'}</span>
                        <span className="dev-trace-check-box">
                          <Check size={14} strokeWidth={2.5} />
                        </span>
                      </div>
                    </div>
                  ))
                )}
              </div>

              {/* 3. 检索详情 */}
              <div className="dev-retrieve-header">
                <h3 className="dev-section-title" style={{ marginBottom: 0 }}>检索详情</h3>
                <span className="dev-retrieve-badge-topk">Top K: 8</span>
              </div>
              <div className="dev-retrieve-grid-card" onClick={() => openChunkPreview()}>
                <div className="dev-retrieve-2x2">
                  <div className="dev-retrieve-item">
                    <span className="dev-retrieve-label">命中率 (Rerank TopK)</span>
                    <span className="dev-retrieve-val">{retrievalHitCount ? `${retrievalHitCount}/8` : '0/8'}</span>
                  </div>
                  <div className="dev-retrieve-item">
                    <span className="dev-retrieve-label">来源文档数</span>
                    <span className="dev-retrieve-val">{documents.length}</span>
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
                  onClick={() => openChunkPreview()}
                >
                  <span>展开</span>
                  <ChevronRight size={12} strokeWidth={1.5} />
                </button>
              </div>
              <div className="dev-chunks-list">
                {chunkPreviewRows.length === 0 ? (
                  <div className="dev-empty-state">暂无真实切片，请先上传文档或执行一次问答。</div>
                ) : (
                  chunkPreviewRows.map((row) => (
                    <div key={`${row.filename}-${row.id}`} className="dev-chunk-item-line" onClick={() => openChunkPreview(row.filename)}>
                      <div className="dev-chunk-left">
                        <span className="dev-chunk-hash-tag">#{row.id}</span>
                        <span className="dev-chunk-meta-text">{row.filename}{row.page ? ` - 第 ${row.page} 页` : ''}</span>
                      </div>
                      <span className="dev-chunk-score-text">{row.score ? Number(row.score).toFixed(3) : 'Indexed'}</span>
                    </div>
                  ))
                )}
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
                      id="kb-file-input-panel" 
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
                          <span className="source-doc-title" title={getCitationFilename(c)}>
                            [{idx + 1}] {getCitationFilename(c)}
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
              {previewChunks.length === 0 ? (
                <div className="audit-empty-state">该文档暂无可展示切片。</div>
              ) : (
                previewChunks.map((chunk, idx) => (
                <div key={idx} className="audit-chunk-card">
                  <div className="audit-chunk-meta-row">
                    <span className="audit-chunk-index">#{idx + 1}</span>
                    <span className="audit-chunk-id">ID: {(chunk.chunk_id || '').substring(0, 12)}...</span>
                  </div>
                  <div className="audit-chunk-content">{chunk.content}</div>
                </div>
              )))}
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

      {/* 左右侧边栏悬浮展开按钮 */}
      {sidebarCollapsed && (
        <button 
          type="button"
          className="floating-expand-btn left-expand" 
          onClick={() => setSidebarCollapsed(false)}
          title="展开侧边栏"
        >
          <ChevronRight size={16} strokeWidth={1.5} />
        </button>
      )}
      
      {rightPanelCollapsed && (
        <button 
          type="button"
          className="floating-expand-btn right-expand" 
          onClick={() => setRightPanelCollapsed(false)}
          title="展开右面板"
        >
          <ChevronLeft size={16} strokeWidth={1.5} />
        </button>
      )}
    </div>
  );
}

export default App;
