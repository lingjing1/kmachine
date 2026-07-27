// frontend/src/services/generatorLogApi.ts
import { authClient } from './authClient';

export interface GeneratorLogRequest {
    session_id: string;
    job_id?: number | null;
    action_config?: Record<string, any>;
    duration_sec?: number;
}

/**
 * Record teacher actions on the Generator Settings page.
 */
export async function submitGeneratorLog(payload: GeneratorLogRequest): Promise<void> {
    try {
        await authClient.post('/api/v1/teacher/generator-logs', payload);
    } catch (err) {
        // We use console.warn for logging errors to avoid disrupting user experience
        console.warn('[Log] Error submitting generator log:', err);
    }
}
