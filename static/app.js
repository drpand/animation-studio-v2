/* ============================================
   Animation Studio v2 — РОДИНА
   Логика интерфейса
   ============================================ */

const API_BASE = '';
let agents = [];
let currentAgentId = null;
let currentAttachmentObjects = [];
let discussionUnreadCount = 0;
let lastDiscussionTimestamp = 0;

// Иконки для агентов
const AGENT_ICONS = {
    orchestrator: '🎛️',
    director: '🎬',
    writer: '✍️',
    critic: '🔍',
    fixer: '🔧',
    storyboarder: '📋',
    dop: '📷',
    art_director: '🎨',
    sound_director: '🎵',
    hr_agent: '👤'
};

// Маппинг статусов
const STATUS_MAP = {
    idle: { label: 'Простаивает', class: 'idle' },
    working: { label: 'Работает', class: 'working' },
    waiting: { label: 'Ждёт', class: 'waiting' },
    error: { label: 'Ошибка', class: 'error' }
};

// --- Инициализация ---
document.addEventListener('DOMContentLoaded', () => {
    checkServer();
    loadAgents();
    bindEvents();
    loadAvailablePatterns();
    setInterval(loadAgents, 5000);
    // Polling Discussion канала каждые 10 сек
    setInterval(loadDiscussion, 10000);
    // Polling v4 данных каждые 15 сек
    setInterval(loadProductionData, 15000);
    loadProductionData();
    // Onboarding
    try {
        if (localStorage.getItem('onboarding_dismissed') === '1') {
            const banner = document.getElementById('onboardingBanner');
            if (banner) banner.classList.add('hidden');
        }
    } catch(e) {}
});

// --- Проверка сервера ---
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
        document.getElementById('serverStatus').classList.remove('online');
        document.querySelector('.status-text').textContent = 'Оффлайн';
    }
}

// --- Загрузка агентов ---
async function loadAgents() {
    try {
        const res = await fetch(`${API_BASE}/api/agents/`);
        const data = await res.json();
        agents = data.agents || [];
        renderOffice();
    } catch (e) {
        console.error('Ошибка загрузки агентов:', e);
    }
}

// --- Рендер офиса ---
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
        const tempBadge = agent.temp ? '<span style="font-size:10px;color:#a855f7">[temp]</span>' : '';
        html += `
            <div class="agent-desk status-${agent.status}" data-agent-id="${agent.agent_id}" onclick="openAgentPanel('${agent.agent_id}')">
                <span class="desk-icon">${icon}</span>
                <div class="desk-name">${agent.name} ${tempBadge}</div>
                <div class="desk-role">${agent.role}</div>
                <div class="desk-footer">
                    <div class="desk-status ${status.class}">
                        <span class="dot"></span>
                        ${status.label}
                    </div>
                    <span class="desk-model">${modelShort}</span>
                </div>
                <span class="desk-open-btn">Открыть →</span>
            </div>
        `;
    }
    grid.innerHTML = html;
}

// --- Onboarding ---
function dismissOnboarding() {
    const banner = document.getElementById('onboardingBanner');
    if (banner) banner.classList.add('hidden');
    try { localStorage.setItem('onboarding_dismissed', '1'); } catch(e) {}
}

// --- Открыть панель агента ---
async function openAgentPanel(agentId) {
    currentAgentId = agentId;
    const panel = document.getElementById('agentPanel');
    const overlay = getOverlay();
    try {
        const res = await fetch(`${API_BASE}/api/agents/${agentId}`);
        const agent = await res.json();
        const icon = agent.icon || AGENT_ICONS[agentId] || '🤖';
        document.getElementById('panelIcon').textContent = icon;
        document.getElementById('panelName').textContent = agent.name;

        // Chat agent header
        const chatIcon = document.getElementById('chatAgentIcon');
        const chatName = document.getElementById('chatAgentName');
        if (chatIcon) chatIcon.textContent = icon;
        if (chatName) chatName.textContent = agent.name;
        const status = STATUS_MAP[agent.status] || STATUS_MAP.idle;
        document.getElementById('panelStatus').textContent = status.label;
        document.getElementById('panelModel').value = agent.model;
        document.getElementById('panelInstructions').value = agent.instructions || '';
        currentAttachmentObjects = agent.attachment_objects || [];
        renderAttachmentChips(currentAttachmentObjects, agent.attachments || []);
        renderChatHistory(agent.chat_history || []);
        await loadAgentMemory(agentId);

        // Collapsible tool sections
        const toolComfyuiSection = document.getElementById('toolComfyuiSection');
        const toolElevenlabsSection = document.getElementById('toolElevenlabsSection');
        if (toolComfyuiSection) toolComfyuiSection.style.display = (agentId === 'art_director') ? 'block' : 'none';
        if (toolElevenlabsSection) toolElevenlabsSection.style.display = (agentId === 'sound_director') ? 'block' : 'none';

        if (agentId === 'sound_director') loadVoices();

        panel.classList.add('open');
        overlay.classList.add('active');

        // Загружаем правила
        loadAgentRules(agentId);
    } catch (e) {
        console.error('Ошибка загрузки агента:', e);
    }
}

