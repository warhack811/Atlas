// =============================================================================
// Cloudflare Deployment Konfigürasyonu
// LOCAL: API_BASE = '' (same origin)
// PRODUCTION: Aynı Workers'ta frontend ve backend varsa boş bırak
// =============================================================================
const API_BASE = '';

// =============================================================================
// Persona Configuration System
// =============================================================================
const PERSONA_CONFIG = {
    standard: {
        name: 'Standart',
        shortName: 'Std',
        icon: '<i class="fa-solid fa-bolt"></i>',
        description: 'Dengeli ve profesyonel yaklaşım',
        color: '#3b82f6'
    },
    professional: {
        name: 'Kurumsal',
        shortName: 'Pro',
        icon: '<i class="fa-solid fa-briefcase"></i>',
        description: 'Formal ve ciddi ton',
        color: '#6366f1'
    },
    kanka: {
        name: 'Kanka',
        shortName: 'Knk',
        icon: '<i class="fa-solid fa-handshake"></i>',
        description: 'Samimi ve rahat sohbet',
        color: '#f59e0b'
    },
    creative: {
        name: 'Sanatçı',
        shortName: 'Art',
        icon: '<i class="fa-solid fa-palette"></i>',
        description: 'Yaratıcı ve ilham verici',
        color: '#a855f7'
    },
    concise: {
        name: 'Net & Öz',
        shortName: 'Öz',
        icon: '<i class="fa-solid fa-bullseye"></i>',
        description: 'Kısa ve net cevaplar',
        color: '#ef4444'
    },
    sincere: {
        name: 'İçten Dost',
        shortName: 'İçt',
        icon: '<i class="fa-solid fa-heart"></i>',
        description: 'Samimi ve anlayışlı',
        color: '#06b6d4'
    },
    detailed: {
        name: 'Eğitmen',
        shortName: 'Eğt',
        icon: '<i class="fa-solid fa-book"></i>',
        description: 'Detaylı ve öğretici',
        color: '#10b981'
    },
    girlfriend: {
        name: 'Sevgili',
        shortName: 'Sev',
        icon: '<i class="fa-solid fa-heart-pulse"></i>',
        description: 'Sevgi dolu ve şefkatli',
        color: '#ec4899'
    },
    friendly: {
        name: 'Yardımsever',
        shortName: 'Yrd',
        icon: '<i class="fa-solid fa-face-smile"></i>',
        description: 'Dostane ve yardımsever',
        color: '#84cc16'
    }
};

// Persona state management
let currentPersona = 'standard';
let isPersonaDropdownOpen = false;

const chatView = document.getElementById('chatView');
const userInput = document.getElementById('userInput');
const personaSelect = document.getElementById('personaSelect');
const statusLabel = document.getElementById('statusLabel');
const statusDot = document.getElementById('statusDot');
const notifCountBadge = document.getElementById('notifCount');
const notifList = document.getElementById('notifList');
const notifPanel = document.getElementById('notifPanel');
const fileInput = document.getElementById('fileInput');

let isProcessing = false;
let currentUser = null;
let activeSessionId = localStorage.getItem('atlas_active_session') || `session-${Date.now()}`;
let sessions = JSON.parse(localStorage.getItem('atlas_sessions') || '[]');

// --- Auth Logic ---
async function checkAuthStatus() {
    try {
        const res = await fetch(`${API_BASE}/api/auth/me`);
        if (res.ok) {
            currentUser = await res.json();
            showLoggedIn();
        } else {
            currentUser = null;
            showLoggedOut();
        }
    } catch (e) {
        console.error("Auth check failed", e);
    }
}

