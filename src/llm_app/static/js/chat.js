const getToken = () => localStorage.getItem('token') ?? ''
const getUserId = () => localStorage.getItem('userId') ?? ''
const getUsername = () => localStorage.getItem('username') ?? ''

let currentSessionId = ''

// === 页面切换 ===
function showLogin(
) {
    document.getElementById('login-page').style.display = 'block';
    document.getElementById('register-page').style.display = 'none';
    document.getElementById('chat-page').style.display = 'none';
}

function showRegister(
) {
    document.getElementById('login-page').style.display = 'none';
    document.getElementById('register-page').style.display = 'block';
    document.getElementById('chat-page').style.display = 'none';
}

function showChat(
) {
    document.getElementById('login-page').style.display = 'none';
    document.getElementById('register-page').style.display = 'none';
    document.getElementById('chat-page').style.display = 'flex';
}

async function login() {
    // @ts-ignore
    const username = document.getElementById('login-username').value;
    // @ts-ignore
    const password = document.getElementById('login-password').value;

    const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
    });
    if (!response.ok) {
        const error = await response.json();
        alert(error.detail || '登录失败!')
        return
    }

    const data = await response.json()
    console.log('登录成功', data)

    localStorage.setItem('token', data.token)
    localStorage.setItem('userId', data.userId)
    localStorage.setItem('username', data.username)
    showChat();
    await loadSessions();
}

async function register() {
    // @ts-ignore
    const username = document.getElementById('register-username').value;
    // @ts-ignore
    const password = document.getElementById('register-password').value;

    const response = await fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
    })
    if (!response.ok) {
        const error = await response.json();
        alert(error.detail || '注册失败!');
        return
    }

    alert('注册成功!请登录!');
    showLogin();
}

async function createSession() {
    const sessionName = prompt('请输入会话名称', '新会话');
    if (!sessionName) return

    const response = await fetch('/api/session', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${getToken()}`,
        },
        body: JSON.stringify({ sessionName })
    })

    const data = await response.json()
    if (!response.ok) {
        alert(data.detail || '创建会话失败!')
        return
    }

    currentSessionId = data.sessionId
    console.log('创建会话成功', data)
    loadSessions();
}

/**
 * 创建 DOM 元素。
 * @param {string} tag 标签名
 * @param {string} [className] CSS 类名
 * @param {string} [text] 文本内容
 * @returns {HTMLElement}
 */


function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text; // 关键：textContent
    return node;
}

async function loadSessions() {
    const response = await fetch('/api/sessions', {
        method: 'GET',
        headers: { 'Authorization': `Bearer ${getToken()}` }
    });

    const sessions = await response.json();

    if (!response.ok) {
        alert(sessions.detail || '加载会话失败!');
        return;
    }


    const sessionList = document.getElementById('session-list');
    sessionList.replaceChildren();

    sessions.forEach(session => {
        const div = el('div', 'session-item');
        div.append(
            el('div', 'session-name', session.sessionName),
            el('div', 'session-time', new Date(session.createdAt).toLocaleString())
        );
        div.addEventListener('click', () => {
            selectSession(session.sessionId, session.sessionName, div);
        });
        sessionList.appendChild(div);
    });
}

async function selectSession(sessionId, sessionName, element) {

    // 在 selectSession 开头加
    if (currentStreamAbortController) {
        currentStreamAbortController.abort('切换会话');
        currentStreamAbortController = null;
    }
    // 1. 保存当前会话 ID
    currentSessionId = sessionId;
    // 2. 情况当前聊天区域
    document.getElementById('chat-messages').replaceChildren();
    // 3. 高亮当前会话
    document.querySelectorAll('.session-item').forEach(item => {
        item.classList.remove('active')
    })
    element.classList.add('active');

    //加载历史消息,并渲染
    try {
        const messages = await loadMessages(sessionId);
        if (!messages) {
            return;
        }
        for (const msg of messages) {
            appendMessage(msg.role, msg.content, msg.createdAt);
        }
    } catch (err) {
        console.error('错误信息', err.message);
    }


    //console.log('点击事件触发', currentSessionId)
}

/* async function sendMessage() {
    const input = document.getElementById('message-input');
    const content = input.value.trim();

    if (!content || !currentSessionId) {
        alert('请先选择会话');
        return;
    }
    //显示用户消息
    appendMessage('user', content);
    input.value = '';
    //创建AI消息占位符
    const assistantContentDiv = appendMessage('assistant', 'thinking~~~~');

    //发送SSE请求
    const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${getToken()}`
        },
        body: JSON.stringify({
            sessionId: currentSessionId,
            content: content,
        })
    });

    //检查响应
    if (!response.ok) {
        assistantContentDiv.textContent = `发送失败（HTTP ${response.status}）`;
        return;
    }

    // 防御：如果请求打到了别的服务（例如静态服务器），这里会立刻暴露
    const contentType = response.headers.get('content-type') ?? '';
    if (!contentType.includes('text/event-stream')) {
        const raw = await response.text();
        console.error('响应不是 SSE：', contentType, raw.slice(0, 200));
        assistantContentDiv.textContent = `响应格式错误：${contentType}`;
        return;
    }

    //读取流式数据
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let fullContent = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // SSE 事件以空行分隔；最后一段可能不完整，留到下次拼接
        const events = buffer.split(/\r?\n\r?\n/);
        buffer = events.pop() ?? '';

        for (const event of events) {
            for (const line of event.split(/\r?\n/)) {
                if (!line.startsWith('data: ')) continue;
                const dataStr = line.slice(6).trim();
                if (dataStr === '[DONE]') continue;
                try {
                    const data = JSON.parse(dataStr);
                    if (typeof data.content === 'string') {
                        fullContent += data.content;
                        assistantContentDiv.textContent = fullContent;
                        scrollToBottom();
                    }
                } catch (error) {
                    console.error('SSE 数据解析失败：', error.message, dataStr);
                }
            }
        }
    }

    if (!fullContent) {
        assistantContentDiv.textContent = '（没有收到回复）';
    }
} */


