// ATLAS Router Sandbox - Chat UI
// =============================================================================
// Cloudflare Deployment Konfigürasyonu
// =============================================================================
// LOCAL: API_BASE = '' (same origin - backend aynı sunucuda)
// PRODUCTION: API_BASE = 'https://atlas-sandbox.YOUR_SUBDOMAIN.workers.dev'
//
// Deployment sonrası aşağıdaki URL'i Workers URL'iniz ile değiştirin:
// =============================================================================

const API_BASE = window.location.hostname === 'localhost'
    ? ''  // Local development - same origin
    : '';  // Production - Aynı Workers'ta çalışıyorsa boş bırak
// : 'https://atlas-sandbox.YOUR_SUBDOMAIN.workers.dev'; // Farklı domain ise uncomment et

// DOM Elements
const messagesEl = document.getElementById('messages');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const mockModeCheckbox = document.getElementById('mockMode');
const rdrContent = document.getElementById('rdrContent');
const stylePresetSelect = document.getElementById('stylePreset');

// Style Presets
const STYLE_PRESETS = {
    'professional': { persona: 'professional', tone: 'formal', length: 'medium', emoji: 'none', detail: 'balanced', preset: 'professional' },
    'friendly': { persona: 'friendly', tone: 'casual', length: 'medium', emoji: 'minimal', detail: 'balanced', preset: 'friendly', mirror_hitap: true },
    'kanka': { persona: 'kanka', tone: 'kanka', length: 'medium', emoji: 'high', detail: 'balanced', preset: 'kanka', mirror_hitap: true },
    'girlfriend': { persona: 'girlfriend', tone: 'kanka', length: 'medium', emoji: 'high', detail: 'balanced', preset: 'girlfriend', mirror_hitap: true },
    'concise': { persona: 'expert', tone: 'formal', length: 'short', emoji: 'none', detail: 'summary', preset: 'concise' },
    'detailed': { persona: 'teacher', tone: 'casual', length: 'detailed', emoji: 'minimal', detail: 'comprehensive', preset: 'detailed' },
    'standard': { persona: 'friendly', tone: 'casual', length: 'medium', emoji: 'minimal', detail: 'balanced', preset: 'standard' },
    'sincere': { persona: 'sincere', tone: 'casual', length: 'medium', emoji: 'high', detail: 'balanced', preset: 'sincere' },
    'creative': { persona: 'creative', tone: 'casual', length: 'detailed', emoji: 'minimal', detail: 'comprehensive', preset: 'creative' }
};

// State
let isLoading = false;
let sessionId = localStorage.getItem('atlas_session_id') || null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !isLoading) {
            sendMessage();
        }
    });

    // Check health
    checkHealth();

    // Show session ID if exists
    if (sessionId) {
        console.log('Session restored:', sessionId);
    }
});

async function checkHealth() {
    try {
        const res = await fetch(`${API_BASE}/api/health`);
        const data = await res.json();

        if (data.available_keys === 0) {
            mockModeCheckbox.checked = true;
            addSystemMessage('⚠️ API key bulunamadı. Mock mode aktif.');
        } else {
            console.log(`✅ ${data.available_keys} API key(s) available`);
        }
    } catch (e) {
        console.error('Health check failed:', e);
    }
}

