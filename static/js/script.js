// ==================================================================================
//  FILE: static/js/script.js
//  DESCRIPTION: Main Frontend Logic (Updated with Global Colors & Image Gen Options)
// ==================================================================================

let currentSessionId = localStorage.getItem('session_id') || null;
let currentMode = 'chat';
let isRecording = false;
let recognition = null;
let currentFile = null;
let lastMessageDate = null;

function getDateLabel(timestamp) {
    let ts = timestamp;
    if (ts && typeof ts === 'string' && !ts.endsWith('Z') && !ts.includes('+')) {
        ts += 'Z';
    }
    const date = ts ? new Date(ts) : new Date();
    return date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

let imageSettings = {
    quality: 'fast',
    style: 'painting'
};

document.addEventListener('DOMContentLoaded', () => {
    loadGlobalPreferences();
    loadHistory();
    loadProfile();

    if (!currentSessionId) {
        createNewChat();
    } else {
        loadChat(currentSessionId);
    }
});

// --- THEME & VANTA CONFIG ---
let vantaEffect = null;

function initVanta() {
    if (!window.VANTA) return;
    const isLight = document.body.classList.contains('light-mode');
    if (vantaEffect) { vantaEffect.destroy(); }

    if (isLight) {
        vantaEffect = VANTA.RINGS({
            el: "#vanta-bg",
            mouseControls: true, touchControls: true, gyroControls: false,
            minHeight: 200.00, minWidth: 200.00, scale: 1.00, scaleMobile: 1.00,
            backgroundColor: 0xe0e7ff, color: 0x2563eb
        });
    } else {
        let pColor = localStorage.getItem('primary_color') || '#00E5FF';
        let hexColor = parseInt(pColor.replace('#', '0x'), 16);
        vantaEffect = VANTA.HALO({
            el: "#vanta-bg",
            mouseControls: true, touchControls: true, gyroControls: false,
            minHeight: 200.00, minWidth: 200.00,
            baseColor: hexColor, backgroundColor: 0x000000,
            size: 0.8, amplitudeFactor: 1.0, xOffset: 0.0, yOffset: 0.0
        });
    }
}

function toggleTheme() {
    document.body.classList.toggle('light-mode');
    const isLight = document.body.classList.contains('light-mode');
    localStorage.setItem('theme', isLight ? 'light' : 'dark');
    initVanta();
}

// --- CHAT FUNCTIONS ---
async function createNewChat() {
    const res = await fetch('/api/new_chat');
    const data = await res.json();
    currentSessionId = data.session_id;
    localStorage.setItem('session_id', currentSessionId);

    document.getElementById('chat-box').innerHTML = `
        <div id="welcome-screen" class="flex flex-col items-center justify-center h-full opacity-80 text-center animate-fade-in px-4">
            <img src="/static/images/logo.png" class="w-20 h-20 md:w-24 md:h-24 rounded-full mb-4 md:mb-6 shadow-[0_0_30px_rgba(0,229,255,0.5)] animate-pulse">
            <h2 class="text-2xl md:text-3xl font-bold mb-2">Namaste!</h2>
            <p class="text-sm md:text-base text-gray-400">Main taiyaar hu. Aaj kya create karein?</p>
        </div>
    `;
    loadHistory();
}

async function loadChat(sid) {
    currentSessionId = sid;
    localStorage.setItem('session_id', sid);
    const res = await fetch(`/api/chat/${sid}`);
    const data = await res.json();

    const chatBox = document.getElementById('chat-box');
    chatBox.innerHTML = '';
    lastMessageDate = null;

    data.messages.forEach(msg => {
        appendMessage(msg.role === 'user' ? 'user' : 'assistant', msg.content, msg.timestamp);
    });
}

async function sendMessage() {
    const input = document.getElementById('user-input');
    const msg = input.value.trim();
    if (!msg && !currentFile) return;

    const welcome = document.getElementById('welcome-screen');
    if (welcome) welcome.remove();

    appendMessage('user', msg, null);
    playSfx('send');
    input.value = '';

    const chatBox = document.getElementById('chat-box');
    const thinkingId = 'thinking_' + Date.now();
    const thinkingDiv = document.createElement('div');
    thinkingDiv.className = 'msg-ai';
    thinkingDiv.id = thinkingId;
    thinkingDiv.innerHTML = '<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>';
    chatBox.appendChild(thinkingDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    try {
        // ── DATA ANALYST MODE — dedicated file upload flow ───────────────────
        if (currentMode === 'data_analyst') {
            await sendDataAnalystMessage(msg, thinkingId);
            return;
        }
        // ── VISION MODE — dedicated file upload flow ─────────────────────────
        if (currentMode === 'vision') {
            await sendVisionMessage(msg, thinkingId);
            return;
        }

        const payload = {
            message: msg, session_id: currentSessionId, mode: currentMode,
            file_data: currentFile ? currentFile.data : null,
            file_type: currentFile ? currentFile.type : null,
            image_quality: imageSettings.quality, image_style: imageSettings.style
        };

        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await res.json();
        document.getElementById(thinkingId).remove();
        currentFile = null;

        if (res.status === 429 || data.limit_reached) {
            appendMessage('assistant', data.reply, null);
            if (data.upgrade_needed) { setTimeout(() => { openUpgradeModal(); }, 600); }
            if (typeof updateUsageBar === 'function' && data.limit !== undefined) {
                updateUsageBar(0, data.limit, 0, data.tool_limit || 10);
            }
            return;
        }

        appendMessage('assistant', data.reply, null);
        loadHistory();

        if (typeof updateUsageBar === 'function' && data.remaining !== undefined) {
            updateUsageBar(data.remaining, data.limit, data.tool_remaining, data.tool_limit);
        }

        let voicePref = document.getElementById('voice-toggle');
        if ((voicePref && voicePref.checked) || localStorage.getItem('voice_reply') === 'true') {
            playAudio(data.reply);
        }
    } catch (e) {
        document.getElementById(thinkingId).innerHTML = '<span class="text-red-400">Error: Could not connect to Ethrix.</span>';
    }
}

function appendMessage(role, text, timestamp = null) {
    const chatBox = document.getElementById('chat-box');

    let ts = timestamp;
    if (ts && typeof ts === 'string' && !ts.endsWith('Z') && !ts.includes('+')) { ts += 'Z'; }
    const msgDateObj = ts ? new Date(ts) : new Date();
    const displayTime = msgDateObj.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true });
    const dateLabel = getDateLabel(ts);

    if (lastMessageDate !== dateLabel) {
        const divider = document.createElement('div');
        divider.className = 'date-divider';
        divider.innerText = dateLabel;
        chatBox.appendChild(divider);
        lastMessageDate = dateLabel;
    }

    const msgId = 'msg_' + Date.now() + Math.floor(Math.random() * 1000);
    const div = document.createElement('div');
    div.className = role === 'user' ? 'msg-user' : 'msg-ai';

    let content = text;
    if (role === 'assistant') { content = marked.parse(text); }

    let actionHTML = '';
    if (role === 'assistant') {
        actionHTML = `
            <div class="msg-meta">
                <span class="msg-time">${displayTime}</span>
                <div class="msg-actions">
                    <button class="action-btn" onclick="regenerateMessage('${msgId}')" title="Regenerate"><i class="fas fa-sync-alt text-[12px]"></i></button>
                    <button class="action-btn" onclick="copyText('${msgId}')" title="Copy"><i class="fas fa-copy text-[12px]"></i></button>
                    <button class="action-btn" onclick="handleFeedback('${msgId}', 'good')" title="Good"><i class="fas fa-thumbs-up text-[12px]"></i></button>
                    <button class="action-btn" onclick="handleFeedback('${msgId}', 'bad')" title="Bad"><i class="fas fa-thumbs-down text-[12px]"></i></button>
                    <button class="action-btn" onclick="shareResponse('${msgId}')" title="Share"><i class="fas fa-share-alt text-[12px]"></i></button>
                </div>
            </div>`;
    } else {
        actionHTML = `
            <div class="msg-meta" style="border-top:none; justify-content:flex-end; gap: 8px;">
                <button class="action-btn" onclick="editMyMessage('${msgId}')" title="Edit Message"><i class="fas fa-pen text-[11px]"></i></button>
                <button class="action-btn" onclick="copyText('${msgId}')" title="Copy Message"><i class="fas fa-copy text-[11px]"></i></button>
                <span class="msg-time">${displayTime}</span>
            </div>`;
    }

    if (role === 'assistant' && window.ethrixPrefs && !window.ethrixPrefs.fast_mode) {
        div.innerHTML = `<div id="${msgId}_content" style="opacity:0; transform: translateY(10px); transition: all 0.4s ease-out;">${content}</div> ${actionHTML}`;
        chatBox.appendChild(div);
        playSfx('pop');
        setTimeout(() => {
            const contentDiv = document.getElementById(`${msgId}_content`);
            if (contentDiv) { contentDiv.style.opacity = '1'; contentDiv.style.transform = 'translateY(0)'; }
        }, 50);
    } else {
        div.innerHTML = `<div id="${msgId}_content">${content}</div> ${actionHTML}`;
        chatBox.appendChild(div);
        if (role === 'assistant') playSfx('pop');
    }

    if (!window.ethrixPrefs || window.ethrixPrefs.auto_scroll) {
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    if (role === 'assistant') {
        div.querySelectorAll('pre code').forEach((block) => {
            if (window.hljs) hljs.highlightElement(block);
            const pre = block.parentElement;
            if (pre && !pre.querySelector('.copy-btn')) {
                pre.style.position = 'relative';
                const copyBtn = document.createElement('button');
                copyBtn.className = 'copy-btn';
                copyBtn.innerHTML = '<i class="fas fa-copy"></i> Copy';
                copyBtn.addEventListener('click', () => {
                    navigator.clipboard.writeText(block.innerText).then(() => {
                        copyBtn.innerHTML = '<i class="fas fa-check"></i> Copied!';
                        copyBtn.style.background = 'rgba(74,222,128,0.3)';
                        setTimeout(() => { copyBtn.innerHTML = '<i class="fas fa-copy"></i> Copy'; copyBtn.style.background = ''; }, 2000);
                    }).catch(() => {
                        const ta = document.createElement('textarea');
                        ta.value = block.innerText;
                        document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove();
                        copyBtn.innerHTML = '<i class="fas fa-check"></i> Copied!';
                        setTimeout(() => { copyBtn.innerHTML = '<i class="fas fa-copy"></i> Copy'; }, 2000);
                    });
                });
                pre.appendChild(copyBtn);
            }
        });
    }
}

// --- ACTIONS & FEEDBACK ---
function copyText(msgId) {
    const content = document.getElementById(msgId + '_content').innerText;
    navigator.clipboard.writeText(content).then(() => {
        const btn = document.querySelector(`button[onclick="copyText('${msgId}')"] i`);
        btn.className = "fas fa-check text-green-400";
        setTimeout(() => { btn.className = "fas fa-copy"; }, 2000);
    });
}

function shareResponse(msgId) {
    const content = document.getElementById(msgId + '_content').innerText;
    if (navigator.share) {
        navigator.share({ title: 'Ethrix AI', text: content, url: window.location.href });
    } else {
        copyText(msgId);
        Swal.fire({ icon: 'success', title: 'Copied!', text: 'Link copied to clipboard', timer: 1500, showConfirmButton: false });
    }
}

async function handleFeedback(msgId, type) {
    const userEmail = document.getElementById('profile-name-sidebar').innerText === 'Guest' ? 'guest' : 'user';
    const options = type === 'good'
        ? [{ id: 'helpful', label: '🧠 Helpful', color: 'bg-green-500/20 text-green-400 border-green-500/50' }, { id: 'creative', label: '🎨 Creative', color: 'bg-purple-500/20 text-purple-400 border-purple-500/50' }, { id: 'fast', label: '⚡ Fast', color: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50' }, { id: 'other', label: '✨ Other', color: 'bg-gray-700 text-gray-300 border-gray-600' }]
        : [{ id: 'inaccurate', label: '❌ Inaccurate', color: 'bg-red-500/20 text-red-400 border-red-500/50' }, { id: 'rude', label: '😠 Rude', color: 'bg-orange-500/20 text-orange-400 border-orange-500/50' }, { id: 'bug', label: '🐞 Bug', color: 'bg-blue-500/20 text-blue-400 border-blue-500/50' }, { id: 'other', label: '❓ Other', color: 'bg-gray-700 text-gray-300 border-gray-600' }];

    let tagsHTML = `<div class="flex flex-wrap gap-2 justify-center mb-4">`;
    options.forEach(opt => { tagsHTML += `<input type="radio" name="fb_category" value="${opt.id}" id="${opt.id}" class="hidden peer"><label for="${opt.id}" class="cursor-pointer px-4 py-2 rounded-full border ${opt.color} hover:brightness-125 transition-all text-sm font-medium peer-checked:ring-2 peer-checked:ring-white peer-checked:brightness-150 select-none">${opt.label}</label>`; });
    tagsHTML += `</div>`;

    const { value: formValues } = await Swal.fire({
        title: type === 'good' ? 'Nice! What did you like? ❤️' : 'Oops! What went wrong? 💔',
        html: `${tagsHTML}<textarea id="fb_comment" class="swal2-textarea w-full bg-[#111] text-white border border-gray-700 rounded-lg p-3 text-sm focus:outline-none focus:border-pink-500" placeholder="(Optional) Tell us more..." style="margin: 0; display: block; height: 80px;"></textarea>`,
        background: '#1e1e1e', color: '#fff', showCancelButton: true,
        confirmButtonText: 'Submit Feedback', confirmButtonColor: type === 'good' ? '#4ade80' : '#f87171', cancelButtonColor: '#374151',
        preConfirm: () => {
            const selected = document.querySelector('input[name="fb_category"]:checked');
            const comment = document.getElementById('fb_comment').value;
            if (!selected) { Swal.showValidationMessage('Please select a category'); }
            return { category: selected ? selected.value : null, comment: comment };
        }
    });

    if (formValues) {
        await fetch('/api/feedback', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message_id: msgId, user_email: userEmail, type: type, category: formValues.category, comment: formValues.comment }) });
        const btn = document.querySelector(`button[onclick="handleFeedback('${msgId}', '${type}')"]`);
        if (btn) { btn.classList.add(type === 'good' ? 'text-green-400' : 'text-red-400'); btn.classList.add('scale-110'); }
        Swal.mixin({ toast: true, position: 'top-end', showConfirmButton: false, timer: 2000, background: '#1e1e1e', color: '#fff' }).fire({ icon: 'success', title: 'Thanks!' });
    }
}

