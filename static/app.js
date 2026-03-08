// Personal X Pipeline — Tabbed Interface
// Tabs: DUMP | IDEAS | DRAFTS | POSTED

const API_BASE = '';

// ── Verify X connection (no post, no quota) ──────────────────────────────────
async function verifyConnection() {
    const btn = document.getElementById('verify-btn');
    btn.disabled = true;
    btn.textContent = '⏳';
    // remove old toast
    document.querySelectorAll('.verify-toast').forEach(el => el.remove());
    try {
        const resp = await fetch(`${API_BASE}/verify`);
        const data = await resp.json();
        const toast = document.createElement('div');
        toast.className = `verify-toast ${data.ok ? 'ok' : 'err'}`;
        toast.textContent = data.ok
            ? `✓ @${data.handle} connected`
            : `✗ ${data.error || 'Auth failed'}`;
        document.body.appendChild(toast);
        btn.textContent = data.ok ? '✅' : '❌';
        setTimeout(() => { toast.remove(); btn.textContent = '⚡'; btn.disabled = false; }, 3500);
    } catch (e) {
        btn.textContent = '❌';
        setTimeout(() => { btn.textContent = '⚡'; btn.disabled = false; }, 3000);
    }
}

// ─── State ───────────────────────────────────────────────────────────────────
let activeTab = 'tab-dump';
let currentEditingIdea = null;
let currentEditingDraft = null;
let uploadedFile = null;

// ─── Swipe Gesture Navigation ─────────────────────────────────────────────────
const TAB_ORDER = ['tab-dump', 'tab-ideas', 'tab-drafts', 'tab-posted'];
let touchStartX = 0;
let touchStartY = 0;
const SWIPE_THRESHOLD = 50;

document.addEventListener('touchstart', (e) => {
    touchStartX = e.touches[0].clientX;
    touchStartY = e.touches[0].clientY;
}, { passive: true });

document.addEventListener('touchend', (e) => {
    const touchEndX = e.changedTouches[0].clientX;
    const touchEndY = e.changedTouches[0].clientY;
    const diffX = touchEndX - touchStartX;
    const diffY = touchEndY - touchStartY;

    // Only handle horizontal swipes (ignore vertical scrolling)
    if (Math.abs(diffX) > Math.abs(diffY) && Math.abs(diffX) > SWIPE_THRESHOLD) {
        const currentIndex = TAB_ORDER.indexOf(activeTab);
        if (diffX < 0 && currentIndex < TAB_ORDER.length - 1) {
            // Swipe left → next tab
            switchTab(TAB_ORDER[currentIndex + 1]);
        } else if (diffX > 0 && currentIndex > 0) {
            // Swipe right → previous tab
            switchTab(TAB_ORDER[currentIndex - 1]);
        }
    }
}, { passive: true });

// ─── Tab Switching ────────────────────────────────────────────────────────────
function switchTab(tabId) {
    // Deactivate all
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.tab-link').forEach(l => l.classList.remove('active'));

    // Activate target
    const panel = document.getElementById(tabId);
    const link = document.querySelector(`.tab-link[data-tab="${tabId}"]`);
    if (panel) panel.classList.add('active');
    if (link) link.classList.add('active');

    activeTab = tabId;

    // Load data for the newly visible tab
    if (tabId === 'tab-ideas') loadIdeas();
    if (tabId === 'tab-drafts') loadDrafts();
    if (tabId === 'tab-posted') loadPosted();
}

// ─── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    // Wire tab bar
    document.querySelectorAll('.tab-link').forEach(link => {
        link.addEventListener('click', () => switchTab(link.dataset.tab));
    });

    // Preload IDEAS and DRAFTS counts in background
    loadIdeas();
    loadDrafts();

    setupEventListeners();
});

