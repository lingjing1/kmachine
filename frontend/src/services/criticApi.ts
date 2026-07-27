/**
 * Critic Evaluation API Helper Functions
 * 
 * This module provides utility functions for interacting with the Critic evaluation APIs.
 * 
 * BACKEND REQUIREMENT:
 * - POST /api/v1/evaluate (✅ Already exists) - Trigger evaluation
 * - GET /api/v1/jobs/{jobId}/evaluations (❌ NEEDS TO BE IMPLEMENTED) - Fetch evaluation results
 * 
 * See: backend_api_requirements.md for implementation details
 */

import authClient from './authClient';

// === Type Definitions ===

export interface CriticEvaluation {
    evaluation_stage: 2 | 3 | 4; // fact_only, quality_only, fact_then_quality
    is_passed: boolean;
    feedback_for_generator: {
        summary?: string;
        overall_feedback?: string;
        question_feedback?: Array<{
            question_id: number;
            question_number: number;
            issue_type: string;
            description: string;
            severity: 'high' | 'medium' | 'low';
            suggestion: string;
        }>;
        rubric_scores?: Array<{
            rubric_name: string;
            score: number;
            max_score: number;
            feedback: string;
        }>;
    };
    metric_details: {
        faithfulness_score?: number;
        task_satisfaction_score?: number;
        geval_scores?: Record<string, number>;
    };
    evaluated_at: string;
}

export interface EvaluationResponse {
    job_id: number;
    status: string;
    critic_workflow: number;
    workflow_name: string;
    evaluation: {
        overall_passed: boolean;
        fact_critic?: {
            passed: boolean;
            faithfulness: {
                score: number;
                raw_score: number;
                analysis: string;
                suggestions: string[];
            };
            task_satisfaction: {
                score: number;
                task_type: string;
                checks: any[];
                analysis: string;
                suggestions: string[];
            };
        };
        quality_critic?: {
            passed: boolean;
            evaluations: Array<{
                rubric_name: string;
                rating: number;
                feedback: string;
                analysis?: string;
                suggestions?: string[];
            }>;
        };
    };
    duration_ms: number;
    saved?: {
        evaluation_task_id: number;
        task_evaluation_id: number;
    };
    evaluated_at?: string;
}

export interface QuestionCriticState {
    questionId: number;
    hasFeedback: boolean;
    feedbackSummary: string;
    severity: 'high' | 'medium' | 'low';
}

// === API Functions ===

/**
 * Fetch critic evaluations for a specific job
 * 
 * ⚠️ BACKEND REQUIREMENT: This function requires a GET endpoint that doesn't exist yet.
 * 
 * Required endpoint: GET /api/v1/jobs/{jobId}/evaluations
 * 
 * Expected response:
 * {
 *   "job_id": 123,
 *   "has_evaluations": true,
 *   "evaluations": [...]
 * }
 * 
 * See backend_api_requirements.md for full specification.
 */
export async function fetchCriticEvaluations(jobId: number): Promise<EvaluationResponse | null> {
    try {
        const data = await authClient.get<any>(`/api/v1/jobs/${jobId}/evaluations`);

        if (!data.has_evaluations || !data.evaluations || data.evaluations.length === 0) {
            return null;
        }

        // Return the most recent evaluation, mapped to EvaluationResponse structure if needed.
        // The backend returns an array of evaluation records.
        // Return the most recent evaluation, mapped to EvaluationResponse structure
        const latest = data.evaluations[0] as EvaluationResponse;
        
        // The backend now returns the exact structure of EvaluationResponse
        return {
            ...latest,
            status: 'completed'
        };

    } catch (error) {
        console.error('Failed to fetch critic evaluations:', error);
        return null;
    }
}

/**
 * Trigger a new critic evaluation (Asynchronous)
 */
export async function triggerCriticEvaluation(
    jobId: number,
    workflow: number = 4,
    mode: string = 'quick'
): Promise<EvaluationResponse | null | any> {
    try {
        console.log(`[criticApi] Triggering evaluation for job ${jobId}, workflow ${workflow}`);
        
        // 1. Get current latest evaluation (if any) to avoid polling catching old data
        const currentEvaluations = await fetchEvaluationHistory(jobId);
        const lastCreatedId = currentEvaluations.length > 0 ? (currentEvaluations[0].saved?.task_evaluation_id || currentEvaluations[0].evaluated_at) : null;

        // 2. Initial trigger request
        const response = await authClient.post<any>('/api/v1/evaluate', { 
            job_id: jobId, 
            critic_workflow: workflow, 
            mode 
        });

        // 3. Start polling for results
        if (response && (response.status === 'started' || response.job_id)) {
            console.log(`[criticApi] Evaluation started for job ${jobId}, polling for new result (after ${lastCreatedId})...`);
            return await pollEvaluationStatus(jobId, lastCreatedId);
        }

        return response;
    } catch (error) {
        console.error('Failed to trigger critic evaluation:', error);
        throw error;
    }
}