// --- FILE UPLOAD & PREVIEW ---
function handleFileUpload(input) {
    const file = input.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = function (e) {
        currentFile = { data: e.target.result.split(',')[1], type: file.type, name: file.name };
        const previewContainer = document.getElementById('file-preview-container');
        const previewName = document.getElementById('file-preview-name');
        if (previewContainer && previewName) {
            previewName.innerText = file.name;
            previewContainer.classList.remove('hidden');
            previewContainer.classList.add('flex');
        }
    };
    reader.readAsDataURL(file);
}

function removeFile() {
    currentFile = null;
    document.getElementById('file-upload').value = '';
    const previewContainer = document.getElementById('file-preview-container');
    if (previewContainer) { previewContainer.classList.add('hidden'); previewContainer.classList.remove('flex'); }
}

// --- MODE SELECTION ---
async function setMode(mode, btn) {
    currentMode = mode;
    document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');

    if (mode === 'image_gen') {
        const { value: formValues } = await Swal.fire({
            title: '🎨 Image Studio Settings',
            html: `<div class="text-left mb-2 text-gray-400 text-sm">Select Quality Mode:</div><div class="flex gap-2 mb-4"><input type="radio" name="quality" value="fast" id="q_fast" class="hidden peer/fast" checked><label for="q_fast" class="flex-1 text-center p-2 rounded-lg border border-gray-600 cursor-pointer peer-checked/fast:bg-pink-600 peer-checked/fast:border-pink-500 hover:bg-white/5 transition">⚡ Fast (CPU)</label><input type="radio" name="quality" value="pro" id="q_pro" class="hidden peer/pro"><label for="q_pro" class="flex-1 text-center p-2 rounded-lg border border-gray-600 cursor-pointer peer-checked/pro:bg-purple-600 peer-checked/pro:border-purple-500 hover:bg-white/5 transition">💎 Pro (HQ)</label></div><div class="text-left mb-2 text-gray-400 text-sm">Select Art Style:</div><div class="flex gap-2"><input type="radio" name="style" value="painting" id="s_paint" class="hidden peer/paint" checked><label for="s_paint" class="flex-1 text-center p-2 rounded-lg border border-gray-600 cursor-pointer peer-checked/paint:bg-orange-600 peer-checked/paint:border-orange-500 hover:bg-white/5 transition">🖌️ Painting</label><input type="radio" name="style" value="realistic" id="s_real" class="hidden peer/real"><label for="s_real" class="flex-1 text-center p-2 rounded-lg border border-gray-600 cursor-pointer peer-checked/real:bg-blue-600 peer-checked/real:border-blue-500 hover:bg-white/5 transition">📸 Realistic</label></div>`,
            background: '#111', color: '#fff', confirmButtonText: 'Set Preferences', confirmButtonColor: '#ec4899',
            preConfirm: () => ({ quality: document.querySelector('input[name="quality"]:checked').value, style: document.querySelector('input[name="style"]:checked').value })
        });
        if (formValues) {
            imageSettings = formValues;
            Swal.mixin({ toast: true, position: 'top', showConfirmButton: false, timer: 2000, background: '#1e1e1e', color: '#fff' }).fire({ icon: 'success', title: `Mode Set: ${imageSettings.quality.toUpperCase()} + ${imageSettings.style.toUpperCase()}` });
        }
    } else if (mode === 'ethrix_agent') {
        Swal.mixin({ toast: true, position: 'top', showConfirmButton: false, timer: 2000, background: '#020205', color: '#0ff' }).fire({ icon: 'success', title: '🌌 Ethrix Agent Online' });
    } else if (mode === 'data_analyst') {
        Swal.mixin({ toast: true, position: 'top', showConfirmButton: false, timer: 2500, background: '#020205', color: '#0ff' })
            .fire({ icon: 'info', title: '📊 Data Analyst Ready', html: '<span style="font-size:0.85rem;color:#aaa">CSV / Excel / JSON file upload karo</span>' });
    } else if (mode === 'vision') {
        Swal.mixin({ toast: true, position: 'top', showConfirmButton: false, timer: 2500, background: '#020205', color: '#0ff' })
            .fire({ icon: 'info', title: '👁️ Vision Mode Ready', html: '<span style="font-size:0.85rem;color:#aaa">Image ya PDF upload karo</span>' });
    } else if (mode === 'screen_share') {
        openScreenSharePanel();
    } else {
        Swal.mixin({ toast: true, position: 'top', showConfirmButton: false, timer: 1000 }).fire({ icon: 'info', title: `Mode: ${mode}` });
    }
}