function setupEventListeners() {
    // Dump form
    document.getElementById('dump-form').addEventListener('submit', handleDumpSubmit);

    // Image upload
    const uploadZone = document.getElementById('upload-zone');
    const dumpImage = document.getElementById('dump-image');
    uploadZone.addEventListener('click', () => dumpImage.click());
    dumpImage.addEventListener('change', handleFileSelect);
    uploadZone.addEventListener('dragover', handleDragOver);
    uploadZone.addEventListener('dragleave', handleDragLeave);
    uploadZone.addEventListener('drop', handleDrop);

    // Idea modal
    document.getElementById('modal-close').addEventListener('click', closeModal);
    document.getElementById('modal-cancel').addEventListener('click', closeModal);
    document.getElementById('modal-save').addEventListener('click', saveIdea);
    document.querySelector('#modal .modal-backdrop').addEventListener('click', closeModal);

    // Draft modal
    document.getElementById('draft-modal-close').addEventListener('click', closeDraftModal);
    document.getElementById('draft-modal-cancel').addEventListener('click', closeDraftModal);
    document.getElementById('draft-modal-save').addEventListener('click', saveDraft);
    document.querySelector('#draft-modal .modal-backdrop').addEventListener('click', closeDraftModal);
}

// ─── API Helper ───────────────────────────────────────────────────────────────
async function apiRequest(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    const config = {
        headers: { 'Content-Type': 'application/json', ...options.headers },
        ...options,
    };

    if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
        config.body = JSON.stringify(options.body);
    }
    if (options.body instanceof FormData) {
        delete config.headers['Content-Type'];
    }

    const response = await fetch(url, config);
    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(error.detail || 'Request failed');
    }
    return response.json();
}

// ─── Tag Normalization (API returns tags as comma-separated string) ────────────
function normalizeTags(tags) {
    return (typeof tags === 'string' ? tags.split(',') : tags || [])
        .map(t => t.trim())
        .filter(Boolean);
}

// ─── IDEAS ────────────────────────────────────────────────────────────────────
// Fetch raw AND refining — ideas stay visible throughout the refine process.
// Only 'drafted' and 'archived' ideas are excluded.
async function loadIdeas() {
    const list = document.getElementById('ideas-list');
    try {
        // No status filter: get all ideas, then exclude drafted/archived on the client
        const all = await apiRequest('/ideas');
        const ideas = all.filter(i => i.status !== 'drafted' && i.status !== 'archived');
        renderIdeas(ideas);
    } catch (error) {
        console.error('Failed to load ideas:', error);
        list.innerHTML = '<div class="card-list-empty">Failed to load ideas</div>';
    }
}

function renderIdeas(ideas) {
    const list = document.getElementById('ideas-list');
    if (!ideas || ideas.length === 0) {
        list.innerHTML = '<div class="card-list-empty">No ideas yet. Dump something.</div>';
        return;
    }

    list.innerHTML = ideas.map(idea => {
        const isRefining = idea.status === 'refining';
        const tagList = normalizeTags(idea.tags);
        return `
        <div class="idea-card${isRefining ? ' refining' : ''}" data-id="${idea.id}">
            <div class="idea-header">
                <div class="idea-preview">${escapeHtml(idea.content)}</div>
                <div class="idea-header-right">
                    <span class="idea-timestamp">${formatTimestamp(idea.created_at)}</span>
                    ${isRefining ? '<span class="badge-refining">Refining...</span>' : ''}
                </div>
            </div>
            ${tagList.length || idea.link ? `
            <div class="idea-meta">
                ${idea.link ? `<a href="${escapeHtml(idea.link)}" class="idea-link" target="_blank">${escapeHtml(truncate(idea.link, 40))}</a>` : ''}
                ${tagList.length ? `
                <div class="idea-tags">
                    ${tagList.map(tag => `<span class="tag">${escapeHtml(tag)}</span>`).join('')}
                </div>` : ''}
            </div>` : ''}
            ${idea.image_path ? `<img src="${escapeHtml(idea.image_path)}" class="idea-thumbnail" alt="">` : ''}
            <div class="idea-actions">
                <button class="btn btn-secondary btn-small" onclick="expandIdea('${idea.id}')">Expand</button>
                <button class="btn btn-primary btn-small btn-refine" onclick="refineIdea('${idea.id}')"${isRefining ? ' disabled' : ''}>Refine</button>
                <button class="btn btn-danger btn-small" onclick="deleteIdea('${idea.id}')">Delete</button>
            </div>
        </div>`;
    }).join('');
}

async function expandIdea(id) {
    try {
        const idea = await apiRequest(`/ideas/${id}`);
        currentEditingIdea = idea;
        document.getElementById('modal-content').value = idea.content || '';
        document.getElementById('modal-link').value = idea.link || '';
        document.getElementById('modal-tags').value = normalizeTags(idea.tags).join(', ');
        document.getElementById('modal-title').textContent = 'Edit Idea';
        document.getElementById('modal').classList.remove('hidden');
    } catch (error) {
        console.error('Failed to load idea:', error);
        showStatus('ideas-status', 'Failed to load idea', 'error');
    }
}