// --- Закрыть панель ---
function closeAgentPanel() {
    document.getElementById('agentPanel').classList.remove('open');
    getOverlay().classList.remove('active');
    currentAgentId = null;
    currentAttachmentObjects = [];
}

// --- Рендер активных вложений ---
function renderAttachmentChips(objects, legacyNames = []) {
    const container = document.getElementById('attachmentChips');
    const normalized = (objects && objects.length)
        ? objects
        : (legacyNames || []).map((name) => ({
            filename: name,
            original_name: name,
            is_text_readable: false,
            uploaded_at: '',
        }));
    if (!normalized.length) {
        container.innerHTML = '';
        return;
    }
    container.innerHTML = normalized.map((file) => {
        const savedName = file.filename || file.saved_name || '';
        const originalName = file.original_name || savedName || 'file';
        const badgeClass = file.is_text_readable ? '' : ' unreadable';
        const badgeText = file.is_text_readable ? 'читается' : (file.unreadable_reason || 'не читается моделью');
        const removeBtn = savedName ? `<button class="attachment-remove" onclick="deleteAttachment('${encodeURIComponent(savedName)}')" title="Удалить">✕</button>` : '';
        return `
            <div class="attachment-chip" title="${escapeHtml(originalName)}${file.unreadable_reason ? ' — ' + escapeHtml(file.unreadable_reason) : ''}">
                <span class="attachment-name">📎 ${escapeHtml(originalName)}</span>
                <span class="attachment-badge${badgeClass}">${badgeText}</span>
                ${removeBtn}
            </div>
        `;
    }).join('');
}

// --- Рендер истории чата ---
function renderChatHistory(history) {
    const container = document.getElementById('chatHistory');
    if (history.length === 0) {
        container.innerHTML = '<div style="font-size:12px;color:var(--text-muted);text-align:center;padding:20px">💬 Напишите задачу, например:<br><em>"Адаптируй сцену 3 эпизода 1"</em></div>';
        return;
    }
    container.innerHTML = history.map(msg => {
        const cls = msg.role === 'user' ? 'user' : 'assistant';
        const time = msg.time ? new Date(msg.time).toLocaleTimeString('ru-RU', {hour:'2-digit', minute:'2-digit'}) : '';
        return `<div class="chat-msg ${cls}">${escapeHtml(msg.content)}${time ? `<div class="msg-time">${time}</div>` : ''}</div>`;
    }).join('');
    container.scrollTop = container.scrollHeight;
}

// --- Отправить сообщение ---
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