// --- VOICE FUNCTIONS ---
function toggleRecording() {
    if (!('webkitSpeechRecognition' in window)) { alert("Voice not supported"); return; }
    if (isRecording) { recognition.stop(); isRecording = false; document.getElementById('mic-btn').classList.remove('text-red-500', 'animate-pulse'); return; }

    recognition = new webkitSpeechRecognition();
    recognition.lang = "en-IN";
    recognition.onstart = () => { isRecording = true; document.getElementById('mic-btn').classList.add('text-red-500', 'animate-pulse'); };
    recognition.onresult = (event) => { document.getElementById('user-input').value = event.results[0][0].transcript; sendMessage(); };
    recognition.onend = () => { isRecording = false; document.getElementById('mic-btn').classList.remove('text-red-500', 'animate-pulse'); };
    recognition.start();
}

async function playAudio(text) {
    try {
        const res = await fetch('/api/speak', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: text }) });
        const blob = await res.blob();
        const audio = new Audio(URL.createObjectURL(blob));
        audio.play();
    } catch (e) { console.error(e); }
}

// --- SIDEBAR DATA LOADERS ---
async function loadHistory() {
    const res = await fetch('/api/history');
    const data = await res.json();
    const list = document.getElementById('history-list');
    list.innerHTML = '';

    data.history.filter(chat => !chat.title.startsWith('Tool:')).forEach(chat => {
        const div = document.createElement('div');
        div.className = 'history-item';
        div.innerHTML = `<div class="history-icon"><i class="far fa-comment-alt"></i></div><span class="nav-label truncate text-xs md:text-sm flex-1">${chat.title}</span>`;
        div.onclick = () => loadChat(chat.id);
        if (typeof showContextMenu === "function") {
            div.oncontextmenu = (e) => { e.preventDefault(); showContextMenu(e, chat.id); };
        }
        list.appendChild(div);
    });
}