/**
 * 发送消息，SSE POST 流式对话（工业加固版）
 * @param {AbortSignal} [outerSignal] 外部传入取消信号（可选，例如切换会话时取消）
 * @returns {Promise<void>}
 */
async function sendMessage(outerSignal) {
    // ========== 提交锁：防止连续点击重复发送 ==========
    if (sendMessage.isGenerating) {
        console.warn('正在生成回复，忽略本次提交');
        return;
    }

    const input = document.getElementById('message-input');
    const content = input.value.trim();

    if (!content || !currentSessionId) {
        alert('请先选择会话');
        return;
    }

    sendMessage.isGenerating = true;
    // 本地 controller：用于超时取消；同时和外部信号联动
    const innerController = new AbortController();
    const timeoutTimer = setTimeout(() => {
        innerController.abort('请求超时 60s');
    }, 60_000);

    // 合并外部取消信号 + 内部超时信号
    const abortSignal = AbortSignal.any([
        innerController.signal,
        ...(outerSignal ? [outerSignal] : [])
    ]);

    let assistantContentDiv = null;
    let reader = null;

    try {
        // 渲染用户消息、清空输入框、创建AI占位
        appendMessage('user', content);
        input.value = '';
        assistantContentDiv = appendMessage('assistant', 'thinking~~~~');

        // SSE POST 请求
        const response = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${getToken()}`
            },
            body: JSON.stringify({
                sessionId: currentSessionId,
                content: content,
            }),
            signal: abortSignal
        });

        // HTTP 状态校验
        if (!response.ok) {
            assistantContentDiv.textContent = `发送失败（HTTP ${response.status}）`;
            return;
        }

        // SSE Content-Type 校验
        const contentType = response.headers.get('content-type') ?? '';
        if (!contentType.includes('text/event-stream')) {
            const raw = await response.text();
            console.error('响应不是 SSE：', contentType, raw.slice(0, 200));
            assistantContentDiv.textContent = `响应格式错误：${contentType}`;
            return;
        }

        // 流式读取
        reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8', { fatal: false });
        let buffer = '';
        let fullContent = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            // 按 SSE 空行分割事件
            const events = buffer.split(/\r?\n\r?\n/);
            buffer = events.pop() ?? '';

            for (const event of events) {
                const lines = event.split(/\r?\n/);
                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    const dataStr = line.slice(6).trim();
                    if (dataStr === '[DONE]') continue;

                    try {
                        const data = JSON.parse(dataStr);
                        if (typeof data.content === 'string') {
                            fullContent += data.content;
                            assistantContentDiv.textContent = fullContent;
                            scrollToBottom();
                        }
                    } catch (parseErr) {
                        console.error('SSE JSON解析失败：', parseErr.message, dataStr);
                    }
                }
            }
        }

        if (!fullContent) {
            assistantContentDiv.textContent = '（没有收到回复）';
        }

    } catch (err) {
        console.error('流式请求异常：', err);
        if (!assistantContentDiv) return;

        if (err.name === 'AbortError') {
            assistantContentDiv.textContent = '（已停止生成）';
        } else {
            assistantContentDiv.textContent = '网络异常，请重试';
        }
    } finally {
        // 清理资源：定时器、reader、释放锁
        clearTimeout(timeoutTimer);
        if (reader) {
            try {
                reader.releaseLock();
            } catch (e) { /* releaseLock 失败静默 */ }
        }
        sendMessage.isGenerating = false;
        document.getElementById('btn-stop').disabled = true;
    }
}

// 在函数对象上挂载锁变量（静态标记）
sendMessage.isGenerating = false;

let currentStreamAbortController = null
function startSend() {
    if (currentStreamAbortController) {
        currentStreamAbortController.abort('终止上一条信息!');
    }
    currentStreamAbortController = new AbortController();
    document.getElementById('btn-stop').disabled = false;
    sendMessage(currentStreamAbortController.signal);
}

function stopGenerat() {
    if (currentStreamAbortController) {
        currentStreamAbortController.abort('用户手动停止');
        currentStreamAbortController = null;
    }

}

function scrollToBottom() {
    const chatMessages = document.getElementById('chat-messages');
    chatMessages.scrollTop = chatMessages.scrollHeight;
}


function appendMessage(role, content, createdAt) {
    //获取聊天容器
    const chatMessages = document.getElementById('chat-messages');
    //动态添加消息容器
    const msgDiv = el('div', 'message');
    msgDiv.classList.add(role)
    //创建消息内容
    const contentDiv = el('div', 'message-content', content);
    //创建时间戳
    const time = createdAt ? new Date(createdAt) : new Date();
    const timeDiv = el('div', 'message-time', time.toLocaleDateString());
    //组装容器并添加到页面
    msgDiv.append(contentDiv, timeDiv)
    chatMessages.append(msgDiv)
    //滚动到底部
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return contentDiv;
}

/**
 * 加载会话历史消息
 * @param {string} sessionId - 会话ID
 * @returns {Promise<Array<Record<string, any>>>} 消息数组，无消息返回空数组
 * @throws {Error} 接口请求异常（404/401/500等）
 */
async function loadMessages(sessionId) {
    const response = await fetch(`/api/sessions/${sessionId}/messages`, {
        method: 'GET',
        headers: {
            "Authorization": `Bearer ${getToken()}`,
        }
    });
    if (!response.ok) {
        console.error('加载历史消息失败!', response.status);
        throw new Error(`加载消息失败，状态码：${response.status}`);
    }
    const messages = await response.json();
    return messages;
}



// === 初始化：有 token 直接进入聊天页 ===
if (getToken()) {
    showChat();
    loadSessions();
} else {
    showLogin();
}
