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

function selectSession(sessionId, sessionName, element) {
    // 1. 保存当前会话 ID
    currentSessionId = sessionId;
    // 2. 情况当前聊天区域
    document.getElementById('chat-messages').replaceChildren();
    // 3. 高亮当前会话
    document.querySelectorAll('.session-item').forEach(item => {
        item.classList.remove('active')
    })
    element.classList.add('active');
    console.log('点击事件触发', currentSessionId)
}

async function sendMessage() {
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
}

function scrollToBottom() {
    const chatMessages = document.getElementById('chat-messages');
    chatMessages.scrollTop = chatMessages.scrollHeight;
}


function appendMessage(role, content) {
    //获取聊天容器
    const chatMessages = document.getElementById('chat-messages');
    //动态添加消息容器
    const msgDiv = el('div', 'message');
    msgDiv.classList.add(role)
    //创建消息内容
    const contentDiv = el('div', 'message-content', content);
    //创建时间戳
    const timeDiv = el('div', 'message-time', new Date().toLocaleDateString());
    //组装容器并添加到页面
    msgDiv.append(contentDiv, timeDiv)
    chatMessages.append(msgDiv)
    //滚动到底部
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return contentDiv;
}


// === 初始化：有 token 直接进入聊天页 ===
if (getToken()) {
    showChat();
} else {
    showLogin();
}