/**
 * Fetch full evaluation history for a job
 */
export async function fetchEvaluationHistory(jobId: number): Promise<EvaluationResponse[]> {
    try {
        const data = await authClient.get<any>(`/api/v1/jobs/${jobId}/evaluations`);
        if (!data.has_evaluations) return [];

        return data.evaluations.map((latest: any) => ({
            ...latest,
            status: 'completed'
        }));
    } catch (error) {
        console.error('Failed to fetch evaluation history:', error);
        return [];
    }
}

/**
 * Poll for evaluation status
 */
export async function pollEvaluationStatus(
    jobId: number,
    lastCreatedMarker: string | number | null = null,
    maxAttempts: number = 60, // 120 seconds total
    intervalMs: number = 2000
): Promise<EvaluationResponse | null> {
    console.log(`[criticApi] Polling status for job ${jobId}, waiting for record newer than ${lastCreatedMarker}...`);
    
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
        try {
            const evaluation = await fetchCriticEvaluations(jobId);

            if (evaluation) {
                const currentMarker = evaluation.saved?.task_evaluation_id || evaluation.evaluated_at;
                
                // If we have a marker for the previous evaluation, ensure this one is different/newer
                if (lastCreatedMarker && currentMarker === lastCreatedMarker) {
                    console.log(`[criticApi] Attempt ${attempt}: Still seeing old evaluation record, continuing poll...`);
                } else {
                    console.log(`[criticApi] New evaluation found for job ${jobId} (ID: ${currentMarker})`);
                    return evaluation;
                }
            }
        } catch (err) {
            console.warn(`[criticApi] Polling attempt ${attempt} failed:`, err);
        }

        // Wait before next attempt
        await new Promise(resolve => setTimeout(resolve, attempt < 5 ? 1000 : intervalMs)); // Poll faster at first
    }

    console.error(`[criticApi] Polling timed out for job ${jobId} after ${maxAttempts} attempts`);
    return null; // Timeout
}

/**
 * Parse evaluation results to extract question-level feedback
 */
export function parseQuestionCritics(
    evaluation: EvaluationResponse | null
): QuestionCriticState[] {
    if (!evaluation || !evaluation.evaluation) {
        return [];
    }

    const questionCritics: QuestionCriticState[] = [];

    // Extract from quality critic evaluations
    const qualityCritic = evaluation.evaluation.quality_critic;
    if (qualityCritic && qualityCritic.evaluations) {
        qualityCritic.evaluations.forEach((rubricEval, index) => {
            // Determine severity based on rating
            let severity: 'high' | 'medium' | 'low' = 'low';
            if (rubricEval.rating < 3) severity = 'high';
            else if (rubricEval.rating < 4) severity = 'medium';

            questionCritics.push({
                questionId: index + 1, // Assuming sequential numbering
                hasFeedback: rubricEval.rating < 4, // Only show feedback if below threshold
                feedbackSummary: rubricEval.analysis || (rubricEval as any).feedback || "",
                severity: severity,
            });
        });
    }

    return questionCritics;
}

/**
 * Calculate content statistics
 */
export function calculateContentStats(content: any): {
    wordCount: number;
    readingTime: number;
    paragraphCount: number;
    questionCount?: number;
} {
    let wordCount = 0;
    let paragraphCount = 0;
    let questionCount = 0;

    const countText = (text: string) => {
        if (!text) return;
        // Count Chinese characters and English words
        const chineseChars = (text.match(/[\u4e00-\u9fa5]/g) || []).length;
        const englishWords = (text.match(/[a-zA-Z]+/g) || []).length;
        wordCount += chineseChars + englishWords;
    };

    const processContent = (item: any) => {
        if (typeof item === 'string') {
            countText(item);
            paragraphCount++;
        } else if (Array.isArray(item)) {
            item.forEach(processContent);
        } else if (typeof item === 'object' && item !== null) {
            // Check if it's a question
            if (item.question_text) {
                questionCount++;
                countText(item.question_text);
            }

            // Process nested content
            Object.values(item).forEach(value => {
                if (typeof value === 'string') {
                    countText(value);
                } else if (Array.isArray(value) || typeof value === 'object') {
                    processContent(value);
                }
            });

            if (item.title || item.content) {
                paragraphCount++;
            }
        }
    };

    processContent(content);

    // Calculate reading time (assuming 300 words per minute for Chinese)
    const readingTime = Math.ceil(wordCount / 300);

    return {
        wordCount,
        readingTime,
        paragraphCount,
        questionCount: questionCount > 0 ? questionCount : undefined,
    };
}