async function refineIdea(id) {
    try {
        const card = document.querySelector(`.idea-card[data-id="${id}"]`);
        if (card) card.classList.add('loading');
        await apiRequest(`/ideas/${id}/refine`, { method: 'POST' });
        showStatus('ideas-status', 'Refining idea...', 'success');
        // Reload so the card shows 'refining' badge (not hidden)
        loadIdeas();
    } catch (error) {
        console.error('Failed to refine idea:', error);
        showStatus('ideas-status', 'Failed to refine idea: ' + error.message, 'error');
        loadIdeas();
    }
}

async function deleteIdea(id) {
    if (!confirm('Delete this idea?')) return;
    try {
        await apiRequest(`/ideas/${id}`, { method: 'DELETE' });
        loadIdeas();
    } catch (error) {
        console.error('Failed to delete idea:', error);
        showStatus('ideas-status', 'Failed to delete idea', 'error');
    }
}

async function saveIdea() {
    if (!currentEditingIdea) return;
    const tags = document.getElementById('modal-tags').value
        .split(',').map(t => t.trim()).filter(Boolean);
    try {
        await apiRequest(`/ideas/${currentEditingIdea.id}`, {
            method: 'PUT',
            body: {
                content: document.getElementById('modal-content').value,
                link: document.getElementById('modal-link').value || null,
                tags,
            },
        });
        closeModal();
        loadIdeas();
    } catch (error) {
        console.error('Failed to save idea:', error);
        showStatus('ideas-status', 'Failed to save idea', 'error');
    }
}

function closeModal() {
    document.getElementById('modal').classList.add('hidden');
    currentEditingIdea = null;
}

// ─── DRAFTS ───────────────────────────────────────────────────────────────────
async function loadDrafts() {
    const list = document.getElementById('drafts-list');
    try {
        // Load pending AND revision_requested drafts
        const [pending, revisionReq] = await Promise.all([
            apiRequest('/drafts?status=pending'),
            apiRequest('/drafts?status=revision_requested'),
        ]);
        renderDrafts([...pending, ...revisionReq]);
    } catch (error) {
        console.error('Failed to load drafts:', error);
        list.innerHTML = '<div class="card-list-empty">Failed to load drafts</div>';
    }
}

// Convert absolute filesystem paths to URL paths for media
function mediaPathToUrl(path) {
    if (!path) return null;
    // Handle absolute filesystem paths
    const mediaMatch = path.match(/\/media\/(.+)$/);
    if (mediaMatch) return `/media/${mediaMatch[1]}`;
    // Handle paths already starting with /media/ or /static/
    if (path.startsWith('/media/') || path.startsWith('/static/')) return path;
    return path;
}

