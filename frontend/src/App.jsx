import React, { useState, useEffect, useRef } from 'react';
import { 
  Lock, User, LogIn, UserPlus, Send, Plus, 
  Trash2, Database, MessageSquare, Shield, 
  UploadCloud, FileText, ChevronRight, LogOut, 
  Search, Activity, AlertCircle, RefreshCw
} from 'lucide-react';
import './App.css';

const API_BASE = 'http://127.0.0.1:8000/api/v1';
const PAGE_SIZE = 10;

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

  // --- RAG 业务状态 ---
  const [sessions, setSessions] = useState([]);
  const [searchQuery, setSearchQuery] = useState(''); // 搜索历史会话
  const [activeSessionId, setActiveSessionId] = useState('');
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isSending, setIsSending] = useState(false);
  
  // 专属知识库分页列表
  const [documents, setDocuments] = useState([]);
  const [kbPage, setKbPage] = useState(1);
  const [kbTotal, setKbTotal] = useState(0);
  const [kbTotalPages, setKbTotalPages] = useState(1);
  const [showKbDetails, setShowKbDetails] = useState(false);
  
  // 文件上传状态
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState('');
  const [isDragging, setIsDragging] = useState(false);

  // 运维审计健康探测
  const [healthData, setHealthData] = useState(null);
  const [isCheckingHealth, setIsCheckingHealth] = useState(false);
  const [showHealthPanel, setShowHealthPanel] = useState(false);

  const messagesEndRef = useRef(null);

  // 校验用户名正则 (^[a-zA-Z0-9_-]{2,50}$)
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

  // 注册请求
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
        setIsRegister(false);
      } else {
        setAuthError(data.detail || '注册失败，用户名可能已存在');
      }
    } catch (err) {
      setAuthError('连接认证服务器失败，请确保数据库与后端服务已拉起');
    }
  };

  // 登录请求
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
      } else {
        setAuthError(data.detail || '用户名或密码错误');
      }
    } catch (err) {
      setAuthError('连接认证服务器失败，请确保数据库与后端服务已拉起');
    }
  };

  // 登出
  const handleLogout = () => {
    setToken('');
    setUsername('');
    setTenantId('');
    setSessions([]);
    setActiveSessionId('');
    setMessages([]);
    setDocuments([]);
    sessionStorage.clear();
  };

  // --- 初始化加载业务数据 ---
  useEffect(() => {
    if (token) {
      fetchDocuments(kbPage);
      fetchSessions();
    }
  }, [token, kbPage]);

  // 滚动至最新消息
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // 分页拉取知识库列表 (GET /list)
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

  // 拉取历史会话列表
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

  // 切换会话并读取对话记录
  const handleSelectSession = async (sessionId) => {
    setActiveSessionId(sessionId);
    setMessages([]);
    try {
      const res = await fetch(`${API_BASE}/history/${sessionId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (res.ok) {
        const mapped = (data.data || []).map(item => [
          { role: 'user', content: item.content, timestamp: new Date().toISOString() }
        ]).flat();
        
        // 修正多轮消息加载的映射逻辑，因为返回格式是 [{'role':'user','content':...}]
        setMessages(data.data || []);
      }
    } catch (err) {
      console.error('获取会话记录失败', err);
    }
  };

  // 新建会话
  const handleCreateNewChat = () => {
    setActiveSessionId('');
    setMessages([]);
  };

  // 删除单个会话
  const handleDeleteSession = async (e, sessionId) => {
    e.stopPropagation();
    try {
      const res = await fetch(`${API_BASE}/history/${sessionId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        if (activeSessionId === sessionId) {
          handleCreateNewChat();
        }
        fetchSessions();
      }
    } catch (err) {
      console.error('删除会话失败', err);
    }
  };

  // 清空知识库与所有会话
  const handleClearAll = async () => {
    if (!window.confirm('您确定要物理清空您租户空间下的所有已上传文档与聊天会话吗？此操作不可逆！')) return;
    try {
      const res = await fetch(`${API_BASE}/clear`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        setDocuments([]);
        setSessions([]);
        setKbPage(1);
        setKbTotal(0);
        setKbTotalPages(1);
        handleCreateNewChat();
        alert('租户数据已全部物理清空。');
      }
    } catch (err) {
      console.error('清空操作失败', err);
    }
  };

  // 拖拽与上传文件
  const handleUploadFile = async (file) => {
    if (!file) return;
    setIsUploading(true);
    setUploadProgress(`正在上传并对 ${file.name} 做租户隔离切片...`);

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
          alert(data.message || '文件已存在，跳过导入');
        } else {
          alert('文件上传并入库成功！');
        }
        setUploadProgress('');
        setIsUploading(false);
        setKbPage(1);
        fetchDocuments(1);
      } else {
        alert(data.detail || '文件上传失败，请检查文件格式');
        setIsUploading(false);
      }
    } catch (err) {
      alert('连接后端服务异常');
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

  // 运行状态自检探测
  const checkHealth = async () => {
    setIsCheckingHealth(true);
    setHealthData(null);
    try {
      const res = await fetch(`${API_BASE}/health`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (res.ok) {
        setHealthData(data);
      } else {
        setHealthData({ error: `状态探测异常: ${res.status}` });
      }
    } catch (err) {
      setHealthData({ error: '连接健康探测服务失败，请确保后端服务正常在线。' });
    }
    setIsCheckingHealth(false);
  };

  // 发送消息并读取原生纯文本流式输出 (修复 JSON.parse 崩溃 Bug)
  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!inputMessage.trim() || isSending) return;

    const userText = inputMessage;
    setInputMessage('');
    setIsSending(true);

    const tempSessionId = activeSessionId || `session_${Date.now()}`;
    if (!activeSessionId) {
      setActiveSessionId(tempSessionId);
    }

    // 追加用户消息
    setMessages(prev => [...prev, { role: 'user', content: userText }]);
    // 助手回复占位
    setMessages(prev => [...prev, { role: 'assistant', content: '' }]);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ question: userText, session_id: tempSessionId })
      });

      if (!res.ok) {
        const errorData = await res.json();
        setMessages(prev => {
          const next = [...prev];
          next[next.length - 1] = { role: 'assistant', content: `[错误] ${errorData.detail || '检索服务生成失败'}` };
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

        setMessages(prev => {
          const next = [...prev];
          next[next.length - 1] = { role: 'assistant', content: assistantText };
          return next;
        });
      }
      
      fetchSessions();
      setIsSending(false);
    } catch (err) {
      setMessages(prev => {
        const next = [...prev];
        next[next.length - 1] = { role: 'assistant', content: `[错误] 无法连接到流式生成服务，请检查网络。` };
        return next;
      });
      setIsSending(false);
    }
  };

  // 搜索会话本地过滤
  const filteredSessions = sessions.filter(s => 
    s.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // --- 登录页面渲染 ---
  if (!token) {
    return (
      <div className="auth-wrapper">
        <div className="nebula-bg"></div>
        <div className="glass-card auth-container">
          <div className="auth-header">
            <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '14px' }}>
              <Shield size={38} color="var(--color-primary)" />
            </div>
            <h1>Enterprise RAG</h1>
            <p>企业多租户安全知识库控制台</p>
          </div>

          <div className="auth-tabs">
            <button 
              className={`auth-tab-btn ${!isRegister ? 'active' : ''}`}
              onClick={() => { setIsRegister(false); setAuthError(''); }}
            >
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                <LogIn size={14} /> 租户登录
              </span>
            </button>
            <button 
              className={`auth-tab-btn ${isRegister ? 'active' : ''}`}
              onClick={() => { setIsRegister(true); setAuthError(''); }}
            >
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                <UserPlus size={14} /> 新建用户
              </span>
            </button>
          </div>

          <form onSubmit={isRegister ? handleRegister : handleLogin}>
            <div className="auth-form-group">
              <label>注册用户名 / 租户账户</label>
              <div style={{ position: 'relative' }}>
                <input 
                  type="text" 
                  className="neon-input" 
                  value={authUsername}
                  onChange={handleUsernameChange}
                  placeholder="请输入您的用户名" 
                  required
                />
                <User size={16} color="var(--text-muted)" style={{ position: 'absolute', right: '14px', top: '14px' }} />
              </div>
              {isRegister && (
                <div className={`auth-input-helper ${usernameError ? 'error' : 'success'}`}>
                  {usernameError || '仅支持字母、数字、下划线与连字符，且长度在 2-50 位之间。'}
                </div>
              )}
            </div>

            <div className="auth-form-group">
              <label>设置登录密码</label>
              <div style={{ position: 'relative' }}>
                <input 
                  type="password" 
                  className="neon-input" 
                  value={authPassword}
                  onChange={(e) => setAuthPassword(e.target.value)}
                  placeholder="请输入 6 位及以上的密码" 
                  required
                />
                <Lock size={16} color="var(--text-muted)" style={{ position: 'absolute', right: '14px', top: '14px' }} />
              </div>
            </div>

            <button type="submit" className="neon-btn" style={{ width: '100%', marginTop: '8px' }}>
              {isRegister ? '创建账户并获取专属租户' : '确认登录'}
            </button>
          </form>

          {authError && <div className="error-toast">{authError}</div>}
          {authSuccess && <div className="success-toast">{authSuccess}</div>}
        </div>
      </div>
    );
  }

  // --- 主控制台页面渲染 ---
  return (
    <div className="console-layout">
      <div className="nebula-bg"></div>

      {/* 1. 左侧历史会话侧边栏 */}
      <div className="sidebar-panel">
        <div className="sidebar-header">
          <Shield size={20} color="var(--color-primary)" />
          <h2>RAG Console</h2>
        </div>

        <button className="neon-btn new-chat-btn" onClick={handleCreateNewChat}>
          <Plus size={15} /> 新对话
        </button>

        {/* 会话过滤搜索框 (恢复 Streamlit history_search 功能) */}
        <div className="search-box-wrapper">
          <input 
            type="text" 
            className="search-input"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="搜索历史对话..."
          />
          <Search size={14} className="search-icon" />
        </div>

        <div className="session-list">
          {filteredSessions.length === 0 ? (
            <span style={{ fontSize: '12px', color: 'var(--text-muted)', textAlign: 'center', marginTop: '10px' }}>
              暂无历史对话
            </span>
          ) : (
            filteredSessions.map(s => (
              <div 
                key={s.session_id} 
                className={`session-item ${activeSessionId === s.session_id ? 'active' : ''}`}
                onClick={() => handleSelectSession(s.session_id)}
              >
                <div className="session-info">
                  <MessageSquare size={14} color={activeSessionId === s.session_id ? 'var(--color-primary)' : 'var(--text-muted)'} />
                  <span className="session-title">{s.title}</span>
                </div>
                <button 
                  className="session-delete-btn" 
                  onClick={(e) => handleDeleteSession(e, s.session_id)}
                  title="删除会话"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            ))
          )}
        </div>

        {/* 侧边栏底部隔离租户 ID 展示 (恢复 Streamlit 多租户审计) */}
        <div className="sidebar-user">
          <div className="user-badge-group">
            <div className="user-badge">
              <User size={14} color="var(--color-success)" />
              <span style={{ fontWeight: 600 }}>{username}</span>
            </div>
            {tenantId && (
              <div className="tenant-id-badge" title={tenantId}>
                租户: {tenantId.substring(0, 16)}...
              </div>
            )}
          </div>
          <button className="logout-btn" onClick={handleLogout} title="登出控制台">
            <LogOut size={15} />
          </button>
        </div>
      </div>

      {/* 2. 右侧主工作区 */}
      <div className="main-workspace">
        {/* 知识库管理与运维审计卡片 */}
        <div className="glass-card kb-section">
          <div className="kb-header">
            <h3>
              <Database size={17} color="var(--color-accent)" /> 专属知识库管理
            </h3>
            <div className="kb-actions">
              <button className="neon-btn-secondary" onClick={() => setShowKbDetails(!showKbDetails)}>
                {showKbDetails ? '隐藏审计面板' : '查看已存文档'}
              </button>
              <button 
                className="neon-btn-secondary" 
                onClick={() => setShowHealthPanel(!showHealthPanel)}
                style={{ borderColor: 'var(--border-glass)' }}
              >
                运行状态探测
              </button>
              <button 
                className="neon-btn-secondary" 
                onClick={handleClearAll} 
                style={{ color: 'var(--color-danger)', borderColor: 'rgba(199, 90, 78, 0.15)' }}
                title="物理清空您租户空间下的所有数据"
              >
                清空知识库
              </button>
            </div>
          </div>

          {/* 拖拽上传框 */}
          <div 
            className={`upload-dropzone ${isDragging ? 'dragging' : ''}`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => document.getElementById('file-input').click()}
          >
            <input 
              type="file" 
              id="file-input" 
              style={{ display: 'none' }} 
              onChange={(e) => handleUploadFile(e.target.files[0])}
            />
            <UploadCloud size={30} className="upload-icon" />
            <p>点击或拖拽文件到这里进行安全上传</p>
            <span>支持 PDF、DOCX、MD、TXT 格式 (物理随机 UUID 化重命名)</span>

            {isUploading && (
              <div className="upload-progress-overlay">
                <div className="progress-spinner"></div>
                <div className="progress-text">{uploadProgress}</div>
              </div>
            )}
          </div>

          {/* 状态自检探测面板 (恢复 Streamlit Health check) */}
          {showHealthPanel && (
            <div className="health-audit-panel">
              <div className="audit-header">
                <span className="title"><Activity size={14} /> 系统健康状态探测自检</span>
                <button className="neon-btn-secondary mini-btn" onClick={checkHealth} disabled={isCheckingHealth}>
                  <RefreshCw size={12} className={isCheckingHealth ? 'spin-icon' : ''} /> {isCheckingHealth ? '检测中' : '开始检测'}
                </button>
              </div>
              {healthData && (
                <pre className="terminal-box">
                  {JSON.stringify(healthData, null, 2)}
                </pre>
              )}
            </div>
          )}

          {/* 专属隔离知识库清单分页大表 (恢复 Streamlit 专属隔离知识库明细面板) */}
          {showKbDetails && (
            <div className="kb-details-panel">
              <div className="audit-header">
                <span className="title"><AlertCircle size={14} /> 租户专属物理数据安全审计</span>
                <span className="meta-badge">文档总数: {kbTotal} 个</span>
              </div>
              
              {documents.length === 0 ? (
                <div className="empty-table-state">当前租户名下暂无已入库的文档</div>
              ) : (
                <>
                  <table className="audit-table">
                    <thead>
                      <tr>
                        <th>物理编码</th>
                        <th>原始文件名称</th>
                        <th>MD5指纹</th>
                        <th>入库时间</th>
                      </tr>
                    </thead>
                    <tbody>
                      {documents.map((doc, idx) => (
                        <tr key={idx}>
                          <td className="code-td">{doc.id}</td>
                          <td style={{ fontWeight: 500 }}>{doc.source}</td>
                          <td className="code-td">{doc.fingerprint}</td>
                          <td>{doc.indexed_at}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  
                  {/* 分页控制 */}
                  <div className="table-pagination">
                    <button 
                      className="neon-btn-secondary mini-btn"
                      disabled={kbPage <= 1}
                      onClick={() => setKbPage(prev => Math.max(1, prev - 1))}
                    >
                      上一页
                    </button>
                    <span className="page-indicator">第 {kbPage} / {kbTotalPages} 页</span>
                    <button 
                      className="neon-btn-secondary mini-btn"
                      disabled={kbPage >= kbTotalPages}
                      onClick={() => setKbPage(prev => Math.min(kbTotalPages, prev + 1))}
                    >
                      下一页
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>

        {/* 聊天问答区 */}
        <div className="chat-container">
          <div className="chat-messages">
            {messages.length === 0 ? (
              <div className="empty-chat-state">
                <MessageSquare size={42} color="rgba(25,25,25,0.04)" />
                <h2>智能知识库助手</h2>
                {tenantId ? (
                  <p style={{ fontSize: '13.5px', color: 'var(--text-secondary)' }}>
                    已为租户 <span className="tenant-highlight">{tenantId}</span> 建立专属加密沙箱隔离通道
                  </p>
                ) : (
                  <p>请输入有关您已上传知识库文档的问题。系统将执行检索并流式生成回答。</p>
                )}
              </div>
            ) : (
              messages.map((msg, idx) => (
                <div key={idx} className={`message-row ${msg.role}`}>
                  <div className="message-meta">
                    {msg.role === 'user' ? '您' : 'AI 小助手'}
                  </div>
                  <div className={`chat-bubble ${msg.role}`}>
                    {/* 直接流式渲染 Markdown 纯文本（包括后端在末尾 yield 出来的参考来源列表） */}
                    <div style={{ whiteSpace: 'pre-wrap' }}>
                      {msg.content || (isSending && idx === messages.length - 1 ? '正在思考检索中...' : '')}
                    </div>
                  </div>
                </div>
              ))
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* 底部输入框 */}
          <form onSubmit={handleSendMessage} className="chat-input-bar">
            <input 
              type="text" 
              className="neon-input" 
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              placeholder="向专属知识库提问，或者和 AI 聊聊天..."
              disabled={isSending}
            />
            <button type="submit" className="neon-btn" disabled={isSending}>
              <Send size={14} /> 发送
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

export default App;
