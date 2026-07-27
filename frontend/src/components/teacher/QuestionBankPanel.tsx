import React, { useState, useEffect, useRef, forwardRef, useImperativeHandle } from 'react';
import API_BASE_URL from '../../config/api';
import { FaFilter, FaSort, FaSearch, FaCheck, FaArchive, FaUndo, FaBoxOpen } from 'react-icons/fa';
import Modal from '../common/Modal';
import Button from '../common/Button';
import ConfirmDialog from '../common/ConfirmDialog';
import ReactMarkdown from 'react-markdown';

export interface QuestionBankItem {
    id: number;
    course_id: number;
    creator_id: number;
    title: string;
    description: string | null;
    question_data: any;
    question_type: string;
    difficulty_level: string | null;
    estimated_time_minutes: number | null;
    tags: string[] | null;
    times_used: number;
    average_score: number | null;
    is_published: boolean;
    created_at: string;
    updated_at: string;
    unit_id?: number;
    kp_id?: number;
    unit_name?: string;
    topic_id?: number;
    kp_name?: string;
}

export interface QuestionBankPanelRef {
    reload: () => void;
}

interface QuestionBankPanelProps {
    courseId: string;
    selectedQuestionIds: number[];
    onQuestionToggle: (question: QuestionBankItem, forceToggle?: boolean) => void;
    onBatchSelect?: (questions: QuestionBankItem[]) => void;
}