async function handleLogin() {
    const u = document.getElementById('loginUser').value;
    const p = document.getElementById('loginPass').value;
    const err = document.getElementById('loginError');

    try {
        const res = await fetch(`${API_BASE}/api/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: u, password: p })
        });

        if (res.ok) {
            await checkAuthStatus();
            // Close forced modal
            const loginModal = document.getElementById('loginModal');
            if (loginModal) {
                loginModal.classList.remove('forced');
                loginModal.style.display = 'none';
            }
        } else {
            err.innerText = "❌ Geçersiz kimlik bilgileri.";
        }
    } catch (e) {
        err.innerText = "🚨 Bağlantı hatası.";
    }
}

async function handleLogout() {
    await fetch(`${API_BASE}/api/auth/logout`, { method: 'POST' });
    currentUser = null;
    showLoggedOut();
}

function showLoggedIn() {
    // Hide login modal
    const loginModal = document.getElementById('loginModal');
    if (loginModal) {
        loginModal.classList.remove('forced');
        loginModal.style.display = 'none';
    }

    // Enable input
    document.getElementById('userInput').disabled = false;

    // Update dropdown trigger
    const userDropdownName = document.getElementById('userDropdownName');
    if (userDropdownName && currentUser) {
        userDropdownName.innerText = currentUser.username;
    }

    // Show/hide dropdown menu items
    const logoutMenuItem = document.getElementById('logoutMenuItem');
    const loginMenuItem = document.getElementById('loginMenuItem');
    if (logoutMenuItem) logoutMenuItem.style.display = 'flex';
    if (loginMenuItem) loginMenuItem.style.display = 'none';

    initSessions();
}

function showLoggedOut() {
    // Force show login modal (unclosable)
    const loginModal = document.getElementById('loginModal');
    if (loginModal) {
        loginModal.classList.add('forced');
        loginModal.style.display = 'flex';
    }

    // Disable input
    document.getElementById('userInput').disabled = true;

    // Update dropdown trigger
    const userDropdownName = document.getElementById('userDropdownName');
    if (userDropdownName) {
        userDropdownName.innerText = 'Guest';
    }

    // Show/hide dropdown menu items
    const logoutMenuItem = document.getElementById('logoutMenuItem');
    const loginMenuItem = document.getElementById('loginMenuItem');
    if (logoutMenuItem) logoutMenuItem.style.display = 'none';
    if (loginMenuItem) loginMenuItem.style.display = 'flex';

    initSessions();
}

// --- Chat Management Logic ---
function initSessions() {
    // Namespace sessions by user
    const key = currentUser ? `atlas_sessions_v1::${currentUser.username}` : `atlas_sessions_v1::anon`;
    sessions = JSON.parse(localStorage.getItem(key) || '[]');
    activeSessionId = localStorage.getItem(`${key}::active`) || `session-${Date.now()}`;
    renderSessions();
}

function saveSessions() {
    const key = currentUser ? `atlas_sessions_v1::${currentUser.username}` : `atlas_sessions_v1::anon`;
    localStorage.setItem(key, JSON.stringify(sessions));
    localStorage.setItem(`${key}::active`, activeSessionId);
}

function renderSessions() {
    // PHASE 4: Render session cards in sidebar instead of dropdown
    const sessionList = document.getElementById('sessionList');
    if (!sessionList) return; // Fallback for compatibility

    if (sessions.length === 0) {
        if (!sessions.find(s => s.id === activeSessionId)) {
            sessions.push({ id: activeSessionId, title: "Mevcut Sohbet", date: new Date().toISOString() });
        }
    }

    // Render session cards
    sessionList.innerHTML = sessions.map(s => {
        const isActive = s.id === activeSessionId;
        const timeAgo = getTimeAgo(new Date(s.date));
        const preview = s.title.length > 30 ? s.title.substring(0, 30) + '...' : s.title;

        return `
                    <div class="session-card ${isActive ? 'active' : ''}" onclick="switchChat('${s.id}')">
                        <div class="session-icon">📝</div>
                        <div class="session-info">
                            <div class="session-title">${s.title}</div>
                            <div class="session-preview">${preview}</div>
                            <div class="session-meta">
                                <span class="timestamp">${timeAgo}</span>
                            </div>
                        </div>
                        <div class="session-actions">
                            ${isActive ? '<span class="active-badge">ACTIVE</span>' : ''}
                            <button class="btn-delete" onclick="event.stopPropagation(); deleteChat('${s.id}')" title="Delete">🗑️</button>
                        </div>
                    </div>
                `;
    }).join('');

    saveSessions();
}

// Helper function for time ago display
function getTimeAgo(date) {
    const seconds = Math.floor((new Date() - date) / 1000);
    if (seconds < 60) return 'Şimdi';
    if (seconds < 3600) return `${Math.floor(seconds / 60)} dk önce`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)} saat önce`;
    return `${Math.floor(seconds / 86400)} gün önce`;
}

// PHASE 3: Toggle sidebar for mobile
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    if (sidebar) {
        sidebar.classList.toggle('open');
    }
}

function newChat() {
    activeSessionId = `session-${Date.now()}`;
    sessions.unshift({ id: activeSessionId, title: "Yeni Sohbet", date: new Date().toISOString() });
    renderSessions();
    chatView.innerHTML = `
                <div class="message-wrapper ai">
                    <div class="bubble">
                        <h3>Sisteme Hoş Geldin, Observer.</h3>
                        <p>Yeni bir sohbet oturumu başlatıldı. Analiz hazır.</p>
                    </div>
                </div>
            `;
    appendSystemNotification("✨ Yeni sohbet başlatıldı.");
}

function switchChat(id) {
    if (!id || id === activeSessionId) return;
    activeSessionId = id;
    saveSessions();
    chatView.innerHTML = '';
    appendSystemNotification(`🔄 Sohbet oturumu değiştirildi: ${sessions.find(s => s.id === id)?.title || id}`);
}

function deleteChat(sessionId) {
    // PHASE 4: Accept session ID parameter for individual deletion
    const idToDelete = sessionId || activeSessionId;
    sessions = sessions.filter(s => s.id !== idToDelete);

    // If deleted active session, switch to first available or create new
    if (idToDelete === activeSessionId) {
        activeSessionId = sessions.length > 0 ? sessions[0].id : `session-${Date.now()}`;
        if (sessions.length === 0) sessions.push({ id: activeSessionId, title: "Yeni Sohbet", date: new Date().toISOString() });
        chatView.innerHTML = '';
    }

    renderSessions();
    appendSystemNotification("🗑️ Sohbet silindi.");
}

function clearAllChats() {
    if (!confirm("Tüm sohbetleri temizlemek istiyor musunuz?")) return;
    sessions = [];
    activeSessionId = `session-${Date.now()}`;
    renderSessions();
    chatView.innerHTML = '';
    appendSystemNotification("🧹 Tüm geçmiş temizlendi.");
}

function updateSessionTitle(msg) {
    const current = sessions.find(s => s.id === activeSessionId);
    if (current && (current.title === "Yeni Sohbet" || current.title === "Mevcut Sohbet")) {
        current.title = msg.substring(0, 25) + (msg.length > 25 ? "..." : "");
        renderSessions();
    }
}

// Init Sessions
renderSessions();

async function refreshNotifications() {
    try {
        const url = `${API_BASE}/api/notifications?session_id=${activeSessionId}${currentUser ? `&user_id=${currentUser.username}` : ''}`;
        const res = await fetch(url);
        const data = await res.json();
        const list = data.notifications || [];

        if (list.length > 0) {
            // Update both badges
            const countText = list.length.toString();
            if (notifCountBadge) { // Null check
                notifCountBadge.innerText = countText;
                notifCountBadge.style.display = 'block';
            }
            const notifCountDropdown = document.getElementById('notifCountDropdown');
            if (notifCountDropdown) {
                notifCountDropdown.innerText = countText;
                notifCountDropdown.style.display = 'block';
            }

            notifList.innerHTML = list.map(n => `
                        <div class="notif-item">
                            <div class="time">${new Date(n.timestamp).toLocaleTimeString()}</div>
                            <div class="msg">⚠️ ${n.message}</div>
                        </div>
                    `).join('');
        } else {
            if (notifCountBadge) { // Null check
                notifCountBadge.style.display = 'none';
            }
            const notifCountDropdown = document.getElementById('notifCountDropdown');
            if (notifCountDropdown) {
                notifCountDropdown.style.display = 'none';
            }
        }
    } catch (e) {
        console.error("Notif fetch error", e);
    }
}

function toggleNotifications() {
    const current = notifPanel.style.display;
    notifPanel.style.display = current === 'block' ? 'none' : 'block';
}

userInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') handleSend();
});

