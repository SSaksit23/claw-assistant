/**
 * Web365 ClawBot - Chat Client
 * Handles WebSocket communication, message rendering, and file uploads.
 */

// --- State ---
let socket = null;
let uploadedFilePath = null;
let isConnected = false;
let selectedExpenseType = null;

// --- DOM Elements ---
const chatMessages = document.getElementById('chatMessages');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const fileInput = document.getElementById('fileInput');
const fileIndicator = document.getElementById('fileIndicator');
const fileName = document.getElementById('fileName');
const dropZone = document.getElementById('dropZone');
const connectionStatus = document.getElementById('connectionStatus');
const sidebarToggle = document.getElementById('sidebarToggle');
const sidebar = document.getElementById('sidebar');
const themeToggle = document.getElementById('themeToggle');

// --- WebSocket Setup ---
function initSocket() {
    socket = io({
        transports: ['websocket', 'polling'],
        reconnection: true,
        reconnectionAttempts: Infinity,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 10000,
        timeout: 120000,
    });

    socket.on('connect', () => {
        isConnected = true;
        connectionStatus.textContent = 'Connected';
        connectionStatus.classList.remove('text-red-400');
        connectionStatus.classList.add('text-green-400');
    });

    socket.on('disconnect', () => {
        isConnected = false;
        connectionStatus.textContent = 'Disconnected - Reconnecting...';
        connectionStatus.classList.remove('text-green-400');
        connectionStatus.classList.add('text-red-400');
    });

    socket.on('connect_error', () => {
        connectionStatus.textContent = 'Connection failed - Retrying...';
        connectionStatus.classList.remove('text-green-400');
        connectionStatus.classList.add('text-red-400');
    });

    socket.on('system_message', (data) => {
        // Already shown in welcome
    });

    socket.on('agent_response', (data) => {
        removeTypingIndicator();
        if (data.type === 'error') {
            appendMessage('error', data.content, 'System');
        } else {
            appendMessage('agent', data.content, data.agent || 'ClawBot');
        }
        if (data.agent && data.agent !== 'Assignment Agent') {
            selectedExpenseType = null;
        }
    });

    socket.on('expense_review', (data) => {
        removeTypingIndicator();
        renderExpenseReview(data.content, data.agent || 'Accounting Agent', data.job_id, data.data);
    });

    socket.on('agent_status', (data) => {
        updateAgentStatus(data.agent, data.status, data.message);
    });

    socket.on('agent_progress', (data) => {
        removeTypingIndicator();
        appendMessage('system', data.message, data.agent || 'ClawBot');
    });

    socket.on('agent_question', (data) => {
        removeTypingIndicator();
        appendMessage('agent', `**${data.question}**`, data.agent || 'Accounting Agent');
        messageInput.focus();
    });

    socket.on('type_selection', (data) => {
        removeTypingIndicator();
        renderTypeSelection(data.prompt || 'Please select the expense type:', data.agent || 'Assignment Agent');
    });
}

// --- Message Handling ---
function sendMessage() {
    const message = messageInput.value.trim();
    if (!message && !uploadedFilePath) return;
    if (!isConnected) {
        appendMessage('error', 'Not connected to server. Please refresh the page.', 'System');
        return;
    }

    // Show user message
    if (message) {
        appendMessage('user', message, 'You');
    }
    if (uploadedFilePath && !message) {
        appendMessage('user', `Uploaded: ${fileName.textContent}`, 'You');
    }

    // Send to server
    const payload = {
        message: message,
        file_path: uploadedFilePath,
    };
    if (selectedExpenseType) {
        payload.expense_type = selectedExpenseType;
    }
    socket.emit('user_message', payload);

    // Clear input
    messageInput.value = '';
    messageInput.style.height = 'auto';

    // Clear file after sending
    if (uploadedFilePath) {
        uploadedFilePath = null;
        fileIndicator.classList.add('hidden');
    }

    showTypingIndicator();
}

