import { useState, useEffect, forwardRef, useImperativeHandle } from 'react';

import { FaClock, FaChevronDown } from 'react-icons/fa';

interface QuestionMetadataDrawerProps {
    isOpen: boolean;
    isCollapsed?: boolean;
    onToggleCollapse?: () => void;
    onClose: () => void;
    onConfirm: (data: QuestionMetadataData) => Promise<void>;
    initialData: {
        title: string;
        question_text?: string;
        question_type?: string;
        difficulty_level?: 1 | 2 | 3 | 4 | null;
        estimated_time_minutes?: number | null;
        unit_id?: number | null;
        kp_id?: number | string | null;
        tags?: string[];
        description?: string | null;
    };
    units?: Array<{ id: number; name: string; chapter_number?: number; topic_id?: number; }>;
    existingTags?: string[]; // Kept for interface compatibility but ignored
    isExisting?: boolean;
    inline?: boolean;
}

export interface QuestionMetadataData {
    title: string;
    description?: string;
    question_type?: string;
    difficulty_level?: 1 | 2 | 3 | 4 | null;
    estimated_time_minutes?: number | null;
    unit_id?: number | null;
    topic_id?: number | null;
    kp_id?: number | string | null;
    tags: string[];
}

const DIFFICULTY_LEVELS = [
    { value: 1, label: '簡單', color: 'text-green-600 bg-green-50 hover:bg-green-100 border-green-200', stars: '⭐' },
    { value: 2, label: '普通', color: 'text-yellow-600 bg-yellow-50 hover:bg-yellow-100 border-yellow-200', stars: '⭐⭐' },
    { value: 3, label: '困難', color: 'text-orange-600 bg-orange-50 hover:bg-orange-100 border-orange-200', stars: '⭐⭐⭐' },
    { value: 4, label: '挑戰', color: 'text-red-600 bg-red-50 hover:bg-red-100 border-red-200', stars: '⭐⭐⭐⭐' }
];

// Re-implementing a custom resizeable drawer...
import ReactDOM from 'react-dom';
import CustomSelect from '../common/CustomSelect';
// TagInput removed - tags now auto-assigned by backend

export interface QuestionMetadataDrawerRef {
    submit: () => Promise<void>;
}