async function sendMessage() {
    const message = messageInput.value.trim();
    if (!message || isLoading) return;

    // Clear welcome message
    const welcome = messagesEl.querySelector('.welcome-message');
    if (welcome) welcome.remove();

    // Add user message
    addMessage(message, 'user');
    messageInput.value = '';

    // Set loading state
    isLoading = true;
    sendBtn.disabled = true;
    const loadingEl = addLoadingMessage();

    try {
        // Get selected style preset
        const selectedPreset = stylePresetSelect ? stylePresetSelect.value : '';
        const styleProfile = selectedPreset ? STYLE_PRESETS[selectedPreset] : null;

        const res = await fetch(`${API_BASE}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                session_id: sessionId,
                use_mock: mockModeCheckbox.checked,
                style: styleProfile
            })
        });

        if (!res.ok) {
            throw new Error(`HTTP ${res.status}`);
        }

        const data = await res.json();

        // Save session ID for future requests
        if (data.session_id) {
            sessionId = data.session_id;
            localStorage.setItem('atlas_session_id', sessionId);
        }

        // Remove loading
        loadingEl.remove();

        // Add assistant message
        addMessage(data.response, 'assistant', data.rdr);

        // Update RDR panel
        updateRDRPanel(data.rdr);

    } catch (e) {
        loadingEl.remove();
        addMessage(`Hata: ${e.message}`, 'assistant');
    } finally {
        isLoading = false;
        sendBtn.disabled = false;
        messageInput.focus();
    }
}

function addMessage(text, type, rdr = null) {
    const div = document.createElement('div');
    div.className = `message ${type}`;

    // Message text
    const textDiv = document.createElement('div');
    textDiv.className = 'message-content';

    if (type === 'assistant' && typeof marked !== 'undefined') {
        // Render markdown for assistant messages
        textDiv.innerHTML = marked.parse(text);
    } else {
        textDiv.textContent = text;
    }
    div.appendChild(textDiv);

    // Metadata badges (for assistant messages)
    if (type === 'assistant' && rdr) {
        const meta = document.createElement('div');
        meta.className = 'meta';

        // Tier badge
        const tierBadge = document.createElement('span');
        tierBadge.className = 'badge tier';
        tierBadge.textContent = `Tier ${rdr.tier_used}`;
        meta.appendChild(tierBadge);

        // Model badge
        const modelBadge = document.createElement('span');
        modelBadge.className = 'badge model';
        modelBadge.textContent = rdr.model_category || (rdr.model_id ? rdr.model_id.split('/').pop() : 'AI');
        meta.appendChild(modelBadge);

        // Latency badge
        const latencyBadge = document.createElement('span');
        latencyBadge.className = 'badge latency';
        latencyBadge.textContent = `${rdr.total_ms}ms`;
        meta.appendChild(latencyBadge);

        div.appendChild(meta);
    }

    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

function addLoadingMessage() {
    const div = document.createElement('div');
    div.className = 'message assistant';
    div.innerHTML = '<div class="loading"></div>';
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
}

function addSystemMessage(text) {
    const div = document.createElement('div');
    div.className = 'message assistant';
    div.style.background = '#2d2d44';
    div.textContent = text;
    messagesEl.appendChild(div);
}

function updateRDRPanel(rdr) {
    if (!rdr) return;
    rdrContent.innerHTML = '';

    // Add pulsing effect
    const panel = document.querySelector('.rdr-panel');
    if (panel) {
        panel.classList.remove('pulse-update');
        void panel.offsetWidth; // Trigger reflow
        panel.classList.add('pulse-update');
    }

    // --- TEMEL BİLGİLER ---
    addRDRItem('İstek Kimliği (Request ID)', rdr.request_id);
    addRDRItem('Niyet (Intent)', `<span style="color: var(--accent); font-weight: bold; font-size: 1.1rem;">${rdr.intent.toUpperCase()}</span>`, true);

    // --- 1. ORKESTRASYON KATMANI ---
    addRDRSectionHeader('🧠 1. Orkestrasyon (Planlama)');
    const orchDiv = document.createElement('div');
    orchDiv.className = 'trace-step';

    let fallbackHtml = '';
    if (rdr.fallback_used) {
        fallbackHtml = `<span class="fallback-badge">⚠️ FALLBACK (${rdr.fallback_attempts}. Deneme)</span>`;
    }

    orchDiv.innerHTML = `
        <div style="font-weight: 600; color: var(--text-primary);">Orkestratör Kararı ${fallbackHtml}</div>
        <div style="font-size: 10px; color: var(--text-muted); margin-top: 4px;">
            Modeller: <span style="color: var(--warning);">${rdr.fallback_models.join(' → ') || 'Gemini-2.0-Flash'}</span>
        </div>
        <div class="prompt-label" style="margin-top: 10px;">Girdi (Rewritten)</div>
        <div style="color: var(--accent); font-style: italic; margin-bottom: 10px;">"${rdr.rewritten_query || rdr.message}"</div>
        
        <details>
            <summary style="cursor: pointer; font-size: 10px; color: var(--text-muted); margin-bottom: 5px;">Orkestratör Promotunu Gör</summary>
            <div class="prompt-details">${rdr.orchestrator_prompt || 'Sistem Promotu (Gizli)'}</div>
        </details>
    `;
    rdrContent.appendChild(orchDiv);

    // --- 2. UZMAN (EXPERT) KATMANI ---
    addRDRSectionHeader('🚀 2. Uzman Katmanı (Yürütme)');
    if (rdr.task_details && rdr.task_details.length > 0) {
        rdr.task_details.forEach(task => {
            const taskDiv = document.createElement('div');
            taskDiv.className = 'trace-step';
            taskDiv.style.borderLeftColor = task.status === 'success' ? 'var(--success)' : 'var(--error)';

            const statusIcon = task.status === 'success' ? '✅' : '❌';
            taskDiv.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-weight: bold; color: var(--text-primary);">${task.id.toUpperCase()}</span>
                    <span>${statusIcon}</span>
                </div>
                <div style="font-size: 10px; color: var(--text-muted); margin-top: 4px;">
                    Uzman: <span style="color: #fbbf24;">${task.model}</span>
                </div>
                <details style="margin-top: 8px;">
                    <summary style="cursor: pointer; font-size: 10px; color: var(--text-muted);">Uzman Promotu & Yanıtı</summary>
                    <div class="prompt-label" style="margin-top: 10px;">Sistem Talimatı (Prompt)</div>
                    <div class="prompt-details">${task.prompt || 'Talimat belirtilmedi'}</div>
                    <div class="prompt-label" style="margin-top: 10px;">Ham Yanıt (Raw Output)</div>
                    <div class="prompt-details" style="color: #cbd5e1; background: #111827;">${(rdr.raw_expert_responses.find(r => r.model === task.model) || {}).response || 'Yanıt alınamadı'}</div>
                </details>
            `;
            rdrContent.appendChild(taskDiv);
        });
    } else {
        addRDRItem('Görevler', 'Tekil Görev (Orchestrator Doğrudan)');
    }

    // --- 3. SENTEZLEYİCİ KATMANI ---
    addRDRSectionHeader('✨ 3. Sentezleyici (Üslup)');
    const synthDiv = document.createElement('div');
    synthDiv.className = 'trace-step';
    synthDiv.style.borderLeftColor = '#10b981';

    synthDiv.innerHTML = `
        <div style="font-weight: 600; color: var(--text-primary);">Nihai Üslup ve Birleştirme</div>
        <div style="font-size: 10px; color: var(--text-muted); margin-top: 4px;">
            Model: <span style="color: #10b981;">${rdr.synthesizer_model || 'Standard'}</span>
        </div>
        <details style="margin-top: 8px;">
            <summary style="cursor: pointer; font-size: 10px; color: var(--text-muted);">Sentezleyici Promotunu Gör</summary>
            <div class="prompt-details">${rdr.synthesizer_prompt || 'Sentezleme promotu oluşturulmadı.'}</div>
        </details>
    `;
    rdrContent.appendChild(synthDiv);

    // --- 4. GÜVENLİK VE KALİTE ---
    addRDRSectionHeader('🛡️ Güvenlik ve Kalite');
    const safetyStatus = rdr.safety_passed ? '<span style="color: var(--success);">✅ Güvenli</span>' : '<span style="color: var(--error);">❌ Engellendi</span>';
    addRDRItem('Güvenlik Durumu', safetyStatus);

    const qualityStatus = rdr.quality_passed ? '<span style="color: var(--success);">✅ Yüksek</span>' : '<span style="color: var(--warning);">⚠️ İyileştirilebilir</span>';
    addRDRItem('Yanıt Kalitesi', qualityStatus);

    if (rdr.quality_issues && rdr.quality_issues.length > 0) {
        addRDRItem('Kalite Notları', rdr.quality_issues.map(i => `<div style="font-size: 10px;">• ${i.details}</div>`).join(''));
    }

    // --- 5. PERFORMANS VE BÜTÇE ---
    addRDRSectionHeader('⏱️ Performans ve Bütçe');
    addRDRItem('Toplam Süre', `<span style="color: var(--warning); font-weight: bold;">${rdr.total_ms}ms</span>`, true);
    addRDRItem('Tokens Kullanımı', rdr.tokens_used ? rdr.tokens_used.toLocaleString() : 'N/A');

    const budgetColor = rdr.budget_remaining_pct > 80 ? 'var(--success)' : rdr.budget_remaining_pct > 50 ? 'var(--warning)' : 'var(--error)';
    addRDRItem('Kalan Günlük Bütçe', `<span style="color:${budgetColor}; font-weight: bold;">%${rdr.budget_remaining_pct || 100}</span>`);

    // --- 6. BAĞLAM (CONTEXT) ---
    if (rdr.user_facts_dump && rdr.user_facts_dump.length > 0) {
        addRDRSectionHeader('🧠 Hatırlanan Bilgiler (Memory)');
        const factsDiv = document.createElement('div');
        factsDiv.innerHTML = rdr.user_facts_dump.map(f => `<div style="font-size: 10px; background: rgba(99, 102, 241, 0.1); border-left: 2px solid var(--accent); padding: 4px 8px; margin-bottom: 4px; border-radius: 0 4px 4px 0;">${f}</div>`).join('');
        rdrContent.appendChild(factsDiv);
    }
}

