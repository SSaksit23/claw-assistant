/**
 * Web365 ClawBot - Chat Client
 * Handles WebSocket communication, message rendering, and file uploads.
 */

// --- State ---
let socket = null;
let uploadedFilePath = null;
let isConnected = false;

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
        reconnectionAttempts: 10,
        reconnectionDelay: 2000,
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
    });

    socket.on('agent_status', (data) => {
        updateAgentStatus(data.agent, data.status, data.message);
    });

    socket.on('agent_progress', (data) => {
        removeTypingIndicator();
        appendMessage('system', data.message, data.agent || 'ClawBot');
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
    socket.emit('user_message', {
        message: message,
        file_path: uploadedFilePath
    });

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