function renderTypeSelection(prompt, sender) {
    const types = [
        { id: 'flight',    label: 'Air Ticket',           icon: '✈' },
        { id: 'land_tour', label: 'Tour Fare',            icon: '🗺' },
        { id: 'insurance', label: 'Insurance',            icon: '🛡' },
        { id: 'misc',      label: 'Misc / เบ็ดเตล็ด',     icon: '📋' },
    ];

    const wrapper = document.createElement('div');
    wrapper.className = 'flex gap-3 max-w-3xl mx-auto';

    const buttonsHtml = types.map(t =>
        `<button class="type-select-btn" data-type="${t.id}">
            <span class="type-icon">${t.icon}</span>
            <span class="type-label">${t.label}</span>
        </button>`
    ).join('');

    wrapper.innerHTML = `
        <div class="w-8 h-8 rounded-lg bg-primary-600 flex items-center justify-center shrink-0 text-sm font-bold">${sender.charAt(0)}</div>
        <div class="message-bubble agent">
            <p class="font-semibold text-primary-400 text-sm mb-1">${sender}</p>
            <div class="prose prose-invert prose-sm mb-3">${renderContent(prompt)}</div>
            <div class="type-select-group">${buttonsHtml}</div>
        </div>
    `;

    chatMessages.appendChild(wrapper);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    wrapper.querySelectorAll('.type-select-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const chosen = btn.dataset.type;
            selectedExpenseType = chosen;

            wrapper.querySelectorAll('.type-select-btn').forEach(b => {
                b.classList.toggle('selected', b.dataset.type === chosen);
                b.disabled = true;
            });

            const labelEl = btn.querySelector('.type-label');
            appendMessage('user', `Selected: ${labelEl.textContent.trim()}`, 'You');

            socket.emit('user_message', {
                message: `[TYPE:${chosen}] ${labelEl.textContent.trim()} selected`,
                expense_type: chosen,
            });
            showTypingIndicator();
        });
    });
}