// --- Сохранить инструкции ---
async function saveInstructions() {
    if (!currentAgentId) return;
    try {
        await fetch(`${API_BASE}/api/agents/${currentAgentId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ instructions: document.getElementById('panelInstructions').value, model: document.getElementById('panelModel').value })
        });
        alert('Сохранено!');
    } catch (e) {
        alert('Ошибка сохранения: ' + e.message);
    }
}

// --- Загрузить файл ---
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
        } else {
            alert('Ошибка: ' + (data.detail || 'Неизвестная ошибка'));
        }
    } catch (e) {
        alert('Ошибка загрузки: ' + e.message);
    }
}

async function deleteAttachment(encodedFilename) {
    if (!currentAgentId) return;
    const filename = decodeURIComponent(encodedFilename);
    try {
        const res = await fetch(`${API_BASE}/api/agents/${currentAgentId}/attachments/${encodeURIComponent(filename)}`, { method: 'DELETE' });
        const data = await res.json();
        if (!res.ok || !data.ok) { alert('Ошибка удаления: ' + (data.detail || 'Неизвестная ошибка')); return; }
        const agentRes = await fetch(`${API_BASE}/api/agents/${currentAgentId}`);
        const agent = await agentRes.json();
        currentAttachmentObjects = agent.attachment_objects || [];
        renderAttachmentChips(currentAttachmentObjects, agent.attachments || []);
    } catch (e) {
        alert('Ошибка удаления: ' + e.message);
    }
}

// ============================================
// МЕД-ОТДЕЛ
// ============================================

async function loadAgentMemory(agentId) {
    try {
        const res = await fetch(`${API_BASE}/api/med-otdel/${agentId}/memory`);
        const data = await res.json();
        document.getElementById('memoryVersion').textContent = data.current_version || 'v1';
        const fails = data.consecutive_failures || 0;
        const failsEl = document.getElementById('memoryFailures');
        failsEl.textContent = fails;
        failsEl.className = 'memory-badge ' + (fails >= 2 ? 'danger' : fails >= 1 ? 'warning' : 'ok');
        const healingEl = document.getElementById('memoryHealing');
        if (fails >= 2) { healingEl.textContent = 'Лечение...'; healingEl.className = 'memory-badge danger'; }
        else { healingEl.textContent = 'Нет'; healingEl.className = 'memory-badge ok'; }
        const lessonsContainer = document.getElementById('memoryLessons');
        if (data.lessons && data.lessons.length > 0) {
            lessonsContainer.innerHTML = data.lessons.map(l => `<div class="lesson-item">📝 ${escapeHtml(l.lesson)}</div>`).join('');
        } else {
            lessonsContainer.innerHTML = '<div style="font-size:12px;color:var(--text-muted)">Уроки появятся после оценки Critic\'ом</div>';
        }
    } catch (e) {
        console.error('Ошибка загрузки памяти:', e);
    }
}

async function evaluateResult() {
    if (!currentAgentId) return;
    const btn = document.getElementById('btnEvaluate');
    btn.disabled = true;
    btn.textContent = '⏳ Оценка...';
    try {
        const res = await fetch(`${API_BASE}/api/med-otdel/evaluate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agent_id: currentAgentId, task_description: '' })
        });
        const data = await res.json();
        const container = document.getElementById('chatHistory');
        const cls = data.passed ? 'assistant' : 'error';
        const icon = data.passed ? '✅' : '❌';
        container.innerHTML += `<div class="chat-msg ${cls}">${icon} Оценка: ${data.passed ? 'PASS' : 'FAIL'} (Score: ${data.score}/10)${data.feedback ? '\n' + escapeHtml(data.feedback) : ''}<div class="msg-time">${new Date().toLocaleTimeString('ru-RU', {hour:'2-digit', minute:'2-digit'})}</div></div>`;
        container.scrollTop = container.scrollHeight;
        await loadAgentMemory(currentAgentId);
        loadAgents();
    } catch (e) {
        alert('Ошибка оценки: ' + e.message);
    }
    btn.disabled = false;
    btn.textContent = '🔍 Оценить результат';
}

async function evolveAgent() {
    if (!currentAgentId) return;
    if (!confirm(`Эволюционировать агента ${currentAgentId}?`)) return;
    const btn = document.getElementById('btnEvolve');
    btn.disabled = true;
    btn.textContent = '⏳ Эволюция...';
    try {
        const res = await fetch(`${API_BASE}/api/med-otdel/${currentAgentId}/evolve`, { method: 'POST' });
        const data = await res.json();
        alert(`Эволюция завершена: ${data.old_version} → ${data.new_version}`);
        document.getElementById('panelInstructions').value = data.new_prompt || '';
        await loadAgentMemory(currentAgentId);
        loadAgents();
    } catch (e) {
        alert('Ошибка эволюции: ' + e.message);
    }
    btn.disabled = false;
    btn.textContent = '🧬 Эволюционировать';
}

// ============================================
// Задачи и МЕД-ОТДЕЛ
// ============================================

async function loadTasks() {
    try {
        const res = await fetch(`${API_BASE}/api/tasks/`);
        const data = await res.json();
        const activeContainer = document.getElementById('activeTasks');
        if (data.active && data.active.length > 0) {
            activeContainer.innerHTML = data.active.map(t => `<div class="task-item"><div class="task-title">${escapeHtml(t.title)}</div><div class="task-agent">${t.agent_id}</div></div>`).join('');
        } else {
            activeContainer.innerHTML = '<div style="font-size:12px;color:var(--text-muted)">Нет активных задач — используйте Orchestrator для запуска</div>';
        }
        try {
            const logRes = await fetch(`${API_BASE}/api/med-otdel/log`);
            const logData = await logRes.json();
            const medContainer = document.getElementById('medLog');
            if (logData.entries && logData.entries.length > 0) {
                medContainer.innerHTML = logData.entries.slice(-10).reverse().map(entry => `<div class="log-entry"><div style="font-weight:600">${escapeHtml(entry.action)}</div><div>${escapeHtml(entry.details)}</div>${entry.agent_id ? `<div style="color:var(--text-muted);font-size:11px">${entry.agent_id}</div>` : ''}</div>`).join('');
            } else {
                medContainer.innerHTML = '<div style="font-size:12px;color:var(--text-muted)">Записи появятся после оценки Critic\'ом</div>';
            }
        } catch (e) { console.error('Ошибка загрузки лога МЕД-ОТДЕЛА:', e); }
    } catch (e) { console.error('Ошибка загрузки задач:', e); }
    await loadStudioHealth();
    await loadTempAgents();
}