fileInput.addEventListener('change', async (e) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    for (const file of files) {
        try {
            appendSystemNotification(`📸 Görsel Analiz Ediliyor: ${file.name}...`);

            const formData = new FormData();
            formData.append('file', file);

            const res = await fetch(`${API_BASE}/api/upload?session_id=${activeSessionId}`, {
                method: 'POST',
                body: formData
            });

            const rawResponse = await res.text();
            let data;
            try {
                data = JSON.parse(rawResponse);
            } catch (jsonErr) {
                appendSystemNotification(`❌ Sunucu Hatası (${res.status}): ${rawResponse.substring(0, 100)}...`);
                return;
            }

            if (data.status === 'success') {
                // Check if the backend returned a structural error message
                if (data.analysis && data.analysis.includes("Sistem Yoğunluğu/Kota")) {
                    appendSystemNotification(`⚠️ Görsel İşlenemedi: (${file.name}) - Kota Dolu`);
                } else {
                    appendSystemNotification(`📸 Görsel Analiz Edildi: ${file.name}`);
                }
            } else {
                const errorDetail = data.message || "Bilinmeyen hata";
                appendSystemNotification(`⚠️ Yükleme Hatası: ${file.name} - ${errorDetail}`);
                console.error("Upload Error Traceback:", data.traceback || "No traceback");
            }
        } catch (err) {
            appendSystemNotification(`❌ Kritik Bağlantı Hatası: ${err.message}`);
        }
    }
    e.target.value = ''; // Reset
});