function renderExpenseReview(content, sender, jobId, data) {
    const wrapper = document.createElement('div');
    wrapper.className = 'flex gap-3 max-w-3xl mx-auto';

    const codeGroups = (data && data.code_groups) || [];

    let codeGroupsHtml = '';
    if (codeGroups.length > 0) {
        codeGroupsHtml = `<div class="review-code-groups" style="margin-bottom:10px;">
            <p style="font-size:0.8rem; color:rgba(255,255,255,0.5); margin-bottom:6px;">Code Group(s) — edit if needed:</p>
            ${codeGroups.map((g, i) => `
                <div style="display:flex; align-items:center; gap:6px; margin-bottom:4px;">
                    <span style="font-size:0.8rem; color:rgba(255,255,255,0.4); min-width:18px;">${i + 1}.</span>
                    <input type="text" class="review-code-input" data-key="${g.key}"
                        value="${g.display}"
                        style="flex:1; padding:4px 8px; border-radius:5px; border:1px solid rgba(255,255,255,0.15);
                        background:rgba(255,255,255,0.05); color:inherit; font-size:0.85rem; font-family:monospace;" />
                </div>
            `).join('')}
        </div>`;
    }

    wrapper.innerHTML = `
        <div class="w-8 h-8 rounded-lg bg-primary-600 flex items-center justify-center shrink-0 text-sm font-bold">${sender.charAt(0)}</div>
        <div class="message-bubble agent">
            <p class="font-semibold text-primary-400 text-sm mb-1">${sender}</p>
            <div class="prose prose-invert prose-sm mb-3">${renderContent(content)}</div>
            <div class="review-form" style="margin-top:12px; border-top:1px solid rgba(255,255,255,0.1); padding-top:12px;">
                ${codeGroupsHtml}
                <div class="review-actions" style="display:flex; gap:8px;">
                    <input type="text" class="review-company-input" placeholder="Company name (e.g. Go365Travel)"
                        style="flex:1; padding:6px 10px; border-radius:6px; border:1px solid rgba(255,255,255,0.15);
                        background:rgba(255,255,255,0.05); color:inherit; font-size:0.875rem;" />
                    <button class="review-confirm-btn"
                        style="padding:6px 16px; border-radius:6px; background:#22c55e; color:#fff;
                        font-weight:600; font-size:0.875rem; border:none; cursor:pointer;">
                        Confirm
                    </button>
                    <button class="review-cancel-btn"
                        style="padding:6px 16px; border-radius:6px; background:#ef4444; color:#fff;
                        font-weight:600; font-size:0.875rem; border:none; cursor:pointer;">
                        Cancel
                    </button>
                </div>
            </div>
        </div>
    `;

    chatMessages.appendChild(wrapper);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    const companyInput = wrapper.querySelector('.review-company-input');
    const confirmBtn = wrapper.querySelector('.review-confirm-btn');
    const cancelBtn = wrapper.querySelector('.review-cancel-btn');
    const formDiv = wrapper.querySelector('.review-form');

    confirmBtn.addEventListener('click', () => {
        const company = companyInput.value.trim();
        if (!company) {
            companyInput.style.borderColor = '#ef4444';
            companyInput.focus();
            return;
        }

        // Collect code group overrides (only changed values)
        const overrides = {};
        let hasOverrides = false;
        wrapper.querySelectorAll('.review-code-input').forEach(input => {
            const origKey = input.dataset.key;
            const origDisplay = codeGroups.find(g => g.key === origKey)?.display || origKey;
            const newVal = input.value.trim();
            if (newVal && newVal !== origDisplay) {
                overrides[origKey] = newVal;
                hasOverrides = true;
            }
        });

        let summary = `Company: ${company}`;
        if (hasOverrides) {
            const changes = Object.entries(overrides).map(([k, v]) => {
                const orig = codeGroups.find(g => g.key === k)?.display || k;
                return `${orig} → ${v}`;
            }).join(', ');
            summary += ` | Code changes: ${changes}`;
        }

        formDiv.innerHTML = `<p style="color:#22c55e; font-weight:600; font-size:0.875rem;">Confirmed — ${summary}</p>`;
        appendMessage('user', `${summary} — Confirmed`, 'You');
        socket.emit('expense_review_confirm', {
            company_name: company,
            job_id: jobId,
            code_group_overrides: hasOverrides ? overrides : null,
        });
        showTypingIndicator();
    });

    cancelBtn.addEventListener('click', () => {
        formDiv.innerHTML = `<p style="color:#ef4444; font-weight:600; font-size:0.875rem;">Review cancelled</p>`;
        appendMessage('user', 'Cancelled expense review', 'You');
    });

    companyInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            confirmBtn.click();
        }
    });

    companyInput.focus();
}

function sendQuickAction(text) {
    messageInput.value = text;
    sendMessage();
}

