#!/usr/bin/env python3
"""
Enterprise RAG MCP (Model Context Protocol) stdio 代理服务器
双模架构：
1. 优先尝试加载官方 python-mcp SDK；
2. 若环境未安装 SDK，自动降级激活纯 Python stdio JSON-RPC 2.0 循环，实现 0 依赖即插即用。
转发客户端请求至 FastAPI 后端的 /api/v1/tools/ 接口。
"""

import os
import sys
import json
import logging
import urllib.request
import urllib.error

# 配置日志输出至标准错误，防止污染 stdio JSON-RPC 的标准输出管道
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr
)
logger = logging.getLogger("Enterprise-RAG-MCP")

# 读取环境变量配置
RAG_BASE_URL = os.environ.get("RAG_BASE_URL", "http://localhost:8010/api/v1/tools")
RAG_JWT_TOKEN = os.environ.get("RAG_JWT_TOKEN", "")

# 工具定义模型 Schema，供两套模式共用
TOOLS_DEFINITION = [
    {
        "name": "search_documents",
        "description": "检索与当前租户关联的企业手册和文档分片 (Chunks)，带有语义混合检索及 RRF 得分。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索词或句子"},
                "top_k": {"type": "integer", "description": "最多返回的分片数量", "default": 5}
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_document_detail",
        "description": "根据文档 ID 获取对应的已上传文档详情，执行所属租户权限强校验。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "integer", "description": "文档在系统数据库中的唯一自增 ID"}
            },
            "required": ["doc_id"]
        }
    },
    {
        "name": "answer_with_citations",
        "description": "非流式企业知识问答。整合混合检索与 Critic 防护，生成带引用来源（citations）的精确解答。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "用户向知识库提出的具体问题"},
                "session_id": {"type": "string", "description": "进行连续追问时关联的会话 ID，如不传则自动生成新会话"}
            },
            "required": ["question"]
        }
    },
    {
        "name": "list_documents",
        "description": "列出当前租户下已成功索引的全部企业文档目录。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "page": {"type": "integer", "description": "分页页码", "default": 1},
                "page_size": {"type": "integer", "description": "每页条数", "default": 20}
            }
        }
    }
]


# ==========================================
# 🛰️ HTTP 转发逻辑 (标准库 0 依赖实现)
# ==========================================

def _request_backend(endpoint: str, method: str = "POST", params: dict = None) -> dict:
    """
    通过 urllib 请求 FastAPI 后端工具接口，强制在 Header 中带上 JWT。
    """
    url = f"{RAG_BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}"
    headers = {
        "Content-Type": "application/json",
    }
    if RAG_JWT_TOKEN:
        # 兼容 Bearer 自动拼接
        token = RAG_JWT_TOKEN if RAG_JWT_TOKEN.lower().startswith("bearer ") else f"Bearer {RAG_JWT_TOKEN}"
        headers["Authorization"] = token

    data = None
    if params is not None and method == "POST":
        data = json.dumps(params).encode("utf-8")
    elif params is not None and method == "GET":
        # 简单拼接 Query 参数
        query_str = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{query_str}"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        logger.info("Forwarding to backend URL: %s", url)
        with urllib.request.urlopen(req, timeout=15) as response:
            res_data = response.read().decode("utf-8")
            return json.loads(res_data)
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        logger.error("HTTP Error from backend: %s - %s", e.code, err_msg)
        try:
            err_json = json.loads(err_msg)
            detail = err_json.get("detail", str(e))
        except Exception:
            detail = err_msg or str(e)
        return {"status": "error", "message": f"后端错误 ({e.code}): {detail}"}
    except Exception as e:
        logger.error("Network connection failed: %s", e)
        return {"status": "error", "message": f"连接 RAG 后端失败: {str(e)}。请检查后端服务是否拉起且 RAG_BASE_URL 配置正确。"}


# ==========================================
# 🔮 工具处理路由器
# ==========================================