async function handleSend() {
    const msg = userInput.value.trim();
    if (!msg || isProcessing) return;

    setLoading(true);
    updateSessionTitle(msg);
    appendMessage('user', msg);
    userInput.value = '';

    const aiMsgId = Date.now();
    const wrapper = document.createElement('div');
    wrapper.className = `message-wrapper ai`;
    wrapper.innerHTML = `<div class="bubble" id="bubble-${aiMsgId}">...</div>`;
    chatView.appendChild(wrapper);
    chatView.scrollTop = chatView.scrollHeight;

    let fullText = "";
    try {
        const response = await fetch(`${API_BASE}/api/chat/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: msg,
                mode: personaSelect.value,
                session_id: activeSessionId
            })
        });

        if (!response.body) throw new Error("Stream not supported");

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        const bubble = document.getElementById(`bubble-${aiMsgId}`);
        bubble.innerHTML = `
                    <details class="ai-thought" id="thought-container-${aiMsgId}">
                        <summary id="thought-header-${aiMsgId}">
                            <span class="pulse-thinking"></span>
                            <span id="header-text-${aiMsgId}">Atlas Düşünüyor...</span>
                        </summary>
                        <div class="thought-content" id="thought-content-${aiMsgId}"></div>
                    </details>
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
            buffer = lines.pop(); // Keep the partial line for the next chunk

            for (const line of lines) {
                const trimmedLine = line.trim();
                if (trimmedLine.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(trimmedLine.substring(6));
                        if (data.type === 'plan') {
                            statusLabel.innerText = "PLANNING: " + (data.intent || "GENERAL").toUpperCase();
                        } else if (data.type === 'thought') {
                            const step = data.step;
                            // Başlığı güncelle (Eğer henüz cevap gelmediyse)
                            if (!thoughtResolved) {
                                thoughtHeader.innerText = step.content.substring(0, 60) + (step.content.length > 60 ? "..." : "");
                            }
                            const stepHtml = `
                                        <div class="thought-step">
                                            <div class="thought-step-title">${step.title}</div>
                                            <div>${step.content}</div>
                                        </div>
                                    `;
                            thoughtContent.innerHTML += stepHtml;
                            chatView.scrollTop = chatView.scrollHeight;
                        } else if (data.type === 'chunk') {
                            if (!thoughtResolved) {
                                thoughtResolved = true;
                                thoughtHeader.innerText = "Atlas Düşünce Sistemi";
                                const pulse = thoughtContainer.querySelector('.pulse-thinking');
                                if (pulse) pulse.style.animation = 'none';
                                if (pulse) pulse.style.opacity = '0.5';
                            }
                            fullText += data.content;
                            answerContainer.innerHTML = marked.parse(fullText);
                            chatView.scrollTop = chatView.scrollHeight;
                        } else if (data.type === 'tasks_done') {
                            statusLabel.innerText = "SYNTHESIZING...";
                        } else if (data.type === 'done') {
                            console.log("RDR Received:", data.rdr);
                            if (data.rdr) {
                                appendRDRTrigger(aiMsgId, data.rdr);
                            }
                        } else if (data.type === 'error') {
                            console.error("Stream error data:", data.content);
                        }
                    } catch (e) {
                        console.error("JSON parse error in line:", line, e);
                    }
                }
            }
        }
    } catch (err) {
        const bubble = document.getElementById(`bubble-${aiMsgId}`);
        bubble.innerHTML = `<span style="color:var(--danger)">🚨 Sistem hatası: ${err.message}</span>`;
    } finally {
        setLoading(false);
    }
}

function toggleThought(id) {
    const container = document.getElementById(`thought-container-${id}`);
    if (container && container.tagName === 'DETAILS') {
        // Native details element handles toggle automatically
        // This function kept for compatibility
    } else if (container) {
        container.classList.toggle('collapsed');
    }
}