async function loadStudioHealth() {
    try {
        const res = await fetch(`${API_BASE}/api/med-otdel/studio-health`);
        const data = await res.json();
        const healthContainer = document.getElementById('medStudioHealth');
        const pct = data.error_percentage || 0;
        const statusClass = data.status || 'ok';
        healthContainer.innerHTML = `<div class="studio-health-bar"><div class="studio-health-fill ${statusClass}" style="width: ${100 - pct}%"></div></div><div class="studio-health-text ${statusClass}">${data.alert_message || `Здорово: ${data.total_agents - data.error_agents}/${data.total_agents} агентов OK`}</div>`;
        const agentList = document.getElementById('medAgentStatus');
        if (data.agents_health) {
            agentList.innerHTML = Object.entries(data.agents_health).map(([id, info]) => {
                const statusDot = info.status === 'error' ? 'error' : info.status === 'working' ? 'working' : 'idle';
                return `<div class="med-agent-item"><span class="agent-name">${info.name || id}</span><div class="agent-meta"><span class="agent-version">${info.version || 'v1'}</span>${info.consecutive_fails > 0 ? `<span class="agent-fails">⚠ ${info.consecutive_fails}</span>` : ''}<span class="agent-status-dot ${statusDot}"></span></div></div>`;
            }).join('');
        }
    } catch (e) { console.error('Ошибка загрузки здоровья студии:', e); }
}

// ============================================
// HR
// ============================================

async function createHrAgent() {
    const input = document.getElementById('hrTaskInput');
    const btn = document.getElementById('btnHrCreate');
    const taskDescription = input.value.trim();
    if (!taskDescription) { alert('Опишите задачу для создания агента'); return; }
    btn.disabled = true;
    btn.textContent = '⏳ HR анализирует...';
    try {
        const res = await fetch(`${API_BASE}/api/hr/create-agent`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ task_description: taskDescription })
        });
        const data = await res.json();
        if (data.ok) { alert(`Агент создан: ${data.name} (${data.role})`); input.value = ''; loadAgents(); loadTempAgents(); }
        else { alert('Ошибка: ' + (data.detail || 'Неизвестная ошибка')); }
    } catch (e) { alert('Ошибка создания агента: ' + e.message); }
    btn.disabled = false;
    btn.textContent = '👤 Создать агента';
}

async function loadTempAgents() {
    try {
        const res = await fetch(`${API_BASE}/api/hr/temp-agents`);
        const data = await res.json();
        const container = document.getElementById('hrTempAgents');
        if (data.agents && data.agents.length > 0) {
            container.innerHTML = data.agents.map(a => `<div class="temp-agent-item"><div class="temp-agent-info"><span class="temp-agent-icon">${a.icon || '🤖'}</span><div><div class="temp-agent-name">${a.name}</div><div class="temp-agent-role">${a.role}</div></div></div><button class="btn-remove-agent" onclick="removeTempAgent('${a.agent_id}')">✕</button></div>`).join('');
        } else {
            container.innerHTML = '<div style="font-size:12px;color:var(--text-muted)">Временные агенты создаются HR по запросу</div>';
        }
    } catch (e) { console.error('Ошибка загрузки временных агентов:', e); }
}

async function removeTempAgent(agentId) {
    if (!confirm('Удалить временного агента?')) return;
    try {
        const res = await fetch(`${API_BASE}/api/hr/${agentId}/remove`, { method: 'POST' });
        const data = await res.json();
        if (data.ok) { loadAgents(); loadTempAgents(); }
        else { alert('Ошибка: ' + (data.detail || 'Неизвестная ошибка')); }
    } catch (e) { alert('Ошибка удаления: ' + e.message); }
}

// ============================================
// Tools — Kie.ai & ElevenLabs
// ============================================

