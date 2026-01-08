/**
 * ATLAS Test Console - Core logic
 * Unified streaming, state, and UI management.
 */

// Configuration
const API_BASE = '';
const BUILT_AT = '2026-01-09T01:45:00Z'; // Placeholder for build time

// DOM References
const elements = {
    chatView: document.getElementById('chatView'),
    messagesContainer: document.getElementById('messagesContainer'),
    userInput: document.getElementById('userInput'),
    sendBtn: document.getElementById('sendBtn'),
    personaSelect: document.getElementById('personaSelect'),
    statusLabel: document.getElementById('statusLabel'),
    statusDot: document.getElementById('statusDot'),
    sessionList: document.getElementById('sessionList'),
    newChatBtn: document.getElementById('newChatBtn'),
    inspector: document.getElementById('inspector'),
    rdrContent: document.getElementById('rdrContent'),
    authOverlay: document.getElementById('authOverlay'),
    authSubmit: document.getElementById('authSubmit'),
    buildTimestamp: document.getElementById('buildTimestamp'),
    userNameDisplay: document.getElementById('userNameDisplay'),
    userRoleDisplay: document.getElementById('userRoleDisplay'),
    notifCount: document.getElementById('notifCount'),
    notifList: document.getElementById('notifList'),
    notifPanel: document.getElementById('notifPanel'),
    sidebarToggle: document.getElementById('sidebarToggle'),
    sidebar: document.getElementById('sidebar'),
    chatSearch: document.getElementById('chatSearch'),
    fileInput: document.getElementById('fileInput'),
    attachBtn: document.getElementById('attachBtn')
};

let isProcessing = false;
let currentRdr = null;

// Initialization
document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

function initApp() {
    // 1. Set build info
    if (elements.buildTimestamp) elements.buildTimestamp.innerText = BUILT_AT;

    // 2. Check Auth
    if (!atlasState.state.user) {
        showAuth();
    } else {
        updateUserInfo();
    }

    // 3. Load Sessions
    renderSessions();
    if (atlasState.state.activeSessionId) {
        loadSession(atlasState.state.activeSessionId);
    } else if (atlasState.state.sessions.length === 0) {
        startNewChat();
    }

    // 4. Set up Event Listeners
    setupListeners();

    // 5. Initial Notification check
    refreshNotifications();
    setInterval(refreshNotifications, 60000);
}

// Auth System
function showAuth() {
    elements.authOverlay.style.display = 'flex';
}

elements.authSubmit.addEventListener('click', () => {
    const name = document.getElementById('authName').value.trim() || 'Observer';
    const role = document.getElementById('authRole').value;
    atlasState.setUser(name, role);
    elements.authOverlay.style.display = 'none';
    updateUserInfo();
    location.reload(); // Refresh to ensure roles are active
});

function updateUserInfo() {
    const user = atlasState.state.user;
    if (user) {
        elements.userNameDisplay.innerText = user.name;
        elements.userRoleDisplay.innerText = user.role;
        elements.userRoleDisplay.className = `role-badge role-${user.role.toLowerCase()}`;
    }
}

// Session Logic
function renderSessions() {
    const sessions = atlasState.state.sessions;
    elements.sessionList.innerHTML = sessions.map(s => `
        <div class="session-item ${s.id === atlasState.state.activeSessionId ? 'active' : ''}" onclick="loadSession('${s.id}')">
            <span class="title"><i class="far fa-comments"></i> ${utils.escapeHtml(s.title)}</span>
            <div class="actions">
                <button onclick="deleteSession(event, '${s.id}')"><i class="fas fa-trash"></i></button>
            </div>
        </div>
    `).join('');
}

function startNewChat() {
    const session = atlasState.createSession('New Session');
    loadSession(session.id);
    renderSessions();
}

