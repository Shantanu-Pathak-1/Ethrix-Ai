document.addEventListener('DOMContentLoaded', () => {
    loadProfile();
    loadMemories();
});

async function loadProfile() {
    const res = await fetch('/api/profile');
    const data = await res.json();
    if (data.custom_instruction) {
        document.getElementById('instructionInput').value = data.custom_instruction;
    }
}

async function saveInstruction() {
    const text = document.getElementById('instructionInput').value;
    const btn = document.querySelector('button[onclick="saveInstruction()"]');
    btn.textContent = "Saving...";
    
    await fetch('/api/save_instruction', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instruction: text })
    });
    
    btn.textContent = "Saved!";
    setTimeout(() => btn.textContent = "Save Persona", 2000);
}

async function loadMemories() {
    const res = await fetch('/api/memories');
    const data = await res.json();
    const list = document.getElementById('memoryList');
    document.getElementById('memCount').textContent = data.memories.length;
    
    list.innerHTML = '';
    
    if (data.memories.length === 0) {
        list.innerHTML = '<p style="text-align: center; color: #64748b; padding: 20px;">No memories saved yet. Chat with Shanvika to build memory!</p>';
        return;
    }

    // 🚀 BUGS FIXED HERE: Direct DOM manipulation instead of innerHTML strings
    data.memories.forEach(mem => {
        const div = document.createElement('div');
        div.className = 'memory-item';
        
        const textSpan = document.createElement('span');
        textSpan.className = 'memory-text';
        textSpan.textContent = mem; // Safe text injection (won't break quotes)
        
        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'delete-btn';
        deleteBtn.innerHTML = '<i class="ri-delete-bin-line"></i>';
        
        // Exact exact string pass ho raha hai bina break hue!
        deleteBtn.onclick = () => deleteMemory(mem); 
        
        div.appendChild(textSpan);
        div.appendChild(deleteBtn);
        list.appendChild(div);
    });
}

async function addMemoryManual() {
    const input = document.getElementById('newMemoryInput');
    const text = input.value.trim();
    if (!text) return;
    
    await fetch('/api/add_memory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ memory_text: text })
    });
    
    input.value = '';
    loadMemories();
}

async function deleteMemory(text) {
    if(!confirm("Forget this memory?")) return;
    
    await fetch('/api/delete_memory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ memory_text: text })
    });
    
    loadMemories();
}