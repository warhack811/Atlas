/**
 * ATLAS UI Utilities Module
 * Helper functions for formatting and DOM manipulation.
 */

const utils = {
    formatTime: (isoString) => {
        const date = new Date(isoString);
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    },

    escapeHtml: (unsafe) => {
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    },

    debounce: (func, wait) => {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    // Safely parse JSON or return null
    safeParse: (str) => {
        try {
            return JSON.parse(str);
        } catch (e) {
            return null;
        }
    },

    // Create a unique element ID
    uuid: () => {
        return Math.random().toString(36).substring(2, 11);
    }
};