async function loadProfile() {
    try {
        const res = await fetch('/api/profile');
        const data = await res.json();
        const sidebarName = document.getElementById('profile-name-sidebar');
        if (sidebarName) sidebarName.innerText = data.name || "User";
        const sidebarImg = document.getElementById('profile-img-sidebar');
        if (sidebarImg) sidebarImg.src = data.avatar || "/static/images/logo.png";
        const sidebarPlan = document.getElementById('profile-plan-sidebar');
        if (sidebarPlan) sidebarPlan.innerText = data.plan;
    } catch (e) { console.log("Profile could not be fetched."); }
}

// --- UTILITIES ---
function closeModal(id) { const el = document.getElementById(id); if (el) el.style.display = 'none'; }
function toggleVoice() { }

async function deleteAllChats() {
    if (confirm("Delete all history?")) {
        await fetch('/api/delete_all_chats', { method: 'DELETE' });
        loadHistory(); createNewChat(); closeModal('settings-modal');
    }
}

function editMyMessage(msgId) {
    const contentDiv = document.getElementById(msgId + '_content');
    if (contentDiv) { document.getElementById('user-input').value = contentDiv.innerText; document.getElementById('user-input').focus(); }
}

async function regenerateMessage(msgId) {
    const chatBox = document.getElementById('chat-box');
    const aiMsgDiv = document.getElementById(msgId + '_content').closest('.msg-ai');
    if (!aiMsgDiv) return;

    let prevElement = aiMsgDiv.previousElementSibling;
    let userText = "";
    while (prevElement) {
        if (prevElement.classList.contains('msg-user')) {
            let contentDiv = prevElement.querySelector('[id$="_content"]');
            if (contentDiv) { userText = contentDiv.innerText.trim(); }
            break;
        }
        prevElement = prevElement.previousElementSibling;
    }

    if (!userText) {
        Swal.fire({ toast: true, position: 'top-end', icon: 'error', title: 'Original message not found!', timer: 2000, showConfirmButton: false, background: '#1e1e1e', color: '#fff' });
        return;
    }

    aiMsgDiv.remove();
    const thinkingId = 'thinking_' + Date.now();
    const thinkingDiv = document.createElement('div');
    thinkingDiv.className = 'msg-ai'; thinkingDiv.id = thinkingId;
    thinkingDiv.innerHTML = '<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>';
    chatBox.appendChild(thinkingDiv); chatBox.scrollTop = chatBox.scrollHeight;

    try {
        const payload = { message: userText, session_id: currentSessionId, mode: currentMode, image_quality: imageSettings.quality, image_style: imageSettings.style };
        const res = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        const data = await res.json();
        document.getElementById(thinkingId).remove();
        appendMessage('assistant', data.reply, null);
    } catch (e) {
        document.getElementById(thinkingId).innerHTML = '<span class="text-red-400">Error: Could not regenerate.</span>';
    }
}

// ==================================================================================
// 🚀 ETHRIX GLOBAL PREFERENCES & CUSTOM THEME INJECTOR
// ==================================================================================
async function loadGlobalPreferences() {
    try {
        const res = await fetch('/api/get_preferences');
        const prefs = await res.json();

        if (prefs.font) {
            const fontFamily = prefs.font + ", sans-serif";
            document.body.style.fontFamily = fontFamily;
            document.querySelectorAll('input, button, select, textarea').forEach(el => { el.style.fontFamily = fontFamily; });
        }

        if (prefs.theme === 'light') {
            document.body.classList.add('light-mode');
            localStorage.setItem('theme', 'light');
        } else {
            document.body.classList.remove('light-mode');
            localStorage.setItem('theme', 'dark');
        }

        const voiceToggle = document.getElementById('voice-toggle');
        if (voiceToggle) voiceToggle.checked = prefs.voice;
        localStorage.setItem('voice_reply', prefs.voice);

        // ✅ CURSOR MODE — neon ya system default
        applyCursorMode(prefs.cursor_mode || 'neon');

        const textSize = prefs.chat_text_size || 'default';
        document.body.setAttribute('data-text-size', textSize);
        let textSizeStyle = document.getElementById('text-size-override');
        if (!textSizeStyle) {
            textSizeStyle = document.createElement('style');
            textSizeStyle.id = 'text-size-override';
            document.head.appendChild(textSizeStyle);
        }
        const sizeMap = { small: '0.82rem', default: '0.95rem', large: '1.1rem', xlarge: '1.25rem' };
        const sz = sizeMap[textSize] || '0.95rem';
        textSizeStyle.innerHTML = `.msg-user, .msg-ai { font-size: ${sz} !important; line-height: 1.6 !important; }`;

        if (prefs.zen_mode) {
            document.body.classList.add('zen-mode-active');
        } else {
            document.body.classList.remove('zen-mode-active');
        }

        window.ethrixPrefs = {
            send_on_enter:  prefs.send_on_enter !== false,
            ui_sfx:         prefs.ui_sfx !== false,
            fast_mode:      prefs.fast_mode === true,
            auto_scroll:    prefs.auto_scroll !== false,
            smart_memory:   prefs.smart_memory !== false,
            ai_persona:     prefs.ai_persona || 'friendly',
            chat_text_size: textSize,
            cursor_mode:    prefs.cursor_mode || 'neon'
        };

        let pColor = prefs.primary_color || '#00E5FF';
        localStorage.setItem('primary_color', pColor);
        applyCustomColor(pColor);

    } catch (e) { console.log("Preferences load error", e); }
}

