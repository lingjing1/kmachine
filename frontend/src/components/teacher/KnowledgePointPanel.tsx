import React, { useState, useEffect, useRef } from 'react';
import ReactDOM from 'react-dom';
import {
    FaSpinner, FaExclamationTriangle, FaSync,
    FaProjectDiagram, FaQuestionCircle, FaCheckSquare, FaRegSquare,
    FaPlus, FaPen, FaTrash, FaCheck, FaTimes,
    FaRobot, FaLightbulb, FaSortAlphaDown, FaSortNumericDown, FaSortNumericUp
} from 'react-icons/fa';
import { MdOpenInFull, MdCloseFullscreen } from 'react-icons/md';
import mermaid from 'mermaid';
import Modal from '../common/Modal';
import Toast from '../common/Toast';
import Tooltip from '../common/Tooltip';
import {
    extractKP, getKPMap, getUnitKPs, createUnitKP, updateUnitKP,
    deleteUnitKP, promoteKPs, KPMap, UnitKP,
} from '../../services/kpApi';

mermaid.initialize({
    startOnLoad: false,
    theme: 'base',
    themeVariables: {
        primaryColor: '#dbeafe',
        primaryTextColor: '#1e3a8a',
        primaryBorderColor: '#2563eb',
        lineColor: '#3b82f6',
        secondaryColor: '#93c5fd',
        tertiaryColor: '#1d4ed8',
        fontFamily: 'Inter, system-ui, -apple-system, sans-serif',
        fontSize: '14px',
        nodeBorder: '2px',
        clusterBkg: '#eff6ff',
        clusterBorder: '#3b82f6',
        edgeLabelBackground: '#eff6ff',
        mainBkg: '#dbeafe',
        nodeTextColor: '#1e3a8a',
    },
    flowchart: { htmlLabels: true, curve: 'basis', padding: 15, nodeSpacing: 30, rankSpacing: 30, diagramPadding: 10, useMaxWidth: false },
});

mermaid.parseError = (err) => console.error('Mermaid Parse Error:', err);

// ==================== Exported types ====================
export interface KPDetail {
    id: number;
    mermaid_id: string;
    name: string;
    level: string;
    description: string;
}

// ==================== Props ====================
interface KnowledgePointPanelProps {
    activePreviewKey: string | null;
    selectedSourceKeys: Set<string>;
    loading: boolean;
    error: string;
    handleGenerate: () => void;
    onKPSelectionChange?: (selectedKPs: Set<number>, kpDetails: KPDetail[]) => void;
    userId?: number;
    courseId?: number;
    unitId?: number;
    preSelectedNames?: string[];
    weakKPNames?: string[];
    onActionLog?: (section: 'kp' | 'source' | 'prompt' | 'general', action_type: string, action_config?: any, duration_ms?: number) => void;
}

