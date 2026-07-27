import React, { useState, useEffect, forwardRef, useImperativeHandle, useRef } from 'react';
import ConfirmDialog from './ConfirmDialog';
import { GradingConfig } from '../../utils/grading';
import { SummaryContentView, SummaryContentViewRef } from '../reports/SummaryContentView';
import { ExamContentView } from '../reports/ExamContentView';

interface ContentRendererProps {
    content: any;
    editable?: boolean;
    onContentChange?: (newContent: any[]) => void;
    gradingConfig?: GradingConfig;
    onScoreChange?: (questionIndex: number, newScore: number) => void;
    onReferenceClick?: (chunkId: number | string, evidence: string, matchScore?: number, fullChunk?: any, questionId?: number, refType?: 'question' | 'section') => void;
    onAddToBank?: (idx: number, question: any) => void;
    onRemoveFromBank?: (idx: number, id: number) => void;
    onEditBankQuestion?: (idx: number, question: any) => void;
    onSaveComplete?: (idx: number, updatedQuestion: any) => void;
    focusIndex?: number | null;
    autoEditIndex?: number | null;
    availableKPs?: Array<{ id: string | number; name: string; category?: string; source_name?: string }>;
    onCancelEdit?: (idx: number) => void;
    courseId?: number | string;
    unitId?: number | string;
    contentId?: number | string;
    isTeacher?: boolean;
    onKPLookup?: (kpName: string) => void;
    onAddKP?: (name: string) => Promise<{ id: string | number; name: string } | null>;
}

export interface ContentRendererRef {
    startEditing: (idx: number) => void;
    stopEditing: () => void;
    getPendingContent: () => any | null;
}

