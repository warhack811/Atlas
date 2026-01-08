/**
 * ATLAS UI State Management Module
 * Handles sessions, persistence, and user roles.
 */

const STATE_KEY = 'atlas_v1_store';
const MAX_SESSIONS = 50;
const MAX_MESSAGES_PER_SESSION = 120;
const FULL_RDR_LIMIT = 5; // Store full RDR only for last 5 assistant messages

class StateManager {
    constructor() {
        this.state = this._loadInitialState();
    }

    _loadInitialState() {
        try {
            const saved = localStorage.getItem(STATE_KEY);
            if (saved) {
                const parsed = JSON.parse(saved);
                // Basic migration / schema check
                if (!parsed.sessions) parsed.sessions = [];
                if (!parsed.user) parsed.user = null;
                return parsed;
            }
        } catch (e) {
            console.error('Failed to load state from localStorage', e);
        }
        return {
            user: null, // { name, role }
            sessions: [], // { id, title, createdAt, messages: [] }
            activeSessionId: null,
            ui: {
                sidebarOpen: window.innerWidth > 768,
                inspectorOpen: false,
                theme: 'dark'
            }
        };
    }

    save() {
        try {
            this._pruneState();
            localStorage.setItem(STATE_KEY, JSON.stringify(this.state));
        } catch (e) {
            if (e.name === 'QuotaExceededError') {
                console.warn('LocalStorage Quota Exceeded. Aggressive pruning...');
                this._aggressivePrune();
                this.save();
            }
        }
    }

    _pruneState() {
        // Prune sessions
        if (this.state.sessions.length > MAX_SESSIONS) {
            this.state.sessions = this.state.sessions.slice(0, MAX_SESSIONS);
        }

        // Prune messages and RDR data
        this.state.sessions.forEach(session => {
            if (session.messages.length > MAX_MESSAGES_PER_SESSION) {
                session.messages = session.messages.slice(-MAX_MESSAGES_PER_SESSION);
            }

            // Prune heavy RDR data for old messages
            let assistantMsgCount = 0;
            for (let i = session.messages.length - 1; i >= 0; i--) {
                const msg = session.messages[i];
                if (msg.role === 'assistant') {
                    assistantMsgCount++;
                    if (assistantMsgCount > FULL_RDR_LIMIT && msg.rdr) {
                        // Drop heavy parts of RDR like raw traces/prompts, keep summary
                        msg.rdr = {
                            total_ms: msg.rdr.total_ms,
                            intent: msg.rdr.intent,
                            model_id: msg.rdr.model_id,
                            is_summary_only: true
                        };
                    }
                }
            }
        });
    }

    _aggressivePrune() {
        // Drop oldest 25% of sessions
        const toDrop = Math.ceil(this.state.sessions.length * 0.25);
        this.state.sessions = this.state.sessions.slice(toDrop);
    }

    setUser(name, role) {
        this.state.user = { name, role };
        this.save();
    }

    createSession(title = 'New Session') {
        const id = Date.now().toString();
        const newSession = {
            id,
            title,
            createdAt: new Date().toISOString(),
            messages: []
        };
        this.state.sessions.unshift(newSession);
        this.state.activeSessionId = id;
        this.save();
        return newSession;
    }

    getActiveSession() {
        return this.state.sessions.find(s => s.id === this.state.activeSessionId);
    }

    setActiveSession(id) {
        this.state.activeSessionId = id;
        this.save();
    }

    deleteSession(id) {
        this.state.sessions = this.state.sessions.filter(s => s.id !== id);
        if (this.state.activeSessionId === id) {
            this.state.activeSessionId = this.state.sessions[0]?.id || null;
        }
        this.save();
    }

    addMessage(role, content, rdr = null, thought = null) {
        const session = this.getActiveSession();
        if (!session) return;

        const msg = {
            id: Date.now().toString(),
            role,
            content,
            rdr,
            thought,
            timestamp: new Date().toISOString()
        };
        session.messages.push(msg);

        // Update session title if it's the first message
        if (session.messages.filter(m => m.role === 'user').length === 1 && role === 'user') {
            session.title = content.substring(0, 30) + (content.length > 30 ? '...' : '');
        }

        this.save();
        return msg;
    }
}

// Global instance
const atlasState = new StateManager();