// ==================================================================================
// ✅ FIXED: applyCursorMode — neon ya bilkul system default cursor
// ==================================================================================
function applyCursorMode(mode) {
    // --- Step 1: Purani state saaf karo ---
    document.body.classList.remove('neon-cursor-active', 'default-cursor-active');
    document.querySelector('.cursor-dot')?.remove();
    document.querySelector('.cursor-outline')?.remove();

    // Purana cursor override style hata do
    document.getElementById('cursor-override-style')?.remove();

    // =========================================================
    // DEFAULT MODE — bilkul normal OS cursor, koi image nahi
    // =========================================================
    if (mode === 'default') {
        document.body.classList.add('default-cursor-active');

        // Ek strong CSS inject karo jo style.css ke !important rules ko override kare
        const s = document.createElement('style');
        s.id = 'cursor-override-style';
        s.innerHTML = `
            /* ✅ Default system cursor — sabhi custom PNG cursors off */
            body.default-cursor-active,
            body.default-cursor-active *,
            body.default-cursor-active a,
            body.default-cursor-active button,
            body.default-cursor-active input,
            body.default-cursor-active select,
            body.default-cursor-active textarea,
            body.default-cursor-active label,
            body.default-cursor-active [role="button"],
            body.default-cursor-active .mode-btn,
            body.default-cursor-active .history-item,
            body.default-cursor-active .tool-card,
            body.default-cursor-active .cursor-pointer {
                cursor: auto !important;
            }
            body.default-cursor-active a,
            body.default-cursor-active button,
            body.default-cursor-active input[type="submit"],
            body.default-cursor-active input[type="button"],
            body.default-cursor-active input[type="checkbox"],
            body.default-cursor-active input[type="radio"],
            body.default-cursor-active select,
            body.default-cursor-active [role="button"],
            body.default-cursor-active .mode-btn,
            body.default-cursor-active .history-item,
            body.default-cursor-active .tool-card,
            body.default-cursor-active .cursor-pointer,
            body.default-cursor-active label[for] {
                cursor: pointer !important;
            }
        `;
        document.head.appendChild(s);
        return; // Yahan se wapas, koi dot/outline nahi banana
    }

    // =========================================================
    // NEON MODE — custom glowing cyan cursor
    // =========================================================
    if (window.matchMedia("(pointer: fine)").matches) {
        document.body.classList.add('neon-cursor-active');

        // Neon dot
        const dot = document.createElement("div");
        dot.className = "cursor-dot";

        // Neon outline ring
        const outline = document.createElement("div");
        outline.className = "cursor-outline";

        document.body.appendChild(dot);
        document.body.appendChild(outline);

        // Mouse follow karna
        window.addEventListener("mousemove", (e) => {
            dot.style.left = `${e.clientX}px`;
            dot.style.top = `${e.clientY}px`;
            outline.animate(
                { left: `${e.clientX}px`, top: `${e.clientY}px` },
                { duration: 500, fill: "forwards" }
            );
        });

        // Click ripple effect
        window.addEventListener("mousedown", (e) => {
            const ripple = document.createElement("div");
            ripple.className = "click-ripple";
            ripple.style.left = `${e.clientX}px`;
            ripple.style.top = `${e.clientY}px`;
            document.body.appendChild(ripple);
            outline.style.transform = "translate(-50%, -50%) scale(0.7)";
            setTimeout(() => { outline.style.transform = "translate(-50%, -50%) scale(1)"; }, 150);
            setTimeout(() => { ripple.remove(); }, 500);
        });

        // Hover pe outline bada ho
        const addHoverEffect = () => {
            document.querySelectorAll("a, button, input, textarea, select, .tool-card, .goti, .dice").forEach(el => {
                el.addEventListener("mouseenter", () => {
                    outline.style.width = "50px";
                    outline.style.height = "50px";
                    outline.style.backgroundColor = "rgba(236, 72, 153, 0.1)";
                });
                el.addEventListener("mouseleave", () => {
                    outline.style.width = "32px";
                    outline.style.height = "32px";
                    outline.style.backgroundColor = "transparent";
                });
            });
        };
        addHoverEffect();
    }
}

// ==================================================================================
// 🎨 CUSTOM COLOR INJECTOR
// ==================================================================================
function applyCustomColor(color) {
    let oldStyle = document.getElementById('dynamic-theme-style');
    if (oldStyle) oldStyle.remove();

    let r = parseInt(color.slice(1, 3), 16);
    let g = parseInt(color.slice(3, 5), 16);
    let b = parseInt(color.slice(5, 7), 16);
    let rgb = `${r}, ${g}, ${b}`;

    let css = `
        .msg-user { background: linear-gradient(135deg, rgba(${rgb}, 0.7), ${color}) !important; box-shadow: 0 4px 12px rgba(${rgb}, 0.3) !important; }
        .mode-btn.active { background: linear-gradient(135deg, rgba(${rgb}, 0.7), ${color}) !important; box-shadow: 0 0 15px rgba(${rgb}, 0.4) !important; color: white !important; }
        .history-item:hover { background: rgba(${rgb}, 0.15) !important; color: ${color} !important; }
        .history-item:hover .history-icon { color: ${color} !important; }
        #chat-search:focus { border-color: rgba(${rgb}, 0.5) !important; box-shadow: 0 0 15px rgba(${rgb}, 0.15) !important; }
        .input-container button[type="submit"] { background: linear-gradient(135deg, rgba(${rgb}, 0.8), ${color}) !important; box-shadow: 0 0 15px rgba(${rgb}, 0.4) !important; }
        .input-container button:hover i { color: ${color} !important; }
        .cursor-dot { background: ${color} !important; box-shadow: 0 0 10px ${color}, 0 0 20px ${color} !important; }
        .cursor-outline { border-color: rgba(${rgb}, 0.6) !important; }
        .click-ripple { background: radial-gradient(circle, rgba(${rgb}, 0.8) 0%, rgba(0, 0, 0, 0) 70%) !important; }
    `;

    let style = document.createElement('style');
    style.id = 'dynamic-theme-style';
    style.innerHTML = css;
    document.head.appendChild(style);

    if (typeof initVanta === 'function') { initVanta(); }
}

