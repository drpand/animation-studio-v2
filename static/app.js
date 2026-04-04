/* ============================================
   Animation Studio v2 — РОДИНА
   Логика интерфейса v4
   ============================================ */

const API_BASE = '';
let agents = [];
let currentAgentId = null;
let currentAttachmentObjects = [];
let discussionUnreadCount = 0;
let lastDiscussionTimestamp = 0;

const AGENT_ICONS = {
    orchestrator: '🎛️', director: '🎬', writer: '✍️', critic: '🔍',
    fixer: '🔧', storyboarder: '📋', dop: '📷', art_director: '🎨',
    sound_director: '🎵', hr_agent: '👤'
};

const STATUS_MAP = {
    idle: { label: 'Свободен', class: 'idle' },
    working: { label: 'Работает', class: 'working' },
    error: { label: 'Ошибка', class: 'error' }
};

// --- Init ---
document.addEventListener('DOMContentLoaded', () => {
    checkServer();
    loadAgents();
    bindEvents();
    loadAvailablePatterns();
    setInterval(loadAgents, 5000);
    setInterval(loadDiscussion, 10000);
    try {
        if (localStorage.getItem('onboarding_dismissed') === '1') {
            const b = document.getElementById('onboardingBanner');
            if (b) b.classList.add('hidden');
        }
    } catch(e) {}
});

// --- Server check ---
async function checkServer() {
    try {
        const res = await fetch(`${API_BASE}/health`);
        if (res.ok) {
            document.getElementById('serverStatus').classList.add('online');
            document.getElementById('serverStatus').classList.remove('offline');
            document.querySelector('.status-text').textContent = 'Онлайн';
        }
    } catch {
        document.getElementById('serverStatus').classList.add('offline');
        document.querySelector('.status-text').textContent = 'Оффлайн';
    }
}

// --- Load agents ---
async function loadAgents() {
    try {
        const res = await fetch(`${API_BASE}/api/agents/`);
        const data = await res.json();
        agents = data.agents || [];
        renderOffice();
    } catch (e) { console.error(e); }
}

// --- Render office ---
function renderOffice() {
    const grid = document.getElementById('officeGrid');
    if (!grid) return;
    if (agents.length === 0) {
        grid.innerHTML = '<div class="office-loading">Нет агентов</div>';
        return;
    }
    let html = '';
    for (const agent of agents) {
        const icon = agent.icon || AGENT_ICONS[agent.agent_id] || '🤖';
        const status = STATUS_MAP[agent.status] || STATUS_MAP.idle;
        const modelShort = agent.model.split('/').pop() || agent.model;
        html += `
            <div class="agent-desk status-${agent.status}" onclick="openAgentPanel('${agent.agent_id}')">
                <span class="desk-icon">${icon}</span>
                <div class="desk-name">${agent.name}</div>
                <div class="desk-role">${agent.role}</div>
                <div class="desk-footer">
                    <div class="desk-status ${status.class}">
                        <span class="dot"></span>${status.label}
                    </div>
                    <span class="desk-model">${modelShort}</span>
                </div>
                <span class="desk-open-btn">Открыть →</span>
            </div>`;
    }
    grid.innerHTML = html;
}

// --- Open agent panel ---
async function openAgentPanel(agentId) {
    currentAgentId = agentId;
    const panel = document.getElementById('agentPanel');
    try {
        const res = await fetch(`${API_BASE}/api/agents/${agentId}`);
        const agent = await res.json();
        const icon = agent.icon || AGENT_ICONS[agentId] || '🤖';
        document.getElementById('panelIcon').textContent = icon;
        document.getElementById('panelName').textContent = agent.name;
        const status = STATUS_MAP[agent.status] || STATUS_MAP.idle;
        document.getElementById('panelStatus').textContent = status.label;
        document.getElementById('panelModel').value = agent.model;
        document.getElementById('panelInstructions').value = agent.instructions || '';
        currentAttachmentObjects = agent.attachment_objects || [];
        renderAttachmentChips(currentAttachmentObjects, agent.attachments || []);
        renderChatHistory(agent.chat_history || []);

        // Show Kie.ai tool for Art Director
        const kieaiSection = document.getElementById('toolKieaiSection');
        if (kieaiSection) kieaiSection.style.display = (agentId === 'art_director') ? 'block' : 'none';

        panel.classList.add('open');
        getOverlay().classList.add('active');
        loadAgentRules(agentId);
    } catch (e) { console.error(e); }
}