async function generateImage() {
    const prompt = document.getElementById('comfyui-prompt').value.trim();
    const negative = document.getElementById('comfyui-negative').value.trim();
    if (!prompt) { showError('comfyui', 'Введите описание изображения'); return; }
    setToolLoading('comfyui', true);
    try {
        const res = await fetch(`${API_BASE}/api/tools/generate-image`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt, negative_prompt: negative })
        });
        const data = await res.json();
        if (data.status === 'rate_limited') { showRateLimited('comfyui', data.retry_after || 30); return; }
        if (data.status === 'error' || data.status === 'timeout') { showError('comfyui', data.error || 'Ошибка генерации'); return; }
        if (data.status === 'success') { showImageResult(data.result_url); }
    } catch (e) { showError('comfyui', e.message); }
    setToolLoading('comfyui', false);
}

async function generateVoice() {
    const text = document.getElementById('elevenlabs-text').value.trim();
    const voiceId = document.getElementById('elevenlabs-voice').value;
    if (!text) { showError('elevenlabs', 'Введите текст для озвучки'); return; }
    if (!voiceId) { showError('elevenlabs', 'Выберите голос'); return; }
    setToolLoading('elevenlabs', true);
    try {
        const res = await fetch(`${API_BASE}/api/tools/generate-audio`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, voice_id: voiceId })
        });
        const data = await res.json();
        if (data.status === 'rate_limited') { showRateLimited('elevenlabs', data.retry_after || 30); return; }
        if (data.status === 'error') { showError('elevenlabs', data.error || 'Ошибка генерации'); return; }
        if (data.status === 'success') { showAudioResult(data.result_url); }
    } catch (e) { showError('elevenlabs', e.message); }
    setToolLoading('elevenlabs', false);
}

async function loadVoices() {
    try {
        const res = await fetch(`${API_BASE}/api/tools/voices`);
        const data = await res.json();
        const select = document.getElementById('elevenlabs-voice');
        if (data.voices && data.voices.length > 0) {
            select.innerHTML = data.voices.map(v => `<option value="${v.voice_id}">${v.name} (${v.category})</option>`).join('');
        } else {
            select.innerHTML = '<option value="">Нет доступных голосов (проверьте API ключ)</option>';
        }
    } catch (e) {
        document.getElementById('elevenlabs-voice').innerHTML = '<option value="">Ошибка загрузки</option>';
    }
}

function setToolLoading(tool, loading) {
    const btn = document.getElementById(tool === 'comfyui' ? 'btnComfyui' : 'btnElevenlabs');
    const spinner = document.getElementById(tool + '-spinner');
    btn.disabled = loading;
    spinner.classList.toggle('hidden', !loading);
    hideToolError(tool);
}

function showError(tool, message) {
    const el = document.getElementById(tool + '-error');
    el.querySelector('.error-text').textContent = message;
    el.classList.remove('hidden');
}

function hideToolError(tool) {
    document.getElementById(tool + '-error').classList.add('hidden');
}

function showImageResult(url) {
    document.getElementById('comfyui-image').src = url;
    document.getElementById('comfyui-result').classList.remove('hidden');
    document.getElementById('comfyui-spinner').classList.add('hidden');
}

function showAudioResult(url) {
    document.getElementById('elevenlabs-audio').src = url;
    document.getElementById('elevenlabs-result').classList.remove('hidden');
    document.getElementById('elevenlabs-spinner').classList.add('hidden');
}

function showRateLimited(tool, seconds) {
    const btn = document.getElementById(tool === 'comfyui' ? 'btnComfyui' : 'btnElevenlabs');
    btn.disabled = true;
    let remaining = seconds;
    btn.textContent = `Доступно через ${remaining} сек`;
    const interval = setInterval(() => {
        remaining--;
        if (remaining <= 0) { clearInterval(interval); btn.disabled = false; btn.textContent = tool === 'comfyui' ? '🎨 Сгенерировать' : '🎵 Сгенерировать голос'; }
        else { btn.textContent = `Доступно через ${remaining} сек`; }
    }, 1000);
}

// ============================================
// Overlay и панели
// ============================================

function getOverlay() { return document.getElementById('overlay'); }

function toggleTasksPanel() {
    const panel = document.getElementById('tasksPanel');
    panel.classList.toggle('open');
    if (panel.classList.contains('open')) { getOverlay().classList.add('active'); loadTasks(); }
    else { getOverlay().classList.remove('active'); }
}

function closeTasksPanel() { document.getElementById('tasksPanel').classList.remove('open'); }

// ============================================
// Утилиты
// ============================================

