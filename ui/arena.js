
// DOM Elements
const categorySelect = document.getElementById('category-select');
const promptInput = document.getElementById('prompt-input');
const outputArea = document.getElementById('output-area');
const welcomeState = document.getElementById('welcome-state');
const blindTestCheckbox = document.getElementById('blind-test-mode');
const leaderboardList = document.getElementById('leaderboard-list');
const questionsList = document.getElementById('questions-list');

// State
let currentResults = []; // [ {model, response, etc.}, ... ]
let isRunning = false;
let blindTestMode = false;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadLeaderboard();
    loadQuestions();

    // Global scope binding for HTML onclick handlers
    window.switchTab = switchTab;
    window.runBenchmark = runBenchmark;
    window.loadQuestions = loadQuestions;
    window.setPrompt = setPrompt;

    console.log("Arena JS Loaded");
});

// Switch Sidebar Tabs
function switchTab(tabName) {
    document.getElementById('view-leaderboard').classList.add('hidden');
    document.getElementById('view-questions').classList.add('hidden');
    document.getElementById(`view-${tabName}`).classList.remove('hidden');

    document.getElementById('tab-leaderboard').classList.remove('text-blue-400', 'bg-slate-800', 'border-blue-500');
    document.getElementById('tab-questions').classList.remove('text-blue-400', 'bg-slate-800', 'border-blue-500');

    document.getElementById(`tab-${tabName}`).classList.add('text-blue-400', 'bg-slate-800', 'border-blue-500');
}

// Check Blind Test Mode
if (blindTestCheckbox) {
    blindTestCheckbox.addEventListener('change', (e) => {
        blindTestMode = e.target.checked;
        document.body.classList.toggle('blind-mode', blindTestMode);
    });
}

// --- API CALLS ---

async function fetchLeaderboard() {
    try {
        const res = await fetch('/api/arena/leaderboard');
        return await res.json();
    } catch (e) { console.error(e); return { results: [] }; }
}

async function fetchQuestions() {
    try {
        const res = await fetch('/api/arena/questions');
        return await res.json();
    } catch (e) { console.error(e); return []; }
}

async function runBenchmarkApi(prompt, category) {
    const res = await fetch('/api/arena/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, category })
    });
    return await res.json(); // Returns array of results
}

async function submitScore(result) {
    await fetch('/api/arena/result', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(result)
    });
}

// --- CORE FUNCTIONALITY ---

async function runBenchmark(customPrompt = null) {
    if (isRunning) return;

    const prompt = customPrompt || promptInput.value.trim();
    if (!prompt) return;

    // UI Reset
    isRunning = true;
    welcomeState.style.display = 'none';
    outputArea.innerHTML = ''; // Clear previous
    currentResults = [];

    // Add User Bubble (Question)
    const questionDiv = document.createElement('div');
    questionDiv.className = 'bg-slate-800/50 border border-slate-700 rounded-xl p-4 mb-8 text-slate-300 italic';
    questionDiv.innerText = `Soru: "${prompt}"`;
    outputArea.appendChild(questionDiv);

    // Loading Indicator
    const loadingDiv = document.createElement('div');
    loadingDiv.id = 'loading-indicator';
    loadingDiv.className = 'text-center text-slate-500 animate-pulse mt-12';
    loadingDiv.innerHTML = '<i data-lucide="loader" class="w-8 h-8 mx-auto mb-2 animate-spin"></i><br>9 Model Savaşıyor...';
    outputArea.appendChild(loadingDiv);
    lucide.createIcons();

    try {
        const category = categorySelect.value;
        const results = await runBenchmarkApi(prompt, category);

        // Remove loading
        loadingDiv.remove();

        // Render Results
        for (const res of results) {
            renderResponseCard(res, prompt, category);
            // Async Judge Call
            triggerJudge(res, prompt, category);
        }

    } catch (e) {
        console.error(e);
        loadingDiv.innerText = "Hata oluştu: " + e.message;
    } finally {
        isRunning = false;
    }
}

function renderResponseCard(res, question, category) {
    const template = document.getElementById('response-card-template');
    const clone = template.content.cloneNode(true);

    const card = clone.querySelector('.response-card');
    card.id = `card-${res.model_id.replace(/[^a-zA-Z0-9]/g, '-')}`;

    // Blind Mode
    if (blindTestMode) card.classList.add('blind');

    // Header Info
    clone.querySelector('.model-name').innerText = res.model_id;
    clone.querySelector('.latency-ms').innerText = `${Math.round(res.latency_ms)}ms`;
    clone.querySelector('.tps-stat').innerText = `${res.tokens_per_sec.toFixed(1)} t/s`;

    // Content (Markdown)
    const contentDiv = clone.querySelector('.markdown-body');
    if (res.error) {
        contentDiv.innerHTML = `<span class="text-red-400">Hata: ${res.error}</span>`;
    } else {
        contentDiv.innerHTML = marked.parse(res.response);
    }

    // Score Buttons
    const buttonsContainer = clone.querySelector('.score-buttons');
    for (let i = 1; i <= 10; i++) {
        const btn = document.createElement('button');
        btn.className = `w-6 h-6 rounded flex items-center justify-center text-[10px] font-bold transition-colors ${i <= 5 ? 'bg-slate-700 hover:bg-slate-600 text-slate-400' : 'bg-slate-700 hover:bg-green-600 text-slate-300'}`;
        btn.innerText = i;
        btn.onclick = () => handleManualScore(res, question, category, i, btn, card);
        buttonsContainer.appendChild(btn);
    }

    outputArea.appendChild(clone);
}