// Helper dropdown component
const CustomDropdown = ({
    value,
    onChange,
    options,
    icon,
    placeholder
}: {
    value: string;
    onChange: (val: string) => void;
    options: { value: string; label: string }[];
    icon: React.ReactNode;
    placeholder: string;
}) => {
    const [isOpen, setIsOpen] = useState(false);
    const ref = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (ref.current && !ref.current.contains(event.target as Node)) {
                setIsOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const selectedLabel = options.find(o => o.value === value)?.label || placeholder;

    return (
        <div className="relative shrink-0" ref={ref}>
            <button
                onClick={() => setIsOpen(!isOpen)}
                className={`flex items-center gap-2 px-3 py-1.5 border rounded-lg text-xs font-medium bg-white transition-all ${isOpen ? 'border-gray-400 ring-2 ring-gray-100' : 'border-gray-200 hover:bg-gray-50'
                    } ${value ? 'text-gray-800' : 'text-gray-500'}`}
            >
                <span className="truncate max-w-[150px]">{selectedLabel}</span>
                <span className="text-gray-400 text-[10px]">{icon}</span>
            </button>

            {isOpen && (
                <div className="absolute top-full left-0 mt-1 min-w-[160px] max-h-60 overflow-y-auto bg-white border border-gray-200 rounded-lg shadow-lg z-50 py-1">
                    <div
                        className={`px-3 py-2 text-xs cursor-pointer hover:bg-gray-50 text-gray-500 ${!value ? 'bg-gray-50 font-bold' : ''}`}
                        onClick={() => { onChange(''); setIsOpen(false); }}
                    >
                        {placeholder}
                    </div>
                    {options.map(opt => (
                        <div
                            key={opt.value}
                            className={`px-3 py-2 text-xs cursor-pointer hover:bg-gray-50 text-gray-700 ${value === opt.value ? 'bg-blue-50 text-blue-600 font-bold' : ''}`}
                            onClick={() => { onChange(opt.value); setIsOpen(false); }}
                        >
                            {opt.label}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};

const QuestionBankPanel = forwardRef<QuestionBankPanelRef, QuestionBankPanelProps>(({
    courseId,
    selectedQuestionIds,
    onQuestionToggle,
}, ref) => {
    // State
    const [activeQuestions, setActiveQuestions] = useState<QuestionBankItem[]>([]);
    const [archivedQuestions, setArchivedQuestions] = useState<QuestionBankItem[]>([]);

    // Loading states
    const [activeLoading, setActiveLoading] = useState(true);
    const [archivedLoading, setArchivedLoading] = useState(true);

    const [viewMode, setViewMode] = useState<'active' | 'archived'>('active'); // active, archived

    // Filters
    const [searchQuery, setSearchQuery] = useState('');
    const [filterType, setFilterType] = useState('');
    const [filterDifficulty, setFilterDifficulty] = useState('');
    const [filterKP, setFilterKP] = useState('');
    // Sort removed as per request, defaulting to created_desc in logic if needed or just letting backend handle default
    const [sortBy] = useState('created_desc');
    const [availableKPs, setAvailableKPs] = useState<any[]>([]);

    // Pagination
    const [currentPage] = useState(1);
    const [perPage] = useState(1000);

    // Initial Delete Modal State
    const [deleteModal, setDeleteModal] = useState<{
        isOpen: boolean;
        question: QuestionBankItem | null;
    }>({
        isOpen: false,
        question: null
    });

    // Confirm Dialog State (for other actions like Restore)
    const [confirmDialog, setConfirmDialog] = useState<{
        isOpen: boolean;
        title: string;
        message: string;
        confirmText: string;
        variant: 'warning' | 'danger';
        onConfirm: () => void;
    }>({
        isOpen: false,
        title: '',
        message: '',
        confirmText: '',
        variant: 'warning',
        onConfirm: () => { }
    });

    // Expose reload method
    useImperativeHandle(ref, () => ({
        reload: () => {
            loadQuestions();
        }
    }));

    // Load KPs on mount
    useEffect(() => {
        if (!courseId) return;
        fetch(`${API_BASE_URL}/api/courses/${courseId}/knowledge-points`)
            .then(res => res.ok ? res.json() : [])
            .then(data => setAvailableKPs(data))
            .catch(err => console.error("Failed to fetch KPs", err));
    }, [courseId]);

    // Load questions
    useEffect(() => {
        loadQuestions();
    }, [courseId, filterType, filterDifficulty, filterKP, searchQuery, sortBy, currentPage]);

    const loadQuestions = async () => {
        if (!courseId) return;

        setActiveLoading(true);
        setArchivedLoading(true);

        const params = new URLSearchParams({
            page: currentPage.toString(),
            per_page: perPage.toString(),
            sort: sortBy
        });

        if (filterType) params.append('question_type', filterType);
        if (filterDifficulty) params.append('difficulty', filterDifficulty);
        if (filterKP) params.append('kp_id', filterKP);
        if (searchQuery) params.append('search', searchQuery);

        // Fetch Active
        fetch(`${API_BASE_URL}/api/courses/${courseId}/question-bank?${params.toString()}`)
            .then(res => res.ok ? res.json() : [])
            .then(data => setActiveQuestions(data))
            .catch(err => console.error(err))
            .finally(() => setActiveLoading(false));

        // Fetch Archived
        fetch(`${API_BASE_URL}/api/courses/${courseId}/question-bank/archived?${params.toString()}`)
            .then(res => res.ok ? res.json() : [])
            .then(data => setArchivedQuestions(data))
            .catch(err => console.error(err))
            .finally(() => setArchivedLoading(false));
    };

    // Derived state for display
    const displayQuestions = viewMode === 'active' ? activeQuestions : archivedQuestions;
    const loading = viewMode === 'active' ? activeLoading : archivedLoading;

    const handleDeleteClick = (e: React.MouseEvent, q: QuestionBankItem) => {
        e.stopPropagation();
        setDeleteModal({
            isOpen: true,
            question: q
        });
    };



    const archiveQuestion = async (id: number) => {
        try {
            const res = await fetch(`${API_BASE_URL}/api/courses/${courseId}/question-bank/${id}/archive`, {
                method: 'POST'
            });
            if (res.ok) {
                loadQuestions();
            } else {
                alert('封存失敗');
            }
        } catch (error) {
            console.error(error);
            alert('封存失敗');
        }
    };

    const handleRestoreClick = (e: React.MouseEvent, id: number) => {
        e.stopPropagation();

        setConfirmDialog({
            isOpen: true,
            title: '恢復題目',
            message: '確定要從封存區恢復此題目嗎？\n題目將重新顯示於題庫列表中。',
            confirmText: '恢復',
            variant: 'warning',
            onConfirm: async () => {
                try {
                    const res = await fetch(`${API_BASE_URL}/api/courses/${courseId}/question-bank/${id}/restore`, {
                        method: 'POST'
                    });
                    if (res.ok) {
                        loadQuestions();
                    }
                } catch (error) {
                    console.error(error);
                    alert('恢復失敗');
                }
                setConfirmDialog(prev => ({ ...prev, isOpen: false }));
            }
        });
    };

    const typeLabels: Record<string, string> = {
        'multiple_choice': '選擇題',
        'short_answer': '簡答題',
        'true_false': '是非題',
        'fill_in_blank': '填充題',
        'matching': '配合題'
    };

    const difficultyLabels: Record<string, string> = {
        'easy': '簡單',
        'medium': '中等',
        'hard': '困難',
        'challenge': '挑戰'
    };


    return (
        <div className="h-full flex flex-col bg-white border-l border-gray-200 relative">
            {/* Header / Filter Area */}
            <div className="px-4 py-3 border-b border-gray-200 sticky top-0 bg-white z-20">
                {/* Search */}
                <div className="relative mb-2">
                    <FaSearch className="absolute left-3 top-1/2 transform -translate-y-1/2 text-blue-500" />
                    <input
                        type="text"
                        placeholder="搜尋題目..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="w-full pl-9 pr-3 py-2 border border-blue-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-100 focus:border-blue-400 outline-none text-blue-900 placeholder-blue-300 transition-all"
                    />
                </div>

                {/* Filters */}
                <div className="flex gap-2 flex-wrap items-center">
                    <CustomDropdown
                        value={filterType}
                        onChange={setFilterType}
                        options={[
                            { value: 'multiple_choice', label: '選擇題' },
                            { value: 'short_answer', label: '簡答題' },
                            { value: 'true_false', label: '是非題' },
                        ]}
                        icon={<FaFilter />}
                        placeholder="所有類型"
                    />

                    <CustomDropdown
                        value={filterDifficulty}
                        onChange={setFilterDifficulty}
                        options={[
                            { value: 'easy', label: '簡單' },
                            { value: 'medium', label: '中等' },
                            { value: 'hard', label: '困難' },
                            { value: 'challenge', label: '挑戰' },
                        ]}
                        icon={<FaSort />}
                        placeholder="所有難度"
                    />

                    {/* KP Filter */}
                    <CustomDropdown
                        value={filterKP}
                        onChange={setFilterKP}
                        options={availableKPs
                            .filter(kp => kp.id) // Only show KPs that have a real ID
                            .map(kp => ({ value: String(kp.id), label: kp.name }))
                        }
                        icon={<FaFilter />}
                        placeholder="知識點篩選"
                    />


                    {/* View Mode Toggle Button */}
                    <button
                        onClick={() => setViewMode(viewMode === 'active' ? 'archived' : 'active')}
                        className={`ml-auto px-3 py-1.5 rounded-lg text-xs font-bold border transition-all flex items-center gap-1.5 ${viewMode === 'active'
                            ? 'bg-gray-100 text-gray-600 border-gray-200 hover:bg-gray-200 hover:text-gray-800'
                            : 'bg-blue-50 text-blue-600 border-blue-200 hover:bg-blue-100'
                            }`}
                        title={viewMode === 'active' ? '前往封存區' : '返回題庫列表'}
                    >
                        {viewMode === 'active' ? (
                            <>
                                <FaArchive /> 封存區
                            </>
                        ) : (
                            <>
                                <FaBoxOpen /> 題庫列表
                            </>
                        )}
                    </button>
                </div>
            </div>

            {/* List */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-gray-50">
                {loading ? (
                    <div className="flex items-center justify-center py-10">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                    </div>
                ) : displayQuestions.length === 0 ? (
                    <div className="text-center py-10 text-gray-500 text-sm">
                        沒有找到符合的題目
                    </div>
                ) : (
                    displayQuestions.map((q) => {
                        const isSelected = selectedQuestionIds.includes(q.id);
                        return (
                            <div
                                key={q.id}
                                onClick={() => onQuestionToggle(q)}
                                className={`relative p-3 rounded-lg border transition-all cursor-pointer group ${isSelected
                                    ? 'bg-blue-50 border-blue-400 shadow-sm ring-1 ring-blue-400'
                                    : 'bg-white border-gray-200 hover:border-blue-300 hover:shadow-sm'
                                    }`}
                            >
                                {viewMode === 'active' ? (
                                    /* Active Actions Row (Vertical Stack) */
                                    <div className="absolute top-2 right-2 flex flex-col gap-1 z-10">
                                        {/* Selection Checkbox */}
                                        <div
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                onQuestionToggle(q, true); // Force toggle (remove if selected) instead of scroll
                                            }}
                                            className={`w-7 h-7 rounded-full flex items-center justify-center transition-all cursor-pointer ${isSelected
                                                ? 'bg-blue-500 text-white shadow-sm scale-110'
                                                : 'text-gray-300 hover:text-blue-400 hover:bg-blue-50'
                                                }`}
                                            title={isSelected ? "取消選擇" : "選擇題目"}
                                        >
                                            {isSelected ? <FaCheck size={12} /> : <div className="w-4 h-4 rounded border border-current" />}
                                        </div>

                                        {/* Archive Button */}
                                        <button
                                            onClick={(e) => handleDeleteClick(e, q)}
                                            className="w-7 h-7 rounded-full flex items-center justify-center transition-all text-gray-300 hover:text-orange-500 hover:bg-orange-50"
                                            title="封存題目"
                                        >
                                            <FaArchive size={12} />
                                        </button>
                                    </div>
                                ) : (
                                    /* Archived Actions Row (Vertical Stack) */
                                    <div className="absolute top-2 right-2 flex flex-col gap-1 z-10">
                                        <button
                                            onClick={(e) => handleRestoreClick(e, q.id)}
                                            className="w-7 h-7 rounded-full flex items-center justify-center text-gray-400 hover:text-green-600 hover:bg-green-50 transition-all display-flex gap-1"
                                            title="恢復題目"
                                        >
                                            <FaUndo size={12} />
                                        </button>
                                    </div>
                                )}


                                {/* Attributes & Tags (Single Flow, Reduced Right Padding) */}
                                <div className="flex flex-wrap items-center gap-2 mb-2 pr-12">
                                    {/* Type */}
                                    <span className="px-2 py-0.5 text-[10px] font-bold bg-blue-50 text-blue-600 rounded border border-blue-100 group-hover:bg-blue-100 group-hover:text-blue-700 group-hover:border-blue-200 transition-colors">
                                        {typeLabels[q.question_type] || q.question_type}
                                    </span>

                                    {/* Difficulty */}
                                    {q.difficulty_level && (
                                        <span className={`px-2 py-0.5 text-[10px] font-bold rounded border bg-blue-50 text-blue-600 border-blue-100 group-hover:bg-blue-100 group-hover:text-blue-700 group-hover:border-blue-200 transition-colors`}>
                                            {difficultyLabels[q.difficulty_level]}
                                        </span>
                                    )}

                                    {/* Unit (Orange) - Use topic_id for chapter number */}
                                    {q.unit_name ? (
                                        <span className="px-2 py-0.5 text-[10px] font-medium bg-blue-50 text-blue-600 rounded border border-blue-100 group-hover:bg-blue-100 group-hover:text-blue-700 group-hover:border-blue-200 transition-colors">
                                            章節 {q.topic_id || q.unit_id} {q.unit_name}
                                        </span>
                                    ) : q.unit_id ? (
                                        <span className="px-2 py-0.5 text-[10px] font-medium bg-blue-50 text-blue-600 rounded border border-blue-100 group-hover:bg-blue-100 group-hover:text-blue-700 group-hover:border-blue-200 transition-colors">
                                            章節 {q.topic_id || q.unit_id}
                                        </span>
                                    ) : null}

                                    {/* KP (Cyan/Blue) */}
                                    {q.kp_name && (
                                        <span className="px-2 py-0.5 text-[10px] font-medium bg-blue-50 text-blue-600 rounded border border-blue-100 group-hover:bg-blue-100 group-hover:text-blue-700 group-hover:border-blue-200 transition-colors">
                                            知識點: {q.kp_name}
                                        </span>
                                    )}

                                    {/* Tags (Cyan - Same as KP) - Filter out system tags */}
                                    {q.tags && q.tags.filter(tag => tag !== 'AI生成' && tag !== '手動新增').length > 0 && q.tags.filter(tag => tag !== 'AI生成' && tag !== '手動新增').map(tag => (
                                        <span key={tag} className="px-2 py-0.5 text-[10px] font-medium bg-blue-50 text-blue-600 rounded border border-blue-100 group-hover:bg-blue-100 group-hover:text-blue-700 group-hover:border-blue-200 transition-colors">
                                            #{tag}
                                        </span>
                                    ))}
                                </div>

                                <div className={`text-sm font-bold mb-1 line-clamp-3 pr-12 overflow-hidden ${isSelected && viewMode === 'active' ? 'text-blue-800' : 'text-gray-800'}`}>
                                    <ReactMarkdown>
                                        {q.question_data?.question_text || q.question_data?.question || q.title}
                                    </ReactMarkdown>
                                </div>

                                <div className="flex items-center gap-2 text-[10px] text-gray-400">
                                    <span>使用 {q.times_used} 次</span>
                                    <span>•</span>
                                    <span>{viewMode === 'active' ? new Date(q.created_at).toLocaleDateString() : `封存於 ${new Date(q.updated_at).toLocaleDateString()}`}</span>
                                </div>
                            </div>
                        );
                    })
                )}
            </div>

            {/* Pagination / Footer can go here if needed, but for now scrolling is enough or existing one uses infinite scroll?
                Looking at original code, it didn't seem to have explicit pagination UI in the bottom, just a list.
                The scroll area handled it or it rendered all?
                The original code had `loadQuestions` using `page` but I didn't see load checks or scroll listeners in the snippet I had.
                I will assume this is sufficient for now as it matches the reconstructed "TargetContent" plus the mapping logic.
            */}

            {/* Generic Confirm Dialog (Refactored to be generic usage) */}
            <ConfirmDialog
                isOpen={confirmDialog.isOpen}
                title={confirmDialog.title}
                message={confirmDialog.message}
                confirmText={confirmDialog.confirmText}
                variant={confirmDialog.variant}
                onConfirm={confirmDialog.onConfirm}
                onCancel={() => setConfirmDialog(prev => ({ ...prev, isOpen: false }))}
            />

            {/* Archive Confirmation Modal */}
            {deleteModal.isOpen && deleteModal.question && (
                <Modal
                    isOpen={true}
                    onClose={() => setDeleteModal({ isOpen: false, question: null })}
                    title="封存題目"
                >
                    <div className="space-y-5">
                        <div className="border rounded-xl p-4 flex items-start gap-3 bg-orange-50 border-orange-200">
                            <FaArchive className="flex-shrink-0 mt-0.5 text-orange-500" size={20} />
                            <div className="text-sm text-gray-700 space-y-2">
                                <p className="font-bold text-orange-800">確定要封存此題目嗎？</p>
                                <p>封存後題目將移至封存區，您可以隨時從封存區恢復。</p>
                                {deleteModal.question.times_used > 0 && (
                                    <p className="text-xs text-gray-500">
                                        目前有 {deleteModal.question.times_used} 份試卷使用此題目，封存不會影響這些試卷。
                                    </p>
                                )}
                            </div>
                        </div>

                        {/* Footer: Cancel and Archive */}
                        <div className="flex items-center justify-end gap-3 pt-2">
                            <Button
                                variant="secondary"
                                onClick={() => setDeleteModal({ isOpen: false, question: null })}
                                idleText="取消"
                            />
                            <Button
                                variant="primary"
                                className="bg-orange-500 hover:bg-orange-600 border-orange-600 text-white"
                                onClick={() => {
                                    if (deleteModal.question) archiveQuestion(deleteModal.question.id);
                                    setDeleteModal({ isOpen: false, question: null });
                                }}
                                idleText={<span className="flex items-center gap-2"><FaArchive /> 封存題目</span>}
                            />
                        </div>
                    </div>
                </Modal>
            )}
        </div>
    );
});

export default QuestionBankPanel;