function renderDrafts(drafts) {
    const list = document.getElementById('drafts-list');
    if (!drafts || drafts.length === 0) {
        list.innerHTML = '<div class="card-list-empty">No pending drafts. Refine some ideas.</div>';
        return;
    }

    list.innerHTML = drafts.map(draft => {
        const thread = draft.thread || [];
        const mediaUrl = mediaPathToUrl(draft.media_path);
        const isRevisionRequested = draft.status === 'revision_requested';
        return `
        <div class="draft-card${isRevisionRequested ? ' draft-revision-requested' : ''}" data-id="${draft.id}">
            ${isRevisionRequested ? `<div class="draft-status-badge">✏️ Revision Requested</div>` : ''}
            <div class="thread-preview">
                ${thread.map((tweet, i) => {
                    // Per-tweet media takes priority, then fall back to draft media on first tweet
                    const tweetMedia = tweet.media_path ? mediaPathToUrl(tweet.media_path) : (i === 0 ? mediaUrl : null);
                    return `
                <div class="tweet ${i > 0 ? 'tweet-reply' : ''}">
                    <div class="tweet-number">${i === 0 ? '1/' : `\u21b3 ${i + 1}/`}</div>
                    <div class="tweet-content">${escapeHtml(tweet.text)}</div>
                    ${tweetMedia ? `<div class="tweet-media"><img src="${escapeHtml(tweetMedia)}" alt="Tweet media" loading="eager" onerror="this.parentElement.innerHTML='<div class=\\'media-error\\'>⚠️ Image failed to load: ${escapeHtml(tweetMedia)}</div>'"></div>` : ''}
                </div>`;
                }).join('')}
            </div>
            <div class="media-section">
                <label>Media Prompt</label>
                <input type="text" id="media-prompt-${draft.id}" placeholder="Describe the image to generate...">
                <div class="media-buttons">
                    <button class="btn btn-secondary btn-small" onclick="generateMedia('${draft.id}')">Generate Media</button>
                    <button class="btn btn-secondary btn-small" onclick="uploadMedia('${draft.id}')">Upload Image</button>
                </div>
            </div>
            <div class="revision-section" id="revision-section-${draft.id}">
                <button class="revision-toggle" onclick="toggleRevision('${draft.id}')">
                    <span class="revision-toggle-icon" id="revision-icon-${draft.id}">${isRevisionRequested ? '▼' : '▶'}</span>
                    ✨ Revision Notes
                    ${isRevisionRequested ? '<span class="revision-badge">Notes saved</span>' : ''}
                </button>
                <div class="revision-body${isRevisionRequested ? ' open' : ''}" id="revision-body-${draft.id}">
                    <textarea
                        id="revision-notes-${draft.id}"
                        class="revision-textarea"
                        rows="3"
                        placeholder="e.g. Use the hook from the other draft&#10;Make tweet 3 punchier&#10;Add a call to action at the end"
                    >${escapeHtml(draft.revision_notes || '')}</textarea>
                    <div class="revision-actions">
                        <button class="btn btn-primary btn-small" onclick="requestRevision('${draft.id}')">Request Revision</button>
                        <span class="revision-status" id="revision-status-${draft.id}"></span>
                    </div>
                </div>
            </div>
            <div class="draft-actions">
                <button class="btn btn-secondary btn-small" onclick="editDraft('${draft.id}')">Edit</button>
                <button class="btn btn-primary btn-small" onclick="approveDraft('${draft.id}')">Approve & Post</button>
                <button class="btn btn-danger btn-small" onclick="rejectDraft('${draft.id}')">Reject</button>
                <button class="btn btn-secondary btn-small" onclick="archiveDraft('${draft.id}')">Archive</button>
            </div>
        </div>`;
    }).join('');
}

function toggleRevision(draftId) {
    const body = document.getElementById(`revision-body-${draftId}`);
    const icon = document.getElementById(`revision-icon-${draftId}`);
    if (!body) return;
    const isOpen = body.classList.toggle('open');
    icon.textContent = isOpen ? '▼' : '▶';
}

async function requestRevision(draftId) {
    const textarea = document.getElementById(`revision-notes-${draftId}`);
    const statusEl = document.getElementById(`revision-status-${draftId}`);
    if (!textarea) return;

    const notes = textarea.value.trim();
    if (!notes) {
        if (statusEl) { statusEl.textContent = 'Write some notes first.'; statusEl.className = 'revision-status revision-status-error'; }
        return;
    }

    try {
        if (statusEl) { statusEl.textContent = 'Saving...'; statusEl.className = 'revision-status'; }
        await apiRequest(`/drafts/${draftId}/request-revision`, {
            method: 'POST',
            body: { notes },
        });
        if (statusEl) { statusEl.textContent = '✓ Saved'; statusEl.className = 'revision-status revision-status-ok'; }
        // Reload drafts after a brief moment so the badge updates
        setTimeout(() => loadDrafts(), 800);
    } catch (error) {
        console.error('Failed to request revision:', error);
        if (statusEl) { statusEl.textContent = 'Failed: ' + error.message; statusEl.className = 'revision-status revision-status-error'; }
    }
}

async function editDraft(id) {
    try {
        const draft = await apiRequest(`/drafts/${id}`);
        currentEditingDraft = draft;
        const thread = draft.thread || [];
        const editor = document.getElementById('draft-editor');
        editor.innerHTML = thread.map((tweet, i) => `
            <div class="tweet-edit">
                <label>Tweet ${i + 1}${i > 0 ? ' (reply)' : ''}</label>
                <textarea id="draft-tweet-${i}" rows="3">${escapeHtml(tweet.text)}</textarea>
            </div>`).join('');
        document.getElementById('draft-modal').classList.remove('hidden');
    } catch (error) {
        console.error('Failed to load draft:', error);
        showStatus('drafts-status', 'Failed to load draft', 'error');
    }
}