function closeAgentPanel() {
    document.getElementById('agentPanel').classList.remove('open');
    getOverlay().classList.remove('active');
    currentAgentId = null;
    currentAttachmentObjects = [];
}

// --- Chat ---
function renderChatHistory(history) {
    const container = document.getElementById('chatHistory');
    if (history.length === 0) {
        container.innerHTML = '<div style="font-size:12px;color:var(--text-muted);text-align:center;padding:20px">💬 Напишите задачу агенту</div>';
        return;
    }
    container.innerHTML = history.map(msg => {
        const cls = msg.role === 'user' ? 'user' : 'assistant';
        const time = msg.time ? new Date(msg.time).toLocaleTimeString('ru-RU', {hour:'2-digit', minute:'2-digit'}) : '';
        return `<div class="chat-msg ${cls}">${escapeHtml(msg.content)}${time ? `<div class="msg-time">${time}</div>` : ''}</div>`;
    }).join('');
    container.scrollTop = container.scrollHeight;
}

async function sendMessage() {
    const input = document.getElementById('chatInput');
    const btn = document.getElementById('btnSend');
    const message = input.value.trim();
    if (!message || !currentAgentId) return;
    btn.disabled = true;
    input.value = '';

    const container = document.getElementById('chatHistory');
    container.innerHTML += `<div class="chat-msg user">${escapeHtml(message)}<div class="msg-time">${new Date().toLocaleTimeString('ru-RU', {hour:'2-digit', minute:'2-digit'})}</div></div>`;
    container.scrollTop = container.scrollHeight;

    try {
        const res = await fetch(`${API_BASE}/api/chat/${currentAgentId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message })
        });
        const data = await res.json();
        container.innerHTML += `<div class="chat-msg assistant">${escapeHtml(data.reply)}<div class="msg-time">${new Date().toLocaleTimeString('ru-RU', {hour:'2-digit', minute:'2-digit'})}</div></div>`;
    } catch (e) {
        container.innerHTML += `<div class="chat-msg error">Ошибка: ${e.message}</div>`;
    }
    container.scrollTop = container.scrollHeight;
    btn.disabled = false;
    input.focus();
    loadAgents();
}

// --- Attachments ---
function renderAttachmentChips(objects, legacyNames) {
    const container = document.getElementById('attachmentChips');
    const normalized = (objects && objects.length) ? objects : (legacyNames || []).map(n => ({ filename: n, original_name: n, is_text_readable: false }));
    if (!normalized.length) { container.innerHTML = ''; return; }
    container.innerHTML = normalized.map(f => {
        const name = f.original_name || f.filename || 'file';
        const badge = f.is_text_readable ? '<span class="attachment-badge">читается</span>' : '<span class="attachment-badge unreadable">не читается</span>';
        const removeBtn = f.filename ? `<button class="attachment-remove" onclick="deleteAttachment('${encodeURIComponent(f.filename)}')">✕</button>` : '';
        return `<div class="attachment-chip"><span>📎 ${escapeHtml(name)}</span>${badge}${removeBtn}</div>`;
    }).join('');
}

async function uploadFile() {
    if (!currentAgentId) return;
    const input = document.getElementById('fileInput');
    const file = input.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    try {
        const res = await fetch(`${API_BASE}/api/agents/${currentAgentId}/upload`, { method: 'POST', body: formData });
        const data = await res.json();
        if (data.ok) {
            const agentRes = await fetch(`${API_BASE}/api/agents/${currentAgentId}`);
            const agent = await agentRes.json();
            currentAttachmentObjects = agent.attachment_objects || [];
            renderAttachmentChips(currentAttachmentObjects, agent.attachments || []);
            input.value = '';
        } else { alert('Ошибка: ' + (data.detail || 'Неизвестная ошибка')); }
    } catch (e) { alert('Ошибка загрузки: ' + e.message); }
}

async function deleteAttachment(encodedFilename) {
    if (!currentAgentId) return;
    const filename = decodeURIComponent(encodedFilename);
    try {
        const res = await fetch(`${API_BASE}/api/agents/${currentAgentId}/attachments/${encodeURIComponent(filename)}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.ok) {
            const agentRes = await fetch(`${API_BASE}/api/agents/${currentAgentId}`);
            const agent = await agentRes.json();
            currentAttachmentObjects = agent.attachment_objects || [];
            renderAttachmentChips(currentAttachmentObjects, agent.attachments || []);
        }
    } catch (e) { alert('Ошибка: ' + e.message); }
}