function escapeHtml(text) { const div = document.createElement('div'); div.textContent = text; return div.innerHTML; }

// ============================================
// Discussion Panel
// ============================================

async function loadDiscussion() {
    try {
        const res = await fetch(`${API_BASE}/api/discussion/`);
        const data = await res.json();
        const messages = data.messages || [];

        // Обновляем счётчик непрочитанных
        if (messages.length > 0) {
            const latestTimestamp = messages[messages.length - 1].timestamp || '';
            if (latestTimestamp > lastDiscussionTimestamp) {
                const newMessages = messages.filter(m => m.timestamp > lastDiscussionTimestamp);
                if (newMessages.length > 0 && !document.getElementById('discussionPanel').classList.contains('open')) {
                    discussionUnreadCount += newMessages.length;
                    updateDiscussionBadge();
                }
                lastDiscussionTimestamp = latestTimestamp;
            }
        }

        renderDiscussionMessages(messages);
    } catch (e) {
        console.error('Ошибка загрузки обсуждения:', e);
    }
}

function updateDiscussionBadge() {
    const badge = document.getElementById('discussionBadge');
    if (badge) {
        if (discussionUnreadCount > 0) {
            badge.textContent = discussionUnreadCount > 99 ? '99+' : discussionUnreadCount;
            badge.style.display = 'inline-block';
        } else {
            badge.style.display = 'none';
        }
    }
}

function resetDiscussionBadge() {
    discussionUnreadCount = 0;
    updateDiscussionBadge();
}

function renderDiscussionMessages(messages) {
    const container = document.getElementById('discussionMessages');
    if (!messages.length) {
        container.innerHTML = '<div style="font-size:12px;color:var(--text-muted);text-align:center;padding:20px">Нет сообщений</div>';
        return;
    }
    const typeLabels = {
        user: 'Вы',
        agent: 'Агент',
        critic: 'Критик',
        med_otdel: 'МЕД-ОТДЕЛ',
        system: 'Система'
    };
    container.innerHTML = messages.map(msg => {
        const type = msg.msg_type || 'system';
        const sender = msg.agent_id || 'system';
        const time = msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString('ru-RU', {hour:'2-digit', minute:'2-digit'}) : '';
        return `
            <div class="discussion-msg type-${type}">
                <div class="msg-header">
                    <span class="msg-sender">${typeLabels[type] || sender}</span>
                    <span class="msg-time">${time}</span>
                </div>
                <div class="msg-content">${escapeHtml(msg.content)}</div>
            </div>
        `;
    }).join('');
    container.scrollTop = container.scrollHeight;
}