async function saveDraft() {
    if (!currentEditingDraft) return;
    const thread = currentEditingDraft.thread.map((tweet, i) => {
        const textarea = document.getElementById(`draft-tweet-${i}`);
        return { ...tweet, text: textarea ? textarea.value : tweet.text };
    });
    try {
        await apiRequest(`/drafts/${currentEditingDraft.id}`, {
            method: 'PUT',
            body: { thread },
        });
        closeDraftModal();
        loadDrafts();
    } catch (error) {
        console.error('Failed to save draft:', error);
        showStatus('drafts-status', 'Failed to save draft', 'error');
    }
}

function closeDraftModal() {
    document.getElementById('draft-modal').classList.add('hidden');
    currentEditingDraft = null;
}

async function generateMedia(draftId) {
    const promptInput = document.getElementById(`media-prompt-${draftId}`);
    const prompt = promptInput ? promptInput.value.trim() : '';
    if (!prompt) {
        showStatus('drafts-status', 'Please enter a media prompt', 'error');
        return;
    }
    
    try {
        showStatus('drafts-status', 'Generating media...', 'info');
        const response = await apiRequest(`/drafts/${draftId}/generate-media`, {
            method: 'POST',
            body: JSON.stringify({ prompt: prompt, tweet_index: 0 })
        });
        showStatus('drafts-status', 'Media generated!', 'success');
        loadDrafts();  // Refresh to show new media
    } catch (error) {
        console.error('Failed to generate media:', error);
        showStatus('drafts-status', 'Failed to generate: ' + error.message, 'error');
    }
}

function uploadMedia(draftId) {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const formData = new FormData();
        formData.append('file', file);
        formData.append('draft_id', draftId);
        try {
            await apiRequest('/upload', { method: 'POST', body: formData });
            loadDrafts();
            showStatus('drafts-status', 'Image uploaded', 'success');
        } catch (error) {
            console.error('Failed to upload:', error);
            showStatus('drafts-status', 'Failed to upload image', 'error');
        }
    };
    input.click();
}

async function approveDraft(id) {
    if (!confirm('Post this thread to X?')) return;
    try {
        const card = document.querySelector(`.draft-card[data-id="${id}"]`);
        if (card) card.classList.add('loading');
        await apiRequest(`/drafts/${id}/approve`, { method: 'POST' });
        showStatus('drafts-status', 'Posted to X', 'success');
        loadDrafts();
        // Auto-switch to POSTED tab
        switchTab('tab-posted');
    } catch (error) {
        console.error('Failed to approve draft:', error);
        showStatus('drafts-status', 'Failed to post: ' + error.message, 'error');
        loadDrafts();
    }
}

async function rejectDraft(id) {
    if (!confirm('Reject this draft?')) return;
    try {
        await apiRequest(`/drafts/${id}/reject`, { method: 'POST' });
        loadDrafts();
    } catch (error) {
        console.error('Failed to reject draft:', error);
        showStatus('drafts-status', 'Failed to reject draft', 'error');
    }
}

async function archiveDraft(id) {
    try {
        await apiRequest(`/drafts/${id}/archive`, { method: 'POST' });
        loadDrafts();
    } catch (error) {
        console.error('Failed to archive draft:', error);
        showStatus('drafts-status', 'Failed to archive draft', 'error');
    }
}

// ─── POSTED ───────────────────────────────────────────────────────────────────
async function loadPosted() {
    const list = document.getElementById('posted-list');
    try {
        const posted = await apiRequest('/drafts?status=posted');
        renderPosted(posted);
    } catch (error) {
        console.error('Failed to load posted:', error);
        list.innerHTML = '<div class="card-list-empty">Failed to load posted threads</div>';
    }
}