// --- Evaluate ---
async function evaluateResult() {
    if (!currentAgentId) return;
    const btn = document.getElementById('btnEvaluate');
    btn.disabled = true;
    btn.textContent = '⏳ Оценка...';
    try {
        const res = await fetch(`${API_BASE}/api/med-otdel/evaluate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agent_id: currentAgentId })
        });
        const data = await res.json();
        const container = document.getElementById('chatHistory');
        const cls = data.passed ? 'assistant' : 'error';
        const icon = data.passed ? '✅' : '❌';
        container.innerHTML += `<div class="chat-msg ${cls}">${icon} Оценка: ${data.passed ? 'PASS' : 'FAIL'} (Score: ${data.score}/10)\n${data.feedback || ''}<div class="msg-time">${new Date().toLocaleTimeString('ru-RU', {hour:'2-digit', minute:'2-digit'})}</div></div>`;
        container.scrollTop = container.scrollHeight;
    } catch (e) { alert('Ошибка: ' + e.message); }
    btn.disabled = false;
    btn.textContent = '🔍 Оценить';
}

// --- Save instructions ---
async function saveInstructions() {
    if (!currentAgentId) return;
    try {
        await fetch(`${API_BASE}/api/agents/${currentAgentId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ instructions: document.getElementById('panelInstructions').value, model: document.getElementById('panelModel').value })
        });
        alert('Сохранено!');
    } catch (e) { alert('Ошибка: ' + e.message); }
}

// --- Rules ---
async function loadAgentRules(agentId) {
    try {
        const res = await fetch(`${API_BASE}/api/med-otdel/${agentId}/rules`);
        const data = await res.json();
        const container = document.getElementById('rulesList');
        if (!container) return;
        if (!data.rules || !data.rules.length) {
            container.innerHTML = '<div style="font-size:12px;color:var(--text-muted)">Нет применённых правил</div>';
            return;
        }
        container.innerHTML = data.rules.map(r => `<div style="font-size:12px;padding:4px 0;border-bottom:1px solid var(--border)">📜 ${escapeHtml(r)}</div>`).join('');
    } catch (e) {}
}

async function loadAvailablePatterns() {
    try {
        const res = await fetch(`${API_BASE}/api/med-otdel/patterns`);
        const data = await res.json();
        const select = document.getElementById('rulesSelect');
        if (!select) return;
        select.innerHTML = '<option value="">Выберите правило...</option>';
        (data.patterns || []).forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.key;
            opt.textContent = p.name || p.key;
            select.appendChild(opt);
        });
    } catch (e) {}
}

async function addRule() {
    if (!currentAgentId) return;
    const select = document.getElementById('rulesSelect');
    const key = select.value;
    if (!key) return;
    try {
        const res = await fetch(`${API_BASE}/api/med-otdel/apply-pattern`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agent_id: currentAgentId, pattern_key: key })
        });
        const data = await res.json();
        if (data.ok) { loadAgentRules(currentAgentId); select.value = ''; }
        else { alert('Ошибка: ' + (data.error || 'Неизвестная ошибка')); }
    } catch (e) { alert('Ошибка: ' + e.message); }
}

// --- Kie.ai Image Generation ---
async function generateImage() {
    const prompt = document.getElementById('kieai-prompt').value.trim();
    if (!prompt || !currentAgentId) return;
    const btn = document.getElementById('btnKieai');
    const spinner = document.getElementById('kieai-spinner');
    const errorDiv = document.getElementById('kieai-error');
    const resultDiv = document.getElementById('kieai-result');

    btn.disabled = true;
    spinner.classList.remove('hidden');
    errorDiv.classList.add('hidden');
    resultDiv.classList.add('hidden');

    try {
        const res = await fetch(`${API_BASE}/api/tools/generate-image`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt })
        });
        const data = await res.json();
        if (data.status === 'success') {
            document.getElementById('kieai-image').src = data.result_url;
            resultDiv.classList.remove('hidden');
        } else {
            errorDiv.querySelector('.error-text').textContent = data.error || 'Ошибка генерации';
            errorDiv.classList.remove('hidden');
        }
    } catch (e) {
        errorDiv.querySelector('.error-text').textContent = e.message;
        errorDiv.classList.remove('hidden');
    }
    btn.disabled = false;
    spinner.classList.add('hidden');
}

