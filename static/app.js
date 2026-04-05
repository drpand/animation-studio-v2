/* ============================================
   Animation Studio v2 — РОДИНА
   Logic v12: Orchestrator First & Script Upload Fix
   ============================================ */

const API_BASE = '';
let agents = [];
let currentAgentId = null;
let currentAttachmentObjects = [];

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
    loadActiveProject();
    loadAgents();
    loadStoryboard();
    bindEvents();
    loadAvailablePatterns();
    setInterval(loadAgents, 5000);
    setInterval(loadStoryboard, 10000);
    setInterval(loadActiveProject, 15000);

    // Start with Agents View
    switchView('agentsView');
});

// --- Navigation ---
function switchView(viewId) {
    document.querySelectorAll('.main-view').forEach(v => v.classList.add('hidden'));
    document.getElementById(viewId).classList.remove('hidden');
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    if (viewId === 'dashboardView') document.getElementById('dashboardBtn').classList.add('active');
    if (viewId === 'storyboardView') document.getElementById('storyboardBtn').classList.add('active');
    if (viewId === 'agentsView') document.getElementById('agentsBtn').classList.add('active');
}

// --- Server Check ---
async function checkServer() {
    try {
        const res = await fetch(`${API_BASE}/health`);
        if (res.ok) {
            document.getElementById('serverStatus').classList.add('online');
            document.querySelector('.status-text').textContent = 'Онлайн';
        }
    } catch {
        document.querySelector('.status-text').textContent = 'Оффлайн';
    }
}

// --- Active Project ---
async function loadActiveProject() {
    try {
        const res = await fetch(`${API_BASE}/api/project/`);
        if (res.ok) {
            const data = await res.json();
            const project = data.active_project;
            const badge = document.getElementById('projectBadge');
            if (badge && project) {
                badge.textContent = project.name ? `Проект: ${project.name}` : 'Проект: Новый';
                window._activeProject = project;
            }
        }
    } catch (e) {
        console.error("Failed to load project", e);
    }
}

// --- Agents ---
async function loadAgents() {
    try {
        const res = await fetch(`${API_BASE}/api/agents/`);
        const data = await res.json();
        agents = data.agents || [];
        renderOffice();
    } catch (e) { console.error(e); }
}

function renderOffice() {
    const grid = document.getElementById('officeGrid');
    if (!grid) return;
    if (agents.length === 0) {
        grid.innerHTML = '<div class="office-loading">Нет агентов</div>';
        return;
    }
    grid.innerHTML = agents.map(agent => {
        const icon = agent.icon || AGENT_ICONS[agent.agent_id] || '🤖';
        const isOrchestrator = agent.agent_id === 'orchestrator';
        return `
            <div class="agent-desk ${isOrchestrator ? 'orchestrator-desk' : ''}" onclick="openAgentPanel('${agent.agent_id}')">
                <span class="desk-icon">${icon}</span>
                <div class="desk-name">${agent.name}</div>
                <div class="desk-role">${agent.role}</div>
            </div>`;
    }).join('');
}

async function openAgentPanel(agentId) {
    currentAgentId = agentId;
    const panel = document.getElementById('agentPanel');
    try {
        const res = await fetch(`${API_BASE}/api/agents/${agentId}`);
        const agent = await res.json();
        const icon = agent.icon || AGENT_ICONS[agentId] || '🤖';
        document.getElementById('panelIcon').textContent = icon;
        document.getElementById('panelName').textContent = agent.name;
        document.getElementById('panelModel').value = agent.model;
        document.getElementById('panelInstructions').value = agent.instructions || '';
        currentAttachmentObjects = agent.attachment_objects || [];
        renderAttachmentChips(currentAttachmentObjects, agent.attachments || []);
        renderChatHistory(agent.chat_history || []);
        
        const kieaiSection = document.getElementById('toolKieaiSection');
        if (kieaiSection) kieaiSection.style.display = (agentId === 'art_director') ? 'block' : 'none';

        panel.classList.add('open');
        loadAgentRules(agentId);
    } catch (e) { console.error(e); }
}