// ==================================================================================
// 🎵 UI SOUND EFFECTS & ENTER KEY LOGIC
// ==================================================================================
function playSfx(type = 'pop') {
    if (!window.ethrixPrefs || !window.ethrixPrefs.ui_sfx) return;
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain); gain.connect(ctx.destination);
        if (type === 'pop') {
            osc.type = 'sine';
            osc.frequency.setValueAtTime(600, ctx.currentTime);
            osc.frequency.exponentialRampToValueAtTime(300, ctx.currentTime + 0.1);
            gain.gain.setValueAtTime(0.1, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.1);
        } else if (type === 'send') {
            osc.type = 'triangle';
            osc.frequency.setValueAtTime(300, ctx.currentTime);
            osc.frequency.exponentialRampToValueAtTime(600, ctx.currentTime + 0.1);
            gain.gain.setValueAtTime(0.1, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.1);
        }
        osc.start(ctx.currentTime); osc.stop(ctx.currentTime + 0.1);
    } catch (e) { console.log("SFX Error", e); }
}

document.addEventListener('DOMContentLoaded', () => {
    const userInput = document.getElementById('user-input');
    if (userInput) {
        userInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                if (window.ethrixPrefs && window.ethrixPrefs.send_on_enter) {
                    e.preventDefault();
                    sendMessage();
                }
            }
        });
    }
});
// ==================================================================================
// 📊 DATA ANALYST MODE
// ==================================================================================

async function sendDataAnalystMessage(msg, thinkingId) {
    const chatBox = document.getElementById('chat-box');

    if (!currentFile) {
        document.getElementById(thinkingId).remove();
        appendMessage('assistant',
            '📊 **Data Analyst Mode**\n\nPehle ek file upload karo:\n- **.csv** — Comma-separated data\n- **.xlsx / .xls** — Excel spreadsheet\n- **.json** — JSON data\n\nFile upload ke baad apna sawaal poocho!', null);
        return;
    }

    try {
        // File + question dono bhejo
        const formData = new FormData();
        // base64 → Blob
        const byteStr   = atob(currentFile.data);
        const arr       = new Uint8Array(byteStr.length);
        for (let i = 0; i < byteStr.length; i++) arr[i] = byteStr.charCodeAt(i);
        const blob      = new Blob([arr], { type: currentFile.type });
        formData.append('file', blob, currentFile.name);

        const res  = await fetch('/api/data-analyst/analyze', {
            method: 'POST',
            body:   formData,
        });
        const data = await res.json();
        document.getElementById(thinkingId)?.remove();
        currentFile = null;
        removeFile();

        if (!res.ok || data.error) {
            appendMessage('assistant', `⚠️ ${data.error || 'Analysis failed. Retry karo.'}`, null);
            return;
        }

        // AI insights text dikhao
        appendMessage('assistant', data.insights || '⚠️ No insights returned.', null);

        // Charts render karo (agar Chart.js available hai)
        if (data.charts && data.charts.length > 0) {
            renderDataAnalystCharts(data.charts, data.filename);
        }

        // Agar user ne question bhi likha tha — follow-up automatically bhejo
        if (msg && msg.trim()) {
            await sendFollowUpDataQuestion(msg, currentFile);
        }

    } catch (e) {
        document.getElementById(thinkingId)?.remove();
        appendMessage('assistant', `⚠️ Connection error: ${e.message}`, null);
    }
}