function renderPosted(items) {
    const list = document.getElementById('posted-list');
    if (!items || items.length === 0) {
        list.innerHTML = '<div class="card-list-empty">Nothing posted yet.</div>';
        return;
    }

    list.innerHTML = items.map(item => {
        const thread = item.thread || [];
        const firstTweet = thread[0];
        const preview = firstTweet ? truncate(firstTweet.text, 180) : '(empty thread)';
        return `
        <div class="posted-card" data-id="${item.id}">
            <div class="posted-header">
                <div class="posted-preview">${escapeHtml(preview)}</div>
                <span class="posted-timestamp">${formatTimestamp(item.updated_at || item.created_at)}</span>
            </div>
            <div class="posted-meta">
                ${thread.length > 1 ? `<span style="font-size:12px;color:var(--text-muted)">${thread.length} tweets</span>` : ''}
                ${item.tweet_url ? `<a href="${escapeHtml(item.tweet_url)}" class="posted-url" target="_blank">${escapeHtml(item.tweet_url)}</a>` : ''}
            </div>
            <div class="posted-actions">
                <button class="btn btn-secondary btn-small" onclick="archivePosted('${item.id}')">Archive</button>
            </div>
        </div>`;
    }).join('');
}

async function archivePosted(id) {
    try {
        await apiRequest(`/drafts/${id}/archive`, { method: 'POST' });
        loadPosted();
    } catch (error) {
        console.error('Failed to archive:', error);
        showStatus('posted-status', 'Failed to archive', 'error');
    }
}

// ─── DUMP Form ────────────────────────────────────────────────────────────────
async function handleDumpSubmit(e) {
    e.preventDefault();

    const content = document.getElementById('dump-content').value.trim();
    if (!content) {
        showStatus('dump-status', 'Please enter some content', 'error');
        return;
    }

    const tags = document.getElementById('dump-tags').value
        .split(',').map(t => t.trim()).filter(Boolean);

    const body = {
        content,
        link: document.getElementById('dump-link').value.trim() || null,
        tags: tags.length ? tags : null,
    };

    try {
        if (uploadedFile) {
            const formData = new FormData();
            formData.append('file', uploadedFile);
            const uploadResult = await apiRequest('/upload', { method: 'POST', body: formData });
            body.image = uploadResult.path;
        }

        await apiRequest('/ideas', { method: 'POST', body });

        // Clear form
        document.getElementById('dump-content').value = '';
        document.getElementById('dump-link').value = '';
        document.getElementById('dump-tags').value = '';
        uploadedFile = null;
        document.getElementById('upload-preview').textContent = '';
        document.getElementById('upload-zone').classList.remove('has-file');

        showStatus('dump-status', 'Idea captured', 'success');

        // Auto-switch to IDEAS tab
        switchTab('tab-ideas');
    } catch (error) {
        console.error('Failed to submit:', error);
        showStatus('dump-status', 'Failed to submit: ' + error.message, 'error');
    }
}

// ─── File Upload Handlers ─────────────────────────────────────────────────────
function handleFileSelect(e) {
    const file = e.target.files[0];
    if (file) {
        uploadedFile = file;
        document.getElementById('upload-preview').textContent = file.name;
        document.getElementById('upload-zone').classList.add('has-file');
    }
}

function handleDragOver(e) {
    e.preventDefault();
    document.getElementById('upload-zone').classList.add('dragover');
}

function handleDragLeave(e) {
    e.preventDefault();
    document.getElementById('upload-zone').classList.remove('dragover');
}

function handleDrop(e) {
    e.preventDefault();
    document.getElementById('upload-zone').classList.remove('dragover');
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith('image/')) {
        uploadedFile = file;
        document.getElementById('upload-preview').textContent = file.name;
        document.getElementById('upload-zone').classList.add('has-file');
    }
}

// ─── Utilities ────────────────────────────────────────────────────────────────
function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function truncate(str, len) {
    if (!str) return '';
    return str.length <= len ? str : str.slice(0, len) + '...';
}

function formatTimestamp(ts) {
    if (!ts) return '';
    const date = new Date(ts);
    const diff = Date.now() - date;
    if (diff < 60000) return 'just now';
    if (diff < 3600000) return Math.floor(diff / 60000) + 'm ago';
    if (diff < 86400000) return Math.floor(diff / 3600000) + 'h ago';
    if (diff < 604800000) return Math.floor(diff / 86400000) + 'd ago';
    return date.toLocaleDateString();
}

function showStatus(containerId, message, type) {
    const container = document.getElementById(containerId);
    if (!container) return;

    // Remove existing
    const existing = container.querySelector('.status-message');
    if (existing) existing.remove();

    const el = document.createElement('div');
    el.className = `status-message status-${type}`;
    el.textContent = message;
    container.appendChild(el);

    setTimeout(() => el.remove(), 3500);
}