function closeAgentPanel() {
    document.getElementById('agentPanel').classList.remove('open');
    currentAgentId = null;
    currentAttachmentObjects = [];
}

// --- Chat ---
function renderChatHistory(history) {
    const container = document.getElementById('chatHistory');
    if (!container) return;
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
            method: 'POST', headers: { 'Content-Type': 'application/json' },
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
    if (!container) return;
    const normalized = (objects && objects.length) ? objects : (legacyNames || []).map(n => ({ filename: n, original_name: n, is_text_readable: false }));
    if (!normalized.length) { container.innerHTML = ''; return; }
    container.innerHTML = normalized.map(f => {
        const name = f.original_name || f.filename || 'file';
        const badge = f.is_text_readable ? '<span class="attachment-badge">читается</span>' : '<span class="attachment-badge unreadable">не читается</span>';
        return `<div class="attachment-chip"><span>📎 ${escapeHtml(name)}</span>${badge}</div>`;
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
        }
    } catch (e) { alert('Ошибка загрузки: ' + e.message); }
}

// --- Send Task to Orchestrator (Text or File) ---
async function sendTask() {
    const input = document.getElementById('producerInput');
    const fileInput = document.getElementById('scriptFile');
    const task = input.value.trim();
    const hasFile = fileInput && fileInput.files && fileInput.files.length > 0;

    const statusDiv = document.getElementById('currentTaskStatus');
    
    // Если есть файл — загружаем его
    if (hasFile) {
        await uploadScript();
        return;
    }

    // Если есть текст — отправляем задачу
    if (!task) { 
        statusDiv.textContent = '❌ Введите задачу или выберите файл';
        statusDiv.style.color = 'var(--red)';
        return; 
    }

    statusDiv.textContent = '⏳ Оркестратор анализирует задачу...';
    statusDiv.style.color = 'var(--yellow)';

    try {
        const res = await fetch(`${API_BASE}/api/orchestrator/task`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ description: task })
        });
        const data = await res.json();
        if (data.ok) {
            statusDiv.textContent = '✅ Задача принята!';
            statusDiv.style.color = 'var(--green)';
            input.value = '';
            setTimeout(() => switchView('storyboardView'), 1000);
        } else {
            statusDiv.textContent = '❌ Ошибка: ' + (data.error || 'Неизвестная ошибка');
            statusDiv.style.color = 'var(--red)';
        }
    } catch (e) {
        statusDiv.textContent = '❌ Ошибка сети: ' + e.message;
        statusDiv.style.color = 'var(--red)';
    }
}

// --- Script Upload for Orchestrator ---
async function uploadScript() {
    const input = document.getElementById('scriptFile');
    const nameDisplay = document.getElementById('selectedFileName');
    
    if (!input || !input.files || input.files.length === 0) {
        nameDisplay.textContent = '';
        return;
    }
    
    const file = input.files[0];
    // Show file name immediately
    nameDisplay.textContent = `📄 ${file.name}`;
    
    console.log('Uploading file:', file.name, file.size, 'bytes');

    const statusDiv = document.getElementById('uploadStatus');
    statusDiv.textContent = `⏳ Загрузка: ${file.name}...`;
    statusDiv.style.color = 'var(--yellow)';

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch(`${API_BASE}/api/orchestrator/upload-script`, {
            method: 'POST',
            body: formData
        });
        
        console.log('Server response status:', res.status);
        const data = await res.json();
        console.log('Server response data:', data);

        if (res.ok && data.ok) {
            statusDiv.textContent = `✅ Сценарий "${file.name}" успешно загружен! Открываю Оркестратора...`;
            statusDiv.style.color = 'var(--green)';
            nameDisplay.textContent = `✅ ${file.name}`;
            // Автоматически открываем чат с Оркестратором
            setTimeout(() => openAgentPanel('orchestrator'), 1500);
        } else {
            throw new Error(data.detail || data.error || 'Ошибка сервера');
        }
    } catch (e) {
        console.error('Upload failed:', e);
        statusDiv.textContent = `❌ Ошибка загрузки: ${e.message}`;
        statusDiv.style.color = 'var(--red)';
        nameDisplay.textContent = `❌ ${file.name}`;
    }
    
    // Очищаем input чтобы можно было загрузить тот же файл снова
    input.value = '';
}