export const ContentRenderer = forwardRef(({
    content,
    editable = false,
    onContentChange,
    gradingConfig,
    onScoreChange,
    onReferenceClick,
    onAddToBank,
    onRemoveFromBank,
    onEditBankQuestion,
    onSaveComplete,
    focusIndex,
    autoEditIndex,
    availableKPs = [],
    onCancelEdit,
    courseId,
    unitId,
    contentId,
    isTeacher = false,
    onKPLookup,
    onAddKP
}: ContentRendererProps, ref: React.Ref<ContentRendererRef>) => {
    const [editingId, setEditingId] = useState<number | null>(null);
    const [tempQuestion, setTempQuestion] = useState<any>(null);
    const summaryRef = useRef<SummaryContentViewRef>(null);
    const [deleteTargetIndex, setDeleteTargetIndex] = useState<number | null>(null);
    const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

    // Scroll to focused item
    useEffect(() => {
        if (typeof focusIndex === 'number' && focusIndex >= 0) {
            setTimeout(() => {
                const el = document.getElementById(`question-item-${focusIndex}`);
                if (el) {
                    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    el.classList.add('ring-2', 'ring-blue-400');
                    setTimeout(() => el.classList.remove('ring-2', 'ring-blue-400'), 800);
                }
            }, 100);
        }
    }, [focusIndex]);

    // Auto-edit newly added questions
    useEffect(() => {
        if (typeof autoEditIndex === 'number' && autoEditIndex >= 0 && editable) {
            setTimeout(() => {
                if (flatItems[autoEditIndex]) {
                    startEditing(autoEditIndex, flatItems[autoEditIndex]);
                }
            }, 200);
        }
    }, [autoEditIndex, editable]);

    if (!content) return <div className="text-gray-500">無內容</div>;

    // Normalize content structure to a flat list
    let flatItems: any[] = [];

    if (content) {
        let rawItems: any[] = [];
        if (content.type === 'exam_questions' && Array.isArray(content.content)) {
            rawItems = content.content;
        } else if (content.display_type === 'exam_questions' && Array.isArray(content.content)) {
            rawItems = content.content;
        } else if (typeof content === 'object' && content.content && !Array.isArray(content.content)) {
            rawItems = [content.content];
        } else if (Array.isArray(content.content)) {
            rawItems = content.content;
        } else if (Array.isArray(content)) {
            rawItems = content;
        }

        rawItems.forEach((item: any) => {
            if (item.questions && Array.isArray(item.questions)) {
                const type = item.type || item.question_type || 'unknown';
                item.questions.forEach((q: any) => {
                    flatItems.push({
                        ...q,
                        type: q.type || q.question_type || type,
                        question_type: q.question_type || type
                    });
                });
            } else {
                flatItems.push(item);
            }
        });
    }

    const wrapUpdatedContent = (newItems: any[]) => {
        if (Array.isArray(content)) {
            return newItems;
        }

        if (content && typeof content === 'object') {
            // Priority 1: content.content is an array
            if (Array.isArray(content.content)) {
                return { ...content, content: newItems };
            }

            // Priority 2: content.content is a single object (lifted up)
            if (content.content && !Array.isArray(content.content)) {
                return { ...content, content: newItems[0] };
            }

            // Priority 3: Fallback - just set content property
            return { ...content, content: newItems };
        }

        return newItems;
    };

    useImperativeHandle(ref, () => ({
        startEditing: (idx: number) => {
            if (idx === 0 && (content.type === 'summary' || content.type === 'summary_report' || content.display_type === 'summary_report')) {
                setEditingId(0);
                return;
            }
            if (flatItems[idx]) {
                startEditing(idx, flatItems[idx]);
            }
        },
        stopEditing: () => {
            setEditingId(null);
            setTempQuestion(null);
        },
        getPendingContent: () => {
            if (editingId === 0 && summaryRef.current) {
                return summaryRef.current.getPendingContent();
            }
            if (editingId !== null && tempQuestion) {
                const newItems = [...flatItems];
                newItems[editingId] = tempQuestion;
                return wrapUpdatedContent(newItems);
            }
            return null;
        }
    }), [editingId, tempQuestion, flatItems, content]);

    const startEditing = (idx: number, question: any) => {
        // [Auto-Save] If already editing another item, save it before switching to avoid data loss
        if (editingId !== null && editingId !== idx && tempQuestion && onContentChange) {
            const newItems = [...flatItems];
            newItems[editingId] = tempQuestion;
            onContentChange(wrapUpdatedContent(newItems));
            onSaveComplete?.(editingId, tempQuestion);
        }

        console.log('[ContentRenderer] startEditing called', idx);
        setEditingId(idx);
        setTempQuestion(JSON.parse(JSON.stringify(question)));
    };

    const cancelEditing = () => {
        console.log('[ContentRenderer] cancelEditing called', editingId);
        console.trace('[ContentRenderer] cancelEditing trace');
        if (editingId !== null && onCancelEdit) {
            console.log('[ContentRenderer] invoking onCancelEdit prop', editingId);
            onCancelEdit(editingId);
        }
        setEditingId(null);
        setTempQuestion(null);
    };

    const saveEditing = (idx: number) => {
        if (!onContentChange || !tempQuestion) return;

        const newItems = [...flatItems];
        newItems[idx] = tempQuestion;

        onContentChange(wrapUpdatedContent(newItems));

        setEditingId(null);
        setTempQuestion(null);

        onSaveComplete?.(idx, tempQuestion);
    };

    const handleTempChange = (field: string, value: any) => {
        setTempQuestion((prev: any) => ({ ...prev, [field]: value }));
    };

    const handleTempOptionChange = (optKey: string, value: string) => {
        setTempQuestion((prev: any) => ({
            ...prev,
            options: {
                ...prev.options,
                [optKey]: value
            }
        }));
    };

    const moveQuestion = (idx: number, direction: 'up' | 'down') => {
        if (!onContentChange) return;
        const newItems = [...flatItems];

        if (direction === 'up' && idx > 0) {
            [newItems[idx], newItems[idx - 1]] = [newItems[idx - 1], newItems[idx]];
        } else if (direction === 'down' && idx < newItems.length - 1) {
            [newItems[idx], newItems[idx + 1]] = [newItems[idx + 1], newItems[idx]];
        }

        let newContent = { ...content, content: newItems };
        onContentChange(newContent);
    };

    const deleteQuestion = (idx: number) => {
        if (!onContentChange) return;
        setDeleteTargetIndex(idx);
        setShowDeleteConfirm(true);
    };

    const handleConfirmDelete = () => {
        if (deleteTargetIndex === null || !onContentChange) return;

        const newItems = [...flatItems];
        newItems.splice(deleteTargetIndex, 1);

        onContentChange(wrapUpdatedContent(newItems));

        setShowDeleteConfirm(false);
        setDeleteTargetIndex(null);
    };

    // Calculate display indices (skip non-questions)
    let qCounter = 0;
    const itemIndices = flatItems.map(item => {
        if ((item.type === 'section_header') || (!item.question_text && item.title)) return null;
        return ++qCounter;
    });

    // Special handling for summary/summary_report type
    if (content.type === 'summary_report' || content.display_type === 'summary_report' || content.type === 'summary') {
        return (
            <div className="relative">
                <SummaryContentView
                    ref={summaryRef}
                    summary={content}
                    materialType={content.material_type || 'preview'}
                    editable={editable}
                    isEditing={editingId === 0}
                    onStartEdit={() => setEditingId(0)}
                    onSaveEdit={() => setEditingId(null)}
                    onCancelEdit={() => setEditingId(null)}
                    onContentChange={(newSummary) => {
                        if (onContentChange) {
                            onContentChange({ ...content, ...newSummary });
                        }
                    }}
                    onReferenceClick={onReferenceClick}
                    availableKPs={availableKPs}

                    courseId={courseId}
                    unitId={unitId}
                    contentId={contentId || (content as any).id}
                    isTeacher={isTeacher}
                    onKPLookup={onKPLookup}
                    onAddKP={onAddKP}
                />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {flatItems.map((q: any, idx: number) => {
                const type = q.type || q.question_type || 'unknown';

                // Summary content block
                if (type === 'summary' || type === 'summary_report' || q.display_type === 'summary_report') {
                    return (
                        <div key={idx} className="relative">
                            <SummaryContentView
                                summary={q}
                                materialType={q.material_type || 'preview'}
                                editable={editable}
                                isEditing={editingId === idx}
                                onStartEdit={() => setEditingId(idx)}
                                onSaveEdit={() => setEditingId(null)}
                                onCancelEdit={() => setEditingId(null)}
                                onContentChange={(updates) => {
                                    if (editingId !== null) {
                                        // 編輯模式下，暫存到 tempQuestion
                                        if (updates.sections || updates.content) {
                                            handleTempChange('sections', updates.sections || updates.content);
                                        }
                                        if (updates.recommendation_config) {
                                            handleTempChange('recommendation_config', updates.recommendation_config);
                                        }
                                    } else if (onContentChange) {
                                        // 非編輯模式下，直接調用外部更新介面
                                        const updatedContent = { ...q };
                                        if (updates.sections || updates.content) {
                                            updatedContent.sections = updates.sections || updates.content;
                                        }
                                        if (updates.recommendation_config) {
                                            updatedContent.recommendation_config = updates.recommendation_config;
                                        }
                                        const newItems = [...flatItems];
                                        newItems[idx] = updatedContent;
                                        onContentChange(wrapUpdatedContent(newItems));
                                    }
                                }}
                                onReferenceClick={onReferenceClick}
                                availableKPs={availableKPs}

                                courseId={courseId}
                                unitId={unitId}
                                contentId={contentId || (q as any).id}
                                isTeacher={isTeacher}
                                onKPLookup={onKPLookup}
                                onAddKP={onAddKP}
                            />
                        </div>
                    );
                }

                // Section header block
                if (type === 'section_header' || (!q.question_text && q.title)) {
                    return (
                        <div key={idx} className="bg-white p-6 rounded-lg border border-neutral-border shadow-sm">
                            <h4 className="text-lg font-bold text-neutral-text-main mb-4 pb-2 border-b border-gray-100">{q.title}</h4>
                            {q.content && (
                                <div className="prose prose-sm max-w-none text-neutral-text-secondary whitespace-pre-wrap">
                                    {typeof q.content === 'string' || typeof q.content === 'number'
                                        ? q.content
                                        : (Array.isArray(q.content) || typeof q.content === 'object'
                                            ? <pre className="text-xs bg-gray-50 p-2 rounded">{JSON.stringify(q.content, null, 2)}</pre>
                                            : '')}
                                </div>
                            )}
                        </div>
                    );
                }

                // Exam question - delegate to ExamContentView
                return (
                    <ExamContentView
                        key={idx}
                        question={q}
                        index={idx}
                        displayNumber={itemIndices[idx]}
                        editable={editable}
                        isEditing={editingId === idx}
                        tempQuestion={editingId === idx ? tempQuestion : undefined}
                        onStartEdit={startEditing}
                        onSaveEdit={saveEditing}
                        onCancelEdit={cancelEditing}
                        onTempChange={handleTempChange}
                        onTempOptionChange={handleTempOptionChange}
                        onMoveUp={(idx) => moveQuestion(idx, 'up')}
                        onMoveDown={(idx) => moveQuestion(idx, 'down')}
                        onDelete={deleteQuestion}
                        onAddToBank={onAddToBank}
                        onRemoveFromBank={onRemoveFromBank}
                        onEditBankQuestion={onEditBankQuestion}
                        gradingConfig={gradingConfig}
                        onScoreChange={onScoreChange}
                        onReferenceClick={onReferenceClick}
                        isFirstItem={idx === 0}
                        isLastItem={idx === flatItems.length - 1}
                        availableKPs={availableKPs}
                        onKPLookup={onKPLookup}
                        onAddKP={onAddKP}
                    />
                );
            })}

            {/* Delete Confirmation Dialog */}
            <ConfirmDialog
                isOpen={showDeleteConfirm}
                onConfirm={handleConfirmDelete}
                onCancel={() => setShowDeleteConfirm(false)}
                title="確認刪除"
                message="確定要刪除此題目嗎？"
            />
        </div>
    );
});