export default forwardRef<QuestionMetadataDrawerRef, QuestionMetadataDrawerProps>(function QuestionMetadataDrawer({
    isOpen,
    isCollapsed = false,
    onToggleCollapse,
    onClose,
    onConfirm,
    initialData,
    units = [],
    isExisting = false,
}: QuestionMetadataDrawerProps, ref) {
    // courseId removed - no longer needed for tag fetching
    const [description, setDescription] = useState('');
    const [difficulty, setDifficulty] = useState<1 | 2 | 3 | 4 | null>(null);
    const [time, setTime] = useState<number | null>(null);
    const [unitId, setUnitId] = useState<number | null>(null);
    // Tags now auto-assigned by backend ('AI生成' or '手動新增')

    const [loading, setLoading] = useState(false);

    // Resizing State
    const [drawerWidth, setDrawerWidth] = useState(() => {
        const width = window.innerWidth * 0.31;
        return Math.min(Math.max(width, 300), 1200); // Clamp between 300 and 1200
    });
    const [isResizing, setIsResizing] = useState(false);

    useEffect(() => {
        if (isOpen) {
            setDescription(initialData.description || '');
            setDifficulty(initialData.difficulty_level || null);
            setTime(initialData.estimated_time_minutes || 5);
            setUnitId(isExisting ? (initialData.unit_id || null) : null);
            // Tags no longer managed here - auto-assigned by backend
        }
    }, [isOpen, initialData]);

    // Resizing Logic
    useEffect(() => {
        const handleMouseMove = (e: MouseEvent) => {
            if (!isResizing) return;
            const newWidth = window.innerWidth - e.clientX;
            const minWidth = window.innerWidth * 0.31; // Minimum 31%

            // Clamp width: Min is 30%, Max is 1200px
            if (newWidth > minWidth && newWidth < 1200) {
                setDrawerWidth(newWidth);
            } else if (newWidth <= minWidth) {
                setDrawerWidth(minWidth);
            }
        };

        const handleMouseUp = () => {
            setIsResizing(false);
            document.body.style.cursor = 'default';
            document.body.style.userSelect = 'auto';
        };

        if (isResizing) {
            document.addEventListener('mousemove', handleMouseMove);
            document.addEventListener('mouseup', handleMouseUp);
            document.body.style.cursor = 'ew-resize';
            document.body.style.userSelect = 'none'; // Prevent text selection while dragging
        }

        return () => {
            document.removeEventListener('mousemove', handleMouseMove);
            document.removeEventListener('mouseup', handleMouseUp);
        };
    }, [isResizing]);

    const handleConfirm = async () => {
        setLoading(true);
        try {
            await onConfirm({
                title: initialData.title,
                description,
                question_type: initialData.question_type,
                difficulty_level: difficulty,
                estimated_time_minutes: time,
                unit_id: unitId,
                kp_id: initialData.kp_id,
                tags: [] // Tags auto-assigned by backend
            });
            // Don't close here, wait for parent to decide or close on success
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    // Expose submit method to parent via ref
    useImperativeHandle(ref, () => ({
        submit: handleConfirm
    }));

    if (!isOpen) return null;

    return ReactDOM.createPortal(
        <>
            {/* Backdrop - non-interactive, allows scrolling */}
            <div
                className="fixed inset-0 bg-transparent z-40 pointer-events-none"
                aria-hidden="true"
            />

            {/* Resizable Drawer Panel */}
            <div
                className={`fixed inset-y-0 right-0 z-50 bg-white shadow-2xl flex flex-col transition-all duration-300 ${isCollapsed ? 'translate-x-full' : 'translate-x-0'
                    }`}
                style={{ width: drawerWidth }}
                role="dialog"
                aria-modal="true"
            >
                {/* Expand button when collapsed */}
                {isCollapsed && onToggleCollapse && (
                    <button
                        onClick={onToggleCollapse}
                        className="absolute left-0 top-1/2 -translate-x-full -translate-y-1/2 bg-blue-500/90 text-white p-2 rounded-l-lg shadow-[0_2px_8px_-2px_rgba(0,0,0,0.15)] hover:bg-blue-600 transition-colors flex items-center justify-center w-8 h-12 border-y border-l border-blue-400"
                        title="展開抽屜"
                    >
                        <FaChevronDown size={14} className="rotate-90" />
                    </button>
                )}

                {/* Resize Handle */}
                <div
                    className="absolute left-0 top-0 bottom-0 w-1.5 cursor-ew-resize hover:bg-blue-400/50 z-50 transition-colors"
                    onMouseDown={(e) => {
                        e.stopPropagation();
                        setIsResizing(true);
                    }}
                >
                    {/* Visual indicator line on hover/active */}
                    <div className={`h-full w-[1px] mx-auto bg-gray-200 ${isResizing ? 'bg-blue-400' : ''}`} />
                </div>

                {/* Toggle Collapse Button - 位於左側外部邊界 */
                    onToggleCollapse && !isCollapsed && (
                        <button
                            onClick={onToggleCollapse}
                            className="absolute left-0 top-1/2 -translate-x-full -translate-y-1/2 z-[60] p-2 bg-white text-gray-600 rounded-l-lg shadow-[0_2px_8px_-2px_rgba(0,0,0,0.15)] border-y border-l border-gray-100 hover:bg-gray-50 transition-colors flex items-center justify-center w-8 h-12"
                            title="收合抽屜"
                        >
                            <FaChevronDown size={14} className="-rotate-90" />
                        </button>
                    )}

                {/* Gradient Header */}
                <div className="flex-none flex items-center justify-between px-6 py-4 border-b border-blue-100 bg-gradient-to-r from-blue-50 via-cyan-50 to-blue-50">
                    <h2 className="text-xl font-bold bg-gradient-to-r from-blue-600 to-cyan-600 bg-clip-text text-transparent">
                        {isExisting ? '編輯題庫資訊' : '加入題庫'}
                    </h2>
                </div>

                {/* Scrollable Body - Compact Spacing Layout */}
                <div className="flex-1 overflow-y-auto p-6 space-y-6 custom-scrollbar">
                    {/* 1. Basic Info Section */}
                    <div className="space-y-6">
                        {/* Difficulty Section */}
                        <div className="space-y-3">
                            <label className="text-sm font-black text-gray-800 uppercase tracking-[0.15em] block border-l-4 border-blue-500 pl-3">題目難度</label>
                            <div className="grid grid-cols-4 gap-3">
                                {DIFFICULTY_LEVELS.map((level) => (
                                    <button
                                        key={level.value}
                                        type="button"
                                        onClick={() => setDifficulty(level.value as any)}
                                        className={`flex flex-col items-center justify-center p-2 rounded-xl border-2 transition-all duration-300 ${difficulty === level.value
                                            ? 'bg-blue-50/30 border-blue-500 scale-105 shadow-[0_4px_12px_-6px_rgba(59,130,246,0.3)] ring-4 ring-blue-50 ' + level.color.replace('bg-', 'border-').replace('text-', 'text-').split(' ').filter(c => c.startsWith('text-')).join(' ')
                                            : 'bg-blue-50/10 border-blue-100/50 text-blue-300 hover:border-blue-200 hover:text-blue-500 opacity-80 hover:opacity-100'
                                            }`}
                                    >
                                        <span className="text-sm mb-1">{level.stars}</span>
                                        <span className="text-[10px] font-black tracking-widest">{level.label}</span>
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* Estimated Time Section */}
                        <div className="space-y-3">
                            <label className="text-sm font-black text-gray-800 uppercase tracking-[0.15em] block border-l-4 border-blue-500 pl-3 flex justify-between items-center">
                                <span>預估作答時間</span>
                                {time && <span className="text-theme-primary font-mono text-base font-black">{time} <span className="text-[10px] tracking-normal">分</span></span>}
                            </label>
                            <div className="flex items-center gap-4 bg-gray-50/50 p-4 rounded-xl border border-gray-100/50">
                                <div className="p-2 bg-blue-100/50 text-blue-600 rounded-lg">
                                    <FaClock size={16} />
                                </div>
                                <input
                                    type="range"
                                    min="1"
                                    max="30"
                                    value={time && time <= 30 ? time : 30}
                                    onChange={(e) => setTime(parseInt(e.target.value))}
                                    className="flex-1 h-1.5 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-500"
                                />
                                <div className="flex items-center gap-2">
                                    <input
                                        type="number"
                                        min="1"
                                        value={time || ''}
                                        onChange={(e) => {
                                            const val = parseInt(e.target.value);
                                            setTime(isNaN(val) ? null : val);
                                        }}
                                        className="w-16 px-2 py-1 text-center text-base font-black text-gray-700 border-2 border-gray-200 rounded-lg focus:border-blue-500 outline-none transition-all shadow-inner"
                                    />
                                    <span className="text-[10px] font-black text-gray-400 uppercase">分</span>
                                </div>
                            </div>
                            <div className="text-[10px] text-gray-400 mt-1.5 text-right font-bold italic opacity-80">
                                ※ 可手動輸入更長時間
                            </div>
                        </div>
                    </div>

                    {/* 2. Classification Section */}
                    <div className="space-y-6">
                        {/* Chapter/Unit Section */}
                        <div className="space-y-3">
                            <label className="text-sm font-black text-gray-800 uppercase tracking-[0.15em] block border-l-4 border-blue-500 pl-3">所屬課程章節</label>
                            <div className="p-0.5 px-1 bg-gray-50/50 rounded-xl border border-gray-100/50">
                                <CustomSelect
                                    value={unitId}
                                    onChange={setUnitId}
                                    placeholder="不限章節 (通用題目)"
                                    options={units.map(u => ({
                                        value: u.id,
                                        label: `第 ${u.topic_id || u.chapter_number || '?'} 章 : ${u.name}`
                                    }))}
                                />
                            </div>
                        </div>


                        {/* Description Section */}
                        <div className="space-y-3">
                            <label className="text-sm font-black text-gray-800 uppercase tracking-[0.15em] block border-l-4 border-blue-500 pl-3">備註或補充說明</label>
                            <textarea
                                value={description}
                                onChange={(e) => setDescription(e.target.value)}
                                placeholder="輸入給本題目的額外備註或背景說明..."
                                className="w-full px-4 py-3 bg-gray-50/30 border-2 border-gray-100 rounded-xl text-sm focus:border-blue-500 outline-none transition-all min-h-[100px] shadow-inner resize-none placeholder:text-gray-300"
                            />
                        </div>
                    </div>
                </div>

                {/* Footer with Actions - Always visible */}
                <div className="flex-none p-6 border-t border-gray-100 bg-white flex items-center justify-end gap-3">
                    <button
                        onClick={onClose}
                        className="px-6 py-2.5 text-gray-500 bg-gray-50 border border-gray-200 hover:bg-gray-100 rounded-xl font-bold transition-all"
                        disabled={loading}
                    >
                        取消
                    </button>
                    <button
                        onClick={handleConfirm}
                        className="px-10 py-2.5 bg-theme-primary text-white rounded-xl font-bold hover:bg-theme-primary/90 shadow-md transition-all disabled:opacity-70"
                        disabled={loading}
                    >
                        {loading ? '處理中...' : (isExisting ? '儲存變更' : '加入題庫')}
                    </button>
                </div>
            </div>
        </>,
        document.body
    );
});