async function sendDiscussionMessage() {
    const input = document.getElementById('discussionInput');
    const content = input.value.trim();
    if (!content) return;
    input.value = '';
    try {
        await fetch(`${API_BASE}/api/discussion/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agent_id: 'user', content, msg_type: 'user' })
        });
        loadDiscussion();
    } catch (e) {
        alert('Ошибка отправки: ' + e.message);
    }
}

function toggleDiscussionPanel() {
    const panel = document.getElementById('discussionPanel');
    panel.classList.toggle('open');
    if (panel.classList.contains('open')) {
        getOverlay().classList.add('active');
        loadDiscussion();
        resetDiscussionBadge();
    } else {
        getOverlay().classList.remove('active');
    }
}

function closeDiscussionPanel() {
    document.getElementById('discussionPanel').classList.remove('open');
}

// ============================================
// Rule Builder
// ============================================

let availablePatterns = [];

async function loadAgentRules(agentId) {
    try {
        const res = await fetch(`${API_BASE}/api/med-otdel/${agentId}/rules`);
        const data = await res.json();
        renderRules(data.rules || []);
    } catch (e) {
        console.error('Ошибка загрузки правил:', e);
    }
}

async function loadAvailablePatterns() {
    try {
        const res = await fetch(`${API_BASE}/api/med-otdel/patterns`);
        const data = await res.json();
        availablePatterns = data.patterns || [];
        renderPatternsSelect();
    } catch (e) {
        console.error('Ошибка загрузки паттернов:', e);
    }
}

function renderRules(rules) {
    const container = document.getElementById('rulesList');
    if (!rules.length) {
        container.innerHTML = '<div style="font-size:12px;color:var(--text-muted)">Правила появятся автоматически после оценки Critic\'ом</div>';
        return;
    }
    container.innerHTML = rules.map(rule => `
        <div class="rule-item">
            <div>
                <div class="rule-name">${escapeHtml(rule.name || rule.key)}</div>
                <div class="rule-desc">${escapeHtml(rule.description || '')}</div>
            </div>
            <button class="rule-remove" onclick="removeRule('${rule.key}')" title="Удалить правило">✕</button>
        </div>
    `).join('');
}

function renderPatternsSelect() {
    const select = document.getElementById('rulesSelect');
    select.innerHTML = '<option value="">Выберите правило...</option>';
    availablePatterns.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.key;
        opt.textContent = p.name || p.key;
        select.appendChild(opt);
    });
}

async function addRule() {
    const select = document.getElementById('rulesSelect');
    const patternKey = select.value;
    if (!patternKey || !currentAgentId) return;

    try {
        const res = await fetch(`${API_BASE}/api/med-otdel/apply-pattern`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agent_id: currentAgentId, pattern_key: patternKey })
        });
        const data = await res.json();
        if (data.ok) {
            loadAgentRules(currentAgentId);
            select.value = '';
        } else {
            alert('Ошибка: ' + (data.error || 'Неизвестная ошибка'));
        }
    } catch (e) {
        alert('Ошибка добавления правила: ' + e.message);
    }
}

async function removeRule(patternKey) {
    if (!currentAgentId) return;
    try {
        const res = await fetch(`${API_BASE}/api/med-otdel/remove-pattern`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agent_id: currentAgentId, pattern_key: patternKey })
        });
        const data = await res.json();
        if (data.ok) {
            loadAgentRules(currentAgentId);
        } else {
            alert('Ошибка: ' + (data.error || 'Неизвестная ошибка'));
        }
    } catch (e) {
        alert('Ошибка удаления правила: ' + e.message);
    }
}

// ============================================
// Orchestrator
// ============================================

async function submitOrchTask() {
    const input = document.getElementById('orchTaskInput');
    const btn = document.getElementById('btnOrchSubmit');
    const desc = input.value.trim();
    if (!desc) { alert('Опишите задачу'); return; }

    btn.disabled = true;
    btn.textContent = '⏳ Анализ...';

    try {
        const res = await fetch(`${API_BASE}/api/orchestrator/submit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ description: desc })
        });
        const data = await res.json();
        if (data.ok) {
            input.value = '';
            loadOrchTasks();
        } else {
            alert('Ошибка: ' + (data.detail || 'Неизвестная ошибка'));
        }
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }

    btn.disabled = false;
    btn.textContent = '🚀 Запустить';
}

async function loadOrchTasks() {
    try {
        const res = await fetch(`${API_BASE}/api/orchestrator/active`);
        const data = await res.json();
        renderOrchTasks(data.tasks || []);
    } catch (e) {
        console.error('Ошибка загрузки задач Orchestrator:', e);
    }
}

function renderOrchTasks(tasks) {
    const container = document.getElementById('orchActiveTasks');
    if (!tasks.length) {
        container.innerHTML = '<div style="font-size:12px;color:var(--text-muted)">Нет активных задач</div>';
        return;
    }
    container.innerHTML = tasks.map(t => {
        const progress = Math.round(t.progress || 0);
        const statusClass = t.status || 'pending';
        const stepsInfo = t.steps ? `Шаг ${t.current_step + 1}/${t.steps.length}` : '';
        const cancelBtn = t.status === 'running' ? `<button class="btn-orch-cancel" onclick="cancelOrchTask('${t.task_id}')">✕ Отмена</button>` : '';
        return `
            <div class="orch-task-item">
                <div class="orch-task-desc">${escapeHtml(t.description)}</div>
                <div class="orch-task-progress">${stepsInfo} — ${progress}%</div>
                <div class="orch-task-bar"><div class="orch-task-fill" style="width: ${progress}%"></div></div>
                <div class="orch-task-status ${statusClass}">${statusClass}</div>
                ${cancelBtn}
            </div>
        `;
    }).join('');
}