function appendRDRTrigger(msgId, rdr) {
    const bubble = document.getElementById(`bubble-${msgId}`);
    if (!bubble) return; // Safety check

    const trigger = document.createElement('div');
    trigger.className = "rdr-trigger";
    trigger.onclick = () => toggleInspector(msgId);
    trigger.innerHTML = `<span><i class="fa-solid fa-bolt"></i> RDR Raporu [Observability]</span>`;

    const insp = document.createElement('div');
    insp.className = "inspector-panel";
    insp.id = `insp-${msgId}`;
    insp.innerHTML = `
                <div class="inspector-tabs">
                    <div class="tab active" onclick="switchTab(event, '${msgId}', 'summ')">Özet</div>
                    <div class="tab" onclick="switchTab(event, '${msgId}', 'orch')"><i class="fa-solid fa-brain"></i> Orhc</div>
                    <div class="tab" onclick="switchTab(event, '${msgId}', 'tool')"><i class="fa-solid fa-wrench"></i> Tools</div>
                    <div class="tab" onclick="switchTab(event, '${msgId}', 'safe')"><i class="fa-solid fa-shield"></i> Safe</div>
                    <div class="tab" onclick="switchTab(event, '${msgId}', 'synth')"><i class="fa-solid fa-masks-theater"></i> Synth</div>
                    <div class="tab" style="color:var(--danger)" onclick="switchTab(event, '${msgId}', 'err')"><i class="fa-solid fa-triangle-exclamation"></i> Hata</div>
                </div>
                
                <div class="tab-content active" id="summ-${msgId}">
                    <div class="rdr-grid">
                        <div class="stat-card"><div class="stat-label">Toplam Süre</div><div class="stat-value">${rdr.total_ms || 0}ms</div></div>
                        <div class="stat-card"><div class="stat-label">Orkestratör</div><div class="stat-value" style="font-size:0.6rem">${rdr.orchestrator_model || "N/A"}</div></div>
                        <div class="stat-card"><div class="stat-label">Sentezleyici</div><div class="stat-value" style="font-size:0.6rem">${rdr.synthesizer_model || "N/A"}</div></div>
                        <div class="stat-card">
                            <div class="stat-label">Güvenlik</div>
                            <div class="stat-value" style="font-size:0.6rem; color:${rdr.safety_passed ? 'var(--matrix-green)' : 'var(--danger)'}">
                                ${rdr.safety_passed ? 'TEMİZ' : 'İHLAL'} [${rdr.safety_model || "Regex"}]
                            </div>
                        </div>
                    </div>
                    
                    <div style="margin-top:15px; background:rgba(0,0,0,0.2); border-radius:8px; padding:10px; border:1px solid var(--border);">
                        <div style="font-size:0.7rem; color:var(--text-dim); margin-bottom:8px; font-weight:700; text-transform:uppercase; letter-spacing:1px;">Performans ve Model Kırılımı</div>
                        <div style="display:grid; grid-template-columns: 1fr; gap:8px; font-size:0.75rem;">
                            <div class="timing-item"><i class="fa-solid fa-shield"></i> Güvenlik: <span style="color:var(--matrix-green)">${rdr.safety_ms || 0}ms</span> <span style="opacity:0.6; font-size:0.65rem;">[${rdr.safety_model || "Regex"}]</span></div>
                            <div class="timing-item"><i class="fa-solid fa-brain"></i> Orkestrasyon: <span style="color:var(--matrix-green)">${rdr.classification_ms || 0}ms</span> <span style="opacity:0.6; font-size:0.65rem;">[${rdr.orchestrator_model || "N/A"}]</span></div>
                            <div class="timing-item"><i class="fa-solid fa-cog"></i> Yürütme (Tool): <span style="color:var(--matrix-green)">${rdr.dag_execution_ms || 0}ms</span> <span style="opacity:0.6; font-size:0.65rem;">[Expert DAG]</span></div>
                            <div class="timing-item"><i class="fa-solid fa-masks-theater"></i> Sentez: <span style="color:var(--matrix-green)">${rdr.synthesis_ms || 0}ms</span> <span style="opacity:0.6; font-size:0.65rem;">[${rdr.synthesizer_model || "N/A"}]</span></div>
                            <div class="timing-item"><i class="fa-solid fa-check"></i> Kalite: <span style="color:var(--matrix-green)">${rdr.quality_ms || 0}ms</span></div>
                        </div>
                    </div>
                </div>
                
                <div class="tab-content" id="orch-${msgId}">
                    <div class="stat-label">Intent: <span style="color:var(--cyan)">${rdr.intent || "Unknown"}</span></div>
                    <div class="stat-label" style="margin-top:10px">Graf Hafıza Bağlamı:</div>
                    <div style="font-size:0.7rem; color:var(--matrix-green); background:rgba(0,255,150,0.1); padding:5px; border-radius:4px; margin-bottom:10px; border:1px dashed var(--matrix-green);">
                        ${rdr.full_context_injection || "Hafıza vuruşu (hit) yok."}
                    </div>
                    <div class="stat-label">Mantıksal Karar Gerekçesi (Reasoning):</div>
                    <div style="font-size:0.75rem; color:var(--cyan); background:rgba(0,255,255,0.05); padding:10px; border-radius:8px; margin-bottom:10px; border:1px solid rgba(0,255,255,0.2); line-height:1.4;">
                        ${rdr.orchestrator_reasoning || "Düşünce süreci loglanmadı."}
                    </div>
                    <div class="stat-label">Raw Orchestrator Prompt:</div>
                    <pre class="code-block">${rdr.orchestrator_prompt || "Loglanmadı"}</pre>
                </div>

                <div class="tab-content" id="tool-${msgId}">
                    <div id="toolList-${msgId}">
                        ${(rdr.task_details || []).map(t => `
                            <div style="margin-bottom:12px; border-left: 2px solid var(--matrix-green); padding-left:10px;">
                                <div style="font-size:0.75rem; font-weight:700;">Task ID: ${t.id} - ${t.status === 'failed' ? '❌' : '✅'}</div>
                                <div style="font-size:0.65rem; color:var(--text-dim)">Model: ${t.model || "N/A"} | Süre: <span style="color:var(--matrix-green)">${t.duration_ms || 0}ms</span></div>
                                <pre class="code-block" style="margin-top:5px; max-height:100px;">${JSON.stringify(t.result || {}, null, 2)}</pre>
                            </div>
                        `).join('') || "Hiçbir araç tetiklenmedi."}
                    </div>
                </div>

                <div class="tab-content" id="safe-${msgId}">
                    <div class="stat-label">Safety Status: <span style="color:${rdr.safety_passed ? 'var(--matrix-green)' : 'var(--danger)'}">${rdr.safety_passed ? 'PASSED' : 'BLOCKED'}</span></div>
                    <div class="stat-label" style="margin-top:10px">Security Logs:</div>
                    <pre class="code-block">${(rdr.safety_issues || []).map(i => `[${i.type}] ${i.details}`).join('\n') || "No safety issues detected."}</pre>
                    <div class="stat-label" style="margin-top:10px">PII Filter:</div>
                    <div class="stat-value" style="font-size:0.7rem; color:var(--text-dim)">${rdr.pii_redacted ? '⚠️ Redaction Applied' : '✅ Clear'}</div>
                </div>

                <div class="tab-content" id="synth-${msgId}">
                    <div class="stat-label">Seçilen Persona: <span style="color:var(--cyan)">${rdr.style_persona || "N/A"}</span></div>
                    <div class="stat-label">Style Preset: <span style="color:var(--cyan)">${rdr.style_preset || "N/A"}</span></div>
                    <div class="stat-label" style="margin-top:10px">Sentezleyici Prompt:</div>
                    <pre class="code-block">${rdr.synthesizer_prompt || "Bilinmiyor"}</pre>
                </div>
                <div class="tab-content" id="err-${msgId}">
                    <div class="stat-label" style="color:var(--danger)">Teknik Hata Kayıtları:</div>
                    <div id="errorList-${msgId}" style="margin-top:10px">
                        ${(rdr.technical_errors || []).map(e => `
                            <div style="margin-bottom:12px; border-left: 2px solid var(--danger); padding-left:10px;">
                                <div style="font-size:0.7rem; color:var(--text-dim)">${e.timestamp}</div>
                                <div style="font-size:0.8rem; color:var(--text-main); margin-top:4px;">${e.error}</div>
                                <pre class="code-block" style="margin-top:5px; max-height:100px; color:var(--danger)">${e.traceback}</pre>
                            </div>
                        `).join('') || "Herhangi bir teknik hata kaydedilmedi."}
                    </div>
                </div>
             `;

    // CRITICAL: Append to bubble, not wrapper!
    bubble.appendChild(trigger);
    bubble.appendChild(insp);
}

