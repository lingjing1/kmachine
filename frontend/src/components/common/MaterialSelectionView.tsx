import { useState } from 'react';
import { useDropzone } from 'react-dropzone';
import {
    FaSpinner, FaHistory, FaCalendarAlt,
    FaPen, FaTrash, FaCheck, FaTimes, FaGlobe, FaCloudUploadAlt,
    FaCheckCircle, FaTimesCircle, FaSortAmountDown, FaSortAmountUp
} from 'react-icons/fa';
import { getFileIcon } from '../../utils/contentUtils';
import { formatDateTime } from '../../utils/dateUtils';

export interface MaterialOption {
    id: number;
    file_name: string;
    unique_content_id: number;
    processing_status?: 'pending' | 'in_progress' | 'completed' | 'failed';
    created_at?: string;
    file_path?: string;
    source_type?: string;
    file_type?: string;
}

export interface GeneratedMaterialOption {
    id: number;
    title: string;
    content_type: string;
    content_subtype?: string | null;
    created_at: string;
    job_id?: number;
    unit_id?: number | null;
    source_type?: string;
    source_id?: number;
    content?: any;
}

export interface MaterialSelectionViewProps {
    activeTab: 'uploaded' | 'generated';
    onTabChange: (tab: 'uploaded' | 'generated') => void;
    hideUploadedTab?: boolean;

    materials: MaterialOption[];
    generatedMaterials: GeneratedMaterialOption[];
    courseUnits?: Array<{ id: number; name: string; topic_id?: number }>;

    selectedKeys: Set<string>;
    onSelectionChange: (keys: Set<string>) => void;
    onGeneratedClick?: (material: GeneratedMaterialOption) => void;

    isUploading?: boolean;
    onUploadFile?: (file: File) => Promise<void>;
    onUploadUrl?: (url: string) => Promise<void>;

    onRename?: (id: number, newName: string) => Promise<boolean>;
    onDelete?: (id: number) => Promise<boolean>;

    // [New] Existing items in the target unit to filter out duplicates
    existingContents?: any[];

    isLoading?: boolean;
    isFetching?: boolean;
    // Bottom Action Bar (Optional in view)
    footerActions?: React.ReactNode;
}

