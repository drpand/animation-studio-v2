/* ============================================
   Animation Studio v2
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
            statusDiv.textContent = `✅ ${data.message}`;
            statusDiv.style.color = 'var(--green)';
            input.value = '';
            
            // Запускаем polling статуса задачи
            pollTaskStatus(data.task_id);
        } else {
            statusDiv.textContent = '❌ Ошибка: ' + (data.error || 'Неизвестная ошибка');
            statusDiv.style.color = 'var(--red)';
        }
    } catch (e) {
        statusDiv.textContent = '❌ Ошибка сети: ' + e.message;
        statusDiv.style.color = 'var(--red)';
    }
}

// --- Poll Task Status ---
async function pollTaskStatus(taskId) {
    const statusDiv = document.getElementById('currentTaskStatus');
    const pollInterval = 3000; // 3 секунды
    const maxPolls = 200; // ~10 минут максимум
    let pollCount = 0;

    const poll = async () => {
        pollCount++;
        if (pollCount > maxPolls) {
            statusDiv.textContent = '⏱️ Таймаут. Проверь Storyboard — возможно задача завершена.';
            statusDiv.style.color = 'var(--yellow)';
            return;
        }

        try {
            const res = await fetch(`${API_BASE}/api/orchestrator/task/${taskId}`);
            if (!res.ok) {
                statusDiv.textContent = '❌ Задача не найдена';
                statusDiv.style.color = 'var(--red)';
                return;
            }
            const data = await res.json();

            // Обновляем статус с прогрессом
            const progress = data.progress || 0;
            const step = data.current_step || '';
            const bar = '█'.repeat(Math.floor(progress / 5)) + '░'.repeat(20 - Math.floor(progress / 5));
            statusDiv.innerHTML = `
                <div style="margin-bottom:4px;">${step}</div>
                <div style="font-family:monospace;color:var(--yellow);">${bar} ${progress}%</div>
            `;

            if (data.status === 'completed') {
                statusDiv.innerHTML = `✅ Конвейер завершён! Загружаю storyboard...`;
                statusDiv.style.color = 'var(--green)';
                loadStoryboard();
                setTimeout(() => switchView('storyboardView'), 1500);
                return;
            }

            if (data.status === 'failed') {
                statusDiv.textContent = `❌ Ошибка: ${data.error || 'Неизвестная ошибка'}`;
                statusDiv.style.color = 'var(--red)';
                return;
            }

            // Продолжаем polling
            setTimeout(poll, pollInterval);
        } catch (e) {
            console.error('Poll error:', e);
            setTimeout(poll, pollInterval);
        }
    };

    // Первый poll через 2 секунды
    setTimeout(poll, 2000);
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
    const frame = (window._storyboardFrames || [])[index];
    if (!frame) return;
    currentSceneData = frame;

    document.getElementById('modalSceneTitle').textContent = `Кадр ${frame.scene_num || index + 1}`;
    document.getElementById('modalSceneText').textContent = frame.writer_text || frame.final_prompt || 'Нет текста';
    document.getElementById('modalSceneImage').src = frame.image_url || '';
    document.getElementById('modalCriticReport').textContent = frame.critic_feedback || 'Нет замечаний';

    // Показываем промпт для редактирования
    const promptSection = document.getElementById('promptEditSection');
    const promptEditor = document.getElementById('modalPromptEditor');
    const btnRegenerate = document.getElementById('btnRegenerate');
    if (frame.final_prompt) {
        promptSection.style.display = 'block';
        promptEditor.value = frame.final_prompt;
        btnRegenerate.style.display = 'inline-block';
    } else {
        promptSection.style.display = 'none';
        btnRegenerate.style.display = 'none';
    }

    // Решения цехов
    const deptSection = document.getElementById('departmentsSection');
    const dopField = document.getElementById('modalDopPrompt');
    const artField = document.getElementById('modalArtPrompt');
    const soundField = document.getElementById('modalSoundPrompt');
    const hintClothing = document.getElementById('hintClothing');
    const hintSeason = document.getElementById('hintSeason');
    const hintColor = document.getElementById('hintColor');
    if (deptSection) {
        deptSection.style.display = 'block';
        const pp = frame.prompt_parts || {};
        dopField.value = frame.dop_prompt || (pp.source?.dop ? JSON.stringify(pp.source.dop, null, 2) : '');
        artField.value = frame.art_prompt || (pp.source?.art ? JSON.stringify(pp.source.art, null, 2) : '');
        soundField.value = frame.sound_prompt || (pp.source?.sound ? JSON.stringify(pp.source.sound, null, 2) : '');
        const hints = frame.edit_hints || pp.edit_hints || {};
        hintClothing.value = hints.clothing || '';
        hintSeason.value = hints.season || '';
        hintColor.value = hints.color || '';
    }

    // CV секция — показываем если есть изображение
    const cvSection = document.getElementById('cvCheckSection');
    const cvStatus = document.getElementById('cvStatus');
    const cvResult = document.getElementById('cvResult');
    if (frame.image_url) {
        cvSection.style.display = 'block';
        if (frame.cv_score > 0) {
            // Уже есть CV проверка — показываем результат
            cvStatus.style.display = 'block';
            const scoreColor = frame.cv_score >= 8 ? 'var(--green)' : frame.cv_score >= 6 ? 'var(--yellow)' : 'var(--red)';
            const scoreIcon = frame.cv_score >= 8 ? '✅' : frame.cv_score >= 6 ? '⚠️' : '❌';
            cvStatus.innerHTML = `${scoreIcon} CV Оценка: <strong style="color:${scoreColor}">${frame.cv_score}/10</strong>`;
            cvStatus.style.color = scoreColor;

            try {
                const details = JSON.parse(frame.cv_details || '{}');
                cvResult.innerHTML = `
                    <div style="margin-top:8px;">
                        <p><strong>🤖 Описание:</strong> ${escapeHtml(frame.cv_description)}</p>
                        ${details.matched?.length > 0 ? `<p><strong style="color:var(--green)">✅ Совпало:</strong> ${details.matched.map(escapeHtml).join(', ')}</p>` : ''}
                        ${details.missing?.length > 0 ? `<p><strong style="color:var(--red)">❌ Отсутствует:</strong> ${details.missing.map(escapeHtml).join(', ')}</p>` : ''}
                        ${details.attempts ? `<p style="font-size:11px;color:var(--text-muted);">Попыток: ${details.attempts}</p>` : ''}
                    </div>
                `;
            } catch {
                cvResult.innerHTML = `<p>${escapeHtml(frame.cv_description)}</p>`;
            }
        } else {
            cvStatus.style.display = 'none';
            cvResult.innerHTML = '';
        }
    } else {
        cvSection.style.display = 'none';
    }

    // Консистентность персонажей — показываем если есть данные
    const consistencySection = document.getElementById('consistencySection');
    const consistencyStatus = document.getElementById('consistencyStatus');
    const consistencyResult = document.getElementById('consistencyResult');
    if (consistencySection && frame.consistency_score > 0) {
        consistencySection.style.display = 'block';
        const cScore = frame.consistency_score;
        const cColor = cScore >= 8 ? 'var(--green)' : cScore >= 6 ? 'var(--yellow)' : 'var(--red)';
        const cIcon = cScore >= 8 ? '✅' : cScore >= 6 ? '⚠️' : '❌';
        consistencyStatus.innerHTML = `${cIcon} Консистентность персонажей: <strong style="color:${cColor}">${cScore}/10</strong>`;
        consistencyStatus.style.color = cColor;

        try {
            const cDetails = JSON.parse(frame.consistency_issues || '{}');
            const issues = cDetails.issues || [];
            const checked = cDetails.characters_checked || 0;
            consistencyResult.innerHTML = `
                <div style="margin-top:8px;">
                    <p>Персонажей проверено: <strong>${checked}</strong></p>
                    ${issues.length > 0 ? `<p><strong style="color:var(--red)">⚠️ Проблемы:</strong><ul style="margin:4px 0;padding-left:20px;">${issues.map(i => `<li>${escapeHtml(i)}</li>`).join('')}</ul></p>` : '<p style="color:var(--green);">Все персонажи соответствуют описанию</p>'}
                </div>
            `;
        } catch {
            consistencyResult.innerHTML = `<p>Консистентность: ${cScore}/10</p>`;
        }
    } else if (consistencySection) {
        consistencySection.style.display = 'none';
    }

    // Сбрасываем статус
    document.getElementById('reviseStatus').style.display = 'none';
    document.getElementById('revisionComment').value = '';

    document.getElementById('sceneModal').classList.add('open');
}

async function saveDepartmentEdits() {
    if (!currentSceneData) return;
    const frame = currentSceneData;
    const dop = (document.getElementById('modalDopPrompt')?.value || '').trim();
    const art = (document.getElementById('modalArtPrompt')?.value || '').trim();
    const sound = (document.getElementById('modalSoundPrompt')?.value || '').trim();
    const hints = {
        clothing: (document.getElementById('hintClothing')?.value || '').trim(),
        season: (document.getElementById('hintSeason')?.value || '').trim(),
        color: (document.getElementById('hintColor')?.value || '').trim(),
    };

    // Обновляем структурную карточку кадра (source of truth)
    const promptParts = Object.assign({}, frame.prompt_parts || {});
    promptParts.edit_hints = hints;
    if (!promptParts.source) promptParts.source = {};
    // Сохраняем raw строки цехов как есть (для ручного редактирования/аудита)
    promptParts.source.dop_raw = dop;
    promptParts.source.art_raw = art;
    promptParts.source.sound_raw = sound;

    // Попробуем аккуратно распарсить JSON-цеха и обновить ключевые поля карточки
    try {
        const d = JSON.parse(dop);
        if (d.location) promptParts.location = d.location;
        if (d.lighting) promptParts.lighting = d.lighting;
        if (d.shot) promptParts.composition = d.shot;
    } catch {}
    try {
        const a = JSON.parse(art);
        if (a.style) promptParts.style = a.style;
        if (a.palette) promptParts.palette = a.palette;
    } catch {}

    if (hints.season) {
        promptParts.location = `${promptParts.location || ''}, season: ${hints.season}`.trim();
    }
    if (hints.clothing) {
        promptParts.subject = `${promptParts.subject || 'adult human protagonist'}, clothing: ${hints.clothing}`;
    }
    if (hints.color) {
        promptParts.palette = hints.color;
    }

    // user_comment хранит envelope с edit hints
    const userCommentEnvelope = JSON.stringify({ type: 'frame_edit_hints', hints });

    try {
        const res = await fetch(`${API_BASE}/api/orchestrator/scene-frame/${frame.season_num}/${frame.episode_num}/${frame.scene_num}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                dop_prompt: dop,
                art_prompt: art,
                sound_prompt: sound,
                prompt_parts_json: JSON.stringify(promptParts),
                user_comment: userCommentEnvelope,
            })
        });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || 'save failed');
        // Обновим локальный frame
        frame.dop_prompt = dop;
        frame.art_prompt = art;
        frame.sound_prompt = sound;
        frame.edit_hints = hints;
        frame.prompt_parts = promptParts;
        alert('Решения цехов сохранены');
    } catch (e) {
        alert('Ошибка сохранения: ' + e.message);
    }
}

function applyQuickEditToPrompt() {
    if (!currentSceneData) return;
    const editor = document.getElementById('modalPromptEditor');
    if (!editor) return;
    let p = (editor.value || '').trim();
    if (!p) {
        p = currentSceneData.final_prompt || '';
    }
    const clothing = (document.getElementById('hintClothing')?.value || '').trim();
    const season = (document.getElementById('hintSeason')?.value || '').trim();
    const color = (document.getElementById('hintColor')?.value || '').trim();

    const additions = [];
    if (clothing) additions.push(`clothing: ${clothing}`);
    if (season) additions.push(`season: ${season}`);
    if (color) additions.push(`color palette override: ${color}`);

    if (additions.length) {
        // Важно: sound_prompt НЕ добавляем в image prompt
        p = `${p}, ${additions.join(', ')}`;
        editor.value = p;
        if (!currentSceneData.prompt_parts) currentSceneData.prompt_parts = {};
        if (clothing) currentSceneData.prompt_parts.subject = `${currentSceneData.prompt_parts.subject || 'adult human protagonist'}, clothing: ${clothing}`;
        if (season) currentSceneData.prompt_parts.location = `${currentSceneData.prompt_parts.location || ''}, season: ${season}`.trim();
        if (color) currentSceneData.prompt_parts.palette = color;
    }
}

function closeSceneModal() {
    document.getElementById('sceneModal').classList.remove('open');
    currentSceneData = null;
}

async function approveScene() {
    if (!currentSceneData) return;
    try {
        const frame = currentSceneData;
        await fetch(`${API_BASE}/api/orchestrator/scene-action/${frame.season_num}/${frame.episode_num}/${frame.scene_num}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'approve', comment: '' })
        });
        closeSceneModal();
        loadStoryboard();
    } catch (e) { alert('Ошибка: ' + e.message); }
}

async function reviseScene() {
    if (!currentSceneData) return;
    const comment = document.getElementById('revisionComment').value.trim();
    if (!comment) {
        alert('Напиши что изменить в кадре');
        return;
    }

    const statusDiv = document.getElementById('reviseStatus');
    const btnRevise = document.getElementById('btnReviseScene');
    const btnApprove = document.getElementById('btnApproveScene');
    const btnRegenerate = document.getElementById('btnRegenerate');

    // Блокируем кнопки
    btnRevise.disabled = true;
    btnRevise.textContent = '⏳ Перегенерация...';
    btnApprove.disabled = true;
    btnRegenerate.disabled = true;
    statusDiv.style.display = 'block';
    statusDiv.innerHTML = '⏳ Art Director переписывает промпт → Kie.ai генерирует (~60 сек)...';
    statusDiv.style.color = 'var(--yellow)';

    try {
        const frame = currentSceneData;
        // Большой таймаут 120 сек
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 120000);

        const res = await fetch(`${API_BASE}/api/orchestrator/revise-frame/${frame.id}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ comment: comment, edited_prompt: '' }),
            signal: controller.signal
        });
        clearTimeout(timeoutId);

        const data = await res.json();

        if (data.ok) {
            statusDiv.innerHTML = '✅ Кадр перегенерирован! Новое изображение загружено.';
            statusDiv.style.color = 'var(--green)';
            // Обновляем изображение с cache-buster
            document.getElementById('modalSceneImage').src = data.image_url + '?t=' + Date.now();
            // Обновляем промпт редактор
            document.getElementById('modalPromptEditor').value = data.new_prompt || '';
            // Обновляем локальные данные
            frame.image_url = data.image_url;
            frame.final_prompt = data.new_prompt || frame.final_prompt;
            frame.user_status = 'in_review';
        } else {
            statusDiv.innerHTML = '❌ Ошибка: ' + (data.error || 'Неизвестная ошибка');
            statusDiv.style.color = 'var(--red)';
        }
    } catch (e) {
        if (e.name === 'AbortError') {
            statusDiv.innerHTML = '⏱️ Таймаут. Проверь Storyboard — изображение может быть готово.';
            statusDiv.style.color = 'var(--yellow)';
        } else {
            statusDiv.innerHTML = '❌ Ошибка сети: ' + e.message;
            statusDiv.style.color = 'var(--red)';
        }
    }

    // Разблокируем кнопки
    btnRevise.disabled = false;
    btnRevise.textContent = '🔄 На доработку (Art Director)';
    btnApprove.disabled = false;
    btnRegenerate.disabled = false;
}

// Перегенерация с отредактированным промптом
async function regenerateFrame() {
    if (!currentSceneData) return;
    const newPrompt = document.getElementById('modalPromptEditor').value.trim();
    if (!newPrompt) {
        alert('Промпт пустой');
        return;
    }

    const statusDiv = document.getElementById('reviseStatus');
    const btnRegenerate = document.getElementById('btnRegenerate');

    btnRegenerate.disabled = true;
    btnRegenerate.textContent = '⏳ Генерация...';
    statusDiv.style.display = 'block';
    statusDiv.innerHTML = '⏳ Kie.ai генерирует изображение...';
    statusDiv.style.color = 'var(--yellow)';

    try {
        const frame = currentSceneData;
        const res = await fetch(`${API_BASE}/api/orchestrator/revise-frame/${frame.id}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ comment: 'Ручная правка промпта', edited_prompt: newPrompt })
        });
        const data = await res.json();

        if (data.ok) {
            document.getElementById('modalSceneImage').src = data.image_url + '?t=' + Date.now();
            statusDiv.innerHTML = '✅ Перегенерировано!';
            statusDiv.style.color = 'var(--green)';
            frame.image_url = data.image_url;
            frame.final_prompt = newPrompt;
        } else {
            statusDiv.innerHTML = '❌ Ошибка: ' + (data.error || 'Неизвестная ошибка');
            statusDiv.style.color = 'var(--red)';
        }
    } catch (e) {
        statusDiv.innerHTML = '❌ Ошибка сети: ' + e.message;
        statusDiv.style.color = 'var(--red)';
    }

    btnRegenerate.disabled = false;
    btnRegenerate.textContent = '🎨 Перегенерировать с новым промптом';
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
    const saveDeptBtn = document.getElementById('btnSaveDepartmentEdits');
    if (saveDeptBtn) saveDeptBtn.addEventListener('click', saveDepartmentEdits);
    const applyQuickBtn = document.getElementById('btnApplyQuickEdit');
    if (applyQuickBtn) applyQuickBtn.addEventListener('click', applyQuickEditToPrompt);
    document.getElementById('overlay').addEventListener('click', closeSceneModal);

    document.getElementById('chatInput').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    });

    // New Project
    document.getElementById('btnNewProject').addEventListener('click', openNewProjectModal);
}

// ============================================
// NEW PROJECT
// ============================================

function openNewProjectModal() {
    document.getElementById('newProjectModal').classList.add('open');
    document.getElementById('newProjectStatus').style.display = 'none';
    document.getElementById('btnCreateProject').disabled = false;
    document.getElementById('btnCreateProject').textContent = '🚀 Создать проект';
}

function closeNewProjectModal() {
    document.getElementById('newProjectModal').classList.remove('open');
}

async function createNewProject() {
    const name = document.getElementById('newProjectName').value.trim();
    if (!name) {
        alert('Введи название проекта');
        return;
    }

    const statusDiv = document.getElementById('newProjectStatus');
    const btn = document.getElementById('btnCreateProject');

    btn.disabled = true;
    btn.textContent = '⏳ Создание...';
    statusDiv.style.display = 'block';
    statusDiv.innerHTML = '⏳ Создаю проект и очищаю старый контент...';
    statusDiv.style.color = 'var(--yellow)';

    try {
        // 1. Создаём проект
        const res = await fetch(`${API_BASE}/api/project/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                description: document.getElementById('newProjectDesc').value.trim(),
                genre: document.getElementById('newProjectGenre').value.trim(),
                visual_style: document.getElementById('newProjectStyle').value.trim(),
                color_palette: document.getElementById('newProjectPalette').value.trim(),
                music_reference: document.getElementById('newProjectMusic').value.trim(),
                duration_seconds: parseInt(document.getElementById('newProjectDuration').value) || 80,
                total_episodes: 1,
            })
        });
        const data = await res.json();

        if (data.ok) {
            statusDiv.innerHTML = '⏳ Очищаю старый контент...';

            // 2. Сбрасываем контент
            await fetch(`${API_BASE}/api/project/reset`, { method: 'POST' });

            statusDiv.innerHTML = '✅ Проект создан!';
            statusDiv.style.color = 'var(--green)';

            // Обновляем UI
            document.getElementById('projectBadge').textContent = `Проект: ${name}`;

            // Очищаем поля
            document.getElementById('newProjectName').value = '';
            document.getElementById('newProjectDesc').value = '';
            document.getElementById('newProjectGenre').value = '';
            document.getElementById('newProjectPalette').value = '';
            document.getElementById('newProjectMusic').value = '';

            // Перезагружаем storyboard и агентов
            loadStoryboard();
            loadAgents();

            setTimeout(() => closeNewProjectModal(), 1500);
        } else {
            statusDiv.innerHTML = '❌ Ошибка: ' + (data.detail || 'Неизвестная ошибка');
            statusDiv.style.color = 'var(--red)';
        }
    } catch (e) {
        statusDiv.innerHTML = '❌ Ошибка сети: ' + e.message;
        statusDiv.style.color = 'var(--red)';
    }

    btn.disabled = false;
    btn.textContent = '🚀 Создать проект';
}

// ============================================
// CV CHECK
// ============================================

async function cvCheckFrame(frameId) {
    const cvSection = document.getElementById('cvCheckSection');
    const cvStatus = document.getElementById('cvStatus');
    const cvResult = document.getElementById('cvResult');

    cvSection.style.display = 'block';
    cvStatus.style.display = 'block';
    cvStatus.innerHTML = '⏳ OpenRouter анализирует изображение...';
    cvStatus.style.color = 'var(--yellow)';
    cvResult.innerHTML = '';

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 90000);

        const res = await fetch(`${API_BASE}/api/tools/cv-check`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ frame_id: frameId, model: 'google/gemini-3.1-flash-lite-preview' }),
            signal: controller.signal
        });
        clearTimeout(timeoutId);

        const data = await res.json();

        if (data.ok) {
            const scoreColor = data.score >= 8 ? 'var(--green)' : data.score >= 6 ? 'var(--yellow)' : 'var(--red)';
            const scoreIcon = data.score >= 8 ? '✅' : data.score >= 6 ? '⚠️' : '❌';

            cvStatus.innerHTML = `${scoreIcon} CV Оценка: <strong style="color:${scoreColor}">${data.score}/10</strong>`;
            cvStatus.style.color = scoreColor;

            cvResult.innerHTML = `
                <div style="margin-top:12px;">
                    <p><strong>🤖 Что видит модель:</strong> ${escapeHtml(data.description)}</p>
                    <p><strong>Вердикт:</strong> ${escapeHtml(data.verdict)}</p>
                    ${data.matched.length > 0 ? `<p><strong style="color:var(--green)">✅ Совпало:</strong> ${data.matched.map(escapeHtml).join(', ')}</p>` : ''}
                    ${data.missing.length > 0 ? `<p><strong style="color:var(--red)">❌ Отсутствует:</strong> ${data.missing.map(escapeHtml).join(', ')}</p>` : ''}
                    <p style="font-size:11px;color:var(--text-muted);margin-top:8px;">Модель: ${escapeHtml(data.model || 'N/A')}</p>
                </div>
            `;
        } else {
            cvStatus.innerHTML = '❌ Ошибка: ' + (data.error || 'Неизвестная ошибка');
            cvStatus.style.color = 'var(--red)';
        }
    } catch (e) {
        if (e.name === 'AbortError') {
            cvStatus.innerHTML = '⏱️ Таймаут. Попробуй снова.';
        } else {
            cvStatus.innerHTML = '❌ Ошибка: ' + e.message;
        }
        cvStatus.style.color = 'var(--red)';
    }
}

// ============================================
// AUTO-FIX: CV → Critic → Fixer → Kie.ai цикл
// ============================================

async function autoFixFrame(frameId) {
    if (!frameId) return;

    const cvSection = document.getElementById('cvCheckSection');
    const cvStatus = document.getElementById('cvStatus');
    const cvResult = document.getElementById('cvResult');
    const btnAutoFix = document.getElementById('btnAutoFix');
    const btnCvCheck = document.getElementById('btnCvCheck');

    cvSection.style.display = 'block';
    btnAutoFix.disabled = true;
    btnAutoFix.textContent = '⏳ Авто-испление...';
    btnCvCheck.disabled = true;
    cvStatus.style.display = 'block';
    cvStatus.innerHTML = '⏳ Запуск CV → Critic → Fixer цикла (макс 3 попытки, ~2-3 мин)...';
    cvStatus.style.color = 'var(--yellow)';
    cvResult.innerHTML = '';

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 300000); // 5 мин

        const res = await fetch(`${API_BASE}/api/tools/cv-auto-fix/${frameId}`, {
            method: 'POST',
            signal: controller.signal
        });
        clearTimeout(timeoutId);

        const data = await res.json();

        if (data.ok) {
            const score = data.final_score || 0;
            const scoreColor = score >= 8 ? 'var(--green)' : score >= 6 ? 'var(--yellow)' : 'var(--red)';
            const scoreIcon = score >= 8 ? '✅' : score >= 6 ? '⚠️' : '❌';

            cvStatus.innerHTML = `${scoreIcon} Авто-исправление завершено за ${data.attempts} попыток. Итог: <strong style="color:${scoreColor}">${score}/10</strong>`;
            cvStatus.style.color = scoreColor;

            // История попыток
            let historyHtml = '<div style="margin-top:12px;"><strong>История:</strong><ul style="margin:8px 0;padding-left:20px;">';
            (data.history || []).forEach(h => {
                const hColor = h.cv_score >= 8 ? 'var(--green)' : h.cv_score >= 6 ? 'var(--yellow)' : 'var(--red)';
                historyHtml += `<li>Попытка ${h.attempt}: <strong style="color:${hColor}">${h.cv_score}/10</strong> ${h.missing?.length > 0 ? '| Пропущено: ' + h.missing.map(escapeHtml).join(', ') : ''}</li>`;
            });
            historyHtml += '</ul></div>';
            cvResult.innerHTML = historyHtml;

            // Обновляем изображение
            if (currentSceneData) {
                document.getElementById('modalSceneImage').src = currentSceneData.image_url + '?t=' + Date.now();
            }

            // Обновляем storyboard
            loadStoryboard();
        } else {
            cvStatus.innerHTML = '❌ Ошибка: ' + (data.error || 'Неизвестная ошибка');
            cvStatus.style.color = 'var(--red)';
        }
    } catch (e) {
        if (e.name === 'AbortError') {
            cvStatus.innerHTML = '⏱️ Таймаут (5 мин). Проверь Storyboard — возможно изображение готово.';
        } else {
            cvStatus.innerHTML = '❌ Ошибка: ' + e.message;
        }
        cvStatus.style.color = 'var(--red)';
    }

    btnAutoFix.disabled = false;
    btnAutoFix.textContent = '🔧 Авто-исправление (Critic+Fixer)';
    btnCvCheck.disabled = false;
}