// --- Evaluate ---
async function evaluateResult() {
    if (!currentAgentId) return;
    const btn = document.getElementById('btnEvaluate');
    btn.disabled = true;
    btn.textContent = '⏳ Оценка...';
    try {
        const res = await fetch(`${API_BASE}/api/med-otdel/evaluate`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
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
            method: 'POST', headers: { 'Content-Type': 'application/json' },
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

// --- Storyboard ---
async function loadStoryboard() {
    try {
        const res = await fetch(`${API_BASE}/api/orchestrator/storyboard/frames`);
        if (res.ok) {
            const data = await res.json();
            window._storyboardFrames = data.frames || [];
            renderStoryboard(window._storyboardFrames);
        } else {
            window._storyboardFrames = [];
            renderStoryboard([]);
        }
    } catch (e) {
        console.error("Failed to load storyboard", e);
        window._storyboardFrames = [];
        renderStoryboard([]);
    }
}

function renderStoryboard(scenes) {
    const grid = document.getElementById('storyboardGrid');
    if (!grid) return;

    if (!scenes || scenes.length === 0) {
        grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-muted);">Нет кадров. Запустите конвейер — студия создаёт раскадровку автоматически.</div>';
        return;
    }

    grid.innerHTML = scenes.map((frame, index) => {
        const status = frame.status || 'draft';
        const hasImage = frame.image_url;

        let statusIcon = '🔄';
        if (status === 'approved') statusIcon = '✅';
        else if (status === 'in_review') statusIcon = '👀';
        else if (status === 'revision') statusIcon = '📝';

        return `
            <div class="scene-card" onclick="openSceneModal(${index})">
                <div class="card-header">
                    <span class="card-title">Кадр ${frame.scene_num || index + 1}</span>
                    <span class="card-status">${statusIcon}</span>
                </div>
                <div class="card-preview">
                    ${hasImage ? `<img src="${frame.image_url}" alt="Кадр ${frame.scene_num || index + 1}">` : '<span class="placeholder">Нет изображения</span>'}
                </div>
                <div class="card-footer">
                    <div class="card-desc">${(frame.writer_text || frame.final_prompt || 'Ожидание...').substring(0, 100)}...</div>
                </div>
            </div>
        `;
    }).join('');
}

let currentSceneData = null;

function openSceneModal(index) {
    // Получаем данные кадра из уже загруженного списка
    const frame = (window._storyboardFrames || [])[index];
    if (!frame) return;
    currentSceneData = frame;
    document.getElementById('modalSceneTitle').textContent = `Кадр ${frame.scene_num || index + 1}`;
    document.getElementById('modalSceneText').textContent = frame.writer_text || frame.final_prompt || 'Нет текста';
    document.getElementById('modalSceneImage').src = frame.image_url || '';
    document.getElementById('modalCriticReport').textContent = frame.critic_feedback || 'Нет замечаний';
    document.getElementById('sceneModal').classList.add('open');
}

function closeSceneModal() {
    document.getElementById('sceneModal').classList.remove('open');
    currentSceneData = null;
}

async function approveScene() {
    if (!currentSceneData) return;
    try {
        await fetch(`${API_BASE}/api/orchestrator/scene-action/1/1/1`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'approve', comment: '' })
        });
        alert('Сцена утверждена! Запуск следующей сцены...');
        closeSceneModal();
        loadStoryboard();
    } catch (e) { alert('Ошибка: ' + e.message); }
}

async function reviseScene() {
    if (!currentSceneData) return;
    const comment = document.getElementById('revisionComment').value;
    try {
        await fetch(`${API_BASE}/api/orchestrator/scene-action/1/1/1`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'revise', comment })
        });
        alert('Отправлено на доработку!');
        closeSceneModal();
        loadStoryboard();
    } catch (e) { alert('Ошибка: ' + e.message); }
}