function appendMessage(type, content, sender) {
    const wrapper = document.createElement('div');
    wrapper.className = 'flex gap-3 max-w-3xl mx-auto';

    if (type === 'user') {
        wrapper.classList.add('justify-end');
        wrapper.innerHTML = `
            <div class="message-bubble user">
                <div class="prose prose-invert prose-sm">${renderContent(content)}</div>
            </div>
            <div class="w-8 h-8 rounded-lg bg-dark-600 flex items-center justify-center shrink-0 text-sm font-bold">U</div>
        `;
    } else {
        const bubbleClass = type === 'error' ? 'error' : type === 'system' ? 'system' : 'agent';
        const iconBg = type === 'error' ? 'bg-red-600' : type === 'system' ? 'bg-yellow-600' : 'bg-primary-600';
        const label = sender || 'ClawBot';
        const labelColor = type === 'error' ? 'text-red-400' : type === 'system' ? 'text-yellow-400' : 'text-primary-400';

        wrapper.innerHTML = `
            <div class="w-8 h-8 rounded-lg ${iconBg} flex items-center justify-center shrink-0 text-sm font-bold">${label.charAt(0)}</div>
            <div class="message-bubble ${bubbleClass}">
                <p class="font-semibold ${labelColor} text-sm mb-1">${label}</p>
                <div class="prose prose-invert prose-sm">${renderContent(content)}</div>
            </div>
        `;
    }

    chatMessages.appendChild(wrapper);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function renderContent(text) {
    if (!text) return '';
    try {
        return marked.parse(text);
    } catch {
        return text.replace(/\n/g, '<br>');
    }
}

// --- Typing Indicator ---
function showTypingIndicator() {
    if (document.getElementById('typingIndicator')) return;
    const wrapper = document.createElement('div');
    wrapper.id = 'typingIndicator';
    wrapper.className = 'flex gap-3 max-w-3xl mx-auto';
    wrapper.innerHTML = `
        <div class="w-8 h-8 rounded-lg bg-primary-600 flex items-center justify-center shrink-0 text-sm font-bold">C</div>
        <div class="typing-indicator">
            <span></span><span></span><span></span>
        </div>
    `;
    chatMessages.appendChild(wrapper);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function removeTypingIndicator() {
    const el = document.getElementById('typingIndicator');
    if (el) el.remove();
}

// --- Agent Status ---
function updateAgentStatus(agentName, status, message) {
    const agentMap = {
        'Assignment Agent': 'assignment',
        'Accounting Agent': 'accounting',
        'Data Analysis Agent': 'data_analysis',
        'Market Analysis Agent': 'market_analysis',
        'Admin Agent': 'admin',
        'Executive Agent': 'executive',
        'Document Parser': 'assignment',
        'n8n Workflow': 'accounting',
        'System': 'assignment',
        'ClawBot': 'assignment',
    };

    const key = agentMap[agentName];
    if (!key) return;

    const card = document.querySelector(`.agent-card[data-agent="${key}"]`);
    if (!card) return;

    const dot = card.querySelector('.status-dot');
    const text = card.querySelector('.agent-status-text');

    dot.className = `status-dot ${status}`;
    text.textContent = message || status;
    card.classList.toggle('active', status === 'working' || status === 'thinking');
}

// --- File Upload ---
fileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) uploadFile(file);
});

async function uploadFile(file) {
    // Show immediate feedback
    appendMessage('system', `Uploading: **${file.name}** (${(file.size / 1024).toFixed(1)} KB)...`, 'System');

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch('/upload', {
            method: 'POST',
            body: formData,
        });

        if (!res.ok) {
            const errData = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
            appendMessage('error', errData.error || `Upload failed (${res.status})`, 'System');
            return;
        }

        const data = await res.json();
        uploadedFilePath = data.path;
        fileName.textContent = data.original_name || file.name;
        fileIndicator.classList.remove('hidden');

        appendMessage('system', `File **${file.name}** uploaded successfully. Click send or press Enter to start processing.`, 'System');

        // Auto-send if no text in input
        if (!messageInput.value.trim()) {
            messageInput.value = `Process expense file: ${file.name}`;
        }

    } catch (err) {
        console.error('Upload error:', err);
        appendMessage('error', `Upload failed: ${err.message}. Make sure the server is running on port 5000.`, 'System');
    }
}

function clearFile() {
    uploadedFilePath = null;
    fileInput.value = '';
    fileIndicator.classList.add('hidden');
}

// --- Drag & Drop ---
document.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.remove('hidden');
    dropZone.classList.add('drag-over');
});

document.addEventListener('dragleave', (e) => {
    if (!e.relatedTarget || e.relatedTarget === document.documentElement) {
        dropZone.classList.add('hidden');
        dropZone.classList.remove('drag-over');
    }
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.add('hidden');
    dropZone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) uploadFile(file);
});

dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
});

// --- Input Handling ---
messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

messageInput.addEventListener('input', () => {
    messageInput.style.height = 'auto';
    messageInput.style.height = Math.min(messageInput.scrollHeight, 150) + 'px';
});

// --- Sidebar Toggle (mobile) ---
sidebarToggle.addEventListener('click', () => {
    sidebar.classList.toggle('show');
    sidebar.classList.toggle('hidden');
});

// --- Theme Toggle ---
themeToggle.addEventListener('click', () => {
    document.documentElement.classList.toggle('dark');
    document.body.classList.toggle('bg-dark-900');
    document.body.classList.toggle('bg-gray-100');
    document.body.classList.toggle('text-gray-100');
    document.body.classList.toggle('text-gray-900');
});

// --- Init ---
initSocket();
