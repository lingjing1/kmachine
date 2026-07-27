/**
 * Formats a date string from the backend (Taipei time) for display.
 * Since the backend already provides the time in Taipei timezone and we want to
 * "take it directly without any action", we simply format the string.
 */
export const formatDateTime = (dateStr: string | null | undefined): string => {
    if (!dateStr) return '';

    try {
        // If it's an ISO string (contains T), normalize it
        const normalized = dateStr.replace('T', ' ');
        // Remove milliseconds and any trailing Z or timezone offset if present
        const clean = normalized.split('.')[0].replace('Z', '').split('+')[0];
        return clean;
    } catch (e) {
        return dateStr || '';
    }
};

/**
 * Alternative that uses Date but ensures we just want the components as they are.
 * This is safer for different input formats but keeps the "naive" feel.
 */
export const formatDateOnly = (dateStr: string | null | undefined): string => {
    if (!dateStr) return '';
    return dateStr.split('T')[0].split(' ')[0];
};