export default function KnowledgePointPanel({
    activePreviewKey,
    selectedSourceKeys,
    loading: generateLoading,
    error: generateError,
    handleGenerate,
    onKPSelectionChange,
    userId = 1,
    courseId,
    unitId,
    preSelectedNames,
    weakKPNames,
    onActionLog,
}: KnowledgePointPanelProps) {

    // ---- Extracted KP states ----
    const [kpMap, setKpMap] = useState<KPMap | null>(null);
    const [loadingExtracted, setLoadingExtracted] = useState(false);
    const [isExtracting, setIsExtracting] = useState(false);
    const [extractedError, setExtractedError] = useState<string | null>(null);
    const [promotingKPs, setPromotingKPs] = useState<Set<string>>(new Set());
    const [promotedKPs, setPromotedKPs] = useState<Set<string>>(new Set());
    const [showReExtractConfirm, setShowReExtractConfirm] = useState(false);

    // ---- Unit KP states ----
    const [unitKPs, setUnitKPs] = useState<UnitKP[]>([]);
    const [loadingUnitKPs, setLoadingUnitKPs] = useState(false);
    const [unitKPError, setUnitKPError] = useState<string | null>(null);
    const [selectedKPIds, setSelectedKPIds] = useState<Set<number>>(new Set());

    // ---- Manual add ----
    const [showAddInput, setShowAddInput] = useState(false);
    const [newKPName, setNewKPName] = useState('');
    const [addingKP, setAddingKP] = useState(false);
    const [addError, setAddError] = useState<string | null>(null);

    // ---- Edit ----
    const [editingKPId, setEditingKPId] = useState<number | null>(null);
    const [editingName, setEditingName] = useState('');
    const [savingEdit, setSavingEdit] = useState(false);

    // ---- Delete ----
    const [deletingKP, setDeletingKP] = useState<UnitKP | null>(null);

    // ---- UI ----
    const [showHelp, setShowHelp] = useState(false);
    const [showExtractPanel, setShowExtractPanel] = useState(false);
    const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' | 'info' } | null>(null);
    const [sortMode, setSortMode] = useState<'time_desc' | 'time_asc' | 'extracted_first' | 'manual_first' | null>('time_desc');
    const initializedRef = useRef(false);
    const selectionInitializedRef = useRef(false);

    // ---- Map pan/zoom ----
    const [zoom, setZoom] = useState(1);
    const [minZoom, setMinZoom] = useState(0.5);
    const [pan, setPan] = useState({ x: 0, y: 0 });
    const [isDragging, setIsDragging] = useState(false);
    const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
    const [svgContent, setSvgContent] = useState('');
    const mapContainerRef = useRef<HTMLDivElement>(null);

    const uniqueContentId = activePreviewKey?.startsWith('uploaded:')
        ? parseInt(activePreviewKey.split(':')[1])
        : null;

    // ---- Load unit KPs ----
    useEffect(() => {
        if (!courseId || !unitId) return;
        setLoadingUnitKPs(true);
        setUnitKPError(null);
        getUnitKPs(courseId, unitId)
            .then(setUnitKPs)
            .catch(() => setUnitKPError('載入單元知識點失敗'))
            .finally(() => setLoadingUnitKPs(false));
    }, [courseId, unitId]);

    // Notify parent of map open/close
    const prevShowExtractPanelRef = useRef(false);
    useEffect(() => {
        if (prevShowExtractPanelRef.current !== showExtractPanel) {
            if (showExtractPanel) {
                onActionLog?.('kp', 'MAP_OPEN');
            } else {
                onActionLog?.('kp', 'MAP_CLOSE');
            }
            prevShowExtractPanelRef.current = showExtractPanel;
        }
    }, [showExtractPanel, onActionLog]);

    // ---- Load extracted KPs when preview changes ----
    useEffect(() => {
        let ignore = false;
        if (!uniqueContentId) { setKpMap(null); setExtractedError(null); return; }
        setIsExtracting(false);
        setLoadingExtracted(true);
        setExtractedError(null);
        setKpMap(null);
        setPromotedKPs(new Set());
        getKPMap(uniqueContentId, userId)
            .then(res => { if (!ignore) setKpMap(res.kp_map); })
            .catch(err => {
                if (!ignore) {
                    if (err.message === 'NO_KP_FOUND') setKpMap(null);
                    else setExtractedError('載入知識點失敗');
                }
            })
            .finally(() => { if (!ignore) setLoadingExtracted(false); });
        return () => { ignore = true; };
    }, [uniqueContentId, userId]);

    // ---- Render Mermaid when panel opens or kpMap changes ----
    useEffect(() => {
        if (!showExtractPanel || !kpMap?.mermaid_graph) {
            if (!showExtractPanel) setSvgContent('');
            return;
        }
        setZoom(1);
        setPan({ x: 0, y: 0 });

        let graph = kpMap.mermaid_graph;
        if (!graph.trim().startsWith('graph') && !graph.trim().startsWith('flowchart')) {
            graph = `graph LR\n${graph}`;
        }
        const classDefs = [
            'classDef big_idea fill:#1e3a8a,stroke:#1e3a8a,color:#ffffff,stroke-width:2px',
            'classDef core_concept fill:#ffffff,stroke:#2563eb,color:#1e3a8a,stroke-width:2px',
            'classDef sub_technique fill:#eff6ff,stroke:#93c5fd,color:#1e40af,stroke-width:1.5px',
        ].join('\n');
        const classAssignments = (kpMap.knowledge_points || [])
            .filter(kp => kp.level && kp.mermaid_id)
            .map(kp => `class ${kp.mermaid_id} ${kp.level}`)
            .join('\n');
        graph = `${graph}\n${classDefs}\n${classAssignments}`;

        const renderMermaid = async () => {
            try {
                const uid = `mermaid-kp-${Date.now()}`;
                const { svg } = await mermaid.render(uid, graph);
                const rounded = svg.replace(/<rect ([^>]*?)(\/?>)/g, (m, attrs, closing) => {
                    if (attrs.includes('rx=')) return m;
                    return `<rect rx="10" ry="10" ${attrs}${closing}`;
                });
                setSvgContent(rounded);
            } catch (e) { console.error('Mermaid render error:', e); }
        };
        renderMermaid();
    }, [showExtractPanel, kpMap]);

    // ---- Fit zoom after SVG renders ----
    useEffect(() => {
        if (!svgContent || !mapContainerRef.current) return;
        const container = mapContainerRef.current;
        const svgEl = container.querySelector('svg');
        if (svgEl) {
            const svgW = svgEl.viewBox?.baseVal?.width || svgEl.getBoundingClientRect().width;
            const svgH = svgEl.viewBox?.baseVal?.height || svgEl.getBoundingClientRect().height;
            const cW = container.clientWidth;
            const cH = container.clientHeight;
            if (svgW > 0 && svgH > 0) {
                const fit = Math.min(cW / svgW, cH / svgH, 1);
                setMinZoom(Math.max(fit * 0.8, 0.1));
            }
        }
    }, [svgContent]);

    // ---- Auto-select pre-selected names & Auto-promote if missing ----
    useEffect(() => {
        if (!preSelectedNames || preSelectedNames.length === 0) return;

        // 1. Check if ANY pre-selected names are missing from the unit
        const missingFromUnit = preSelectedNames.filter(name => !unitKPs.some(ukp => ukp.name === name));

        if (missingFromUnit.length > 0 && kpMap && uniqueContentId && unitId && courseId) {
            // 2. Are these missing names available in the extracted KPs of the current content?
            const canBePromoted = missingFromUnit.filter(name =>
                kpMap.knowledge_points.some(ekp => ekp.name === name)
            );

            if (canBePromoted.length > 0) {
                console.log('[KnowledgePointPanel] Guided generation: auto-promoting missing KPs:', canBePromoted);
                promoteKPs(uniqueContentId, canBePromoted, unitId, courseId)
                    .then(() => {
                        // After promotion, refresh unit KPs
                        getUnitKPs(courseId, unitId).then(setUnitKPs);
                        setToast({ message: `已自動將 ${canBePromoted.length} 個知識點加入單元中`, type: 'success' });
                    })
                    .catch(err => console.error('Auto-promote failed:', err));
            }
        }

        // 3. Selection logic (runs whenever names or unit KPs change)
        if (unitKPs.length > 0 && !selectionInitializedRef.current) {
            const idsToSelect = unitKPs
                .filter(kp => preSelectedNames.includes(kp.name))
                .map(kp => kp.id);

            if (idsToSelect.length > 0) {
                console.log('[KnowledgePointPanel] Auto-selecting KPs (Initial):', idsToSelect);
                setSelectedKPIds(new Set(idsToSelect));
            }
            selectionInitializedRef.current = true;
            initializedRef.current = true;
        }
    }, [preSelectedNames, unitKPs, kpMap, uniqueContentId, unitId, courseId]);

    // ---- Auto-select Weak KPs ----
    useEffect(() => {
        if (!weakKPNames || weakKPNames.length === 0 || unitKPs.length === 0) return;

        const idsToSelect = unitKPs
            .filter(kp => weakKPNames.includes(kp.name))
            .map(kp => kp.id);

        if (idsToSelect.length > 0) {
            setSelectedKPIds(prev => {
                const newSet = new Set(prev);
                let added = false;
                for (const id of idsToSelect) {
                    if (!newSet.has(id)) {
                        if (newSet.size < 10) {
                            newSet.add(id);
                            added = true;
                        } else {
                            break;
                        }
                    }
                }
                return added ? newSet : prev;
            });
        }
    }, [weakKPNames, unitKPs]);

    // ---- Notify parent ----
    useEffect(() => {
        if (!onKPSelectionChange) return;
        // [MOD] If we have preSelectedNames, wait until we've processed them
        if (preSelectedNames && preSelectedNames.length > 0 && !initializedRef.current) {
            return;
        }

        const details: KPDetail[] = unitKPs
            .filter(kp => selectedKPIds.has(kp.id))
            .map(kp => ({ id: kp.id, mermaid_id: String(kp.id), name: kp.name, level: 'sub_technique', description: kp.source_name || '' }));
        onKPSelectionChange(selectedKPIds, details);
    }, [selectedKPIds, unitKPs, preSelectedNames]); // eslint-disable-line

    // ==================== Handlers ====================
    const handleExtract = async (forceRegenerate = false) => {
        if (!uniqueContentId) return;
        setIsExtracting(true);
        setLoadingExtracted(true);
        setExtractedError(null);
        const startTime = Date.now();
        try {
            const res = await extractKP(uniqueContentId, userId, forceRegenerate);
            const duration = Date.now() - startTime;
            if (res.status === 'success' && res.kp_map) {
                setKpMap(res.kp_map);
                setPromotedKPs(new Set());
                onActionLog?.('kp', 'KP_EXTRACT_SUCCESS', { content_id: uniqueContentId, kp_count: res.kp_map.knowledge_points.length }, duration);
            } else if (res.status === 'exists') {
                const existing = await getKPMap(uniqueContentId, userId);
                setKpMap(existing.kp_map);
                onActionLog?.('kp', 'KP_EXTRACT_EXISTS', { content_id: uniqueContentId });
            } else {
                setExtractedError(res.message || '提取失敗');
                onActionLog?.('kp', 'KP_EXTRACT_FAILED', { content_id: uniqueContentId, error: res.message }, duration);
            }
        } catch (err: any) {
            setExtractedError('提取發生錯誤');
            onActionLog?.('kp', 'KP_EXTRACT_ERROR', { content_id: uniqueContentId, error: err.message });
        }
        finally { setLoadingExtracted(false); setIsExtracting(false); }
    };

    const handleToggleKP = (id: number) => {
        const isSelected = selectedKPIds.has(id);
        const kp = unitKPs.find(k => k.id === id);
        if (kp && preSelectedNames?.includes(kp.name)) return;

        if (!isSelected && selectedKPIds.size >= 10) {
            setToast({ message: '不可選超過 10 個知識點', type: 'info' });
            return;
        }

        const action = isSelected ? 'deselect' : 'select';
        onActionLog?.('kp', 'KP_TOGGLE', { id, name: kp?.name || 'unknown', action });

        setSelectedKPIds(prev => {
            const s = new Set(prev);
            if (s.has(id)) {
                s.delete(id);
            } else {
                s.add(id);
            }
            return s;
        });
    };
    const toggleAllUnitKPs = () => {
        // Condition: if all are selected OR if we've reached the 10-item limit, treated as "fully selected"
        const maxSelectable = Math.min(unitKPs.length, 10);
        if (selectedKPIds.size === maxSelectable) {
            // Deselect all except locked ones
            const lockedIds = unitKPs.filter(kp => preSelectedNames?.includes(kp.name)).map(kp => kp.id);
            setSelectedKPIds(new Set(lockedIds));
        } else {
            // Select all (up to 10)
            const lockedIds = unitKPs.filter(kp => preSelectedNames?.includes(kp.name)).map(kp => kp.id);
            const otherIds = unitKPs.filter(kp => !preSelectedNames?.includes(kp.name)).map(kp => kp.id);

            const newSelection = new Set(lockedIds);
            for (const id of otherIds) {
                if (newSelection.size < 10) {
                    newSelection.add(id);
                } else {
                    break;
                }
            }

            if (unitKPs.length > 10 && newSelection.size === 10 && selectedKPIds.size < 10) {
                setToast({ message: '已選取上限 10 個知識點', type: 'info' });
            }

            onActionLog?.('kp', 'KP_SELECT_ALL_UP_TO_LIMIT', { count: newSelection.size });
            setSelectedKPIds(newSelection);
        }
    };

    const handlePromote = async (kpName: string, mermaidId: string) => {
        if (!courseId || !unitId || !uniqueContentId) return;
        setPromotingKPs(prev => new Set(prev).add(mermaidId));
        const startTime = Date.now();
        try {
            const res = await promoteKPs(uniqueContentId, [kpName], unitId, courseId);
            setPromotedKPs(prev => new Set(prev).add(mermaidId));
            const updated = await getUnitKPs(courseId, unitId);
            setUnitKPs(updated);
            const newKP = res.knowledge_points.find(k => k.name === kpName);
            if (newKP) setSelectedKPIds(prev => new Set(prev).add(newKP.id));
            const duration = (Date.now() - startTime);
            onActionLog?.('kp', 'KP_PROMOTE', { name: kpName, content_id: uniqueContentId }, duration);
        } catch (err: any) {
            onActionLog?.('kp', 'KP_PROMOTE_FAILED', { name: kpName, error: err.message });
        }
        finally { setPromotingKPs(prev => { const s = new Set(prev); s.delete(mermaidId); return s; }); }
    };

    const handlePromoteAll = async () => {
        if (!kpMap || !courseId || !unitId || !uniqueContentId) return;
        const unpromoted = kpMap.knowledge_points.filter(k => !promotedKPs.has(k.mermaid_id));
        if (!unpromoted.length) return;
        setPromotingKPs(new Set(unpromoted.map(k => k.mermaid_id)));
        const startTime = Date.now();
        try {
            const res = await promoteKPs(uniqueContentId, unpromoted.map(k => k.name), unitId, courseId);
            setPromotedKPs(new Set(kpMap.knowledge_points.map(k => k.mermaid_id)));
            const updated = await getUnitKPs(courseId, unitId);
            setUnitKPs(updated);
            setSelectedKPIds(prev => new Set([...prev, ...res.knowledge_points.map(k => k.id)]));
            const duration = (Date.now() - startTime);
            onActionLog?.('kp', 'KP_PROMOTE_ALL', { count: unpromoted.length }, duration);
        } catch (err: any) {
            onActionLog?.('kp', 'KP_PROMOTE_ALL_FAILED', { error: err.message });
        }
        finally { setPromotingKPs(new Set()); }
    };

    const handleAddKP = async () => {
        if (!courseId || !unitId || !newKPName.trim()) return;
        setAddingKP(true);
        setAddError(null);
        try {
            const name = newKPName.trim();
            const res = await createUnitKP(courseId, unitId, name);
            setUnitKPs(prev => [...prev, res]);
            setNewKPName('');
            setShowAddInput(false);
            onActionLog?.('kp', 'KP_MANUAL_ADD', { name });
        } catch (err: any) { setAddError(err.message || '新增失敗'); }
        finally { setAddingKP(false); }
    };

    const startEdit = (kp: UnitKP) => { setEditingKPId(kp.id); setEditingName(kp.name); };

    const handleSaveEdit = async () => {
        if (!courseId || !unitId || !editingKPId || !editingName.trim()) return;
        setSavingEdit(true);
        try {
            await updateUnitKP(courseId, unitId, editingKPId, editingName.trim());
            onActionLog?.('kp', 'KP_RENAME', { id: editingKPId, name: editingName.trim() });
            setUnitKPs(prev => prev.map(k => k.id === editingKPId ? { ...k, name: editingName.trim() } : k));
            setEditingKPId(null);
        } catch (err: any) { alert(err.message || '儲存失敗'); }
        finally { setSavingEdit(false); }
    };

    const handleDeleteConfirmed = async () => {
        if (!courseId || !unitId || !deletingKP) return;
        try {
            await deleteUnitKP(courseId, unitId, deletingKP.id);
            onActionLog?.('kp', 'KP_DELETE', { name: deletingKP.name, id: deletingKP.id });
            setUnitKPs(prev => prev.filter(k => k.id !== deletingKP.id));
            setSelectedKPIds(prev => { const s = new Set(prev); s.delete(deletingKP.id); return s; });
            // Sync promotedKPs: if the deleted unit KP was promoted from extracted list,
            // revert the "已加入" label so it can be re-added later.
            if (kpMap) {
                const matching = kpMap.knowledge_points.filter(ekp => ekp.name === deletingKP.name);
                if (matching.length > 0) {
                    setPromotedKPs(prev => {
                        const s = new Set(prev);
                        matching.forEach(ekp => s.delete(ekp.mermaid_id));
                        return s;
                    });
                }
            }
        } catch (err: any) { alert(err.message || '刪除失敗'); }
        finally { setDeletingKP(null); }
    };

    const handleWheel = (e: React.WheelEvent) => { e.preventDefault(); setZoom(prev => Math.max(minZoom, Math.min(5, prev - e.deltaY * 0.001))); };
    const handleMouseDown = (e: React.MouseEvent) => { setIsDragging(true); setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y }); };
    const handleMouseMove = (e: React.MouseEvent) => { if (isDragging) setPan({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y }); };
    const handleMouseUp = () => setIsDragging(false);

    const getLevelIcon = (level: string) => {
        switch (level) { case 'big_idea': return '🎯'; case 'core_concept': return '💡'; default: return '🔧'; }
    };

    const sourceLabel = (kp: UnitKP) => {
        if (kp.source_type === 'manual') return { text: '手動', color: 'bg-gray-100 text-gray-500', isExtracted: false };
        if (kp.source_name === '舊版匯入') return { text: '舊版', color: 'bg-gray-50 text-gray-400', isExtracted: false };
        if (kp.source_name) return { text: kp.source_name, color: 'text-blue-400', isExtracted: true };
        return { text: '提取', color: 'text-blue-400', isExtracted: true };
    };

    // ==================== Render ====================
    return (
        <div className="col-span-3 bg-white/50 backdrop-blur-md rounded-xl border border-gray-200 sticky top-4 min-h-[calc(100vh-6.5rem)] max-h-[calc(100vh-6.5rem)] flex flex-col shadow-sm">

            {/* ===== Panel Header ===== */}
            <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between bg-gradient-to-r from-blue-50 to-slate-50 rounded-t-xl shrink-0 relative z-20">
                <h2 className="text-base font-bold text-gray-800 flex items-center gap-2">
                    <span className="w-7 h-7 bg-blue-100 text-blue-600 rounded-lg flex items-center justify-center text-sm font-bold">3</span>
                    鎖定知識點
                    <button onClick={() => setShowHelp(!showHelp)} className="text-gray-400 hover:text-blue-500 transition-colors">
                        <FaQuestionCircle size={14} />
                    </button>
                    {showHelp && (
                        <>
                            <div className="fixed inset-0 z-10" onClick={() => setShowHelp(false)} />
                            <div className="absolute left-0 top-9 bg-white p-3 rounded-xl shadow-lg border border-gray-200 text-xs text-gray-500 w-64 z-20">
                                <p className="mb-1 text-gray-700 font-medium">勾選知識點後 AI 會聚焦生成對應內容。</p>
                                <p>點下方「從教材提取知識點」可查看 AI 分析結果並加入。</p>
                            </div>
                        </>
                    )}
                </h2>
                <span className="text-xs text-blue-600 bg-blue-50 px-2 py-1 rounded-full font-medium border border-blue-100">
                    已選 {selectedKPIds.size} 個
                </span>
            </div>

            {/* ===== Unit KP Section Header ===== */}
            <div className="px-4 py-2 flex items-center gap-1.5 border-b border-gray-100 shrink-0">
                <FaLightbulb size={12} className="text-blue-500 shrink-0" />
                <span className="text-xs font-semibold text-gray-600 tracking-wide">單元知識點</span>
                {unitKPs.length > 0 && (
                    <span className="text-[10px] text-blue-500 bg-blue-50 border border-blue-100 px-1.5 py-0.5 rounded-full">{unitKPs.length}</span>
                )}

                <div className="flex-1" />

                {/* Sorting Controls */}
                {unitKPs.length > 0 && (
                    <div className="flex items-center gap-1 mr-2 px-1 py-0.5 bg-gray-50 rounded-lg border border-gray-100 shadow-sm">
                        <button
                            onClick={() => {
                                if (sortMode === 'extracted_first') setSortMode('manual_first');
                                else if (sortMode === 'manual_first') setSortMode(null);
                                else setSortMode('extracted_first');
                            }}
                            className={`px-1.5 py-0.5 rounded flex items-center gap-0.5 transition-colors ${sortMode?.includes('first') ? 'bg-blue-100 text-blue-600' : 'text-gray-400 hover:text-blue-400'}`}
                            title={sortMode === 'extracted_first' ? "改為手動優先" : sortMode === 'manual_first' ? "取消類別排序" : "依類別排序 (教材優先)"}
                        >
                            <FaSortAlphaDown size={10} />
                            <span className="text-[10px] font-bold">類別</span>
                        </button>
                        <button
                            onClick={() => {
                                if (sortMode === 'time_desc') setSortMode('time_asc');
                                else if (sortMode === 'time_asc') setSortMode(null);
                                else setSortMode('time_desc');
                            }}
                            className={`px-1.5 py-0.5 rounded flex items-center gap-0.5 transition-colors ${sortMode?.startsWith('time') ? 'bg-blue-100 text-blue-600' : 'text-gray-400 hover:text-blue-400'}`}
                            title={sortMode === 'time_desc' ? "改為最早優先" : sortMode === 'time_asc' ? "取消時間排序" : "依時間排序 (最新優先)"}
                        >
                            {sortMode === 'time_asc' ? <FaSortNumericUp size={10} /> : <FaSortNumericDown size={10} />}
                            <span className="text-[10px] font-bold">時間</span>
                        </button>
                    </div>
                )}

                {/* 全選 button */}
                {unitKPs.length > 0 && (
                    <button
                        onClick={toggleAllUnitKPs}
                        className="text-[12px] font-semibold text-gray-400 hover:text-blue-500 flex items-center gap-0.5 transition-colors px-1.5 py-0.5 hover:bg-blue-50 rounded"
                    >
                        {selectedKPIds.size === Math.min(unitKPs.length, 10)
                            ? <FaCheckSquare size={13} className="text-blue-400" />
                            : <FaRegSquare size={13} />}
                        全選
                    </button>
                )}
            </div>

            {/* ===== Unit KP List (scrollable, flex-1) ===== */}
            <div className="flex-1 overflow-y-auto custom-scrollbar px-3 py-2 space-y-0.5 min-h-0">
                {loadingUnitKPs ? (
                    <div className="flex items-center justify-center py-6 gap-2">
                        <FaSpinner className="animate-spin text-blue-300" size={14} />
                        <span className="text-xs text-gray-400">載入中...</span>
                    </div>
                ) : unitKPError ? (
                    <p className="text-xs text-red-400 text-center py-4">{unitKPError}</p>
                ) : unitKPs.length === 0 && !showAddInput ? (
                    <p className="text-xs text-gray-400 text-center py-6 leading-relaxed">
                        尚無單元知識點<br />
                        <span className="text-gray-300">點下方「手動新增」或從教材提取後加入</span>
                    </p>
                ) : (
                    [...unitKPs].sort((a, b) => {
                        if (sortMode === 'time_desc') return b.id - a.id;
                        if (sortMode === 'time_asc') return a.id - b.id;
                        if (sortMode === 'extracted_first' || sortMode === 'manual_first') {
                            // Align priority with sourceLabel logic (isExtracted: blue vs grey)
                            const isBlueA = a.source_type === 'extracted' && a.source_name !== '舊版匯入';
                            const isBlueB = b.source_type === 'extracted' && b.source_name !== '舊版匯入';

                            if (isBlueA !== isBlueB) {
                                if (sortMode === 'extracted_first') return isBlueA ? -1 : 1;
                                return isBlueA ? 1 : -1;
                            }
                            // Same category, sub-sort by source_name
                            return (a.source_name || '').localeCompare(b.source_name || '');
                        }
                        return 0; // Default: follow API order
                    }).map(kp => {
                        const isSelected = selectedKPIds.has(kp.id);
                        const isEditing = editingKPId === kp.id;
                        const isLocked = false; // [MOD] Removed lock for pre-selected KPs
                        const label = sourceLabel(kp);
                        return (
                            <div
                                key={kp.id}
                                onClick={() => { if (!isEditing && !isLocked) handleToggleKP(kp.id); }}
                                className={`group flex items-start gap-2 px-2 py-1.5 rounded-lg transition-all ${isLocked ? 'cursor-default' : 'cursor-pointer'} ${isSelected ? 'bg-blue-50' : 'hover:bg-gray-50'}`}
                            >
                                {/* Checkbox — aligned to top on multi-line */}
                                <Tooltip
                                    content={!isSelected && selectedKPIds.size >= 10 ? "不可選超過 10 個知識點" : isSelected ? "取消選擇" : "選擇知識點"}
                                    position="top"
                                >
                                    <button
                                        onClick={e => { e.stopPropagation(); if (!isLocked) handleToggleKP(kp.id); }}
                                        className={`shrink-0 transition-transform mt-0.5 ${isLocked ? 'text-blue-300' : 'text-blue-500'}`}
                                        disabled={isLocked || (!isSelected && selectedKPIds.size >= 10)}
                                    >
                                        {isSelected ? <FaCheckSquare size={15} /> : <FaRegSquare size={15} className={`text-gray-300 ${!isSelected && selectedKPIds.size >= 10 ? '' : 'hover:text-blue-400'} transition-colors`} />}
                                    </button>
                                </Tooltip>

                                {/* Name / edit */}
                                {isEditing ? (
                                    <input
                                        autoFocus
                                        value={editingName}
                                        onChange={e => setEditingName(e.target.value)}
                                        onClick={e => e.stopPropagation()}
                                        onKeyDown={e => { if (e.key === 'Enter') handleSaveEdit(); if (e.key === 'Escape') setEditingKPId(null); }}
                                        className="flex-1 text-sm border border-blue-300 rounded px-2 py-0.5 outline-none focus:ring-1 focus:ring-blue-400"
                                    />
                                ) : (
                                    <div className="flex-1 flex flex-col min-w-0">
                                        <div className="flex justify-between items-start gap-2">
                                            <span className={`text-sm leading-snug break-words font-medium ${isLocked ? 'text-gray-700' : 'text-gray-900'}`}>{kp.name}</span>
                                            <div className="flex items-center gap-1.5 shrink-0 mt-0.5">
                                                {isLocked && (
                                                    <span className="text-[10px] text-blue-400 font-bold bg-blue-50 px-1 rounded border border-blue-100 shrink-0">鎖定</span>
                                                )}
                                                {weakKPNames?.includes(kp.name) && (
                                                    <span className="text-[10px] text-red-500 font-bold bg-red-50 px-1 rounded border border-red-100 shrink-0">班級弱點</span>
                                                )}
                                                {/* 非提取標籤：保持在右方 */}
                                                {!label.isExtracted && (
                                                    <span className={`text-[10px] px-1.5 py-0.5 rounded shrink-0 ${label.color}`}>{label.text}</span>
                                                )}
                                            </div>
                                        </div>
                                        {/* 提取標籤：換行顯示於下方 */}
                                        {/* 提取標籤：換行顯示於下方 */}
                                        {label.isExtracted && (
                                            <div className="mt-0.5 flex items-center gap-1 group/link">
                                                <FaProjectDiagram size={10} className="text-blue-400 group-hover/link:text-blue-500 transition-colors ml-0.5" />
                                                <span className="text-[10px] text-blue-600 truncate font-semibold" title={label.text}>
                                                    {label.text}
                                                </span>
                                            </div>
                                        )}
                                    </div>
                                )}


                                {/* Actions — align to top, stop propagation */}
                                {isEditing ? (
                                    <div className="flex items-center gap-1 shrink-0 mt-0.5" onClick={e => e.stopPropagation()}>
                                        <button onClick={handleSaveEdit} disabled={savingEdit}
                                            className="w-6 h-6 bg-blue-500 text-white rounded flex items-center justify-center hover:bg-blue-600 disabled:opacity-50 transition-colors">
                                            {savingEdit ? <FaSpinner size={9} className="animate-spin" /> : <FaCheck size={9} />}
                                        </button>
                                        <button onClick={() => setEditingKPId(null)}
                                            className="w-6 h-6 bg-gray-100 text-gray-500 rounded flex items-center justify-center hover:bg-gray-200 transition-colors">
                                            <FaTimes size={9} />
                                        </button>
                                    </div>
                                ) : (
                                    <div className="flex items-center gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" onClick={e => e.stopPropagation()}>
                                        {!isLocked && (
                                            <>
                                                <button onClick={() => startEdit(kp)}
                                                    className="w-6 h-6 text-gray-300 hover:text-blue-500 hover:bg-blue-50 rounded flex items-center justify-center transition-colors" title="重新命名">
                                                    <FaPen size={10} />
                                                </button>
                                                <button onClick={() => setDeletingKP(kp)}
                                                    className="w-6 h-6 text-gray-300 hover:text-red-400 hover:bg-red-50 rounded flex items-center justify-center transition-colors" title="刪除">
                                                    <FaTrash size={10} />
                                                </button>
                                            </>
                                        )}
                                    </div>
                                )}
                            </div>
                        );
                    })
                )}

                {/* Inline add input */}
                {showAddInput && (
                    <div className="flex items-center gap-2 pt-1">
                        <input
                            autoFocus
                            value={newKPName}
                            onChange={e => { setNewKPName(e.target.value); setAddError(null); }}
                            onKeyDown={e => { if (e.key === 'Enter') handleAddKP(); if (e.key === 'Escape') { setShowAddInput(false); setNewKPName(''); } }}
                            placeholder="輸入知識點名稱"
                            className="flex-1 text-sm border border-blue-200 rounded-lg px-3 py-1.5 outline-none focus:ring-1 focus:ring-blue-400"
                        />
                        <button onClick={handleAddKP} disabled={addingKP || !newKPName.trim()}
                            className="px-3 py-1.5 bg-blue-500 text-white text-xs font-bold rounded-lg hover:bg-blue-600 disabled:opacity-50 transition-colors">
                            {addingKP ? <FaSpinner className="animate-spin" size={12} /> : '新增'}
                        </button>
                        <button onClick={() => { setShowAddInput(false); setNewKPName(''); setAddError(null); }}
                            className="text-xs text-gray-400 hover:text-gray-600 px-1">取消</button>
                    </div>
                )}
                {addError && <p className="text-xs text-red-400 px-1 pt-0.5">{addError}</p>}
            </div>

            {/* ===== Footer ===== */}
            <div className="px-4 py-3 border-t border-gray-100 shrink-0 flex flex-col gap-2">
                {generateError && (
                    <div className="p-2 bg-red-50 border border-red-200 rounded-lg text-xs text-red-600">{generateError}</div>
                )}

                {/* + 手動新增 button */}
                {!showAddInput && (
                    <button
                        onClick={() => setShowAddInput(true)}
                        disabled={!courseId || !unitId}
                        className="w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl border border-dashed border-gray-300 text-gray-600 bg-gray-50 hover:bg-gray-100 text-sm font-medium transition-all disabled:opacity-30 disabled:cursor-not-allowed"
                    >
                        <FaPlus size={11} />
                        手動新增知識點
                    </button>
                )}

                {/* Extract panel toggle button */}
                <Tooltip
                    content={isExtracting ? "正在提取中..." : selectedSourceKeys.size === 0 ? "請先選擇至少一個參考資料" : "AI 分析教材並提取知識點"}
                    position="top"
                    className="w-full"
                >
                    <button
                        onClick={async () => {
                            if (showExtractPanel) {
                                setShowExtractPanel(false);
                            } else if (kpMap) {
                                setShowExtractPanel(true);
                            } else {
                                // First open: show toast, then extract, then open overlay
                                setToast({ message: 'AI 正在分析教材並提取知識點，完成後將自動開啟...', type: 'info' });
                                await handleExtract(false);
                                setShowExtractPanel(true);
                            }
                        }}
                        disabled={isExtracting || selectedSourceKeys.size === 0}
                        className={`w-full flex items-center justify-center gap-2 px-3 py-2 rounded-xl border text-sm font-medium transition-all ${showExtractPanel
                            ? 'bg-blue-50 border-blue-200 text-blue-700'
                            : 'bg-gray-50 border-gray-200 text-gray-600 hover:bg-blue-50 hover:border-blue-200 hover:text-blue-700'
                            } ${selectedSourceKeys.size === 0 ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                        <FaProjectDiagram size={13} className={showExtractPanel ? 'text-blue-500' : 'text-gray-400'} />
                        <span>從參考資料提取知識點</span>
                        {kpMap && !loadingExtracted && (
                            <span className={`w-5 h-5 flex items-center justify-center rounded-full text-[10px] font-bold ${showExtractPanel ? 'bg-blue-200 text-blue-700' : 'bg-gray-200 text-gray-500'}`}>
                                {kpMap.knowledge_points.length}
                            </span>
                        )}
                        {loadingExtracted && <FaSpinner size={10} className="animate-spin text-gray-400" />}
                        {showExtractPanel
                            ? <MdCloseFullscreen size={14} className="text-blue-500 shrink-0" />
                            : <MdOpenInFull size={14} className="text-gray-400 shrink-0" />}
                    </button>
                </Tooltip>

                {/* Generate button */}
                <Tooltip
                    content={
                        generateLoading
                            ? "正在生成中..."
                            : selectedSourceKeys.size === 0
                                ? "請先選擇至少一個參考資料"
                                : selectedKPIds.size === 0
                                    ? "請至少選取一個知識點"
                                    : "開始生成教材"
                    }
                    position="top"
                    className="w-full"
                >
                    <button
                        onClick={handleGenerate}
                        disabled={generateLoading || selectedSourceKeys.size === 0 || selectedKPIds.size === 0}
                        className="w-full px-6 py-3 btn-primary flex items-center justify-center gap-3 text-lg font-bold shadow-lg shadow-blue-100 disabled:opacity-50 disabled:cursor-not-allowed hover:scale-[1.02] active:scale-[0.98] transition-all"
                    >
                        {generateLoading ? (
                            <><div className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full" />生成中...</>
                        ) : (
                            <><FaRobot size={16} />開始生成</>
                        )}
                    </button>
                </Tooltip>
            </div>

            {/* ===== Expanded Overlay: Map (flex:2) + Extracted list (flex:1) ===== */}
            {showExtractPanel && ReactDOM.createPortal(
                <div style={{
                    position: 'fixed', top: '88px', left: '16px',
                    right: 'calc(25% + 12px)', bottom: '16px',
                    zIndex: 50, display: 'flex', gap: '4px',
                }}>
                    {/* Map panel — flex 2 */}
                    <div style={{
                        flex: 2, borderRadius: '14px', overflow: 'hidden',
                        background: 'rgba(255,255,255,0.97)', backdropFilter: 'blur(12px)',
                        border: '1px solid #bfdbfe',
                        display: 'flex', flexDirection: 'column',
                    }}>
                        {/* Map header */}
                        <div style={{ padding: '12px 16px', borderBottom: '1px solid #dbeafe', background: 'linear-gradient(to right, #eff6ff, #f8fafc)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0, minHeight: '52px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <FaProjectDiagram style={{ color: '#3b82f6' }} size={15} />
                                <span style={{ fontWeight: 700, color: '#1e3a8a', fontSize: '16px' }}>知識地圖</span>
                                {kpMap && <span style={{ fontSize: '11px', background: '#dbeafe', color: '#2563eb', padding: '2px 8px', borderRadius: '999px' }}>{kpMap.knowledge_points.length} 個知識點</span>}
                            </div>
                            <div style={{ display: 'flex', gap: '6px' }}>
                                {[
                                    { label: '+', action: () => setZoom(z => Math.min(5, z + 0.2)) },
                                    { label: `${Math.round(zoom * 100)}%`, action: () => setZoom(1) },
                                    { label: '−', action: () => setZoom(z => Math.max(minZoom, z - 0.2)) },
                                ].map((btn, i) => (
                                    <button key={i} onClick={btn.action} style={{ padding: '2px 8px', background: '#fff', border: '1px solid #e2e8f0', borderRadius: '6px', fontSize: '12px', color: '#374151', cursor: 'pointer' }}>
                                        {btn.label}
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* Map canvas */}
                        {!kpMap ? (
                            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '12px' }}>
                                <p style={{ fontSize: '13px', color: '#9ca3af' }}>尚未提取知識點</p>
                            </div>
                        ) : !svgContent ? (
                            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                <FaSpinner size={24} style={{ color: '#93c5fd' }} className="animate-spin" />
                            </div>
                        ) : (
                            <div
                                ref={mapContainerRef}
                                style={{ flex: 1, overflow: 'hidden', cursor: isDragging ? 'grabbing' : 'grab' }}
                                onWheel={handleWheel}
                                onMouseDown={handleMouseDown}
                                onMouseMove={handleMouseMove}
                                onMouseUp={handleMouseUp}
                                onMouseLeave={handleMouseUp}
                            >
                                <div style={{ transform: `translate(${pan.x}px,${pan.y}px) scale(${zoom})`, transformOrigin: 'center center', width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                    <div dangerouslySetInnerHTML={{ __html: svgContent }} className="select-none [&_svg]:max-w-none" />
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Extracted KP list — flex 1 */}
                    <div style={{
                        flex: 1, borderRadius: '14px', overflow: 'hidden',
                        background: 'rgba(255,255,255,0.97)', backdropFilter: 'blur(12px)',
                        border: '1px solid #e2e8f0',
                        display: 'flex', flexDirection: 'column',
                    }}>
                        {/* Extracted header */}
                        <div style={{ padding: '12px 14px', borderBottom: '1px solid #dbeafe', background: 'linear-gradient(to right, #eff6ff, #f8fafc)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0, minHeight: '52px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <span style={{ fontWeight: 700, color: '#1e3a8a', fontSize: '16px' }}>提取知識點</span>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                    {[
                                        { icon: '🎯', label: '大概念' },
                                        { icon: '💡', label: '核心概念' },
                                        { icon: '🔧', label: '子技能' },
                                    ].map(({ icon, label }) => (
                                        <span key={label} style={{ display: 'flex', alignItems: 'center', gap: '2px', fontSize: '10px', color: '#6b7280' }}>
                                            <span style={{ fontSize: '11px' }}>{icon}</span>
                                            <span>{label}</span>
                                        </span>
                                    ))}
                                </div>
                            </div>
                            <button onClick={() => setShowReExtractConfirm(true)}
                                style={{ fontSize: '11px', color: '#9ca3af', background: 'none', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '3px' }}>
                                <FaSync size={9} /> 重新提取
                            </button>
                        </div>

                        {/* Extracted list body */}
                        <div className="overflow-y-auto custom-scrollbar flex-1 p-2">
                            {!uniqueContentId ? (
                                <p className="text-xs text-gray-400 text-center py-6">請先在中間欄選擇文件</p>
                            ) : loadingExtracted ? (
                                <div className="flex items-center justify-center py-6 gap-2">
                                    <FaSpinner className="animate-spin text-blue-300" size={14} />
                                    <span className="text-xs text-gray-400">{isExtracting ? '提取中...' : '載入中...'}</span>
                                </div>
                            ) : extractedError ? (
                                <div className="text-center py-4">
                                    <p className="text-xs text-red-400 mb-2">{extractedError}</p>
                                    <button onClick={() => handleExtract(false)} className="text-xs text-blue-500 hover:underline">重試</button>
                                </div>
                            ) : (!kpMap || (loadingExtracted && !extractedError)) ? (
                                <div className="flex flex-col items-center justify-center py-10 gap-3">
                                    <FaSpinner className="animate-spin text-blue-300" size={22} />
                                    <span className="text-xs text-gray-400">{isExtracting ? 'AI 提取知識點中...' : '載入中...'}</span>
                                </div>
                            ) : (
                                <div className="space-y-1">
                                    {kpMap.knowledge_points.map(kp => {
                                        const isPromoted = promotedKPs.has(kp.mermaid_id);
                                        const isPromoting = promotingKPs.has(kp.mermaid_id);
                                        let studentOutcome = kp.description;
                                        if (kp.description?.includes('en_name:')) {
                                            const dp = kp.description.split('en_name:');
                                            const afterEn = dp[1] || '';
                                            const dot = afterEn.indexOf('.');
                                            studentOutcome = dot !== -1 ? afterEn.substring(dot + 1).trim() : afterEn;
                                        }
                                        return (
                                            <div key={kp.mermaid_id} className="px-2 py-2.5 rounded-lg hover:bg-gray-50 transition-colors">
                                                <div className="flex items-center gap-2">
                                                    <span className="text-sm shrink-0">{getLevelIcon(kp.level)}</span>
                                                    <span className="flex-1 text-sm text-gray-800 font-medium leading-snug">{kp.name}</span>
                                                    <button
                                                        onClick={e => { e.stopPropagation(); if (!isPromoted) handlePromote(kp.name, kp.mermaid_id); }}
                                                        disabled={isPromoted || isPromoting || !courseId || !unitId}
                                                        className={`shrink-0 flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium transition-all ${isPromoted
                                                            ? 'bg-blue-100 text-blue-600 border border-blue-200 cursor-default'
                                                            : 'bg-blue-500 text-white border border-blue-500 hover:bg-blue-600 hover:border-blue-600'
                                                            } disabled:opacity-40`}>
                                                        {isPromoting ? <FaSpinner size={8} className="animate-spin" /> : isPromoted ? <FaCheck size={8} /> : <FaPlus size={8} />}
                                                        {isPromoted ? '已加入' : '加入'}
                                                    </button>
                                                </div>
                                                {studentOutcome && (
                                                    <div className="pl-7 pt-1.5 text-xs text-gray-600 leading-relaxed">{studentOutcome}</div>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>

                        {/* Footer: 全部加入 */}
                        {kpMap && (
                            <div style={{ padding: '10px 12px', borderTop: '1px solid #e2e8f0', flexShrink: 0 }}>
                                <button
                                    onClick={handlePromoteAll}
                                    disabled={promotingKPs.size > 0 || !courseId || !unitId}
                                    style={{
                                        width: '100%', fontSize: '13px', color: '#2563eb',
                                        background: '#eff6ff', border: '1px solid #bfdbfe',
                                        padding: '7px 12px', borderRadius: '999px', cursor: 'pointer',
                                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                                        gap: '5px', fontWeight: 600,
                                        opacity: (promotingKPs.size > 0 || !courseId || !unitId) ? 0.4 : 1,
                                        transition: 'background 0.15s',
                                    }}>
                                    {promotingKPs.size > 0 ? <FaSpinner size={10} className="animate-spin" /> : <FaPlus size={10} />}
                                    全部加入單元知識點
                                </button>
                            </div>
                        )}
                    </div>
                </div>,
                document.body
            )}

            {/* Re-extract Confirm Modal */}
            <Modal isOpen={showReExtractConfirm} onClose={() => setShowReExtractConfirm(false)} title="重新提取確認" maxWidth="max-w-md">
                <div className="space-y-6 py-2">
                    <div className="flex items-center gap-4 px-2">
                        <div className="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center text-gray-500 shrink-0">
                            <FaExclamationTriangle size={20} />
                        </div>
                        <div>
                            <p className="font-semibold text-gray-800 mb-1">確定要重新提取嗎？</p>
                            <p className="text-sm text-gray-500">這將<span className="font-bold text-red-500">移除當前提取結果</span>並重新生成。單元知識點不受影響。</p>
                        </div>
                    </div>
                    <div className="flex items-center justify-end gap-3">
                        <button onClick={() => setShowReExtractConfirm(false)}
                            className="px-5 py-2 rounded-full text-sm font-medium text-gray-500 bg-white border border-gray-200 hover:bg-gray-50 transition-all">取消</button>
                        <button onClick={() => { handleExtract(true); setShowReExtractConfirm(false); }}
                            className="px-6 py-2 rounded-full text-sm font-bold text-white bg-blue-500 hover:bg-blue-600 shadow-sm transition-all">重新提取</button>
                    </div>
                </div>
            </Modal>

            {/* Delete Confirm Modal */}
            <Modal isOpen={!!deletingKP} onClose={() => setDeletingKP(null)} title="刪除知識點" maxWidth="max-w-md">
                <div className="space-y-6 py-2">
                    <div className="flex items-center gap-4 px-2">
                        <div className="w-11 h-11 rounded-full bg-red-50 flex items-center justify-center text-red-400 shrink-0">
                            <FaTrash size={18} />
                        </div>
                        <div>
                            <p className="font-semibold text-gray-800 mb-1">確定要刪除「{deletingKP?.name}」？</p>
                            <p className="text-sm text-gray-500">此操作無法復原。若有題目與此知識點關聯，其關聯將被清除。</p>
                        </div>
                    </div>
                    <div className="flex items-center justify-end gap-3">
                        <button onClick={() => setDeletingKP(null)}
                            className="px-5 py-2 rounded-full text-sm text-gray-500 bg-white border border-gray-200 hover:bg-gray-50 transition-all">取消</button>
                        <button onClick={handleDeleteConfirmed}
                            className="px-5 py-2 rounded-full text-sm font-bold text-white bg-red-500 hover:bg-red-600 shadow-sm transition-all">確認刪除</button>
                    </div>
                </div>
            </Modal>

            {/* Toast notification */}
            {toast && (
                <Toast
                    message={toast.message}
                    type={toast.type}
                    position="top-right"
                    duration={5000}
                    onClose={() => setToast(null)}
                />
            )}
        </div>
    );
}