// --- Characters ---
async function loadCharacters() {
    try {
        const res = await fetch(`${API_BASE}/api/characters/`);
        const data = await res.json();
        renderCharacters(data.characters || []);
    } catch (e) {}
}

function renderCharacters(characters) {
    const container = document.getElementById('charactersList');
    if (!container) return;
    if (!characters.length) {
        container.innerHTML = '<div style="font-size:12px;color:var(--text-muted);text-align:center;padding:20px">Нет персонажей. Запустите конвейер — HR создаст карточки автоматически.</div>';
        return;
    }
    container.innerHTML = characters.map(c => `
        <div class="character-card">
            <div class="char-name">${escapeHtml(c.name)}</div>
            <div class="char-desc">${escapeHtml(c.description || '')}</div>
        </div>
    `).join('');
}

function toggleCharactersPanel() {
    const panel = document.getElementById('charactersPanel');
    panel.classList.toggle('open');
    if (panel.classList.contains('open')) {
        loadCharacters();
    }
}

function closeCharactersPanel() {
    document.getElementById('charactersPanel').classList.remove('open');
}

// --- Utils ---
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// --- Save Instructions ---
async function saveInstructions() {
    if (!currentAgentId) return;
    const instructions = document.getElementById('panelInstructions').value;
    const model = document.getElementById('panelModel').value;
    const btn = document.getElementById('btnSaveInstructions');
    btn.textContent = '? ࠭...';
    btn.disabled = true;
    try {
        const res = await fetch(`${API_BASE}/api/agents/${currentAgentId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ instructions, model })
        });
        const data = await res.json();
        if (data.ok) {
            btn.textContent = '? ࠭';
            setTimeout(() => { btn.textContent = '࠭'; btn.disabled = false; }, 1500);
        } else {
            btn.textContent = '? 訡';
            setTimeout(() => { btn.textContent = '࠭'; btn.disabled = false; }, 2000);
        }
    } catch (e) {
        btn.textContent = '? 訡 ';
        setTimeout(() => { btn.textContent = '࠭'; btn.disabled = false; }, 2000);
    }
}

// --- Bind Events ---
function bindEvents() {
    // Navigation
    document.getElementById('dashboardBtn').addEventListener('click', () => switchView('dashboardView'));
    document.getElementById('storyboardBtn').addEventListener('click', () => switchView('storyboardView'));
    document.getElementById('agentsBtn').addEventListener('click', () => switchView('agentsView'));
    document.getElementById('charactersBtn').addEventListener('click', toggleCharactersPanel);
    document.getElementById('charactersClose').addEventListener('click', closeCharactersPanel);
    
    // Agent Panel
    document.getElementById('panelClose').addEventListener('click', closeAgentPanel);
    document.getElementById('btnSend').addEventListener('click', sendMessage);
    document.getElementById('btnSaveInstructions').addEventListener('click', saveInstructions);
    document.getElementById('btnAttach').addEventListener('click', () => document.getElementById('fileInput').click());
    document.getElementById('fileInput').addEventListener('change', uploadFile);
    document.getElementById('btnEvaluate').addEventListener('click', evaluateResult);

    // Script Upload — only on "Execute" button click (not on file select to avoid double upload)
    document.getElementById('scriptFile').addEventListener('change', () => {
        const nameDisplay = document.getElementById('selectedFileName');
        const file = document.getElementById('scriptFile').files[0];
        if (file) {
            nameDisplay.textContent = `📄 ${file.name}`;
        }
    });
    
    // Execute Task Button
    document.getElementById('btnSendTask').addEventListener('click', sendTask);

    // Modal
    document.getElementById('modalClose').addEventListener('click', closeSceneModal);
    document.getElementById('btnApproveScene').addEventListener('click', approveScene);
    document.getElementById('btnReviseScene').addEventListener('click', reviseScene);
    document.getElementById('overlay').addEventListener('click', closeSceneModal);

    document.getElementById('chatInput').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    });
}