export default function MaterialSelectionView({
    activeTab,
    onTabChange,
    hideUploadedTab,
    materials,
    generatedMaterials,
    courseUnits = [],
    selectedKeys,
    onSelectionChange,
    onGeneratedClick,
    isUploading,
    onUploadFile,
    onUploadUrl,
    onRename,
    onDelete,
    existingContents = [],
    isLoading = false,
    isFetching = false,
    footerActions
}: MaterialSelectionViewProps) {
    // Sort Configs
    const [uploadSort, setUploadSort] = useState<{ key: 'date' | 'name' | 'type', direction: 'asc' | 'desc' }>({ key: 'date', direction: 'desc' });
    const [genSort, setGenSort] = useState<{ key: 'date' | 'name' | 'type', direction: 'asc' | 'desc' }>({ key: 'date', direction: 'desc' });

    // [New] Historical Sub-tabs state
    const [activeSubTab, setActiveSubTab] = useState<'all' | 'preview' | 'review' | 'homework' | 'exam'>('all');

    // Rename State
    const [editingMaterialId, setEditingMaterialId] = useState<number | null>(null);
    const [editingName, setEditingName] = useState('');

    // URL Input
    const [urlInput, setUrlInput] = useState('');

    // Error State
    const [uploadError, setUploadError] = useState<string>('');

    const { getRootProps, getInputProps, isDragActive } = useDropzone({
        onDrop: async (acceptedFiles) => {
            if (acceptedFiles.length > 0) {
                const file = acceptedFiles[0];
                if (file.size === 0) {
                    setUploadError('您選擇的檔案內容為空，請確認您選擇的檔案。');
                    return;
                }
                setUploadError('');
                if (onUploadFile) await onUploadFile(file);
            }
        },
        maxFiles: 1,
        accept: {
            'application/pdf': ['.pdf'],
            'application/msword': ['.doc'],
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
            'application/vnd.ms-powerpoint': ['.ppt'],
            'application/vnd.openxmlformats-officedocument.presentationml.presentation': ['.pptx'],
            'text/plain': ['.txt'],
            'image/jpeg': ['.jpg', '.jpeg'],
            'image/png': ['.png']
        }
    });

    const handleSourceSelect = (id: number, type: 'uploaded' | 'generated', item?: any) => {
        if (type === 'generated' && onGeneratedClick && item) {
            onGeneratedClick(item);
            return;
        }
        const key = `${type}:${id}`;
        const newSet = new Set(selectedKeys);
        if (newSet.has(key)) {
            newSet.delete(key);
        } else {
            newSet.add(key);
        }
        onSelectionChange(newSet);
    };

    const handleRenameSubmit = async (id: number) => {
        if (!onRename) return;
        const success = await onRename(id, editingName);
        if (success) {
            setEditingMaterialId(null);
        }
    };

    const sortedMaterials = materials
        .filter(m => {
            if (m.processing_status === 'failed') return false;

            // [FIX] Filter out uploaded materials already in this unit
            const exists = existingContents.some(c =>
                c.source_id === m.unique_content_id &&
                c.source_type === 'uploaded_content'
            );
            return !exists;
        })
        .sort((a, b) => {
            let res = 0;
            if (uploadSort.key === 'date') {
                res = new Date(a.created_at || 0).getTime() - new Date(b.created_at || 0).getTime();
            } else if (uploadSort.key === 'name') {
                res = (a.file_name || '').localeCompare(b.file_name || '');
            } else if (uploadSort.key === 'type') {
                res = (a.file_name?.split('.').pop() || '').localeCompare(b.file_name?.split('.').pop() || '');
            }
            return uploadSort.direction === 'asc' ? res : -res;
        });

    // [FIX] Filter out items already in the target unit (by source_id)
    const filteredGenerated = generatedMaterials.filter(m => {
        // Find if this source is already used in course_contents of this unit
        const exists = existingContents.some(c =>
            c.source_id === m.id &&
            c.source_type === 'generated_content'
        );
        if (exists) return false;

        // Apply sub-tab filtering
        if (activeSubTab === 'preview') return m.content_subtype === 'preview';
        if (activeSubTab === 'review') return m.content_subtype === 'review';

        // Add support for Exam tabs
        if (activeSubTab === 'homework') return m.content_subtype === 'homework';
        if (activeSubTab === 'exam') return m.content_subtype === 'quiz' || m.content_subtype === 'midterm' || m.content_subtype === 'final' || m.content_subtype === 'exam';

        return true;
    });

    const sortedGenerated = filteredGenerated.sort((a, b) => {
        let res = 0;
        if (genSort.key === 'date') {
            res = new Date(a.created_at || 0).getTime() - new Date(b.created_at || 0).getTime();
        } else if (genSort.key === 'name') {
            res = (a.title || '').localeCompare(b.title || '');
        } else if (genSort.key === 'type') {
            // Content type sort fallback
            res = (a.content_subtype || a.content_type || '').localeCompare(b.content_subtype || b.content_type || '');
        }
        return genSort.direction === 'asc' ? res : -res;
    });

    return (
        <div className="flex flex-col h-full bg-white bg-opacity-100">
            {/* Tabs */}
            <div className="flex border-b border-neutral-border shrink-0 bg-white">
                {!hideUploadedTab && (
                    <button
                        onClick={() => onTabChange('uploaded')}
                        className={`flex-1 py-3 text-sm font-medium transition-colors ${activeTab === 'uploaded'
                            ? 'text-theme-primary border-b-2 border-theme-primary bg-theme-primary-light/10'
                            : 'text-neutral-text-secondary hover:text-neutral-text-main'
                            }`}
                    >
                        已上傳教材 ({sortedMaterials.length})
                    </button>
                )}
                <button
                    onClick={() => onTabChange('generated')}
                    className={`flex-1 py-3 text-sm font-medium transition-colors ${activeTab === 'generated'
                        ? 'text-theme-primary border-b-2 border-theme-primary bg-theme-primary-light/10'
                        : 'text-neutral-text-secondary hover:text-neutral-text-main'
                        } ${hideUploadedTab ? 'border-b-2 border-theme-primary text-theme-primary bg-theme-primary-light/5' : ''}`}
                >
                    歷史生成紀錄 {isLoading ? <FaSpinner className="inline animate-spin ml-1 w-3 h-3" /> : `(${sortedGenerated.length})`}
                </button>
            </div>

            {/* Content Area */}
            <div className="flex-1 flex overflow-hidden">
                {activeTab === 'uploaded' && !hideUploadedTab && (
                    <div className="flex-1 flex flex-col md:flex-row h-full">
                        {/* List Area */}
                        <div className="w-full md:w-3/5 flex flex-col min-w-0 bg-gray-50 h-full overflow-hidden relative">
                            <div className="p-3 border-b border-gray-200 flex items-center justify-between shrink-0 bg-white/80 backdrop-blur-md z-10 sticky top-0">
                                <span className="text-xs font-bold text-gray-500 uppercase tracking-wider pl-2">
                                    參考資料列表
                                </span>
                                <div className="flex items-center gap-2">
                                    <span className="text-xs text-gray-500 mr-1">排序:</span>
                                    {(['date', 'type', 'name'] as const).map((key) => (
                                        <button
                                            key={key}
                                            onClick={() => setUploadSort(prev => ({
                                                key,
                                                direction: prev.key === key && prev.direction === 'desc' ? 'asc' : 'desc'
                                            }))}
                                            className={`px-2 py-1 text-xs font-medium rounded-md transition-all flex items-center gap-1 ${uploadSort.key === key
                                                ? 'bg-white text-theme-primary shadow-sm border border-theme-primary'
                                                : 'bg-transparent text-gray-500 hover:bg-gray-200 hover:text-gray-700'
                                                }`}
                                        >
                                            {key === 'date' && '時間'}
                                            {key === 'type' && '類型'}
                                            {key === 'name' && '名稱'}
                                            {uploadSort.key === key && (
                                                uploadSort.direction === 'desc' ? <FaSortAmountDown /> : <FaSortAmountUp />
                                            )}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            <div className="flex-1 overflow-y-auto p-4 scroll-smooth">
                                {sortedMaterials.length === 0 ? (
                                    <div className="h-full flex flex-col items-center justify-center text-neutral-text-secondary opacity-60 pb-10">
                                        <FaCloudUploadAlt className="w-12 h-12 mb-3 text-gray-300" />
                                        <p className="text-sm font-medium">尚未上傳任何教材</p>
                                    </div>
                                ) : (
                                    <div className="grid grid-cols-1 gap-3">
                                        {sortedMaterials.map((material) => {
                                            const key = `uploaded:${material.unique_content_id}`;
                                            const isSelected = selectedKeys.has(key);
                                            const isProcessing = material.processing_status === 'pending' || material.processing_status === 'in_progress';
                                            const isFailed = material.processing_status === 'failed';

                                            return (
                                                <div
                                                    key={material.id}
                                                    className={`flex items-center gap-3 p-3 border rounded-lg transition-all relative group bg-white hover:shadow-sm ${isSelected
                                                        ? 'border-theme-primary bg-blue-50/50 ring-1 ring-theme-primary'
                                                        : 'border-gray-200 hover:border-gray-300'
                                                        } ${isProcessing || isFailed ? 'opacity-80' : 'cursor-pointer'}`}
                                                    onClick={() => !isProcessing && !isFailed && handleSourceSelect(material.unique_content_id, 'uploaded')}
                                                >
                                                    <div className="flex items-center justify-center w-10 h-10 bg-gray-50 rounded-lg shrink-0 text-lg">
                                                        {isProcessing ? (
                                                            <FaSpinner className="animate-spin text-theme-primary w-4 h-4" />
                                                        ) : isFailed ? (
                                                            <FaTimesCircle className="text-red-500 w-4 h-4" />
                                                        ) : (
                                                            (() => {
                                                                const isWeb = material.file_path?.startsWith('http') || material.source_type === 'web' || material.source_type === 'url' || material.file_type === 'web';
                                                                const type = material.file_type || (isWeb ? 'url' : 'file');
                                                                return getFileIcon(type, material.file_name || '', 24, "flex items-center justify-center");
                                                            })()
                                                        )}
                                                    </div>

                                                    <div className="flex-1 min-w-0">
                                                        {editingMaterialId === material.id ? (
                                                            <div className="flex items-center gap-1 pr-10" onClick={(e) => e.stopPropagation()}>
                                                                <input
                                                                    type="text"
                                                                    value={editingName}
                                                                    onChange={(e) => setEditingName(e.target.value)}
                                                                    onKeyDown={(e) => {
                                                                        if (e.key === 'Enter') handleRenameSubmit(material.id);
                                                                        else if (e.key === 'Escape') setEditingMaterialId(null);
                                                                    }}
                                                                    autoFocus
                                                                    className="flex-1 text-sm font-medium border border-theme-primary rounded px-2 py-0.5 focus:outline-none focus:ring-1 focus:ring-theme-primary min-w-0"
                                                                />
                                                                <button onClick={() => handleRenameSubmit(material.id)} className="p-1 text-green-600 hover:bg-green-50 rounded bg-white shadow-sm border"><FaCheck size={12} /></button>
                                                                <button onClick={() => setEditingMaterialId(null)} className="p-1 text-gray-400 hover:text-red-500 rounded bg-white shadow-sm border"><FaTimes size={12} /></button>
                                                            </div>
                                                        ) : (
                                                            <div className="font-medium text-sm text-gray-900 truncate pr-16" title={material.file_name}>
                                                                {material.file_name}
                                                            </div>
                                                        )}
                                                        <div className="flex items-center gap-2 mt-0.5">
                                                            {material.created_at && (
                                                                <span className="text-[10px] text-gray-400 flex items-center gap-1">
                                                                    <FaCalendarAlt className="w-3 h-3" />
                                                                    {formatDateTime(material.created_at)}
                                                                </span>
                                                            )}
                                                            {isProcessing && <span className="text-[10px] text-theme-primary font-bold bg-blue-50 px-1.5 py-0.5 rounded">處理中</span>}
                                                            {isFailed && <span className="text-[10px] text-red-600 font-bold bg-red-50 px-1.5 py-0.5 rounded">失敗</span>}
                                                        </div>
                                                    </div>

                                                    {isSelected && <div className="text-theme-primary absolute right-3"><FaCheckCircle size={20} /></div>}

                                                    {onRename && onDelete && (
                                                        <div className={`absolute right-2 top-1/2 -translate-y-1/2 flex items-center transition-opacity ${editingMaterialId === material.id ? 'hidden' : (isSelected ? 'mr-6 opacity-0 group-hover:opacity-100' : 'opacity-0 group-hover:opacity-100')}`}>
                                                            <button
                                                                onClick={(e) => { e.stopPropagation(); setEditingMaterialId(material.id); setEditingName(material.file_name); }}
                                                                className="p-2 text-gray-400 hover:text-theme-primary rounded-full bg-white shadow-sm border mr-1" title="重新命名"
                                                            >
                                                                <FaPen size={12} />
                                                            </button>
                                                            <button
                                                                onClick={(e) => { e.stopPropagation(); onDelete(material.id); }}
                                                                className="p-2 text-gray-400 hover:text-red-500 rounded-full bg-white shadow-sm border" title="刪除"
                                                            >
                                                                <FaTrash size={14} />
                                                            </button>
                                                        </div>
                                                    )}
                                                </div>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Upload Input Area */}
                        <div className="w-full md:w-2/5 shrink-0 flex flex-col justify-center border-l border-gray-200 bg-white z-10 overflow-y-auto w-full">
                            <div className="p-5 space-y-6">
                                {onUploadFile && (
                                    <div className="space-y-2">
                                        <h3 className="font-bold text-gray-700 flex items-center gap-2 text-base">
                                            <FaCloudUploadAlt className="text-theme-primary" /> 上傳本機檔案
                                        </h3>
                                        <div
                                            {...getRootProps()}
                                            className={`border-2 border-dashed rounded-xl p-4 text-center transition-all cursor-pointer group flex flex-col items-center justify-center min-h-[120px] ${isDragActive ? 'border-theme-primary bg-blue-50' : (uploadError ? 'border-red-300 bg-red-50' : 'border-gray-300 hover:border-theme-primary')}`}
                                        >
                                            <input {...getInputProps()} />
                                            <div className={`w-8 h-8 rounded-full flex items-center justify-center mb-2 ${uploadError ? 'bg-red-100' : 'bg-gray-100'}`}>
                                                <FaCloudUploadAlt className={`w-4 h-4 ${uploadError ? 'text-red-500' : 'text-gray-400 group-hover:text-theme-primary'}`} />
                                            </div>
                                            <p className={`text-sm font-medium ${uploadError ? 'text-red-600' : 'text-gray-700'}`}>
                                                點擊或拖曳檔案上傳
                                            </p>
                                        </div>
                                        {uploadError && (
                                            <p className="text-red-500 text-xs mt-1 animate-in slide-in-from-top-1">{uploadError}</p>
                                        )}
                                    </div>
                                )}

                                {onUploadFile && onUploadUrl && (
                                    <div className="relative py-2">
                                        <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-gray-200"></div></div>
                                        <div className="relative flex justify-center"><span className="px-3 bg-white text-xs text-gray-400">或</span></div>
                                    </div>
                                )}

                                {onUploadUrl && (
                                    <div className="space-y-2">
                                        <h3 className="font-bold text-gray-700 flex items-center gap-2 text-base">
                                            <FaGlobe className="text-blue-500" /> 匯入網頁連結
                                        </h3>
                                        <div className="flex gap-2">
                                            <input
                                                type="url"
                                                value={urlInput}
                                                onChange={(e) => setUrlInput(e.target.value)}
                                                onKeyDown={(e) => { if (e.key === 'Enter' && urlInput.trim()) { setUrlInput(''); onUploadUrl(urlInput); } }}
                                                placeholder="https://..."
                                                className="flex-1 px-3 py-2 border rounded-lg focus:ring-2 focus:ring-theme-primary text-sm h-9"
                                                disabled={isUploading}
                                            />
                                            <button
                                                onClick={() => { setUrlInput(''); onUploadUrl(urlInput); }}
                                                disabled={!urlInput.trim() || isUploading}
                                                className="px-3 py-1.5 bg-neutral-800 text-white rounded-lg hover:bg-neutral-700 disabled:opacity-50 text-sm font-medium h-9"
                                            >
                                                {isUploading ? '處理中' : '匯入'}
                                            </button>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                )}

                {activeTab === 'generated' && (
                    <div className="flex-1 flex flex-col min-w-0 bg-white h-full overflow-hidden relative">
                        <div className="p-3 border-b border-gray-200 flex items-center justify-between shrink-0 bg-white/80 backdrop-blur-md z-10 sticky top-0">
                            <div className="flex items-center gap-4">
                                <span className="text-xs font-bold text-gray-500 uppercase tracking-wider pl-2 flex items-center gap-2">
                                    歷史生成紀錄
                                    {isFetching && !isLoading && <FaSpinner className="animate-spin text-theme-primary opacity-60 w-3 h-3" />}
                                </span>

                                {/* [New] Type Filter Tabs */}
                                <div className="flex bg-gray-100 p-0.5 rounded-lg border border-gray-200">
                                    {(hideUploadedTab ? ['all', 'homework', 'exam'] as const : ['all', 'preview', 'review'] as const).map((tab) => (
                                        <button
                                            key={tab}
                                            onClick={() => setActiveSubTab(tab)}
                                            className={`px-3 py-1 text-[11px] font-bold rounded-md transition-all ${activeSubTab === tab
                                                ? 'bg-white text-theme-primary shadow-sm'
                                                : 'text-gray-500 hover:text-gray-700'
                                                }`}
                                        >
                                            {tab === 'all' && '全部'}
                                            {tab === 'preview' && '預習'}
                                            {tab === 'review' && '複習'}
                                            {tab === 'homework' && '作業'}
                                            {tab === 'exam' && '考試'}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            <div className="flex items-center gap-2">
                                <span className="text-xs text-gray-500 mr-1">排序:</span>
                                {(['date', 'name'] as const).map((key) => (
                                    <button
                                        key={key}
                                        onClick={() => setGenSort(prev => ({ key, direction: prev.key === key && prev.direction === 'desc' ? 'asc' : 'desc' }))}
                                        className={`px-2 py-1 text-xs font-medium rounded-md transition-all flex items-center gap-1 ${genSort.key === key ? 'bg-white text-theme-primary border border-theme-primary' : 'text-gray-500'}`}
                                    >
                                        {key === 'date' && '時間'}
                                        {key === 'name' && '名稱'}
                                        {genSort.key === key && (genSort.direction === 'desc' ? <FaSortAmountDown /> : <FaSortAmountUp />)}
                                    </button>
                                ))}
                            </div>
                        </div>

                        <div className="flex-1 overflow-y-auto p-4 scroll-smooth">
                            {isLoading ? (
                                <div className="h-full flex flex-col items-center justify-center text-theme-primary pb-10">
                                    <FaSpinner className="w-10 h-10 mb-4 animate-spin opacity-80" />
                                    <p className="text-sm font-bold tracking-widest animate-pulse">正在載入歷史紀錄...</p>
                                </div>
                            ) : sortedGenerated.length === 0 ? (
                                <div className="h-full flex flex-col items-center justify-center">
                                    <div className="flex flex-col items-center opacity-40 -mt-12">
                                        <FaHistory className="w-12 h-12 mb-3 text-gray-300" />
                                        <p className="text-sm font-medium text-neutral-text-secondary">尚無歷史生成紀錄</p>
                                    </div>
                                </div>
                            ) : (
                                <div className="grid grid-cols-1 gap-3">
                                    {sortedGenerated.map((material) => {
                                        const key = `generated:${material.id}`;
                                        const isSelected = selectedKeys.has(key);

                                        return (
                                            <div
                                                key={material.id}
                                                className={`flex items-center gap-3 p-3 border rounded-lg transition-all relative group bg-white hover:shadow-sm ${isSelected ? 'border-theme-primary bg-blue-50/50 ring-1 ring-theme-primary' : 'border-gray-200 hover:border-gray-300'} cursor-pointer`}
                                                onClick={() => handleSourceSelect(material.id, 'generated', material)}
                                            >
                                                {getFileIcon(material.content_type || 'material', material.title, 20, "flex items-center justify-center w-10 h-10 bg-blue-50 rounded-full shrink-0 text-lg text-blue-600", material.content_subtype)}

                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-2 mb-0.5 pr-6">
                                                        <div className="font-medium text-sm text-gray-900 truncate" title={material.title}>
                                                            {material.title}
                                                        </div>
                                                    </div>
                                                    <div className="flex items-center gap-2 mt-0.5">
                                                        {material.content_subtype === 'preview' && (
                                                            <span className="text-[10px] px-2 py-0.5 bg-blue-100 text-blue-700 rounded-full font-medium shrink-0">預習</span>
                                                        )}
                                                        {material.content_subtype === 'review' && (
                                                            <span className="text-[10px] px-2 py-0.5 bg-blue-100 text-blue-700 rounded-full font-medium shrink-0">複習</span>
                                                        )}
                                                        <span className="text-[10px] text-gray-400 flex items-center gap-1 shrink-0">
                                                            <FaCalendarAlt className="w-3 h-3" />
                                                            {formatDateTime(material.created_at) || 'N/A'}
                                                        </span>
                                                        {material.unit_id !== null && material.unit_id !== undefined && (() => {
                                                            const unit = courseUnits.find(u => u.id === material.unit_id);
                                                            const unitLabel = unit ? `${unit.topic_id || ''}. ${unit.name}` : `章節 ${material.unit_id}`;
                                                            return (
                                                                <span className="text-[10px] px-2 py-0.5 bg-blue-100 text-blue-700 rounded-full font-medium truncate shrink-0 max-w-[200px]" title={`章節${unitLabel}`}>
                                                                    章節{unitLabel}
                                                                </span>
                                                            );
                                                        })()}
                                                    </div>
                                                </div>
                                                {isSelected && <div className="text-theme-primary absolute right-3"><FaCheckCircle size={20} /></div>}
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>

            {/* Footer */}
            {footerActions && (
                <div className="p-4 border-t border-gray-200 bg-white shrink-0 flex items-center justify-end gap-3 z-10 shadow-sm relative">
                    {footerActions}
                </div>
            )}
        </div>
    );
}