function addRDRSectionHeader(title) {
    const div = document.createElement('div');
    div.className = 'rdr-section-header';
    div.innerHTML = `<strong>${title}</strong>`;
    div.style.cssText = 'margin-top: 12px; padding: 4px 0; border-bottom: 1px solid #444; color: #888; font-size: 11px;';
    rdrContent.appendChild(div);
}

function addRDRItem(label, value, highlight = false) {
    const div = document.createElement('div');
    div.className = 'rdr-item';
    div.innerHTML = `
        <div class="label">${label}</div>
        <div class="value ${highlight ? 'highlight' : ''}">${value}</div>
    `;
    rdrContent.appendChild(div);
}

// ========== STATS MODAL ==========

function openStatsModal() {
    const modal = document.getElementById('statsModal');
    modal.classList.add('active');
    loadStats();
}

function closeStatsModal() {
    const modal = document.getElementById('statsModal');
    modal.classList.remove('active');
}

// Close modal on backdrop click
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal')) {
        e.target.classList.remove('active');
    }
});

async function loadStats() {
    const statsContent = document.getElementById('statsContent');
    statsContent.innerHTML = '<p>Yükleniyor...</p>';

    try {
        const res = await fetch(`${API_BASE}/api/keys`);
        const data = await res.json();

        if (!data.keys || data.keys.length === 0) {
            statsContent.innerHTML = '<p>Henüz key istatistiği yok.</p>';
            return;
        }

        statsContent.innerHTML = data.keys.map(key => renderKeyCard(key)).join('');
    } catch (e) {
        statsContent.innerHTML = `<p>Hata: ${e.message}</p>`;
    }
}