function setLoading(loading) {
    isProcessing = loading;
    document.getElementById('sendBtn').disabled = loading;
    statusLabel.innerText = loading ? "REASONING..." : "ENGINE STANDBY";
    statusDot.style.background = loading ? "var(--cyan)" : "var(--matrix-green)";
}

function appendMessage(role, text) {
    const wrapper = document.createElement('div');
    wrapper.className = `message-wrapper ${role} `;
    wrapper.innerHTML = `<div class="bubble">${marked.parse(text)}</div>`;
    chatView.appendChild(wrapper);
    chatView.scrollTop = chatView.scrollHeight;
}

function appendSystemNotification(text) {
    const wrapper = document.createElement('div');
    wrapper.className = 'message-wrapper ai';
    wrapper.innerHTML = `
                <div class="bubble" style="background:rgba(255,255,255,0.05); color:var(--text-dim); border:1px solid var(--border); font-style:italic; font-size:0.8rem; padding:8px 12px; border-radius:8px; align-self:flex-start;">
                    ${text}
                </div>
            `;
    chatView.appendChild(wrapper);
    chatView.scrollTop = chatView.scrollHeight;
}



function toggleInspector(id) {
    const insp = document.getElementById(`insp-${id}`);
    insp.style.display = insp.style.display === 'block' ? 'none' : 'block';
    chatView.scrollTop = chatView.scrollHeight;
}