function renderDataAnalystCharts(charts, filename) {
    const chatBox = document.getElementById('chat-box');

    const wrapper = document.createElement('div');
    wrapper.className = 'msg-ai';
    wrapper.style.cssText = 'padding: 16px; display: flex; flex-direction: column; gap: 20px;';

    const title = document.createElement('div');
    title.style.cssText = 'font-weight: 700; color: #00E5FF; font-size: 0.9rem; margin-bottom: 4px;';
    title.textContent = `📊 Charts — ${filename || 'Dataset'}`;
    wrapper.appendChild(title);

    charts.forEach(chart => {
        const container = document.createElement('div');
        container.style.cssText = 'background: rgba(0,0,0,0.3); border-radius: 12px; padding: 12px;';

        const chartTitle = document.createElement('div');
        chartTitle.style.cssText = 'font-size: 0.8rem; color: #9ca3af; margin-bottom: 8px; font-weight: 600;';
        chartTitle.textContent = chart.title;
        container.appendChild(chartTitle);

        const canvas = document.createElement('canvas');
        canvas.style.cssText = 'max-height: 200px;';
        container.appendChild(canvas);
        wrapper.appendChild(container);

        // Chart.js render
        if (window.Chart) {
            const ctx = canvas.getContext('2d');
            const commonOpts = {
                responsive: true,
                plugins: {
                    legend: { labels: { color: '#9ca3af', font: { size: 11 } } }
                },
                scales: {
                    x: { ticks: { color: '#6b7280', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.05)' } },
                    y: { ticks: { color: '#6b7280', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.05)' } }
                }
            };

            if (chart.type === 'bar') {
                new Chart(ctx, {
                    type: 'bar',
                    data: { labels: chart.x, datasets: [{ label: chart.ylabel || 'Count', data: chart.y, backgroundColor: chart.color + '99', borderColor: chart.color, borderWidth: 1, borderRadius: 6 }] },
                    options: { ...commonOpts }
                });
            } else if (chart.type === 'line') {
                new Chart(ctx, {
                    type: 'line',
                    data: { labels: chart.x, datasets: [{ label: chart.ylabel || 'Value', data: chart.y, borderColor: chart.color, backgroundColor: chart.color + '22', tension: 0.4, pointRadius: 2, fill: true }] },
                    options: { ...commonOpts }
                });
            } else if (chart.type === 'pie') {
                const pieColors = ['#00E5FF', '#A855F7', '#F59E0B', '#10B981', '#EF4444', '#F97316', '#3B82F6', '#EC4899'];
                new Chart(ctx, {
                    type: 'pie',
                    data: { labels: chart.labels, datasets: [{ data: chart.values, backgroundColor: pieColors.slice(0, chart.labels.length) }] },
                    options: { responsive: true, plugins: { legend: { labels: { color: '#9ca3af', font: { size: 11 } } } } }
                });
            } else if (chart.type === 'scatter') {
                const points = chart.x.map((x, i) => ({ x, y: chart.y[i] }));
                new Chart(ctx, {
                    type: 'scatter',
                    data: { datasets: [{ label: chart.title, data: points, backgroundColor: chart.color + '88', borderColor: chart.color, pointRadius: 4 }] },
                    options: { ...commonOpts }
                });
            }
        } else {
            // Chart.js nahi mila — fallback text
            canvas.style.display = 'none';
            const fallback = document.createElement('div');
            fallback.style.cssText = 'font-size: 0.75rem; color: #6b7280; text-align: center; padding: 20px;';
            fallback.textContent = `[Chart: ${chart.type} — Chart.js load nahi hua]`;
            container.appendChild(fallback);
        }
    });

    chatBox.appendChild(wrapper);
    chatBox.scrollTop = chatBox.scrollHeight;
}

// ==================================================================================
// 👁️ VISION MODE
// ==================================================================================

async function sendVisionMessage(msg, thinkingId) {
    const chatBox = document.getElementById('chat-box');

    if (!currentFile) {
        document.getElementById(thinkingId)?.remove();
        appendMessage('assistant',
            '👁️ **Vision Mode**\n\nPehle ek file upload karo:\n- **Image** — JPG, PNG, WEBP, GIF\n- **PDF** — Document pages analyze\n\nFir koi bhi sawaal poocho — main image mein dekh ke jawab dunga!', null);
        return;
    }

    try {
        const formData = new FormData();
        // base64 → Blob
        const byteStr = atob(currentFile.data);
        const arr     = new Uint8Array(byteStr.length);
        for (let i = 0; i < byteStr.length; i++) arr[i] = byteStr.charCodeAt(i);
        const blob    = new Blob([arr], { type: currentFile.type });
        formData.append('file', blob, currentFile.name);
        formData.append('question', msg || '');

        // Mode decide karo
        let visionMode = 'describe';
        if (msg && msg.trim())          visionMode = 'qa';
        if (!msg && /text|ocr|read|extract/i.test(currentFile.name)) visionMode = 'ocr';
        formData.append('mode', visionMode);

        const res  = await fetch('/api/vision/analyze', {
            method: 'POST',
            body:   formData,
        });
        const data = await res.json();
        document.getElementById(thinkingId)?.remove();

        const savedFileName = currentFile.name;
        currentFile = null;
        removeFile();

        if (!res.ok || data.error) {
            appendMessage('assistant', `⚠️ ${data.error || 'Vision analysis failed. Retry karo.'}`, null);
            return;
        }

        // Result dikhao — different modes ka alag response
        let reply = '';
        if (data.answer)      reply = data.answer;
        else if (data.description) reply = data.description;
        else if (data.analysis)    reply = data.analysis;
        else if (data.ocr)         reply = `**📝 Extracted Text:**\n\n${data.ocr.text || 'No text found.'}\n\n*Method: ${data.ocr.method || 'auto'} | Characters: ${data.ocr.char_count || 0}*`;
        else if (data.results) {
            // PDF multi-page
            reply = data.results.map(r => `**Page ${r.page}:**\n${r.analysis}`).join('\n\n---\n\n');
        }

        if (!reply) reply = '⚠️ No analysis returned. Try again.';

        // Image preview bhi dikhao (agar image tha)
        if (!currentFile && savedFileName && /\.(jpg|jpeg|png|webp|gif)$/i.test(savedFileName)) {
            // preview already visible tha file-preview-container mein, ab remove ho gaya
        }

        appendMessage('assistant', reply, null);

    } catch (e) {
        document.getElementById(thinkingId)?.remove();
        appendMessage('assistant', `⚠️ Vision error: ${e.message}`, null);
    }
}

// ==================================================================================
// 🖥️ SCREEN SHARE MODE
// ==================================================================================

let screenState = {
    ws:           null,
    stream:       null,
    sessionId:    null,
    wsUrl:        null,
    captureMode:  '',    // 'screen' | 'webcam'
    autoTimer:    null,
    isThinking:   false,
    voiceEnabled: false,
    panelOpen:    false,
};

async function openScreenSharePanel() {
    if (screenState.panelOpen) {
        document.getElementById('screen-panel')?.remove();
        screenState.panelOpen = false;
        stopScreenCapture();
        return;
    }

    // Session ID lo server se
    try {
        const res  = await fetch('/api/screen/session');
        const data = await res.json();
        if (data.error) { showToast('error', '⚠️ Screen Space unreachable'); return; }
        screenState.sessionId = data.session_id;
        screenState.wsUrl     = data.ws_url;
    } catch (e) {
        showToast('error', '⚠️ Screen Space offline');
        return;
    }

    // Panel HTML inject karo
    const panel = document.createElement('div');
    panel.id = 'screen-panel';
    panel.style.cssText = `
        position: fixed; bottom: 80px; right: 20px; z-index: 9999;
        width: 340px; background: rgba(10,14,26,0.97);
        border: 1px solid rgba(0,229,255,0.2); border-radius: 16px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.5), 0 0 0 1px rgba(0,229,255,0.05);
        overflow: hidden; font-family: inherit;
    `;
    panel.innerHTML = `
        <div style="padding:12px 16px; border-bottom:1px solid rgba(0,229,255,0.1); display:flex; align-items:center; justify-content:space-between;">
            <span style="font-weight:700; color:#00E5FF; font-size:0.9rem;">🖥️ Screen Share AI</span>
            <button onclick="closeScreenPanel()" style="background:none;border:none;color:#6b7280;cursor:pointer;font-size:1.1rem;">✕</button>
        </div>
        <div id="screen-preview-area" style="width:100%; height:160px; background:#000; position:relative; display:flex; align-items:center; justify-content:center;">
            <video id="screen-video" autoplay muted playsinline style="width:100%;height:100%;object-fit:contain;display:none;"></video>
            <div id="screen-placeholder" style="text-align:center; color:rgba(255,255,255,0.3); font-size:0.8rem;">
                <div style="font-size:2rem; margin-bottom:8px;">🖥️</div>
                Share karo ya Camera on karo
            </div>
        </div>
        <div id="screen-commentary" style="max-height:120px; overflow-y:auto; padding:10px 14px; font-size:0.8rem; color:#9ca3af; line-height:1.5;">
            <div style="text-align:center; color:rgba(255,255,255,0.2);">AI commentary yahan dikhega...</div>
        </div>
        <div style="padding:10px 12px; border-top:1px solid rgba(255,255,255,0.06); display:flex; gap:8px; flex-wrap:wrap;">
            <button onclick="startScreenShare()" style="flex:1; padding:8px; border-radius:8px; border:1px solid rgba(0,229,255,0.3); background:rgba(0,229,255,0.1); color:#00E5FF; cursor:pointer; font-size:0.78rem; font-weight:600;">🖥️ Screen</button>
            <button onclick="startScreenCam()" style="flex:1; padding:8px; border-radius:8px; border:1px solid rgba(0,255,135,0.3); background:rgba(0,255,135,0.1); color:#00ff87; cursor:pointer; font-size:0.78rem; font-weight:600;">📷 Camera</button>
            <button id="screen-stop-btn" onclick="stopScreenCapture()" style="flex:1; padding:8px; border-radius:8px; border:1px solid rgba(239,68,68,0.3); background:rgba(239,68,68,0.1); color:#ef4444; cursor:pointer; font-size:0.78rem; font-weight:600; display:none;">⏹ Stop</button>
        </div>
        <div style="padding:0 12px 10px; display:flex; gap:8px;">
            <input id="screen-question-input" type="text" placeholder="Sawaal poocho..." style="flex:1; background:rgba(255,255,255,0.05); border:1px solid rgba(0,229,255,0.15); border-radius:8px; padding:7px 10px; color:white; font-size:0.8rem; outline:none;" onkeydown="if(event.key==='Enter') sendScreenQuestion()">
            <button onclick="sendScreenQuestion()" style="padding:7px 12px; border-radius:8px; background:#00E5FF; color:#000; border:none; cursor:pointer; font-weight:700; font-size:0.8rem;">↑</button>
        </div>
    `;
    document.body.appendChild(panel);
    screenState.panelOpen = true;

    // WebSocket connect
    connectScreenWS();
}

function closeScreenPanel() {
    stopScreenCapture();
    if (screenState.ws) { screenState.ws.close(); screenState.ws = null; }
    document.getElementById('screen-panel')?.remove();
    screenState.panelOpen = false;
}

function connectScreenWS() {
    if (!screenState.wsUrl) return;
    if (screenState.ws && screenState.ws.readyState === WebSocket.OPEN) return;

    screenState.ws = new WebSocket(screenState.wsUrl);

    screenState.ws.onopen = () => {
        addScreenComment('✅ AI Connected — screen ya camera share karo', 'system');
    };
    screenState.ws.onclose = () => {
        addScreenComment('🔄 Reconnecting...', 'system');
        setTimeout(connectScreenWS, 3000);
    };
    screenState.ws.onmessage = (evt) => {
        const msg = JSON.parse(evt.data);
        if (msg.type === 'analysis') {
            screenState.isThinking = false;
            addScreenComment(msg.text, 'ai');
            // Chat box mein bhi dikhao
            appendMessage('assistant', `🖥️ *[Screen AI]:* ${msg.text}`, null);
        }
        if (msg.type === 'audio' && screenState.voiceEnabled) {
            const audio = new Audio('data:audio/mp3;base64,' + msg.data);
            audio.play().catch(() => {});
        }
        if (msg.type === 'thinking') {
            screenState.isThinking = true;
        }
    };
}

async function startScreenShare() {
    try {
        screenState.stream = await navigator.mediaDevices.getDisplayMedia({ video: { cursor: 'always' }, audio: false });
        screenState.captureMode = 'screen';
        _startScreenPreview();
    } catch (e) {
        if (e.name !== 'NotAllowedError') addScreenComment('⚠️ Screen share failed: ' + e.message, 'system');
    }
}

async function startScreenCam() {
    try {
        screenState.stream = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 }, audio: false });
        screenState.captureMode = 'webcam';
        _startScreenPreview();
    } catch (e) {
        addScreenComment('⚠️ Camera failed: ' + e.message, 'system');
    }
}

