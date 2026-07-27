import React, { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { FaLink, FaLightbulb, FaBookOpen, FaCheck, FaTimes, FaPen, FaPlus, FaTrash, FaArrowUp, FaArrowDown, FaSearch, FaMagic } from 'react-icons/fa';
import { HiOutlineViewGridAdd } from 'react-icons/hi';
import { getKPStats } from '../../services/kpApi';
import TeacherRecommendedPreview from '../teacher/TeacherRecommendedPreview';
import { useNavigate } from 'react-router-dom';
import { SummaryListItem } from './SummaryListItem';
import ConfirmDialog from '../common/ConfirmDialog';

interface Citation {
    chunk_id: number | string;
    match_score: number;
    source: string;
    page_number?: string | number;
    text?: string;
    source_metadata?: any;
    structured_content?: any[];
}

interface SummarySection {
    section_title: string;
    related_kps?: string[];
    content_list: string[];
    chunk_ids?: (number | string)[];
    match_scores?: number[];
    citations?: Citation[];
}

interface RecommendationConfig {
    total_max?: number;
    count_per_kp?: number;
    enabled?: boolean;
}

interface SummaryResult {
    content: SummarySection[];
    summary?: string;
    recommendation_config?: RecommendationConfig;
}

interface SummaryContentViewProps {
    summary: SummaryResult | any;
    materialType?: 'preview' | 'review';

    // 編輯模式支援
    editable?: boolean;
    isEditing?: boolean;
    onStartEdit?: () => void;
    onSaveEdit?: () => void;
    onCancelEdit?: () => void;
    onContentChange?: (newSummary: any) => void;

    // 引用功能
    onReferenceClick?: (chunkId: number | string, evidence: string, matchScore?: number, fullChunk?: any, questionId?: number, refType?: 'question' | 'section') => void;

    // 知識點選擇器（從父組件提供）
    availableKPs?: Array<{ id: string | number; name: string; category?: string; source_name?: string; source_type?: string }>;


    courseId?: string | number;
    unitId?: string | number;
    contentId?: number | string;
    isTeacher?: boolean;
    onKPLookup?: (kpName: string, kpId?: number) => void;
    onAddKP?: (name: string) => Promise<{ id: string | number; name: string } | null>;
}

export interface SummaryContentViewRef {
    getPendingContent: () => any | null;
}

export const SummaryContentView = React.forwardRef<SummaryContentViewRef, SummaryContentViewProps>(({
    summary,
    materialType,
    editable = false,
    isEditing = false,
    onStartEdit,
    onSaveEdit,
    onCancelEdit,
    onContentChange,
    onReferenceClick,
    availableKPs = [],

    courseId,
    unitId,
    contentId,
    isTeacher = false,
    onKPLookup,
    onAddKP
}, ref) => {
    const navigate = useNavigate();
    const [tempSummary, setTempSummary] = useState<SummaryResult | null>(null);
    const [showKPSelector, setShowKPSelector] = useState<{ sectionIdx: number } | null>(null);
    const [originalKey, setOriginalKey] = useState<'sections' | 'content'>('sections');
    const [kpStats, setKpStats] = useState<Record<string, number>>({});
    const [showGenerateConfirm, setShowGenerateConfirm] = useState(false);
    const [newKPName, setNewKPName] = useState('');
    const [isAddingKP, setIsAddingKP] = useState(false);

    // 當 isEditing 從外部傳入且為 true 時，初始化 tempSummary
    useEffect(() => {
        if (isEditing && !tempSummary) {
            const hasSections = !!summary.sections;
            const sectionsData = summary.sections || (summary as any).content;

            setOriginalKey(hasSections ? 'sections' : 'content');

            if (sectionsData) {
                setTempSummary({
                    content: JSON.parse(JSON.stringify(sectionsData)),
                    recommendation_config: summary.recommendation_config
                        ? JSON.parse(JSON.stringify(summary.recommendation_config))
                        : { total_max: 5, count_per_kp: 1, enabled: true }
                });
            }
        } else if (!isEditing && tempSummary) {
            setTempSummary(null);
        }
    }, [isEditing, summary, tempSummary]);

    // Expose method to parent ContentRenderer
    React.useImperativeHandle(ref, () => ({
        getPendingContent: () => {
            if (isEditing && tempSummary) {
                return {
                    [originalKey]: tempSummary.content,
                    recommendation_config: tempSummary.recommendation_config
                };
            }
            return null;
        }
    }), [isEditing, tempSummary, originalKey]);

    // Process sections to handle different data formats (legacy vs new summary)
    const rawSections = isEditing && tempSummary ? tempSummary.content : (summary.sections || (summary as any).content);
    const sections = Array.isArray(rawSections) ? rawSections.map((sec: any) => {
        let contentList = sec.content_list;
        let sectionTitle = sec.section_title;

        // Compatibility for new 'summary' format where content might be in citations text
        if ((!contentList || contentList.length === 0) && sec.citations && sec.citations.length > 0) {
            const texts = sec.citations.map((c: any) => c.text).filter((t: any) => t);
            if (texts.length > 0) {
                // Combined text
                const fullText = texts.join('\n');
                // Split by newline to create list
                const lines = fullText.split('\n').map((l: string) => l.trim()).filter((l: string) => l);

                // Heuristic: if title is missing and first line looks like a title (no bullet), use it
                if (!sectionTitle && lines.length > 0 && !lines[0].startsWith('•') && !lines[0].startsWith('-') && !lines[0].startsWith('—') && !lines[0].match(/^\d+\./)) {
                    sectionTitle = lines[0];
                    contentList = lines.slice(1);
                } else {
                    contentList = lines;
                }
            }
        }

        return {
            ...sec,
            section_title: sectionTitle || '',
            content_list: contentList || []
        };
    }) : [];

    // Fetch KP Stats for counters
    useEffect(() => {
        if (!courseId || sections.length === 0) return;

        const allKps = Array.from(new Set(sections.flatMap(s => s.related_kps || [])));
        if (allKps.length === 0) return;

        getKPStats(courseId, allKps)
            .then(stats => {
                setKpStats(stats);
            })
            .catch(err => console.error('Failed to load KP stats:', err));
    }, [courseId, summary]);

    const allKps = Array.from(new Set(sections.flatMap(s => s.related_kps || [])));
    const lowCoverageKps = allKps.filter(kp => (kpStats[kp] || 0) < 2);

    // 初始化編輯狀態
    const handleStartEdit = () => {
        const hasSections = !!summary.sections;
        const sectionsData = summary.sections || (summary as any).content;

        setOriginalKey(hasSections ? 'sections' : 'content');
        setTempSummary({
            content: JSON.parse(JSON.stringify(sectionsData)),
            recommendation_config: summary.recommendation_config
                ? JSON.parse(JSON.stringify(summary.recommendation_config))
                : { total_max: 5, count_per_kp: 1, enabled: true }
        });
        onStartEdit?.();
    };

    // 儲存編輯
    const handleSaveEdit = () => {
        if (tempSummary && onContentChange) {
            onContentChange({
                [originalKey]: tempSummary.content,
                recommendation_config: tempSummary.recommendation_config
            });
        }
        setTempSummary(null);
        onSaveEdit?.();
    };

    // 取消編輯
    const handleCancelEdit = () => {
        setTempSummary(null);
        onCancelEdit?.();
    };

    // Section 標題修改
    const handleSectionTitleChange = (sectionIdx: number, newTitle: string) => {
        if (!tempSummary) return;
        const newContent = [...tempSummary.content];
        newContent[sectionIdx] = { ...newContent[sectionIdx], section_title: newTitle };
        setTempSummary({ ...tempSummary, content: newContent });
    };

    // Content 要點修改
    const handleContentChange = (sectionIdx: number, contentIdx: number, newText: string) => {
        if (!tempSummary) return;
        const newContent = [...tempSummary.content];
        const newContentList = [...newContent[sectionIdx].content_list];
        newContentList[contentIdx] = newText;
        newContent[sectionIdx] = { ...newContent[sectionIdx], content_list: newContentList };
        setTempSummary({ ...tempSummary, content: newContent });
    };

    // 新增 Content 要點
    const handleAddContent = (sectionIdx: number) => {
        if (!tempSummary) return;
        const newContent = [...tempSummary.content];
        const newContentList = [...newContent[sectionIdx].content_list, ''];
        newContent[sectionIdx] = { ...newContent[sectionIdx], content_list: newContentList };
        setTempSummary({ ...tempSummary, content: newContent });
    };

    // 刪除 Content 要點
    const handleDeleteContent = (sectionIdx: number, contentIdx: number) => {
        if (!tempSummary) return;
        const newContent = [...tempSummary.content];
        const newContentList = newContent[sectionIdx].content_list.filter((_: string, idx: number) => idx !== contentIdx);
        newContent[sectionIdx] = { ...newContent[sectionIdx], content_list: newContentList };
        setTempSummary({ ...tempSummary, content: newContent });
    };

    // 新增知識點
    const handleAddKP = (sectionIdx: number, kpName: string) => {
        if (!tempSummary) return;
        const newContent = [...tempSummary.content];
        const currentKPs = newContent[sectionIdx].related_kps || [];
        newContent[sectionIdx] = {
            ...newContent[sectionIdx],
            related_kps: [...currentKPs, kpName]
        };
        setTempSummary({ ...tempSummary, content: newContent });
        setShowKPSelector(null);
    };

    // 移除知識點
    const handleRemoveKP = (sectionIdx: number, kpIdx: number) => {
        if (!tempSummary) return;
        const newContent = [...tempSummary.content];
        const newKPs = (newContent[sectionIdx].related_kps || []).filter((_: string, idx: number) => idx !== kpIdx);
        newContent[sectionIdx] = { ...newContent[sectionIdx], related_kps: newKPs };
        setTempSummary({ ...tempSummary, content: newContent });
    };

    // Section 排序
    const handleMoveSection = (sectionIdx: number, direction: 'up' | 'down') => {
        if (!tempSummary) return;
        const newContent = [...tempSummary.content];
        const targetIdx = direction === 'up' ? sectionIdx - 1 : sectionIdx + 1;

        if (targetIdx < 0 || targetIdx >= newContent.length) return;

        [newContent[sectionIdx], newContent[targetIdx]] = [newContent[targetIdx], newContent[sectionIdx]];
        setTempSummary({ ...tempSummary, content: newContent });
    };

    // 刪除 Section
    const handleDeleteSection = (sectionIdx: number) => {
        if (!tempSummary) return;
        const newContent = tempSummary.content.filter((_: any, idx: number) => idx !== sectionIdx);
        setTempSummary({ ...tempSummary, content: newContent });
    };

    // 新增 Section 段落卡片
    const handleAddSection = () => {
        if (!tempSummary) return;
        const newSection: SummarySection = {
            section_title: '',
            content_list: [''], // 預設提供一個空的要點
            related_kps: []
        };
        const newContent = [...tempSummary.content, newSection];
        setTempSummary({ ...tempSummary, content: newContent });
    };

    if (!summary || !sections || !Array.isArray(sections)) {
        return (
            <div className="p-6 rounded-xl border border-red-200 bg-red-50 text-red-700">
                <h3 className="font-bold mb-2">無法顯示摘要內容</h3>
                <p className="text-sm">生成的內容結構不完整或有誤。</p>
            </div>
        );
    }

    return (
        <>
            <div className="space-y-6 font-newsreader relative">
                {/* 浮動整合狀態列 (Unified Sticky Header) */}
                {editable && (
                    <div className="sticky top-0 sm:top-4 z-[120] flex justify-end -mt-[100px] mb-12 pointer-events-none -mx-2 pl-6 pr-2 pt-2">
                        <div className="flex items-center gap-3 p-1.5 bg-white/90 backdrop-blur-xl rounded-2xl border border-blue-100 shadow-[0_20px_50px_rgba(37,99,235,0.18)] pointer-events-auto transition-all hover:shadow-[0_20px_50px_rgba(37,99,235,0.25)] group ring-1 ring-blue-50/50">
                            {!isEditing ? (
                                <button
                                    onClick={handleStartEdit}
                                    className="flex items-center gap-2.5 px-6 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-black hover:bg-blue-700 transition-all shadow-[0_4px_12px_rgba(37,99,235,0.3)] hover:scale-105 active:scale-95"
                                >
                                    <FaPen size={14} className="opacity-80" />
                                    <span className="tracking-tight">編輯摘要</span>
                                </button>
                            ) : (
                                <div className="flex items-center gap-3 px-1">
                                    <button
                                        onClick={handleSaveEdit}
                                        className="flex items-center gap-2.5 px-7 py-2.5 bg-theme-primary text-white rounded-xl text-sm font-black hover:bg-theme-primary-dark transition-all shadow-[0_8px_20px_rgba(59,130,246,0.3)] hover:scale-105 active:scale-95"
                                    >
                                        <FaCheck size={14} className="opacity-90" />
                                        <span className="tracking-tight">儲存</span>
                                    </button>
                                    <div className="w-px h-6 bg-gray-200 mx-1"></div>
                                    <button
                                        onClick={handleCancelEdit}
                                        className="flex items-center gap-2 px-6 py-2.5 bg-white text-gray-500 rounded-xl text-sm font-bold hover:bg-gray-50 hover:text-gray-700 transition-all active:scale-95 border border-gray-100"
                                    >
                                        <FaTimes size={14} className="opacity-60" />
                                        <span>取消</span>
                                    </button>
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {/* Sections */}
                <div className="space-y-6">
                    {sections.map((section: SummarySection, idx: number) => (
                        <div
                            key={idx}
                            className={`bg-white p-6 rounded-xl border shadow-sm transition-all relative group ${isEditing ? 'pt-12 border-theme-primary ring-1 ring-theme-primary/20' : 'border-neutral-border hover:shadow-md'
                                }`}
                        >
                            {/* Section 工具列（編輯模式） */}
                            {isEditing && (
                                <div className="absolute right-2 top-2 flex gap-1 z-10">
                                    <button
                                        onClick={() => handleMoveSection(idx, 'up')}
                                        disabled={idx === 0}
                                        className="p-1.5 text-gray-400 hover:text-theme-primary hover:bg-theme-primary/10 rounded disabled:opacity-30"
                                        title="上移"
                                    >
                                        <FaArrowUp size={12} />
                                    </button>
                                    <button
                                        onClick={() => handleMoveSection(idx, 'down')}
                                        disabled={idx === sections.length - 1}
                                        className="p-1.5 text-gray-400 hover:text-theme-primary hover:bg-theme-primary/10 rounded disabled:opacity-30"
                                        title="下移"
                                    >
                                        <FaArrowDown size={12} />
                                    </button>
                                    <div className="w-px h-4 bg-gray-200 mx-1 self-center"></div>
                                    <button
                                        onClick={() => handleDeleteSection(idx)}
                                        className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded"
                                        title="刪除段落"
                                    >
                                        <FaTrash size={12} />
                                    </button>
                                </div>
                            )}

                            {/* Section Header */}
                            <div className="mb-4">
                                <div className="flex items-start justify-between gap-4">
                                    {isEditing ? (
                                        <input
                                            value={section.section_title}
                                            onChange={(e) => handleSectionTitleChange(idx, e.target.value)}
                                            className="flex-1 text-xl font-bold text-neutral-text-main border border-gray-300 rounded-lg px-3 py-2 bg-gray-50 focus:bg-white focus:border-theme-primary focus:ring-2 focus:ring-theme-primary/20 outline-none transition-all"
                                            placeholder="段落標題..."
                                        />
                                    ) : (
                                        <h3 className="text-xl font-bold text-neutral-text-main flex items-center gap-2">
                                            <span className="w-1.5 h-6 rounded-full bg-blue-500 shrink-0"></span>
                                            <div className="markdown-title line-clamp-1">
                                                <ReactMarkdown components={{ p: ({ children }) => <>{children}</> }}>
                                                    {section.section_title}
                                                </ReactMarkdown>
                                            </div>
                                        </h3>
                                    )}

                                    {/* KP Tags */}
                                    <div className="flex flex-wrap gap-1.5 justify-end max-w-[50%]">
                                        {(section.related_kps || []).map((kp, kpIdx) => (
                                            <span
                                                key={kpIdx}
                                                onClick={() => {
                                                    if (isTeacher && onKPLookup && !isEditing) {
                                                        onKPLookup(kp);
                                                    }
                                                }}
                                                className={`inline-flex items-center px-2 py-1 rounded-md text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200 shadow-sm transition-all group/kp ${isTeacher && !isEditing ? 'cursor-pointer hover:bg-amber-100 hover:scale-105 active:scale-95' : ''}`}
                                                title={isTeacher && !isEditing ? "在題庫中搜尋此知識點" : undefined}
                                            >
                                                <FaLightbulb className="mr-1.5 text-amber-500" size={10} />
                                                {kp}

                                                {/* Count Badge (Teacher Only) */}
                                                {isTeacher && courseId && kpStats[kp] !== undefined && (
                                                    <span className={`ml-1.5 px-1 rounded-full text-[10px] ${kpStats[kp] > 0 ? 'bg-amber-200 text-amber-800' : 'bg-red-100 text-red-600 font-bold'}`}>
                                                        {kpStats[kp]}
                                                    </span>
                                                )}

                                                {/* Lookup Action (Teacher Only) */}
                                                {isTeacher && onKPLookup && !isEditing && (
                                                    <div className="ml-1.5 text-amber-400 opacity-0 group-hover/kp:opacity-100 transition-opacity">
                                                        <FaSearch size={8} />
                                                    </div>
                                                )}

                                                {isEditing && (
                                                    <button
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            handleRemoveKP(idx, kpIdx);
                                                        }}
                                                        className="ml-1.5 p-0.5 text-amber-400 hover:text-red-500 hover:bg-amber-100 rounded-full transition-all"
                                                        title="移除知識點"
                                                    >
                                                        <FaTimes size={8} />
                                                    </button>
                                                )}
                                            </span>
                                        ))}
                                        {isEditing && (
                                            <div className="relative">
                                                <button
                                                    onClick={() => setShowKPSelector({ sectionIdx: idx })}
                                                    className="inline-flex items-center px-2 py-1 rounded-md text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100 transition-all shadow-sm"
                                                    title="新增知識點"
                                                >
                                                    <FaPlus size={8} className="mr-1.5" />
                                                    新增知識點
                                                </button>

                                                {showKPSelector?.sectionIdx === idx && (() => {
                                                    const groupedKPs = availableKPs.reduce((acc, kp) => {
                                                        let label = '';
                                                        if (kp.source_type === 'manual') {
                                                            label = '手動新增';
                                                        } else if (kp.source_name) {
                                                            label = kp.source_name;
                                                        } else {
                                                            const categoryLabels: Record<string, string> = {
                                                                'unit': '單元知識點',
                                                                'extracted': '從參考資料提取',
                                                                'course': '其他課程知識點',
                                                                'other': '其他'
                                                            };
                                                            label = categoryLabels[kp.category || 'other'] || '其它';
                                                        }

                                                        if (!acc[label]) acc[label] = [];
                                                        acc[label].push(kp);
                                                        return acc;
                                                    }, {} as Record<string, typeof availableKPs>);

                                                    const orderedCategories = Object.keys(groupedKPs).sort();

                                                    return (
                                                        <div className="absolute top-full right-0 mt-1 bg-white border border-amber-100 rounded-xl shadow-xl z-50 w-96 max-h-[18rem] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
                                                            <div className="p-2 border-b border-amber-50 flex justify-between items-center bg-amber-50/30 shrink-0">
                                                                <span className="text-[10px] font-bold text-amber-700 uppercase tracking-widest">可選知識點</span>
                                                                <div className="flex items-center gap-2">
                                                                    <button
                                                                        onClick={() => setShowKPSelector(null)}
                                                                        className="text-amber-400 hover:text-amber-600 p-1 hover:bg-amber-100 rounded transition-colors"
                                                                    >
                                                                        <FaTimes size={10} />
                                                                    </button>
                                                                </div>
                                                            </div>

                                                            {/* Manual Add KP Section - Moved to Top */}
                                                            {onAddKP && (
                                                                <div className="p-2 border-b border-amber-100 bg-amber-50/20 shrink-0">
                                                                    <div className="flex gap-1">
                                                                        <input
                                                                            type="text"
                                                                            value={newKPName}
                                                                            onChange={(e) => setNewKPName(e.target.value)}
                                                                            onKeyDown={async (e) => {
                                                                                if (e.key === 'Enter' && newKPName.trim() && !isAddingKP) {
                                                                                    e.preventDefault();
                                                                                    setIsAddingKP(true);
                                                                                    try {
                                                                                        const result = await onAddKP(newKPName.trim());
                                                                                        if (result) {
                                                                                            handleAddKP(idx, result.name);
                                                                                            setNewKPName('');
                                                                                            setShowKPSelector(null);
                                                                                        }
                                                                                    } catch (err) {
                                                                                        console.error("Failed to add KP", err);
                                                                                    } finally {
                                                                                        setIsAddingKP(false);
                                                                                    }
                                                                                }
                                                                            }}
                                                                            placeholder="手動新增知識點..."
                                                                            className="flex-1 px-2 py-1.5 text-xs bg-white border border-amber-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500/20 focus:border-amber-400 transition-all font-medium text-amber-900"
                                                                        />
                                                                        <button
                                                                            onClick={async () => {
                                                                                if (!newKPName.trim() || !onAddKP || isAddingKP) return;
                                                                                setIsAddingKP(true);
                                                                                try {
                                                                                    const result = await onAddKP(newKPName.trim());
                                                                                    if (result) {
                                                                                        handleAddKP(idx, result.name);
                                                                                        setNewKPName('');
                                                                                        setShowKPSelector(null);
                                                                                    }
                                                                                } catch (err) {
                                                                                    console.error("Failed to add KP", err);
                                                                                } finally {
                                                                                    setIsAddingKP(false);
                                                                                }
                                                                            }}
                                                                            disabled={!newKPName.trim() || isAddingKP}
                                                                            className="px-3 py-1.5 bg-amber-500 hover:bg-amber-600 disabled:bg-amber-300 text-white rounded-lg text-xs font-bold shadow-sm transition-all active:scale-95"
                                                                        >
                                                                            {isAddingKP ? <div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <FaPlus size={10} />}
                                                                        </button>
                                                                    </div>
                                                                </div>
                                                            )}

                                                            <div className="overflow-y-auto custom-scrollbar flex-1">
                                                                {availableKPs.length > 0 ? (
                                                                    orderedCategories.map(cat => {
                                                                        const filtered = groupedKPs[cat].filter(kp => !(section.related_kps || []).includes(kp.name));
                                                                        if (filtered.length === 0) return null;

                                                                        return (
                                                                            <div key={cat} className="border-b border-amber-50 last:border-0">
                                                                                <div className="px-3 py-1.5 bg-gray-50/80 border-y border-gray-100/50 sticky top-0 z-10 backdrop-blur-sm">
                                                                                    <span className="text-[10px] font-bold text-gray-500 flex items-center gap-1.5">
                                                                                        <div className="w-1 h-3 bg-amber-400 rounded-full"></div>
                                                                                        {cat}
                                                                                    </span>
                                                                                </div>
                                                                                <div className="grid grid-cols-2 gap-px bg-amber-50/10">
                                                                                    {filtered.map((kp) => (
                                                                                        <button
                                                                                            key={kp.id}
                                                                                            onClick={(e) => {
                                                                                                e.stopPropagation();
                                                                                                handleAddKP(idx, kp.name);
                                                                                            }}
                                                                                            className="text-left px-3 py-2.5 text-xs hover:bg-amber-50 transition-colors flex items-start gap-2 border-b border-amber-50/30"
                                                                                        >
                                                                                            <FaLightbulb className="text-amber-500 shrink-0 mt-0.5" size={10} />
                                                                                            <span className="whitespace-normal break-words leading-relaxed text-neutral-700 font-medium">
                                                                                                {kp.name}
                                                                                            </span>
                                                                                        </button>
                                                                                    ))}
                                                                                </div>
                                                                            </div>
                                                                        );
                                                                    })
                                                                ) : (
                                                                    <div className="p-8 text-xs text-gray-500 text-center italic">
                                                                        目前無可用知識點
                                                                    </div>
                                                                )}
                                                            </div>
                                                        </div>
                                                    );
                                                })()}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>

                            {/* Content List */}
                            <div className="space-y-4 mb-4" >
                                {
                                    section.content_list.map((item, itemIdx) => (
                                        <SummaryListItem
                                            key={itemIdx}
                                            item={item}
                                            idx={itemIdx}
                                            sectionIdx={idx}
                                            isEditing={isEditing}
                                            onContentChange={handleContentChange}
                                            onDeleteContent={handleDeleteContent}
                                        />
                                    ))
                                }

                                {isEditing && (
                                    <button
                                        onClick={() => handleAddContent(idx)}
                                        className="flex items-center gap-2 px-3 py-1.5 text-sm text-gray-600 hover:text-theme-primary hover:bg-theme-primary/10 rounded transition-colors"
                                    >
                                        <FaPlus size={10} />
                                        新增要點
                                    </button>
                                )}
                            </div>

                            {/* References */}
                            {!isEditing && section.citations && section.citations.length > 0 && (
                                <div className="flex justify-end pt-3 border-t border-gray-50 mt-4 opacity-70 group-hover:opacity-100 transition-opacity">
                                    <div className="flex flex-wrap gap-2 justify-end">
                                        {section.citations.map((cite, cIdx) => (
                                            <button
                                                key={cIdx}
                                                onClick={() => {
                                                    if (onReferenceClick) {
                                                        const fullChunk = {
                                                            chunk_id: cite.chunk_id,
                                                            text: cite.text || '',
                                                            source: cite.source,
                                                            page_number: cite.page_number,
                                                            source_metadata: cite.source_metadata || {},
                                                            structured_content: cite.structured_content
                                                        };
                                                        onReferenceClick(cite.chunk_id, cite.text || "語義匹配", cite.match_score, fullChunk, idx, 'section');

                                                    }
                                                }}
                                                className="flex items-center gap-1.5 px-2 py-1 rounded-md text-xs transition-colors border bg-blue-50 text-blue-600 border-blue-100 hover:bg-blue-100"
                                            >
                                                <FaLink size={10} />
                                                <span className="max-w-[150px] truncate">{cite.source || '參照來源'}</span>
                                                {cite.page_number && (
                                                    <span className="font-mono text-[10px] opacity-80">
                                                        (P.{cite.page_number})
                                                    </span>
                                                )}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    ))}

                    {/* 新增 Section 按鈕 - 編輯模式限定 */}
                    {isEditing && (
                        <div className="pt-4 pb-8">
                            <button
                                onClick={handleAddSection}
                                className="w-full py-10 border-2 border-dashed border-blue-100 rounded-2xl bg-blue-50/20 text-blue-500 hover:bg-blue-50/40 hover:border-blue-200 hover:text-blue-600 transition-all flex flex-col items-center justify-center gap-4 group shadow-sm hover:shadow-md"
                            >
                                <div className="p-4 bg-white rounded-2xl shadow-sm border border-blue-50 group-hover:scale-110 transition-all duration-300">
                                    <FaPlus size={24} className="group-hover:rotate-90 transition-transform duration-500" />
                                </div>
                                <div className="text-center">
                                    <span className="font-black text-xl tracking-tight block">新增一個內容段落</span>
                                    <span className="text-sm opacity-60 font-medium">點擊在此下方建立一個新的重點摘要區塊</span>
                                </div>
                            </button>
                        </div>
                    )}
                </div>

                {/* Footer */}
                {!isEditing && (
                    <div className="pt-2 gap-y-2 flex flex-col">

                        <div className="scroll-mt-20" id="recommended-preview">
                            {(() => {
                                const allSummaryKPs = Array.from(new Set(sections.flatMap(s => s.related_kps || [])));
                                const resolvedKpIds = allSummaryKPs
                                    .map(name => availableKPs.find(akp => akp.name === name)?.id)
                                    .filter(id => id !== undefined)
                                    .map(id => parseInt(id as string));

                                const config = (isEditing && tempSummary?.recommendation_config)
                                    ? tempSummary.recommendation_config
                                    : (summary.recommendation_config || { total_max: 10, count_per_kp: 3, enabled: true });

                                const kpsWithQuestionsCount = allSummaryKPs.filter(kp => (kpStats[kp] || 0) > 0).length;
                                const totalQuestionsCount = allSummaryKPs.reduce((sum, kp) => sum + (kpStats[kp] || 0), 0);

                                if (isTeacher) {
                                    return (
                                        <div className="space-y-4">
                                            <TeacherRecommendedPreview
                                                knowledgePointIds={resolvedKpIds}
                                                courseId={courseId}
                                                stage={materialType === 'review' ? 'review' : 'preview'}
                                                countPerKp={config.count_per_kp || 3}
                                                totalMax={config.total_max || 10}
                                                totalQuestions={totalQuestionsCount}
                                                kpsWithQuestions={kpsWithQuestionsCount}
                                                enabled={config.enabled !== false}
                                                onConfigChange={(newConfig: { count_per_kp?: number; total_max?: number; enabled?: boolean }) => {
                                                    if (isEditing) {
                                                        setTempSummary(prev => prev ? {
                                                            ...prev,
                                                            recommendation_config: { ...prev.recommendation_config, ...newConfig }
                                                        } : null);
                                                    } else if (onContentChange) {
                                                        onContentChange({
                                                            recommendation_config: { ...config, ...newConfig }
                                                        });
                                                    }
                                                }}
                                                onKPLookup={onKPLookup}
                                            />
                                        </div>
                                    );
                                }

                                return null;
                            })()}
                        </div>

                        {isTeacher && <div className="h-px bg-gray-100 my-4 opacity-70" />}

                        {isTeacher && (
                            <>
                                <div className="py-2 space-y-4">
                                    <div className="flex items-center justify-between mb-4">
                                        <div className="flex items-center gap-3">
                                            <div className="w-10 h-10 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center shadow-sm">
                                                <FaLightbulb size={20} />
                                            </div>
                                            <div>
                                                <h4 className="text-lg font-bold text-neutral-text-main">知識點練習覆蓋率總覽</h4>
                                                <p className="text-sm text-neutral-text-secondary">檢查教材中各知識點是否有足夠題項，若不足可一鍵生成</p>
                                            </div>
                                        </div>

                                        <button
                                            onClick={() => setShowGenerateConfirm(true)}
                                            className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-blue-50 text-blue-600 border border-blue-200 text-sm font-semibold hover:bg-blue-100 transition-colors"
                                        >
                                            <FaMagic size={12} />
                                            為題目不足的知識點生成 ({lowCoverageKps.length})
                                        </button>
                                    </div>

                                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                                        {allKps.map(kp => {
                                            const count = kpStats[kp] || 0;
                                            const isGood = count >= 3;
                                            const isMid = count >= 1 && count < 3;

                                            return (
                                                <div
                                                    key={kp}
                                                    className={`px-3 py-2.5 rounded-xl border-2 bg-white flex items-center justify-between gap-2 transition-all ${isGood
                                                        ? 'border-blue-300 hover:shadow-sm'
                                                        : isMid
                                                            ? 'border-yellow-300'
                                                            : 'border-orange-300'
                                                        }`}
                                                >
                                                    <div className="flex items-center gap-2 min-w-0">
                                                        {isGood ? (
                                                            <FaCheck className="text-blue-500 shrink-0" size={13} />
                                                        ) : (
                                                            <HiOutlineViewGridAdd
                                                                className={`shrink-0 ${isMid ? 'text-yellow-500' : 'text-orange-400'}`}
                                                                size={15}
                                                            />
                                                        )}
                                                        <span className="text-sm font-medium text-neutral-text-main leading-snug break-words">
                                                            {kp}
                                                        </span>
                                                    </div>
                                                    <div className="flex items-center gap-1.5 shrink-0">
                                                        <span className={`text-xs font-bold px-2 py-0.5 rounded-full whitespace-nowrap ${isGood
                                                            ? 'bg-blue-50 text-blue-600'
                                                            : isMid
                                                                ? 'bg-yellow-50 text-yellow-700'
                                                                : 'bg-orange-50 text-orange-600'
                                                            }`}>
                                                            {count} 題
                                                        </span>
                                                        {onKPLookup && (
                                                            <button
                                                                onClick={() => {
                                                                    const kpObj = availableKPs?.find(akp => akp.name === kp);
                                                                    onKPLookup(kp, kpObj ? Number(kpObj.id) : undefined);
                                                                }}
                                                                className="p-2 text-gray-400 hover:text-theme-primary hover:bg-theme-primary/5 rounded-lg transition-all"
                                                                title="在題庫中查看"
                                                            >
                                                                <FaSearch size={14} />
                                                            </button>
                                                        )}
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            </>
                        )}

                        <div className="flex justify-center text-gray-400 text-[10px] py-1">
                            <span className="flex items-center gap-1.5 opacity-80">
                                <FaBookOpen />
                                AI 生成內容 • 僅供教學參考
                            </span>
                        </div>
                    </div>
                )
                }
            </div >

            <ConfirmDialog
                isOpen={showGenerateConfirm}
                title="確認為題目不足知識點生成練習？"
                message={
                    <div className="space-y-4">
                        <div className="text-neutral-text-main font-semibold">
                            系統將引導您為下列題目不足的知識點生成練習：
                        </div>

                        <div className="flex flex-wrap gap-1.5 py-1">
                            {lowCoverageKps.map(kp => (
                                <span key={kp} className="px-2.5 py-1 bg-blue-50 text-blue-600 rounded-lg border border-blue-100 text-xs font-bold shadow-sm">
                                    {kp}
                                </span>
                            ))}
                        </div>

                        <div className="text-sm text-neutral-text-secondary pt-2 border-t border-gray-50">
                            上述知識點與「簡答題」題型將於設定參數設定介面被鎖定。
                            <p className="mt-2 text-amber-700 font-medium">
                                ⚠️ 跳轉前請先確認您對此教材的編修是否已完成。
                            </p>
                        </div>
                    </div>
                }
                confirmText="儲存並跳轉"
                cancelText="繼續編輯"
                onConfirm={() => {
                    setShowGenerateConfirm(false);
                    if (isEditing && onSaveEdit) {
                        onSaveEdit();
                    }
                    const url = `/teacher/courses/${courseId}/generate?type=exam${unitId ? `&unit_id=${unitId}` : ''}`;
                    navigate(url, {
                        state: {
                            preSelectedKPs: lowCoverageKps,
                            preSelectedType: 'short_answer',
                            sourceContentId: contentId
                        }
                    });
                }}
                onCancel={() => setShowGenerateConfirm(false)}
            />
        </>
    );
});