// Judge Logic
async function triggerJudge(res, question, category) {
    if (res.error) return;

    const cardId = `card-${res.model_id.replace(/[^a-zA-Z0-9]/g, '-')}`;
    const card = document.getElementById(cardId);
    if (!card) return;

    const reasonEl = card.querySelector('.ai-reason');
    const scoreValEl = card.querySelector('.ai-score-val');

    reasonEl.innerText = "Hakem düşünüyor...";

    try {
        const resApi = await fetch('/api/arena/judge', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question,
                response: res.response,
                category
            })
        });
        const judgeResult = await resApi.json();

        reasonEl.innerText = judgeResult.reason || "Puanlandı";
        reasonEl.title = judgeResult.reason;
        scoreValEl.innerText = judgeResult.score;

        // Save Auto Score locally to result object
        res.ai_score = judgeResult.score;
        res.ai_reason = judgeResult.reason;

    } catch (e) {
        reasonEl.innerText = "Hakem hatası";
    }
}

// Manual Score Logic
async function handleManualScore(res, question, category, score, btn, card) {
    // UI Update
    const allBtns = card.querySelectorAll('.score-buttons button');
    allBtns.forEach(b => b.classList.remove('bg-blue-600', 'text-white'));
    btn.classList.add('bg-blue-600', 'text-white');

    // Reveal if blind mode
    if (blindTestMode) {
        card.classList.add('revealed');
        // also remove blur class if it was applied via css only
    }

    // Save
    const finalResult = {
        model_id: res.model_id,
        category: category,
        question_id: uuidv4(), // Generate simple ID
        timestamp: new Date().toISOString(),
        latency_ms: res.latency_ms,
        tokens_per_sec: res.tokens_per_sec,
        human_score: score,
        ai_score: res.ai_score || 0,
        ai_reason: res.ai_reason || ""
    };

    await submitScore(finalResult);

    // Refresh Leaderboard
    loadLeaderboard();
}

// --- SIDEBAR FUNCTIONS ---

async function loadLeaderboard() {
    const data = await fetchLeaderboard();
    const results = data.results || [];

    // Aggregate Scores
    const modelStats = {};

    results.forEach(r => {
        if (!modelStats[r.model_id]) {
            modelStats[r.model_id] = { total: 0, count: 0, ai_total: 0 };
        }
        if (r.human_score > 0) {
            modelStats[r.model_id].total += r.human_score;
            modelStats[r.model_id].count++;
        }
        if (r.ai_score > 0) {
            modelStats[r.model_id].ai_total += r.ai_score;
        }
    });

    // Convert to array and sort
    const leaderboard = Object.keys(modelStats).map(mid => {
        const s = modelStats[mid];
        const avg = s.count > 0 ? (s.total / s.count).toFixed(1) : "0.0";
        return { id: mid, avg, count: s.count };
    }).sort((a, b) => parseFloat(b.avg) - parseFloat(a.avg));

    // Render
    leaderboardList.innerHTML = leaderboard.map((m, idx) => `
        <div class="flex items-center justify-between bg-slate-800 p-2 rounded-lg border border-slate-700">
            <div class="flex items-center gap-2 overflow-hidden">
                <span class="text-xs font-bold text-slate-500 w-4">${idx + 1}</span>
                <span class="text-xs font-mono text-slate-300 truncate" title="${m.id}">${m.id.split('/').pop()}</span>
            </div>
            <div class="flex items-center gap-2">
                <span class="text-xs text-slate-500">(${m.count})</span>
                <span class="text-sm font-bold text-yellow-500">${m.avg}</span>
            </div>
        </div>
    `).join('');
}

async function loadQuestions() {
    const questions = await fetchQuestions();
    questionsList.innerHTML = questions.map(q => `
        <div class="group bg-slate-800 p-3 rounded-lg border border-slate-700 hover:border-blue-500 transition-colors cursor-pointer relative"
             onclick="window.setPrompt('${q.text.replace(/'/g, "\\'")}', '${q.category}')">
            <div class="flex justify-between items-start mb-1">
                <h4 class="text-sm font-bold text-slate-300">${q.title}</h4>
                <span class="text-[10px] bg-slate-700 px-1.5 py-0.5 rounded text-slate-400 capitalize">${q.category}</span>
            </div>
            <p class="text-xs text-slate-500 line-clamp-2">${q.text}</p>
            
            <button onclick="event.stopPropagation(); window.runBenchmark('${q.text.replace(/'/g, "\\'")}')" 
                class="absolute right-2 bottom-2 opacity-0 group-hover:opacity-100 bg-blue-600 hover:bg-blue-500 text-white p-1 rounded transition-opacity">
                <i data-lucide="play" class="w-3 h-3"></i>
            </button>
        </div>
    `).join('');
    lucide.createIcons();
}

function setPrompt(text, category) {
    promptInput.value = text;
    categorySelect.value = category || 'general';
}

function uuidv4() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}
