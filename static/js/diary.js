document.addEventListener('DOMContentLoaded', () => {
    loadDiaryEntries();
});

async function loadDiaryEntries() {
    const grid = document.getElementById('diaryGrid');
    
    try {
        const res = await fetch('/api/diary_entries');
        const data = await res.json();
        
        grid.innerHTML = ''; // Clear loading state

        if (!data.entries || data.entries.length === 0) {
            grid.innerHTML = `
                <div style="grid-column: 1/-1; text-align: center; padding: 60px; color: #64748b;">
                    <i class="fas fa-book-open" style="font-size: 3rem; margin-bottom: 20px; opacity: 0.5;"></i>
                    <h3>Diary is Empty</h3>
                    <p>Shanvika hasn't written anything yet. Chat with her to create memories!</p>
                </div>
            `;
            return;
        }

        // Animation Delay Counter
        let delay = 0;

        data.entries.forEach(entry => {
            const card = document.createElement('div');
            card.className = 'diary-card';
            card.style.animationDelay = `${delay}ms`; // Staggered animation
            
            // Format Date (e.g., "2025-02-14" -> "Feb 14, 2026")
            const dateObj = new Date(entry.date);
            const dateStr = dateObj.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
            
            // Mood Emoji Mapping
            const moodEmojis = {
                "Happy": "😊", "Reflective": "🤔", "Romantic": "🥰", 
                "Sad": "😔", "Excited": "🤩", "Neutral": "😐"
            };
            const moodEmoji = moodEmojis[entry.mood] || "✨";

            card.innerHTML = `
                <div class="card-date">
                    <span><i class="far fa-calendar-alt"></i> ${dateStr}</span>
                    <span class="card-mood" title="${entry.mood}">${moodEmoji}</span>
                </div>
                <div class="card-preview">
                    ${entry.content}
                </div>
                <div class="read-more">
                    Read Secret Note <i class="fas fa-arrow-right" style="font-size: 0.7rem;"></i>
                </div>
            `;

            // Click Event to Open Modal
            card.onclick = () => openDiaryModal(dateStr, entry.content, entry.mood);
            
            grid.appendChild(card);
            delay += 100; // Increase delay for next card
        });

    } catch (error) {
        console.error("Diary Load Error:", error);
        grid.innerHTML = `<p style="text-align:center; color: #ef4444;">Failed to load secret diary. Try again.</p>`;
    }
}

// Open Modal with Animation
function openDiaryModal(date, content, mood) {
    const modal = document.getElementById('diaryModal');
    const modalDate = document.getElementById('modalDate');
    const modalText = document.getElementById('modalText');

    modalDate.innerHTML = `<i class="fas fa-star" style="color: #f472b6;"></i> ${date} • Mood: ${mood}`;
    modalText.innerText = content; // Using innerText preserves newlines

    modal.style.display = 'flex';
    
    // Add pop animation class
    const box = modal.querySelector('.diary-content-box');
    box.style.animation = 'fadeIn 0.3s ease-out';
}

// Close Modal
function closeDiaryModal(event) {
    // If event is present, check if click was on overlay (outside box)
    if (event && !event.target.classList.contains('diary-modal')) return;
    
    const modal = document.getElementById('diaryModal');
    modal.style.display = 'none';
}

// Close on Escape Key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeDiaryModal();
});

async function writeDiaryNow() {
    const btn = document.getElementById('writeDiaryBtn');
    if(btn) btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Likh rahi hu...';
    
    try {
        const res = await fetch('/api/trigger_diary', { method: 'POST' });
        const data = await res.json();
        
        if(data.status === 'success') {
            alert(data.message);
            loadDiaryEntries(); // Page refresh kiye bina nayi entry dikhayega
        } else {
            alert(data.message);
        }
    } catch (err) {
        alert("Kuch gadbad ho gayi!");
    }
    
    if(btn) btn.innerHTML = '<i class="fas fa-pen-nib"></i> Write Diary Now';
}