def execute_tool(name: str, arguments: dict) -> dict:
    """
    接收工具名称与参数，转发给后端，并把返回格式化为符合 MCP 规范的 text 回复。
    """
    if not RAG_JWT_TOKEN:
        return {
            "content": [{
                "type": "text",
                "text": "【配置错误】缺少环境变量 RAG_JWT_TOKEN，无法通过后端多租户鉴权，拒绝服务。"
            }],
            "isError": True
        }

    try:
        if name == "search_documents":
            res = _request_backend("/search_documents", method="POST", params={
                "query": arguments.get("query"),
                "top_k": arguments.get("top_k", 5)
            })
            if res.get("status") == "error":
                return {"content": [{"type": "text", "text": res.get("message")}], "isError": True}
            
            # 美化输出排版
            chunks = res.get("chunks", [])
            if not chunks:
                return {"content": [{"type": "text", "text": "未检索到相关的参考资料。"}]}
            
            text_lines = []
            for idx, c in enumerate(chunks, 1):
                meta = c.get("metadata", {})
                text_lines.append(
                    f"[{idx}] 来源: {meta.get('source')} (RRF得分: {meta.get('rrf_score')})\n"
                    f"内容: {c.get('content')}\n"
                    f"---"
                )
            return {"content": [{"type": "text", "text": "\n".join(text_lines)}]}

        elif name == "get_document_detail":
            res = _request_backend("/get_document_detail", method="POST", params={
                "doc_id": arguments.get("doc_id")
            })
            if res.get("status") == "error":
                return {"content": [{"type": "text", "text": res.get("message")}], "isError": True}
            
            detail_str = (
                f"【文档详情】\n"
                f"- ID: {res.get('doc_id')}\n"
                f"- 文件名: {res.get('filename')}\n"
                f"- MD5指纹: {res.get('file_hash')}\n"
                f"- 上传时间: {res.get('created_at')}\n"
                f"- 向量库分片数: {res.get('total_chunks')}\n"
                f"- 权限状态: 可访问 (租户 {res.get('tenant_id')} / 用户 {res.get('user_id')})"
            )
            return {"content": [{"type": "text", "text": detail_str}]}

        elif name == "answer_with_citations":
            res = _request_backend("/answer_with_citations", method="POST", params={
                "question": arguments.get("question"),
                "session_id": arguments.get("session_id")
            })
            if res.get("status") == "error" or res.get("status") == "blocked":
                ans = res.get("message") or res.get("answer") or "请求异常"
                return {"content": [{"type": "text", "text": ans}], "isError": True}
            
            answer = res.get("answer")
            citations = res.get("citations", [])
            
            text_resp = [answer]
            if citations:
                text_resp.append("\n\n---\n**参考引用来源：**")
                for idx, cite in enumerate(citations, 1):
                    text_resp.append(f"- [{idx}] 《{cite.get('source')}》 (RRF相关度: {cite.get('rrf_score')})")
            
            return {"content": [{"type": "text", "text": "\n".join(text_resp)}]}

        elif name == "list_documents":
            res = _request_backend("/list_documents", method="GET", params={
                "page": arguments.get("page", 1),
                "page_size": arguments.get("page_size", 20)
            })
            if res.get("status") == "error":
                return {"content": [{"type": "text", "text": res.get("message")}], "isError": True}
            
            docs = res.get("documents", [])
            total = res.get("total", 0)
            if not docs:
                return {"content": [{"type": "text", "text": "当前租户下暂无已登记的文档。"}]}
            
            lines = [f"当前租户下共有 {total} 个已上传文档：\n"]
            for d in docs:
                lines.append(f"- [ID: {d.get('doc_id')}] 《{d.get('filename')}》 (指纹: {d.get('file_hash')[:8]}, 登记于: {d.get('created_at')})")
            return {"content": [{"type": "text", "text": "\n".join(lines)}]}

        else:
            return {"content": [{"type": "text", "text": f"未知工具: {name}"}], "isError": True}

    except Exception as e:
        logger.exception("Execute tool %s failed", name)
        return {"content": [{"type": "text", "text": f"内部调用异常: {str(e)}"}], "isError": True}


# ==========================================
# 🚀 模式一：官方 python-mcp SDK 模式
# ==========================================

def run_official_sdk():
    """
    使用官方 python-mcp 模块拉起 stdio 服务
    """
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        import mcp.types as types
    except ImportError:
        return False

    logger.info("Initializing MCP Server using official python-mcp SDK...")
    
    app_server = Server("enterprise-rag-mcp")

    @app_server.list_tools()
    async def list_tools() -> list[types.Tool]:
        mcp_tools = []
        for t in TOOLS_DEFINITION:
            mcp_tools.append(
                types.Tool(
                    name=t["name"],
                    description=t["description"],
                    inputSchema=t["inputSchema"]
                )
            )
        return mcp_tools

    @app_server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        logger.info("Call tool via SDK: %s %s", name, arguments)
        result = execute_tool(name, arguments)
        
        is_error = result.get("isError", False)
        content_list = []
        for c in result.get("content", []):
            content_list.append(types.TextContent(type="text", text=c["text"]))
        
        # 兼容官方异常返回
        return content_list

    import asyncio
    async def main_loop():
        async with stdio_server() as (read_stream, write_stream):
            await app_server.run(read_stream, write_stream, app_server.create_initialization_options())

    try:
        asyncio.run(main_loop())
        return True
    except Exception as e:
        logger.error("SDK main loop failed: %s. Falling back to Raw Python mode.", e)
        return False


# ==========================================
# 🛡️ 模式二：纯 Python JSON-RPC 2.0 降级模式 (高可用无外部依赖)
# ==========================================

def run_raw_jsonrpc():
    """
    纯 Python 实现的轻量 stdio JSON-RPC 2.0 消息处理机制。
    极高可用，Cursor 与 Claude Desktop 在无包环境下可稳定运行。
    """
    logger.info("Official python-mcp SDK missing or failed. Activating raw Python JSON-RPC 2.0 loop...")
    
    # 强制让 sys.stdout 以 UTF-8 格式输出，杜绝 Windows 控制台下中文乱码
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")

    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            
            request = json.loads(line)
            req_id = request.get("id")
            method = request.get("method")
            params = request.get("params", {})
            
            logger.info("Received Raw JSON-RPC request: method=%s, id=%s", method, req_id)

            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": {
                            "name": "enterprise-rag-mcp-fallback",
                            "version": "1.0.0"
                        }
                    }
                }
            elif method == "notifications/initialized":
                # 握手通知，无需回应，继续等待新输入
                continue
            elif method == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": TOOLS_DEFINITION
                    }
                }
            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                logger.info("Call tool raw: %s with args %s", tool_name, arguments)
                
                tool_result = execute_tool(tool_name, arguments)
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": tool_result
                }
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }

            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()

        except json.JSONDecodeError:
            logger.error("JSON decode error from stdin")
            # 格式不符的忽略或返回通用解析错
            pass
        except Exception as e:
            logger.exception("Raw JSON-RPC loop error")
            break


# ==========================================
# 🏁 启动引导入口
# ==========================================

if __name__ == "__main__":
    logger.info("Starting Enterprise RAG MCP stdio Server...")
    logger.info("Configured RAG_BASE_URL: %s", RAG_BASE_URL)
    logger.info("Authorization Token Status: %s", "Loaded" if RAG_JWT_TOKEN else "Missing!")

    # 优先执行 SDK 模式，如果失败则执行纯 Python JSON-RPC
    if not run_official_sdk():
        run_raw_jsonrpc()
