// import { produce } from 'immer'; // Unused


// === Types ===
export interface QuestionTypeGrading {
    type_id: string;
    type_name: string;
    question_count: number;
    points_per_question: number;
    total_points: number;
    auto_gradable: boolean;
}

export interface IndividualQuestionGradingItem {
    question_id: string | number;
    question_type: string;
    points: number;
    auto_gradable: boolean;
    text?: string;
    path?: any[]; // Path to question in content structure
}

export interface GradingConfig {
    total_points: number;
    grading_method: 'by_question_type' | 'by_individual_question';
    question_types: QuestionTypeGrading[];
    individual_questions: IndividualQuestionGradingItem[];
}

export interface ValidationResult {
    isValid: boolean;
    errors: string[];
}

export const QUESTION_TYPE_NAMES: Record<string, string> = {
    'multiple_choice': '選擇題',
    'short_answer': '簡答題',
    'true_false': '是非題',
    'essay': '申論題',
    'fill_in_blank': '填空題',
    'fill_in_the_blank': '填空題', // Keep for backward compatibility
    'unknown': '未分類'
};

// === Helper Functions ===

export const parseQuestionsFromContent = (content: any): { types: QuestionTypeGrading[]; questions: IndividualQuestionGradingItem[] } => {
    let rawItems: any[] = [];

    // Normalize content
    if (content) {
        if (content.type === 'exam_questions' && Array.isArray(content.content)) {
            rawItems = content.content;
        } else if (content.display_type === 'exam_questions' && Array.isArray(content.content)) {
            rawItems = content.content;
        } else if (typeof content === 'object' && content.content && !Array.isArray(content.content)) {
            if (Array.isArray(content.content.content)) {
                rawItems = content.content.content;
            } else {
                rawItems = [content.content];
            }
        } else if (Array.isArray(content.content)) {
            rawItems = content.content;
        } else if (Array.isArray(content)) {
            rawItems = content;
        } else if (typeof content === 'object') {
            rawItems = [content];
        }
    }

    const typeMap = new Map<string, QuestionTypeGrading>();
    const individualQuestions: IndividualQuestionGradingItem[] = [];

    let qIndex = 1;

    // Flatten and Process
    rawItems.forEach((item, idx) => {
        if (item.type === 'section_header' || item.question_type === 'section_header') return;

        if (item.questions && Array.isArray(item.questions)) {
            // Block
            const blockType = item.type || item.question_type || 'unknown';
            item.questions.forEach((q: any, qIdx: number) => {
                const combinedType = q.type || q.question_type || blockType;
                processQuestion(q, combinedType, [idx, qIdx]);
            });
        } else {
            // Flat item
            const type = item.type || item.question_type || 'unknown';
            processQuestion(item, type, [idx]);
        }
    });

    function processQuestion(q: any, typeId: string, path: any[]) {
        if (typeId === 'section_header' || typeId === 'instruction_block') return;

        // Prioritize explicit question text fields
        let contentText = q.question_text || q.text || q.stem || q.title || '';

        // Remove the old fallback logic that used options/JSON stringification
        // User wants "無題目內容" if text is missing, which the UI handles if we return empty string here.
        // We do NOT want to show options A,B,C,D or "true/false" as the question title.
        if (typeof contentText !== 'string') contentText = '';

        if (typeId === 'unknown' && !contentText && !q.question_type) return;
        if (typeId === 'choice') typeId = 'multiple_choice';

        const typeName = QUESTION_TYPE_NAMES[typeId] || ((contentText && contentText.length > 0) ? '其它題型' : typeId);

        // Update Type Map
        if (!typeMap.has(typeId)) {
            typeMap.set(typeId, {
                type_id: typeId,
                type_name: typeName,
                question_count: 0,
                points_per_question: 0,
                total_points: 0,
                auto_gradable: ['multiple_choice', 'true_false', 'fill_in_the_blank', 'fill_in_blank'].includes(typeId)
            });
        }
        const existing = typeMap.get(typeId)!;
        existing.question_count++;

        // Add to Individual
        individualQuestions.push({
            question_id: qIndex++,
            question_type: typeId,
            points: 0,
            auto_gradable: ['multiple_choice', 'true_false', 'fill_in_the_blank', 'fill_in_blank'].includes(typeId),
            text: contentText,
            path: path
        });
    }

    return {
        types: Array.from(typeMap.values()),
        questions: individualQuestions
    };
};

// Smart Distribution Logic
// - Distributes total_points equally among questions
// - Adds REMAINDER to the LAST question
export const distributePoints = (
    questions: IndividualQuestionGradingItem[],
    totalPoints: number = 100
): { questions: IndividualQuestionGradingItem[], types: QuestionTypeGrading[] } => {
    const totalQuestions = questions.length;
    if (totalQuestions === 0) return { questions: [], types: [] };

    const basePoints = Math.floor(totalPoints / totalQuestions);
    const remainder = totalPoints % totalQuestions;

    // Identify the last valid question index to add remainder
    const lastIdx = totalQuestions - 1;

    // Distribute to individuals
    const newQuestions = questions.map((q, idx) => {
        let points = basePoints;
        // Add ALL remainder to the LAST question
        if (idx === lastIdx) {
            points += remainder;
        }
        return { ...q, points };
    });

    // Re-aggregate to types for consistency
    const typeMap = new Map<string, QuestionTypeGrading>();
    newQuestions.forEach(q => {
        const typeName = QUESTION_TYPE_NAMES[q.question_type] || '其它題型';
        if (!typeMap.has(q.question_type)) {
            typeMap.set(q.question_type, {
                type_id: q.question_type,
                type_name: typeName,
                question_count: 0,
                points_per_question: 0, // Will vary if we dump remainder to last question
                total_points: 0,
                auto_gradable: q.auto_gradable
            });
        }
        const t = typeMap.get(q.question_type)!;
        t.question_count++;
        t.total_points += q.points;
    });

    // For types, points_per_question is tricky if they vary. 
    // We'll set it to average or 0 if mixed. 
    // But UI might expect integer. Let's just set it to base if consistent, else marked as mixed?
    // For now, simple logic: total / count
    const newTypes = Array.from(typeMap.values()).map(t => ({
        ...t,
        // Use floor to avoid decimals in the type summary. 
        // Note: If using 'by_question_type' mode, this might result in total < 100 (e.g. 33*3=99).
        // The UI should warn the user, or we switch to 'by_individual_question' mode.
        points_per_question: t.question_count > 0 ? Math.floor(t.total_points / t.question_count) : 0
    }));

    return { questions: newQuestions, types: newTypes };
};