function switchTab(event, msgId, tabName) {
    // Deactivate all tabs in this message
    const parent = event.target.parentElement;
    parent.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    event.target.classList.add('active');

    // Hide all content blocks
    const insp = document.getElementById(`insp-${msgId}`);
    insp.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

    // Show selected
    document.getElementById(`${tabName}-${msgId}`).classList.add('active');
}

// PHASE 6: Input-Integrated Persona Selection Functions
function selectPersona(persona) {
    // Update current persona state
    currentPersona = persona;

    // Update hidden select for backend compatibility
    document.getElementById('personaSelect').value = persona;

    // Update input-integrated UI
    updatePersonaInputDisplay(persona);

    // Update old pill states for backward compatibility (if they exist)
    document.querySelectorAll('.persona-pill').forEach(pill => {
        pill.classList.remove('active');
    });
    document.querySelectorAll('.dropdown-item').forEach(item => {
        item.classList.remove('active');
    });

    // Update new dropdown items
    document.querySelectorAll('.persona-dropdown-item').forEach(item => {
        item.classList.remove('active');
    });

    const selectedItem = document.querySelector(`[data-persona="${persona}"]`);
    if (selectedItem) {
        selectedItem.classList.add('active');
    }

    // Close dropdown
    closePersonaInputDropdown();
}

function updatePersonaInputDisplay(persona) {
    const config = PERSONA_CONFIG[persona];
    if (!config) return;

    const iconElement = document.getElementById('currentPersonaIcon');
    const shortNameElement = document.getElementById('currentPersonaShort');

    if (iconElement) iconElement.textContent = config.icon;
    if (shortNameElement) shortNameElement.textContent = config.shortName;
}

function togglePersonaInput() {
    console.log('togglePersonaInput called');
    const dropdown = document.getElementById('personaInputDropdown');
    const btn = document.getElementById('personaInputBtn');

    console.log('dropdown:', dropdown, 'btn:', btn);

    if (!dropdown || !btn) {
        console.log('Elements not found!');
        return;
    }

    if (isPersonaDropdownOpen) {
        console.log('Closing dropdown');
        closePersonaInputDropdown();
    } else {
        console.log('Opening dropdown');
        openPersonaInputDropdown();
    }
}

// Keyboard navigation for persona selector
document.addEventListener('keydown', (e) => {
    if (!isPersonaDropdownOpen) return;

    const dropdown = document.getElementById('personaInputDropdown');
    if (!dropdown) return;

    const items = dropdown.querySelectorAll('.persona-dropdown-item');
    const currentActive = dropdown.querySelector('.persona-dropdown-item.keyboard-focus');
    let currentIndex = currentActive ? Array.from(items).indexOf(currentActive) : -1;

    switch (e.key) {
        case 'ArrowDown':
            e.preventDefault();
            if (currentActive) currentActive.classList.remove('keyboard-focus');
            currentIndex = (currentIndex + 1) % items.length;
            items[currentIndex].classList.add('keyboard-focus');
            items[currentIndex].scrollIntoView({ block: 'nearest' });
            break;

        case 'ArrowUp':
            e.preventDefault();
            if (currentActive) currentActive.classList.remove('keyboard-focus');
            currentIndex = currentIndex <= 0 ? items.length - 1 : currentIndex - 1;
            items[currentIndex].classList.add('keyboard-focus');
            items[currentIndex].scrollIntoView({ block: 'nearest' });
            break;

        case 'Enter':
        case ' ':
            e.preventDefault();
            if (currentActive) {
                const persona = currentActive.getAttribute('data-persona');
                if (persona) selectPersona(persona);
            }
            break;

        case 'Escape':
            e.preventDefault();
            closePersonaInputDropdown();
            document.getElementById('personaInputBtn')?.focus();
            break;
    }
});