function renderKeyCard(key) {
    const statusClass = key.status.toLowerCase();
    const successRate = (key.success_rate * 100).toFixed(0);

    // Model usage rendering
    let modelUsageHtml = '';
    if (key.model_usage && Object.keys(key.model_usage).length > 0) {
        const models = Object.entries(key.model_usage)
            .sort((a, b) => b[1] - a[1])  // Sort by count desc
            .map(([model, count]) => {
                // Shorten model name
                const shortName = model.split('/').pop().substring(0, 20);
                return `<div class="model-usage-item">
                    <span class="model-name" title="${model}">${shortName}</span>
                    <span class="model-count">${count}</span>
                </div>`;
            }).join('');

        modelUsageHtml = `
            <div class="model-usage-title">📦 Model Kullanımı</div>
            <div class="model-usage-list">${models}</div>
        `;
    } else {
        modelUsageHtml = '<div class="model-usage-title">📦 Henüz model kullanılmadı</div>';
    }

    return `
        <div class="key-card">
            <div class="key-card-header">
                <div class="key-card-title">
                    🔑 ${key.key_id} 
                    <span style="color: var(--text-muted); font-weight: normal;">${key.key_masked}</span>
                </div>
                <span class="key-status ${statusClass}">${key.status.toUpperCase()}</span>
            </div>
            
            <div class="key-stats-grid">
                <div class="key-stat">
                    <div class="key-stat-value">${key.total_requests}</div>
                    <div class="key-stat-label">Toplam</div>
                </div>
                <div class="key-stat">
                    <div class="key-stat-value">${key.daily_requests}</div>
                    <div class="key-stat-label">Bugün</div>
                </div>
                <div class="key-stat">
                    <div class="key-stat-value">${successRate}%</div>
                    <div class="key-stat-label">Başarı</div>
                </div>
                <div class="key-stat">
                    <div class="key-stat-value">${key.rate_limit_hits}</div>
                    <div class="key-stat-label">429 Hit</div>
                </div>
            </div>
            
            ${modelUsageHtml}
        </div>
    `;
}