async function cancelOrchTask(taskId) {
    try {
        await fetch(`${API_BASE}/api/orchestrator/intervene/${taskId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'cancel' })
        });
        loadOrchTasks();
    } catch (e) {
        alert('Ошибка отмены: ' + e.message);
    }
}

// ============================================
// Bind Events
// ============================================

function bindEvents() {
    document.getElementById('panelClose').addEventListener('click', closeAgentPanel);
    document.getElementById('btnSend').addEventListener('click', sendMessage);
    document.getElementById('btnSaveInstructions').addEventListener('click', saveInstructions);
    document.getElementById('btnAttach').addEventListener('click', () => document.getElementById('fileInput').click());
    document.getElementById('fileInput').addEventListener('change', uploadFile);
    document.getElementById('tasksOpenBtn').addEventListener('click', toggleTasksPanel);
    document.getElementById('tasksClose').addEventListener('click', closeTasksPanel);
    document.getElementById('discussionOpenBtn').addEventListener('click', toggleDiscussionPanel);
    document.getElementById('discussionClose').addEventListener('click', closeDiscussionPanel);
    document.getElementById('discussionSend').addEventListener('click', sendDiscussionMessage);
    document.getElementById('btnEvaluate').addEventListener('click', evaluateResult);
    document.getElementById('btnEvolve').addEventListener('click', evolveAgent);
    document.getElementById('btnHrCreate').addEventListener('click', createHrAgent);
    document.getElementById('btnAddRule').addEventListener('click', addRule);
    document.getElementById('btnOrchSubmit').addEventListener('click', submitOrchTask);

    // Загрузка задач Orchestrator каждые 2 сек
    setInterval(loadOrchTasks, 2000);

    getOverlay().addEventListener('click', () => { closeAgentPanel(); closeTasksPanel(); closeDiscussionPanel(); });

    document.getElementById('chatInput').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    });
    document.getElementById('discussionInput').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendDiscussionMessage(); }
    });
}

// ============================================
// Roadmap v4 — Production Data
// ============================================

async function loadProductionData() {
    loadProductionStatus();
    loadCharacters();
    loadMoodBoard();
    loadDecisionLog();
}

async function loadProductionStatus() {
    try {
        const res = await fetch(`${API_BASE}/api/episodes/status`);
        const data = await res.json();
        const container = document.getElementById('productionStatus');
        if (!container) return;
        const total = data.total_episodes || 0;
        const byStatus = data.by_status || {};
        let html = `<div class="status-row"><span class="status-label">Всего эпизодов</span><span class="status-count">${total}</span></div>`;
        const statusLabels = { draft: 'Черновик', in_review: 'На проверке', approved: 'Утверждена', in_generation: 'В генерации', completed: 'Готово' };
        for (const [status, count] of Object.entries(byStatus)) {
            html += `<div class="status-row"><span class="status-label">${statusLabels[status] || status}</span><span class="status-count">${count}</span></div>`;
        }
        container.innerHTML = html;
    } catch (e) { /* silent */ }
}

async function loadCharacters() {
    try {
        const res = await fetch(`${API_BASE}/api/episodes/characters`);
        const data = await res.json();
        const container = document.getElementById('charactersList');
        if (!container) return;
        if (!data.characters || !data.characters.length) {
            container.innerHTML = '<div style="font-size:12px;color:var(--text-muted)">Персонажи появятся после анализа сценария</div>';
            return;
        }
        container.innerHTML = data.characters.map(c => `
            <div class="character-item">
                <div><div class="char-name">${escapeHtml(c.name)}</div><div class="char-desc">${escapeHtml(c.description || '')}</div></div>
            </div>
        `).join('');
    } catch (e) { /* silent */ }
}

async function loadMoodBoard() {
    try {
        const res = await fetch(`${API_BASE}/api/episodes/mood-board`);
        const data = await res.json();
        const container = document.getElementById('moodBoard');
        if (!container) return;
        if (!data.mood_board || !data.mood_board.length) {
            container.innerHTML = '<div style="font-size:12px;color:var(--text-muted);grid-column:span 2">Добавьте референсы через Kie.ai</div>';
            return;
        }
        container.innerHTML = data.mood_board.map(m => `
            <div class="mood-item">${m.url ? `<img src="${escapeHtml(m.url)}" alt="">` : escapeHtml(m.description || '🎨')}</div>
        `).join('');
    } catch (e) { /* silent */ }
}

async function loadDecisionLog() {
    try {
        const res = await fetch(`${API_BASE}/api/episodes/decisions`);
        const data = await res.json();
        const container = document.getElementById('decisionLog');
        if (!container) return;
        if (!data.decisions || !data.decisions.length) {
            container.innerHTML = '<div style="font-size:12px;color:var(--text-muted)">Решения запишутся автоматически при работе агентов</div>';
            return;
        }
        container.innerHTML = data.decisions.slice(-10).reverse().map(d => `
            <div class="decision-item">
                <div class="decision-title">${escapeHtml(d.title)}</div>
                ${d.agent_id ? `<div class="decision-agent">${escapeHtml(d.agent_id)}</div>` : ''}
            </div>
        `).join('');
    } catch (e) { /* silent */ }
}