function openPersonaInputDropdown() {
    const dropdown = document.getElementById('personaInputDropdown');
    const btn = document.getElementById('personaInputBtn');

    if (!dropdown || !btn) return;

    dropdown.classList.add('open');
    btn.classList.add('open');
    btn.setAttribute('aria-expanded', 'true');
    isPersonaDropdownOpen = true;

    // Update active state
    const activeItem = dropdown.querySelector(`[data-persona="${currentPersona}"]`);
    if (activeItem) {
        activeItem.classList.add('active');
        activeItem.setAttribute('aria-selected', 'true');
    }
}

function closePersonaInputDropdown() {
    const dropdown = document.getElementById('personaInputDropdown');
    const btn = document.getElementById('personaInputBtn');

    if (!dropdown || !btn) return;

    dropdown.classList.remove('open');
    btn.classList.remove('open');
    btn.setAttribute('aria-expanded', 'false');
    isPersonaDropdownOpen = false;

    // Clear keyboard focus
    const keyboardFocus = dropdown.querySelector('.keyboard-focus');
    if (keyboardFocus) keyboardFocus.classList.remove('keyboard-focus');
}

// Legacy function for backward compatibility
function togglePersonaDropdown() {
    const dropdown = document.getElementById('personaDropdownMenu');
    if (dropdown) {
        dropdown.classList.toggle('open');
    }
}

// Analytics Modal Functions
function openAnalytics() {
    document.getElementById('analyticsModal').classList.add('open');
}

function closeAnalytics() {
    document.getElementById('analyticsModal').classList.remove('open');
}

// Header Dropdown Toggle
function toggleHeaderDropdown() {
    const menu = document.getElementById('headerDropdownMenu');
    if (menu) {
        menu.classList.toggle('open');
    }
}

// Close dropdowns when clicking outside
document.addEventListener('click', (e) => {
    // Close input-integrated persona dropdown
    const personaInputDropdown = document.getElementById('personaInputDropdown');
    const personaInputBtn = document.getElementById('personaInputBtn');
    if (personaInputDropdown && !personaInputDropdown.contains(e.target) && !personaInputBtn?.contains(e.target)) {
        closePersonaInputDropdown();
    }

    // Legacy persona dropdown (for backward compatibility)
    const dropdown = document.getElementById('personaDropdownMenu');
    const moreBtn = document.querySelector('.more-btn');
    if (dropdown && !dropdown.contains(e.target) && !moreBtn?.contains(e.target)) {
        dropdown.classList.remove('open');
    }

    // Header dropdown
    const headerMenu = document.getElementById('headerDropdownMenu');
    const headerTrigger = document.getElementById('userDropdownTrigger');
    if (headerMenu && !headerMenu.contains(e.target) && !headerTrigger?.contains(e.target)) {
        headerMenu.classList.remove('open');
    }
});


// Global Exposure
window.newChat = newChat;
window.switchChat = switchChat;
window.deleteChat = deleteChat;
window.clearAllChats = clearAllChats;
window.toggleNotifications = toggleNotifications;
window.toggleSidebar = toggleSidebar;
window.toggleThought = toggleThought;
window.toggleInspector = toggleInspector;
window.switchTab = switchTab;
window.handleSend = handleSend;
window.handleLogin = handleLogin;
window.handleLogout = handleLogout;
window.selectPersona = selectPersona;
window.togglePersonaInput = togglePersonaInput;
window.togglePersonaDropdown = togglePersonaDropdown; // Legacy
window.openAnalytics = openAnalytics;
window.closeAnalytics = closeAnalytics;
window.toggleHeaderDropdown = toggleHeaderDropdown;

// Initialize persona UI immediately
function initPersonaUI() {
    console.log('Initializing persona UI...');
    // Set initial persona display
    updatePersonaInputDisplay(currentPersona);

    // Mark initial active persona in dropdown
    const activeItem = document.querySelector(`[data-persona="${currentPersona}"]`);
    if (activeItem) {
        activeItem.classList.add('active');
    }
    console.log('Persona UI initialized');
}

// Init
checkAuthStatus();
setInterval(refreshNotifications, 60000); // 1 min
refreshNotifications();

// Initialize persona UI when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPersonaUI);
} else {
    initPersonaUI();
}
