/**
 * Course 62 LIME 評估頁 (Task A + Task B 合併)
 *
 * 同一筆 history row 同時進行兩個評估：
 * - Task A 掌握度（RoBERTa 預測 vs 教師）
 * - Task B LIME 關鍵字極性（每個 keyword 的 +/-）
 *
 * 左側：54 筆樣本清單，右側：當前樣本的內容 + 兩個評分區。
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { FaArrowLeft, FaCheckCircle, FaRegCircle, FaChevronLeft, FaChevronRight, FaAdjust } from 'react-icons/fa';
import { useUser } from '../../../contexts/UserContext';
import {
    getCourse62Mastery,
    getCourse62Polarity,
    isAllowedForKappaEval,
    listCourse62Mastery,
    listCourse62Polarity,
    submitCourse62Mastery,
    submitCourse62Polarity,
    type Course62MasterySample,
    type Course62PolaritySample,
    type TeacherPolarityItem,
} from '../../../services/kappaEvalApi';
import { useBeforeUnloadGuard } from './useBeforeUnloadGuard';

const MASTERY_LEVELS = ['待加強', '尚可', '精熟'] as const;

// ---------- LIME 高亮 ----------
// 以 feature_weights 的 polarity 上色（weight ≥ 0 綠 / < 0 紅）。
// 僅在「［學生答案］：...」區段內上色，其他區段（題目、參考答案、學生表現）保持純文字。
// hoveredKeyword：滑鼠移到極性表某列時，文中所有同關鍵字出現處加粗 + 環形輪廓。
function findStudentAnswerRegions(text: string): Array<[number, number]> {
    const marker = '［學生答案］：';
    const regions: Array<[number, number]> = [];
    let idx = 0;
    while (true) {
        const found = text.indexOf(marker, idx);
        if (found === -1) break;
        const start = found + marker.length;
        // 學生答案到下一個「［」標記為止（通常是「［學生表現］：」或新題的「［題目］：」）
        const nextMarker = text.indexOf('［', start);
        const end = nextMarker === -1 ? text.length : nextMarker;
        regions.push([start, end]);
        idx = end;
    }
    return regions;
}

function HighlightedText({
    data,
    hoveredKeyword,
}: {
    data: Course62MasterySample['lime_report_json']['highlighted_text'];
    hoveredKeyword: string | null;
}) {
    if (!data || !data.original) return <div className="text-gray-400 text-sm">（此筆無高亮原文）</div>;
    const { original, highlights = [] } = data;

    // 只保留位於「學生答案」區段內的高亮
    const regions = findStudentAnswerRegions(original);
    const inStudentAnswer = (start: number, end: number) =>
        regions.some(([s, e]) => start >= s && end <= e);
    const filtered = highlights.filter((h) => inStudentAnswer(h.start, h.end));

    // 按 start 排序後合併，避免 overlap
    const sorted = [...filtered].sort((a, b) => a.start - b.start);
    const segments: Array<{ text: string; weight?: number; keyword?: string }> = [];
    let cursor = 0;
    for (const h of sorted) {
        if (h.start < cursor) continue;
        if (h.start > cursor) segments.push({ text: original.slice(cursor, h.start) });
        segments.push({ text: original.slice(h.start, h.end), weight: h.weight, keyword: h.keyword });
        cursor = h.end;
    }
    if (cursor < original.length) segments.push({ text: original.slice(cursor) });

    return (
        <pre className="whitespace-pre-wrap font-sans text-sm leading-7 bg-gray-50 rounded-lg p-4 border border-gray-200">
            {segments.map((seg, i) => {
                if (seg.weight === undefined) return <span key={i}>{seg.text}</span>;
                const isHovered = hoveredKeyword && seg.keyword === hoveredKeyword;
                const base = seg.weight >= 0 ? 'bg-green-200 text-green-900' : 'bg-red-200 text-red-900';
                const hoverRing = isHovered
                    ? (seg.weight >= 0 ? ' ring-2 ring-green-600 font-bold' : ' ring-2 ring-red-600 font-bold')
                    : '';
                return (
                    <span
                        key={i}
                        className={`${base} rounded px-0.5 transition-all${hoverRing}`}
                        title={`${seg.keyword} (${seg.weight.toFixed(4)})`}
                    >
                        {seg.text}
                    </span>
                );
            })}
        </pre>
    );
}

// ---------- 掌握度評分區 (Task A) ----------
function MasteryRatingPanel({
    sample,
    onSubmit,
    submitting,
    onDirtyChange,
}: {
    sample: Course62MasterySample;
    onSubmit: (mastery: string, note: string) => void;
    submitting: boolean;
    onDirtyChange?: (dirty: boolean) => void;
}) {
    const [mastery, setMastery] = useState<string>(sample.teacher_mastery || '');
    const [note, setNote] = useState<string>(sample.teacher_note || '');

    useEffect(() => {
        setMastery(sample.teacher_mastery || '');
        setNote(sample.teacher_note || '');
    }, [sample.id]);

    const disabled = !mastery || submitting;

    // 未送出保護
    const isDirty =
        mastery !== (sample.teacher_mastery || '') || note !== (sample.teacher_note || '');
    useBeforeUnloadGuard(isDirty);
    useEffect(() => { onDirtyChange?.(isDirty); }, [isDirty, onDirtyChange]);

    return (
        <div className="bg-white border border-gray-200 rounded-lg p-5 space-y-4 h-full flex flex-col">
            <div>
                <h3 className="font-semibold text-gray-900">Task A · 您判定的掌握度</h3>
                <p className="text-xs text-gray-500 mt-1">（AI 預測為參考，您獨立評估最合適的等級）</p>
            </div>
            <div className="flex gap-2">
                {MASTERY_LEVELS.map((lvl) => (
                    <button
                        key={lvl}
                        type="button"
                        onClick={() => setMastery(lvl)}
                        className={
                            'flex-1 py-2 rounded-md border transition-colors ' +
                            (mastery === lvl
                                ? 'bg-indigo-600 text-white border-indigo-600'
                                : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50')
                        }
                    >
                        {lvl}
                    </button>
                ))}
            </div>
            <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={2}
                placeholder="（可選）評分理由..."
                className="w-full border border-gray-300 rounded-md p-2 text-sm"
            />
            <div className="mt-auto flex items-center justify-between pt-2">
                <div className="text-xs text-gray-500">
                    {sample.submitted_at ? `已於 ${new Date(sample.submitted_at).toLocaleString()} 送出` : '尚未送出'}
                </div>
                <button
                    type="button"
                    disabled={disabled}
                    onClick={() => onSubmit(mastery, note)}
                    className={
                        'px-4 py-2 rounded-md text-sm font-medium ' +
                        (disabled
                            ? 'bg-gray-200 text-gray-500 cursor-not-allowed'
                            : 'bg-indigo-600 text-white hover:bg-indigo-700')
                    }
                >
                    {submitting ? '送出中...' : sample.teacher_mastery ? '更新掌握度' : '送出掌握度'}
                </button>
            </div>
        </div>
    );
}

// ---------- 極性評分區 (Task B) ----------
function PolarityRatingPanel({
    sample,
    onSubmit,
    submitting,
    onHoverKeyword,
    onDirtyChange,
}: {
    sample: Course62PolaritySample;
    onSubmit: (polarities: TeacherPolarityItem[], note: string) => void;
    submitting: boolean;
    onHoverKeyword: (keyword: string | null) => void;
    onDirtyChange?: (dirty: boolean) => void;
}) {
    const [picks, setPicks] = useState<Record<string, '+' | '-' | ''>>({});
    const [note, setNote] = useState<string>(sample.teacher_note || '');

    // 初始化：若教師已評過就帶入舊值，否則空白
    useEffect(() => {
        const init: Record<string, '+' | '-' | ''> = {};
        const prev = new Map((sample.teacher_polarities || []).map((p) => [p.keyword, p.polarity]));
        sample.ai_polarities.forEach((p) => {
            init[p.keyword] = prev.get(p.keyword) ?? '';
        });
        setPicks(init);
        setNote(sample.teacher_note || '');
    }, [sample.id]);

    const allFilled = sample.ai_polarities.every((p) => picks[p.keyword] === '+' || picks[p.keyword] === '-');
    const disabled = !allFilled || submitting;

    // 未送出保護：比對 picks 與 sample.teacher_polarities
    const savedMap = new Map((sample.teacher_polarities || []).map((p) => [p.keyword, p.polarity]));
    const isDirty =
        note !== (sample.teacher_note || '') ||
        sample.ai_polarities.some((p) => (picks[p.keyword] || '') !== (savedMap.get(p.keyword) ?? ''));
    useBeforeUnloadGuard(isDirty);
    useEffect(() => { onDirtyChange?.(isDirty); }, [isDirty, onDirtyChange]);

    const handleSubmit = () => {
        const payload: TeacherPolarityItem[] = sample.ai_polarities.map((p) => ({
            keyword: p.keyword,
            polarity: picks[p.keyword] as '+' | '-',
        }));
        onSubmit(payload, note);
    };

    return (
        <div className="bg-white border border-gray-200 rounded-lg p-5 space-y-4 h-full flex flex-col">
            <div>
                <h3 className="font-semibold text-gray-900">Task B · LIME 關鍵字極性</h3>
                <p className="text-xs text-gray-500 mt-1">
                    針對每個關鍵字，判斷它對「目前掌握度標籤」是<span className="text-green-700">正向支持 (+)</span>
                    還是<span className="text-red-700">反向削弱 (−)</span>
                </p>
            </div>

            <div className="divide-y divide-gray-100 border border-gray-200 rounded-md overflow-hidden">
                <div className="grid grid-cols-[1fr_auto_auto] gap-3 items-center bg-gray-50 text-xs text-gray-500 px-3 py-2">
                    <span>關鍵字 (AI weight)</span>
                    <span>AI 極性</span>
                    <span className="text-center">您的判定</span>
                </div>
                {sample.ai_polarities.map((p) => {
                    const selected = picks[p.keyword];
                    return (
                        <div
                            key={p.keyword}
                            className="grid grid-cols-[1fr_auto_auto] gap-3 items-center px-3 py-2 text-sm hover:bg-indigo-50 transition-colors"
                            onMouseEnter={() => onHoverKeyword(p.keyword)}
                            onMouseLeave={() => onHoverKeyword(null)}
                        >
                            <div>
                                <span className="font-medium">{p.keyword}</span>
                                <span className="ml-2 text-xs text-gray-400 font-mono">{p.weight.toFixed(4)}</span>
                            </div>
                            <span
                                className={
                                    'px-2 py-0.5 rounded text-xs font-mono ' +
                                    (p.polarity === '+' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800')
                                }
                            >
                                {p.polarity}
                            </span>
                            <div className="flex gap-1">
                                <button
                                    type="button"
                                    onClick={() => setPicks({ ...picks, [p.keyword]: '+' })}
                                    className={
                                        'w-14 py-1.5 rounded-md border-2 text-sm font-bold transition-all ' +
                                        (selected === '+'
                                            ? 'bg-green-600 text-white border-green-600 shadow'
                                            : 'bg-white text-green-700 border-green-300 hover:border-green-500 hover:bg-green-50')
                                    }
                                    aria-label={`${p.keyword} 正向`}
                                >
                                    +
                                </button>
                                <button
                                    type="button"
                                    onClick={() => setPicks({ ...picks, [p.keyword]: '-' })}
                                    className={
                                        'w-14 py-1.5 rounded-md border-2 text-sm font-bold transition-all ' +
                                        (selected === '-'
                                            ? 'bg-red-600 text-white border-red-600 shadow'
                                            : 'bg-white text-red-700 border-red-300 hover:border-red-500 hover:bg-red-50')
                                    }
                                    aria-label={`${p.keyword} 負向`}
                                >
                                    −
                                </button>
                            </div>
                        </div>
                    );
                })}
            </div>

            <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={2}
                placeholder="（可選）評分理由..."
                className="w-full border border-gray-300 rounded-md p-2 text-sm"
            />
            <div className="mt-auto flex items-center justify-between pt-2">
                <div className="text-xs text-gray-500">
                    {sample.submitted_at ? `已於 ${new Date(sample.submitted_at).toLocaleString()} 送出` : '尚未送出'}
                </div>
                <button
                    type="button"
                    disabled={disabled}
                    onClick={handleSubmit}
                    className={
                        'px-4 py-2 rounded-md text-sm font-medium ' +
                        (disabled
                            ? 'bg-gray-200 text-gray-500 cursor-not-allowed'
                            : 'bg-emerald-600 text-white hover:bg-emerald-700')
                    }
                >
                    {submitting ? '送出中...' : sample.teacher_polarities ? '更新極性' : '送出極性'}
                </button>
            </div>
        </div>
    );
}

// ---------- 主頁面 ----------
export default function Course62LimeEvalPage() {
    const { user } = useUser();
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const [searchParams, setSearchParams] = useSearchParams();

    // 當前顯示哪一筆（由 query param 控制，方便分享/回退）
    const currentId = Number(searchParams.get('id') || 0);

    // hover 於極性表某一列時，文中該關鍵字加強高亮
    const [hoveredKeyword, setHoveredKeyword] = useState<string | null>(null);

    // 追蹤兩個 panel 的 dirty 狀態，用於導航前的確認
    const masteryDirtyRef = useRef(false);
    const polarityDirtyRef = useRef(false);
    const confirmNav = (): boolean => {
        const anyDirty = masteryDirtyRef.current || polarityDirtyRef.current;
        return !anyDirty || window.confirm('此題有未送出的變更，確定要離開嗎？未送出的選擇會遺失。');
    };

    // 白名單守門
    if (user && !isAllowedForKappaEval(user.user_id)) {
        return (
            <div className="p-8 text-red-700">無權存取此頁面</div>
        );
    }

    // 兩邊清單各自取；側邊欄打勾需 A + B 皆完成
    const enabled = !!user && isAllowedForKappaEval(user.user_id);
    const listAQuery = useQuery({
        queryKey: ['kappa-eval', 'course62-mastery', 'list'],
        queryFn: listCourse62Mastery,
        enabled,
    });
    const listBQuery = useQuery({
        queryKey: ['kappa-eval', 'course62-polarity', 'list'],
        queryFn: listCourse62Polarity,
        enabled,
    });

    // 合併：以 A 的 id 為主（UI 導航鍵），is_completed 取 A∧B
    const items = useMemo(() => {
        const aItems = listAQuery.data?.items ?? [];
        const bByOrder = new Map((listBQuery.data?.items ?? []).map((b) => [b.display_order, b]));
        return aItems.map((a) => {
            const b = bByOrder.get(a.display_order);
            return {
                ...a,
                is_completed: a.is_completed && !!b?.is_completed,
                a_completed: a.is_completed,
                b_completed: !!b?.is_completed,
            };
        });
    }, [listAQuery.data, listBQuery.data]);

    // 首次進頁若沒指定 id，自動帶到第一個未完成題（A∧B 都完成才算完成）
    useEffect(() => {
        if (!currentId && items.length) {
            const firstUnfinished = items.find((x) => !x.is_completed) || items[0];
            setSearchParams({ id: String(firstUnfinished.id) }, { replace: true });
        }
    }, [items, currentId]);

    const masterySampleQuery = useQuery({
        queryKey: ['kappa-eval', 'course62-mastery', 'sample', currentId],
        queryFn: () => getCourse62Mastery(currentId),
        enabled: currentId > 0,
    });

    // Task B 樣本：使用當前 id 查 polarity 表
    const polaritySampleQuery = useQuery({
        queryKey: ['kappa-eval', 'course62-polarity', 'sample', currentId],
        queryFn: () => getCourse62Polarity(currentId),
        enabled: currentId > 0,
    });

    const currentIdx = items.findIndex((x) => x.id === currentId);
    const prevItem = currentIdx > 0 ? items[currentIdx - 1] : null;
    const nextItem = currentIdx >= 0 && currentIdx < items.length - 1 ? items[currentIdx + 1] : null;

    // 當 A+B 都完成時跳到下一個未完成題（雙送出觸發點其中一個即可）
    const advanceToNext = () => {
        const target =
            items.slice(currentIdx + 1).find((x) => !x.is_completed) || nextItem;
        if (target) {
            setSearchParams({ id: String(target.id) });
        }
    };

    const submitMastery = useMutation({
        mutationFn: ({ id, body }: { id: number; body: { teacher_mastery: string; teacher_note: string } }) =>
            submitCourse62Mastery(id, body),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['kappa-eval'] });
            // A 剛送出 → 若 B 已完成，兩者皆 done，跳下一題
            if (polaritySampleQuery.data?.teacher_polarities) {
                advanceToNext();
            }
        },
    });

    const submitPolarity = useMutation({
        mutationFn: ({ id, body }: { id: number; body: { teacher_polarities: TeacherPolarityItem[]; teacher_note: string } }) =>
            submitCourse62Polarity(id, body),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['kappa-eval'] });
            // B 剛送出 → 若 A 已完成，兩者皆 done，跳下一題
            if (masterySampleQuery.data?.teacher_mastery) {
                advanceToNext();
            }
        },
    });

    const m = masterySampleQuery.data;
    const p = polaritySampleQuery.data;

    return (
        <div className="flex h-[calc(100vh-64px)] bg-gray-50 relative z-10">
            {/* 左側：樣本清單 */}
            <aside className="w-64 border-r border-gray-200 bg-gray-50 overflow-y-auto">
                <div className="p-4 border-b border-gray-200 bg-white">
                    <button
                        onClick={() => { if (confirmNav()) navigate('/teacher/kappa-evaluation'); }}
                        className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900"
                    >
                        <FaArrowLeft /> 返回評估中心
                    </button>
                    <h2 className="mt-3 font-semibold text-gray-900">course 62 LIME 樣本</h2>
                    <div className="text-xs text-gray-500 mt-1">
                        完成 {items.filter((i) => i.is_completed).length} / {items.length}
                    </div>
                </div>
                <ul>
                    {items.map((it) => (
                        <li key={it.id}>
                            <button
                                onClick={() => { if (confirmNav()) setSearchParams({ id: String(it.id) }); }}
                                className={
                                    'w-full text-left px-4 py-2 text-sm flex items-center gap-2 border-l-4 ' +
                                    (it.id === currentId
                                        ? 'bg-white border-indigo-500 font-medium'
                                        : 'border-transparent hover:bg-white')
                                }
                            >
                                {it.is_completed ? (
                                    <FaCheckCircle className="text-green-500 shrink-0" title="A 與 B 皆已評" />
                                ) : it.a_completed || it.b_completed ? (
                                    <FaAdjust className="text-amber-400 shrink-0" title={`部分完成（A:${it.a_completed ? '✓' : '✗'} / B:${it.b_completed ? '✓' : '✗'}）`} />
                                ) : (
                                    <FaRegCircle className="text-gray-300 shrink-0" title="未評" />
                                )}
                                <span className="font-mono text-xs text-gray-500">#{String(it.display_order).padStart(2, '0')}</span>
                                <span className="text-xs text-gray-500">{it.stratum}</span>
                                {!it.is_completed && (it.a_completed || it.b_completed) && (
                                    <span className="ml-auto text-[10px] font-mono text-amber-600">
                                        {it.a_completed ? 'A' : ''}{it.b_completed ? 'B' : ''}
                                    </span>
                                )}
                            </button>
                        </li>
                    ))}
                </ul>
            </aside>

            {/* 右側：主內容 */}
            <main className="flex-1 overflow-y-auto bg-gray-50">
                <div className="max-w-7xl mx-auto p-6 space-y-5">
                    {/* 頁首 & 前後翻頁 */}
                    <div className="flex items-center justify-between">
                        <h1 className="text-xl font-bold text-gray-900">
                            Task A + B · course 62 LIME 評估
                            {m && (
                                <span className="ml-3 text-sm text-gray-500 font-normal">
                                    第 {m.display_order} / {items.length} 題 · 分層 {m.stratum}
                                </span>
                            )}
                        </h1>
                        <div className="flex gap-2">
                            <button
                                onClick={() => { if (prevItem && confirmNav()) setSearchParams({ id: String(prevItem.id) }); }}
                                disabled={!prevItem}
                                className="p-2 rounded-md border border-gray-300 disabled:opacity-30 hover:bg-gray-100"
                                title="上一題"
                            >
                                <FaChevronLeft />
                            </button>
                            <button
                                onClick={() => { if (nextItem && confirmNav()) setSearchParams({ id: String(nextItem.id) }); }}
                                disabled={!nextItem}
                                className="p-2 rounded-md border border-gray-300 disabled:opacity-30 hover:bg-gray-100"
                                title="下一題"
                            >
                                <FaChevronRight />
                            </button>
                        </div>
                    </div>

                    {(masterySampleQuery.isLoading || polaritySampleQuery.isLoading) && (
                        <div className="text-sm text-gray-500">載入中...</div>
                    )}

                    {m && p && (
                        <>
                            {/* AI 參考資訊 */}
                            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm space-y-1">
                                <div className="font-semibold text-blue-900">AI 預測參考</div>
                                <div className="text-blue-800">
                                    RoBERTa 掌握度：<span className="font-mono font-semibold">{m.ai_mastery}</span>
                                    {m.ai_mastery_confidence != null && (
                                        <span className="ml-2 text-blue-700">
                                            （confidence {(m.ai_mastery_confidence * 100).toFixed(2)}%）
                                        </span>
                                    )}
                                </div>
                            </div>

                            {/* Task A 容器：左 BERT input / 右 掌握度評分 */}
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                                <section className="flex flex-col h-full">
                                    <h2 className="text-sm font-semibold text-gray-700 mb-2">學生作答紀錄（BERT input）</h2>
                                    <pre className="flex-1 whitespace-pre-wrap font-sans text-sm leading-6 bg-white rounded-lg p-4 border border-gray-200 overflow-auto">
                                        {m.lime_report_json.bert_input || '（無資料）'}
                                    </pre>
                                </section>
                                <MasteryRatingPanel
                                    sample={m}
                                    onSubmit={(mastery, note) =>
                                        submitMastery.mutate({ id: m.id, body: { teacher_mastery: mastery, teacher_note: note } })
                                    }
                                    submitting={submitMastery.isPending}
                                    onDirtyChange={(d) => { masteryDirtyRef.current = d; }}
                                />
                            </div>

                            {/* AI 預測參考（Task B 提示：極性是相對於這個預測類別判定）*/}
                            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm space-y-1">
                                <div className="font-semibold text-blue-900">AI 預測參考</div>
                                <div className="text-blue-800">
                                    RoBERTa 掌握度：<span className="font-mono font-semibold">{m.ai_mastery}</span>
                                    {m.ai_mastery_confidence != null && (
                                        <span className="ml-2 text-blue-700">
                                            （confidence {(m.ai_mastery_confidence * 100).toFixed(2)}%）
                                        </span>
                                    )}
                                    <span className="ml-2 text-xs text-blue-700">← Task B 極性是相對這個類別判定</span>
                                </div>
                            </div>

                            {/* Task B 容器：左 LIME 高亮原文 / 右 極性評分 */}
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                                <section className="flex flex-col h-full">
                                    <h2 className="text-sm font-semibold text-gray-700 mb-2">
                                        LIME 高亮原文 <span className="ml-2 text-xs text-gray-500">綠 = 正向支持，紅 = 反向削弱</span>
                                    </h2>
                                    <div className="flex-1 overflow-auto">
                                        <HighlightedText
                                            data={m.lime_report_json.highlighted_text}
                                            hoveredKeyword={hoveredKeyword}
                                        />
                                    </div>
                                </section>
                                <PolarityRatingPanel
                                    sample={p}
                                    onSubmit={(polarities, note) =>
                                        submitPolarity.mutate({ id: p.id, body: { teacher_polarities: polarities, teacher_note: note } })
                                    }
                                    submitting={submitPolarity.isPending}
                                    onHoverKeyword={setHoveredKeyword}
                                    onDirtyChange={(d) => { polarityDirtyRef.current = d; }}
                                />
                            </div>

                            {(submitMastery.isError || submitPolarity.isError) && (
                                <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm">
                                    送出失敗：{((submitMastery.error || submitPolarity.error) as Error)?.message}
                                </div>
                            )}
                        </>
                    )}
                </div>
            </main>
        </div>
    );
}