// --- Discussion ---
async function loadDiscussion() {
    try {
        const res = await fetch(`${API_BASE}/api/discussion/`);
        const data = await res.json();
        renderDiscussionMessages(data.messages || []);
    } catch (e) {}
}

function renderDiscussionMessages(messages) {
    const container = document.getElementById('discussionMessages');
    if (!container) return;
    if (!messages.length) {
        container.innerHTML = '<div style="font-size:12px;color:var(--text-muted);text-align:center;padding:20px">Нет сообщений</div>';
        return;
    }
    container.innerHTML = messages.map(m => {
        const type = m.msg_type || 'system';
        return `<div class="discussion-msg type-${type}">
            <div class="msg-sender">${escapeHtml(m.agent_id || 'system')}</div>
            ${escapeHtml(m.content || '')}
        </div>`;
    }).join('');
    container.scrollTop = container.scrollHeight;
}

async function sendDiscussionMessage() {
    const input = document.getElementById('discussionInput');
    const content = input.value.trim();
    if (!content) return;
    try {
        await fetch(`${API_BASE}/api/discussion/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agent_id: 'user', content, msg_type: 'user' })
        });
        input.value = '';
        loadDiscussion();
    } catch (e) { alert('Ошибка: ' + e.message); }
}

// --- Pipeline ---
async function startPipeline() {
    const season = parseInt(document.getElementById('pipeSeason').value) || 1;
    const episode = parseInt(document.getElementById('pipeEpisode').value) || 1;
    const scene = parseInt(document.getElementById('pipeScene').value) || 1;
    const desc = document.getElementById('pipeDesc').value.trim();
    if (!desc) { alert('Опишите сцену'); return; }

    const btn = document.getElementById('btnStartPipeline');
    btn.disabled = true;
    btn.textContent = '⏳ Запуск...';

    // Reset stages
    ['writer','director','hr','dop','art','sound','storyboard','image'].forEach(s => {
        const el = document.getElementById('stage-' + s);
        if (el) { el.textContent = '⏳ Ожидание'; el.className = 'stage-status'; }
    });

    try {
        const res = await fetch(`${API_BASE}/api/orchestrator/scene-pipeline`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ season, episode, scene, pdf_context: desc })
        });
        const data = await res.json();
        if (data.ok) {
            btn.textContent = '✅ Запущено';
            // Poll for results
            pollPipelineResults(season, episode, scene);
        } else {
            alert('Ошибка: ' + (data.detail || 'Неизвестная ошибка'));
            btn.disabled = false;
            btn.textContent = '🚀 Запустить конвейер';
        }
    } catch (e) {
        alert('Ошибка: ' + e.message);
        btn.disabled = false;
        btn.textContent = '🚀 Запустить конвейер';
    }
}

function pollPipelineResults(season, episode, scene) {
    let attempts = 0;
    const interval = setInterval(async () => {
        attempts++;
        try {
            const res = await fetch(`${API_BASE}/api/discussion/`);
            const data = await res.json();
            const msgs = data.messages || [];

            // Update stages based on discussion messages
            for (const m of msgs) {
                const content = (m.content || '').toLowerCase();
                if (content.includes('writer') && content.includes('approved')) setStage('writer', 'done', '✅ Готово');
                if (content.includes('director') && content.includes('approved')) setStage('director', 'done', '✅ Готово');
                if (content.includes('hr') && content.includes('approved')) setStage('hr', 'done', '✅ Готово');
                if (content.includes('dop') && content.includes('approved')) setStage('dop', 'done', '✅ Готово');
                if (content.includes('art_director') && content.includes('approved')) setStage('art', 'done', '✅ Готово');
                if (content.includes('sound') && content.includes('approved')) setStage('sound', 'done', '✅ Готово');
                if (content.includes('storyboard') && content.includes('approved')) setStage('storyboard', 'done', '✅ Готово');
                if (content.includes('kie') || content.includes('генерация')) setStage('image', 'running', '🔄 Генерация...');
                if (content.includes('завершена') || content.includes('completed')) {
                    setStage('image', 'done', '✅ Готово');
                    clearInterval(interval);
                    loadPipelineResult(season, episode, scene);
                }
            }

            // Set running stages
            for (const m of msgs.slice(-5)) {
                const c = (m.content || '').toLowerCase();
                if (c.includes('шаг 1') || c.includes('writer описывает')) setStage('writer', 'running', '🔄 Работает...');
                if (c.includes('шаг 2') || c.includes('director')) setStage('director', 'running', '🔄 Работает...');
                if (c.includes('шаг 3') || c.includes('hr')) setStage('hr', 'running', '🔄 Работает...');
                if (c.includes('шаг 4')) { setStage('dop', 'running', '🔄 Работает...'); setStage('art', 'running', '🔄 Работает...'); setStage('sound', 'running', '🔄 Работает...'); }
                if (c.includes('шаг 5') || c.includes('storyboarder собирает')) setStage('storyboard', 'running', '🔄 Работает...');
                if (c.includes('шаг 6') || c.includes('генерация')) setStage('image', 'running', '🔄 Генерация...');
            }
        } catch (e) {}

        if (attempts > 120) { // 10 min timeout
            clearInterval(interval);
            document.getElementById('btnStartPipeline').disabled = false;
            document.getElementById('btnStartPipeline').textContent = '🚀 Запустить конвейер';
        }
    }, 5000);
}

function setStage(stage, status, text) {
    const el = document.getElementById('stage-' + stage);
    if (el) { el.textContent = text; el.className = 'stage-status ' + status; }
}

async function loadPipelineResult(season, episode, scene) {
    try {
        const res = await fetch(`${API_BASE}/api/orchestrator/scene-result/${season}/${episode}/${scene}`);
        const data = await res.json();
        
        if (data.status && data.status !== 'not_found') {
            // Show final prompt
            const promptEl = document.getElementById('resultPrompt');
            if (promptEl && data.final_prompt) {
                promptEl.textContent = data.final_prompt;
            }
            
            // Show image
            const imgEl = document.getElementById('resultImage');
            if (imgEl && data.image_url) {
                imgEl.innerHTML = `<img src="${data.image_url}" alt="Generated image">`;
            }
        }
    } catch (e) { console.error('Failed to load pipeline result:', e); }

    document.getElementById('btnStartPipeline').disabled = false;
    document.getElementById('btnStartPipeline').textContent = '🚀 Запустить конвейер';
}

// --- Panels ---
function getOverlay() { return document.getElementById('overlay'); }

function togglePipelinePanel() {
    const panel = document.getElementById('pipelinePanel');
    panel.classList.toggle('open');
    if (panel.classList.contains('open')) { getOverlay().classList.add('active'); }
    else { getOverlay().classList.remove('active'); }
}

function closePipelinePanel() {
    document.getElementById('pipelinePanel').classList.remove('open');
}

function toggleDiscussionPanel() {
    const panel = document.getElementById('discussionPanel');
    panel.classList.toggle('open');
    if (panel.classList.contains('open')) { getOverlay().classList.add('active'); loadDiscussion(); }
    else { getOverlay().classList.remove('active'); }
}

function closeDiscussionPanel() {
    document.getElementById('discussionPanel').classList.remove('open');
}

function dismissOnboarding() {
    const banner = document.getElementById('onboardingBanner');
    if (banner) banner.classList.add('hidden');
    try { localStorage.setItem('onboarding_dismissed', '1'); } catch(e) {}
}

// --- Utils ---
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// --- Bind Events ---
function bindEvents() {
    const el = (id) => document.getElementById(id);
    const on = (id, event, fn) => { const e = el(id); if (e) e.addEventListener(event, fn); };

    on('panelClose', 'click', closeAgentPanel);
    on('btnSend', 'click', sendMessage);
    on('btnSaveInstructions', 'click', saveInstructions);
    on('btnAttach', 'click', () => { const f = el('fileInput'); if (f) f.click(); });
    on('fileInput', 'change', uploadFile);
    on('btnEvaluate', 'click', evaluateResult);
    on('btnAddRule', 'click', addRule);

    on('pipelineOpenBtn', 'click', togglePipelinePanel);
    on('pipelineClose', 'click', closePipelinePanel);
    on('btnStartPipeline', 'click', startPipeline);

    on('discussionOpenBtn', 'click', toggleDiscussionPanel);
    on('discussionClose', 'click', closeDiscussionPanel);
    on('discussionSend', 'click', sendDiscussionMessage);

    const overlay = getOverlay();
    if (overlay) overlay.addEventListener('click', () => { closeAgentPanel(); closePipelinePanel(); closeDiscussionPanel(); });

    on('chatInput', 'keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } });
    on('discussionInput', 'keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendDiscussionMessage(); } });
}