function loadSession(id) {
    atlasState.setActiveSession(id);
    renderSessions();

    elements.messagesContainer.innerHTML = '';
    const session = atlasState.getActiveSession();

    if (session && session.messages.length > 0) {
        session.messages.forEach(msg => {
            renderMessage(msg.role, msg.content, msg.id, msg.rdr, msg.thought, false);
        });
    } else {
        // Show initial greeting
        appendSystemNotification("Sisteme Hoş Geldin, Observer. ATLAS motoru aktif.");
    }

    // Close sidebar on mobile
    if (window.innerWidth <= 1200) {
        elements.sidebar.classList.remove('open');
    }
}

function deleteSession(event, id) {
    event.stopPropagation();
    if (confirm('Sohbet silinsin mi?')) {
        atlasState.deleteSession(id);
        renderSessions();
        if (atlasState.state.activeSessionId) {
            loadSession(atlasState.state.activeSessionId);
        } else {
            startNewChat();
        }
    }
}

// Messaging Logic
async function handleSend() {
    const msgInput = elements.userInput.value.trim();
    if (!msgInput || isProcessing) return;

    // 1. Save to state and clear input
    const userMsg = atlasState.addMessage('user', msgInput);
    renderMessage('user', msgInput, userMsg.id);
    elements.userInput.value = '';

    // Update sidebar if it was the first message
    renderSessions();

    setLoading(true);

    const aiMsgId = Date.now().toString();
    const wrapper = createMessageWrapper('ai', aiMsgId);
    elements.messagesContainer.appendChild(wrapper);
    elements.chatView.scrollTop = elements.chatView.scrollHeight;

    const bubble = wrapper.querySelector('.message-body');
    let fullText = "";
    let capturedThoughtSteps = [];

    try {
        const response = await fetch(`${API_BASE}/api/chat/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: msgInput,
                mode: elements.personaSelect.value,
                session_id: atlasState.state.activeSessionId,
                role: atlasState.state.user.role
            })
        });

        if (!response.body) throw new Error("Stream not supported");

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        // Prepare bubble structure (preserving thought accordion)
        bubble.innerHTML = `
            <div class="thought-container collapsed" id="thought-container-${aiMsgId}">
                <div class="thought-header" onclick="toggleThought('${aiMsgId}')">
                    <span><span class="pulse-thinking"></span><span id="header-text-${aiMsgId}">Atlas Düşünüyor...</span></span>
                    <i class="fas fa-chevron-down"></i>
                </div>
                <div class="thought-content" id="thought-content-${aiMsgId}"></div>
            </div>
            <div class="final-answer" id="answer-${aiMsgId}">...</div>
        `;

        const thoughtHeader = document.getElementById(`header-text-${aiMsgId}`);
        const thoughtContent = document.getElementById(`thought-content-${aiMsgId}`);
        const answerContainer = document.getElementById(`answer-${aiMsgId}`);
        const thoughtContainer = document.getElementById(`thought-container-${aiMsgId}`);
        let thoughtResolved = false;

        let buffer = "";
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            buffer += chunk;

            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                const trimmedLine = line.trim();
                if (trimmedLine.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(trimmedLine.substring(6));

                        if (data.type === 'thought') {
                            const step = data.step;
                            capturedThoughtSteps.push(step);
                            if (!thoughtResolved) {
                                thoughtHeader.innerText = step.content.substring(0, 60) + (step.content.length > 60 ? "..." : "");
                            }
                            thoughtContent.innerHTML += `
                                <div class="thought-step">
                                    <div class="thought-step-title">${step.title}</div>
                                    <div>${step.content}</div>
                                </div>
                            `;
                            elements.chatView.scrollTop = elements.chatView.scrollHeight;
                        }
                        else if (data.type === 'chunk') {
                            if (!thoughtResolved) {
                                thoughtResolved = true;
                                thoughtHeader.innerText = "Atlas Düşünce Süreci";
                                const pulse = thoughtContainer.querySelector('.pulse-thinking');
                                if (pulse) pulse.style.animation = 'none';
                            }
                            fullText += data.content;
                            answerContainer.innerHTML = marked.parse(fullText);
                            elements.chatView.scrollTop = elements.chatView.scrollHeight;
                        }
                        else if (data.type === 'done') {
                            if (data.rdr) {
                                appendRDRTrigger(aiMsgId, data.rdr);
                                // Save to state
                                atlasState.addMessage('assistant', fullText, data.rdr, capturedThoughtSteps);
                            }
                        }
                    } catch (e) { console.error("Parse error", e); }
                }
            }
        }
    } catch (err) {
        bubble.innerHTML = `<span style="color:var(--danger)">🚨 Bağlantı Hatası: ${err.message}</span>`;
    } finally {
        setLoading(false);
    }
}

// Rendering Helpers
function createMessageWrapper(role, id) {
    const wrapper = document.createElement('div');
    wrapper.className = `message-wrapper ${role} chat-content-limit`;
    wrapper.id = `msg-${id}`;

    const avatarIcon = role === 'user' ? 'fa-user-astronaut' : 'fa-brain';
    const name = role === 'user' ? (atlasState.state.user?.name || 'Observer') : 'ATLAS CORE';

    wrapper.innerHTML = `
        <div class="message-header">
            <div class="avatar"><i class="fas ${avatarIcon}"></i></div>
            <div class="sender-info">
                <span class="sender-name">${name}</span>
                <span class="message-time">${utils.formatTime(new Date())}</span>
            </div>
        </div>
        <div class="message-body">...</div>
    `;
    return wrapper;
}

function renderMessage(role, content, id, rdr = null, thought = null, animate = true) {
    const wrapper = createMessageWrapper(role, id);
    if (!animate) wrapper.style.animation = 'none';
    elements.messagesContainer.appendChild(wrapper);

    const body = wrapper.querySelector('.message-body');

    if (role === 'ai' || role === 'assistant') {
        let thoughtHtml = '';
        if (thought && thought.length > 0) {
            thoughtHtml = `
                <div class="thought-container collapsed" id="thought-container-${id}">
                    <div class="thought-header" onclick="toggleThought('${id}')">
                        <span><i class="fas fa-lightbulb"></i> Atlas Düşünce Süreci</span>
                        <i class="fas fa-chevron-down"></i>
                    </div>
                    <div class="thought-content">
                        ${thought.map(t => `
                            <div class="thought-step">
                                <div class="thought-step-title">${t.title}</div>
                                <div>${t.content}</div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        }
        body.innerHTML = thoughtHtml + `<div class="final-answer">${marked.parse(content)}</div>`;
        if (rdr) appendRDRTrigger(id, rdr);
    } else {
        body.innerText = content;
    }

    elements.chatView.scrollTop = elements.chatView.scrollHeight;
}

function appendSystemNotification(text) {
    const div = document.createElement('div');
    div.className = 'system-notification chat-content-limit';
    div.innerHTML = `<p>${text}</p>`;
    elements.messagesContainer.appendChild(div);
}

// RDR / Inspector Logic
function appendRDRTrigger(msgId, rdr) {
    const wrapper = document.getElementById(`msg-${msgId}`);
    if (!wrapper) return;

    // Check role permissions
    const canSeeRDR = ['Developer', 'Tester'].includes(atlasState.state.user.role);

    const trigger = document.createElement('button');
    trigger.className = "rdr-trigger";

    if (!canSeeRDR) {
        trigger.title = "Giriş yetkiniz yok (Developer/Tester Only)";
        trigger.innerHTML = `<i class="fas fa-lock"></i> RDR Locked`;
        trigger.style.opacity = '0.5';
        trigger.style.cursor = 'not-allowed';
    } else {
        trigger.innerHTML = `<i class="fas fa-bolt"></i> DIVE INTO RDR`;
        trigger.onclick = () => showInInspector(rdr);
    }

    wrapper.appendChild(trigger);
}

function showInInspector(rdr) {
    currentRdr = rdr;
    elements.inspector.classList.remove('collapsed');
    elements.inspector.classList.add('open');
    updateRDRPanel(rdr);
}

function updateRDRPanel(rdr) {
    if (!rdr) return;
    const content = elements.rdrContent;
    content.innerHTML = '';

    // Helper to add sections
    const addSection = (title, items) => {
        const sec = document.createElement('div');
        sec.className = 'rdr-sec';
        sec.innerHTML = `<h4>${title}</h4>`;
        items.forEach(item => {
            const row = document.createElement('div');
            row.className = 'rdr-row';
            row.innerHTML = `<span class="label">${item.label}</span><span class="value">${item.value}</span>`;
            sec.appendChild(row);
        });
        content.appendChild(sec);
    };

    addSection('METRICS', [
        { label: 'Latency', value: `${rdr.total_ms}ms` },
        { label: 'Intent', value: rdr.intent.toUpperCase() },
        { label: 'Classification', value: `${rdr.classification_ms}ms` }
    ]);

    if (rdr.task_details) {
        const expertHtml = rdr.task_details.map(t => `
            <div class="expert-card">
                <b>${t.id}</b> [${t.model}] - ${t.duration_ms}ms
            </div>
        `).join('');
        const expSec = document.createElement('div');
        expSec.innerHTML = `<h4>EXPERT DAG</h4> ${expertHtml}`;
        content.appendChild(expSec);
    }
}

// Notifications
async function refreshNotifications() {
    try {
        const res = await fetch(`${API_BASE}/api/notifications/test_user`);
        const data = await res.json();
        const list = data.notifications || [];

        elements.notifCount.innerText = list.length;
        elements.notifCount.style.display = list.length > 0 ? 'block' : 'none';

        if (list.length > 0) {
            elements.notifList.innerHTML = list.map(n => `
                <div class="notif-item">
                    <div class="time">${utils.formatTime(n.timestamp)}</div>
                    <div class="msg">⚠️ ${n.message}</div>
                </div>
            `).join('');
        }
    } catch (e) { }
}

// Global Helpers (exposed to HTML)
window.toggleThought = (id) => {
    const container = document.getElementById(`thought-container-${id}`);
    if (container) container.classList.toggle('collapsed');
};

// UI Triggers
function setupListeners() {
    elements.sendBtn.onclick = handleSend;
    elements.userInput.onkeypress = (e) => { if (e.key === 'Enter') handleSend(); };
    elements.newChatBtn.onclick = startNewChat;

    elements.sidebarToggle.onclick = () => elements.sidebar.classList.toggle('open');
    document.getElementById('closeInspector').onclick = () => elements.inspector.classList.add('collapsed');

    document.getElementById('bellBtn').onclick = () => {
        elements.notifPanel.style.display = elements.notifPanel.style.display === 'block' ? 'none' : 'block';
    };
    document.getElementById('closeNotif').onclick = () => elements.notifPanel.style.display = 'none';

    // Inspector Tabs
    document.getElementById('inspectorTabs').onclick = (e) => {
        if (e.target.classList.contains('tab')) {
            document.querySelectorAll('#inspectorTabs .tab').forEach(t => t.classList.remove('active'));
            e.target.classList.add('active');
            renderInspectorTab(e.target.dataset.tab);
        }
    };
}

function renderInspectorTab(tab) {
    const rdr = currentRdr;
    if (!rdr) return;

    if (tab === 'raw') {
        const isDev = atlasState.state.user.role === 'Developer';
        if (!isDev) {
            elements.rdrContent.innerHTML = `<p class="p-4 text-warning">Bu alanı sadece Geliştiriciler görebilir.</p>`;
            return;
        }
        elements.rdrContent.innerHTML = `<pre class="raw-json">${JSON.stringify(rdr, null, 2)}</pre>`;
    } else {
        updateRDRPanel(rdr); // Basic render for others for now
    }
}

function setLoading(loading) {
    isProcessing = loading;
    elements.sendBtn.disabled = loading;
    elements.statusLabel.innerText = loading ? "REASONING..." : "ENGINE STANDBY";
    elements.statusDot.style.background = loading ? "var(--cyan)" : "var(--matrix-green)";
}