function _startScreenPreview() {
    const video = document.getElementById('screen-video');
    if (!video) return;
    video.srcObject = screenState.stream;
    video.style.display = 'block';
    document.getElementById('screen-placeholder').style.display = 'none';
    document.getElementById('screen-stop-btn').style.display = 'flex';

    // Auto capture — har 5 sec (conservative for free Gemini tier)
    screenState.autoTimer = setInterval(() => {
        if (screenState.stream && !screenState.isThinking) {
            _sendScreenFrame('');
        }
    }, 5000);

    addScreenComment(`${screenState.captureMode === 'screen' ? '🖥️ Screen' : '📷 Camera'} share started — AI har 5 sec mein analyze karega`, 'system');
}

function stopScreenCapture() {
    if (screenState.stream) {
        screenState.stream.getTracks().forEach(t => t.stop());
        screenState.stream = null;
    }
    if (screenState.autoTimer) { clearInterval(screenState.autoTimer); screenState.autoTimer = null; }
    const video = document.getElementById('screen-video');
    if (video) { video.srcObject = null; video.style.display = 'none'; }
    const ph = document.getElementById('screen-placeholder');
    if (ph) ph.style.display = 'flex';
    const stopBtn = document.getElementById('screen-stop-btn');
    if (stopBtn) stopBtn.style.display = 'none';
    screenState.captureMode = '';
}

function sendScreenQuestion() {
    const inp = document.getElementById('screen-question-input');
    if (!inp) return;
    const text = inp.value.trim();
    if (!text) return;
    inp.value = '';

    if (screenState.stream) {
        _sendScreenFrame(text);
    } else if (screenState.ws && screenState.ws.readyState === WebSocket.OPEN) {
        screenState.ws.send(JSON.stringify({ type: 'question', text }));
    }
    addScreenComment(`You: ${text}`, 'user');
}

function _sendScreenFrame(question) {
    if (!screenState.stream || !screenState.ws || screenState.ws.readyState !== WebSocket.OPEN) return;

    const video = document.getElementById('screen-video');
    if (!video || !video.videoWidth) return;

    // Canvas pe draw karo
    const canvas = document.createElement('canvas');
    let w = video.videoWidth, h = video.videoHeight;
    if (w > 1280) { h = Math.round(h * 1280 / w); w = 1280; }
    canvas.width = w; canvas.height = h;
    canvas.getContext('2d').drawImage(video, 0, 0, w, h);
    const frameData = canvas.toDataURL('image/jpeg', 0.8);

    screenState.ws.send(JSON.stringify({
        type:     'frame',
        data:     frameData,
        mode:     screenState.captureMode,
        question: question,
    }));
}

function addScreenComment(text, role) {
    const box = document.getElementById('screen-commentary');
    if (!box) return;
    const div = document.createElement('div');
    div.style.cssText = role === 'ai'
        ? 'color:#e2e8f0; margin-bottom:6px; padding:6px 8px; background:rgba(0,229,255,0.06); border-radius:8px;'
        : role === 'user'
        ? 'color:#00E5FF; margin-bottom:4px; text-align:right; font-size:0.75rem;'
        : 'color:rgba(255,255,255,0.3); margin-bottom:4px; text-align:center; font-size:0.72rem;';
    div.textContent = text;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
}

// ==================================================================================
// 🔧 SHARED UTILITY
// ==================================================================================
function showToast(icon, title) {
    Swal.mixin({ toast: true, position: 'top-end', showConfirmButton: false, timer: 2500, background: '#1e1e1e', color: '#fff' })
        .fire({ icon, title });
}