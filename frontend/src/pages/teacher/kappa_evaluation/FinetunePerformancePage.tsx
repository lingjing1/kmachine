/**
 * Task C2 · Fine-tune 學生表現評估
 *
 * 教師看單題（題目 + 參考答案 + 學生答案），判定 Correct / Partially Correct / Incorrect
 */
import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { FaArrowLeft, FaCheckCircle, FaRegCircle, FaChevronLeft, FaChevronRight } from 'react-icons/fa';
import { useUser } from '../../../contexts/UserContext';
import {
    getFinetunePerformance,
    isAllowedForKappaEval,
    listFinetunePerformance,
    submitFinetunePerformance,
} from '../../../services/kappaEvalApi';
import { useBeforeUnloadGuard } from './useBeforeUnloadGuard';

const PERFORMANCE_LEVELS = ['Correct', 'Partially Correct', 'Incorrect'] as const;

const LEVEL_COLOR: Record<string, string> = {
    Correct: 'bg-green-100 text-green-800',
    'Partially Correct': 'bg-amber-100 text-amber-800',
    Incorrect: 'bg-red-100 text-red-800',
};

export default function FinetunePerformancePage() {
    const { user } = useUser();
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const [searchParams, setSearchParams] = useSearchParams();
    const currentId = Number(searchParams.get('id') || 0);

    const [performance, setPerformance] = useState<string>('');
    const [note, setNote] = useState<string>('');

    if (user && !isAllowedForKappaEval(user.user_id)) {
        return <div className="p-8 text-red-700">無權存取此頁面</div>;
    }

    const listQuery = useQuery({
        queryKey: ['kappa-eval', 'finetune-performance', 'list'],
        queryFn: listFinetunePerformance,
        enabled: !!user && isAllowedForKappaEval(user.user_id),
    });

    useEffect(() => {
        if (!currentId && listQuery.data?.items.length) {
            const firstUnfinished = listQuery.data.items.find((x) => !x.is_completed) || listQuery.data.items[0];
            setSearchParams({ id: String(firstUnfinished.id) }, { replace: true });
        }
    }, [listQuery.data, currentId]);

    const sampleQuery = useQuery({
        queryKey: ['kappa-eval', 'finetune-performance', 'sample', currentId],
        queryFn: () => getFinetunePerformance(currentId),
        enabled: currentId > 0,
    });

    useEffect(() => {
        if (sampleQuery.data) {
            setPerformance(sampleQuery.data.teacher_performance || '');
            setNote(sampleQuery.data.teacher_note || '');
        }
    }, [sampleQuery.data?.id]);

    const items = listQuery.data?.items || [];
    const currentIdx = items.findIndex((x) => x.id === currentId);
    const prevItem = currentIdx > 0 ? items[currentIdx - 1] : null;
    const nextItem = currentIdx >= 0 && currentIdx < items.length - 1 ? items[currentIdx + 1] : null;

    // 未送出草稿保護
    const isDirty =
        sampleQuery.data !== undefined &&
        (performance !== (sampleQuery.data.teacher_performance || '') ||
            note !== (sampleQuery.data.teacher_note || ''));
    useBeforeUnloadGuard(isDirty);
    const confirmNav = (): boolean =>
        !isDirty || window.confirm('此題有未送出的變更，確定要離開嗎？未送出的選擇會遺失。');

    const submitMutation = useMutation({
        mutationFn: ({ id, body }: { id: number; body: { teacher_performance: string; teacher_note: string } }) =>
            submitFinetunePerformance(id, body),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['kappa-eval'] });
            // 送出成功 → 自動跳下一個未完成題，最後一題停留
            const target =
                items.slice(currentIdx + 1).find((x) => !x.is_completed) || nextItem;
            if (target) {
                setSearchParams({ id: String(target.id) });
            }
        },
    });

    const s = sampleQuery.data;

    return (
        <div className="flex h-[calc(100vh-64px)] bg-gray-50 relative z-10">
            <aside className="w-64 border-r border-gray-200 bg-gray-50 overflow-y-auto">
                <div className="p-4 border-b border-gray-200 bg-white">
                    <button
                        onClick={() => { if (confirmNav()) navigate('/teacher/kappa-evaluation'); }}
                        className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900"
                    >
                        <FaArrowLeft /> 返回評估中心
                    </button>
                    <h2 className="mt-3 font-semibold text-gray-900">Task C2 學生表現</h2>
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
                                        ? 'bg-white border-rose-500 font-medium'
                                        : 'border-transparent hover:bg-white')
                                }
                            >
                                {it.is_completed ? (
                                    <FaCheckCircle className="text-green-500 shrink-0" />
                                ) : (
                                    <FaRegCircle className="text-gray-300 shrink-0" />
                                )}
                                <span className="font-mono text-xs text-gray-500">#{String(it.display_order).padStart(2, '0')}</span>
                                <span className="text-xs text-gray-500 truncate">{it.stratum}</span>
                            </button>
                        </li>
                    ))}
                </ul>
            </aside>

            <main className="flex-1 overflow-y-auto bg-gray-50">
                <div className="max-w-3xl mx-auto p-6 space-y-5">
                    <div className="flex items-center justify-between">
                        <h1 className="text-xl font-bold text-gray-900">
                            Task C2 · Fine-tune 學生表現
                            {s && (
                                <span className="ml-3 text-sm text-gray-500 font-normal">
                                    第 {s.display_order} / {items.length} · 分層 {s.stratum}
                                </span>
                            )}
                        </h1>
                        <div className="flex gap-2">
                            <button
                                onClick={() => { if (prevItem && confirmNav()) setSearchParams({ id: String(prevItem.id) }); }}
                                disabled={!prevItem}
                                className="p-2 rounded-md border border-gray-300 disabled:opacity-30 hover:bg-gray-100"
                            >
                                <FaChevronLeft />
                            </button>
                            <button
                                onClick={() => { if (nextItem && confirmNav()) setSearchParams({ id: String(nextItem.id) }); }}
                                disabled={!nextItem}
                                className="p-2 rounded-md border border-gray-300 disabled:opacity-30 hover:bg-gray-100"
                            >
                                <FaChevronRight />
                            </button>
                        </div>
                    </div>

                    {sampleQuery.isLoading && <div className="text-sm text-gray-500">載入中...</div>}

                    {s && (
                        <>
                            {/* 評分標準參考（LLM 當時標註用的 rubric，供教師校準） */}
                            <details className="bg-white border border-gray-200 rounded-lg text-sm">
                                <summary className="cursor-pointer px-4 py-3 font-semibold text-gray-700 hover:bg-gray-50 rounded-lg">
                                    📖 評分標準參考（LLM 當時的 rubric，點擊展開）
                                </summary>
                                <div className="px-4 pb-4 pt-1 space-y-3 text-gray-700 leading-6 border-t border-gray-100">
                                    <p className="text-xs text-gray-500">
                                        此為 fine-tune dataset 產生時 LLM 所使用的評分標準。
                                        您可以參考此 rubric 來校準判斷，或依您的專業直覺評分。
                                    </p>
                                    <div>
                                        <div className="font-semibold text-green-800">1. Correct（正確）</div>
                                        <ul className="list-disc pl-6 mt-1 text-sm">
                                            <li>學生答案是參考答案的完整且正確的改寫</li>
                                            <li>涵蓋參考答案的所有主要概念</li>
                                        </ul>
                                    </div>
                                    <div>
                                        <div className="font-semibold text-amber-800">2. Partially Correct（部分正確）</div>
                                        <ul className="list-disc pl-6 mt-1 text-sm">
                                            <li>答案部分正確，包含參考答案的部分但非全部資訊</li>
                                            <li>有遺漏或不夠完整</li>
                                        </ul>
                                    </div>
                                    <div>
                                        <div className="font-semibold text-red-800">3. Incorrect（錯誤）</div>
                                        <div className="text-sm mt-1">學生答案錯誤，符合以下任一條件：</div>
                                        <ul className="list-disc pl-6 mt-1 text-sm">
                                            <li><span className="font-medium">Contradiction（矛盾）</span>：學生答案明確與參考答案矛盾</li>
                                            <li><span className="font-medium">Irrelevant Content（不相關內容）</span>：學生答案討論了領域內容，但未提供參考答案要求的特定資訊</li>
                                            <li><span className="font-medium">Off-topic（離題）</span>：學生回答不包含相關領域內容（例如：離題評論、拒絕回答）</li>
                                        </ul>
                                    </div>
                                </div>
                            </details>

                            {/* AI 判定 */}
                            <div className="bg-rose-50 border border-rose-200 rounded-lg p-4 text-sm">
                                <div className="font-semibold text-rose-900 mb-1">AI (LLM) 判定參考</div>
                                <span className={'inline-block px-3 py-1 rounded-full font-mono ' + LEVEL_COLOR[s.ai_performance]}>
                                    {s.ai_performance}
                                </span>
                            </div>

                            {/* 題目資訊 */}
                            <section className="bg-white border border-gray-200 rounded-lg p-5 space-y-4 text-sm">
                                {s.question_snapshot.chapter && (
                                    <div className="text-xs text-gray-500">
                                        {s.question_snapshot.chapter} / {s.question_snapshot.section}
                                    </div>
                                )}
                                <div>
                                    <div className="font-semibold text-gray-700 mb-1">題目</div>
                                    <div className="whitespace-pre-wrap leading-6">{s.question_snapshot.question}</div>
                                </div>
                                <div>
                                    <div className="font-semibold text-gray-700 mb-1">參考答案</div>
                                    <div className="whitespace-pre-wrap leading-6 bg-blue-50 rounded-md p-3">
                                        {s.question_snapshot.reference_answer}
                                    </div>
                                </div>
                                <div>
                                    <div className="font-semibold text-gray-700 mb-1">學生答案</div>
                                    <div className="whitespace-pre-wrap leading-6 bg-gray-50 rounded-md p-3">
                                        {s.question_snapshot.student_answer}
                                    </div>
                                </div>
                            </section>

                            {/* 評分區 */}
                            <div className="bg-white border border-gray-200 rounded-lg p-5 space-y-4">
                                <div>
                                    <h3 className="font-semibold text-gray-900">您判定的學生表現</h3>
                                </div>
                                <div className="flex gap-2">
                                    {PERFORMANCE_LEVELS.map((lvl) => (
                                        <button
                                            key={lvl}
                                            type="button"
                                            onClick={() => setPerformance(lvl)}
                                            className={
                                                'flex-1 py-2 rounded-md border transition-colors text-sm ' +
                                                (performance === lvl
                                                    ? 'bg-rose-600 text-white border-rose-600'
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
                                <div className="flex items-center justify-between">
                                    <div className="text-xs text-gray-500">
                                        {s.submitted_at ? `已於 ${new Date(s.submitted_at).toLocaleString()} 送出` : '尚未送出'}
                                    </div>
                                    <button
                                        type="button"
                                        disabled={!performance || submitMutation.isPending}
                                        onClick={() =>
                                            submitMutation.mutate({
                                                id: s.id,
                                                body: { teacher_performance: performance, teacher_note: note },
                                            })
                                        }
                                        className={
                                            'px-4 py-2 rounded-md text-sm font-medium ' +
                                            (!performance || submitMutation.isPending
                                                ? 'bg-gray-200 text-gray-500 cursor-not-allowed'
                                                : 'bg-rose-600 text-white hover:bg-rose-700')
                                        }
                                    >
                                        {submitMutation.isPending ? '送出中...' : s.teacher_performance ? '更新' : '送出'}
                                    </button>
                                </div>
                            </div>

                            {submitMutation.isError && (
                                <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm">
                                    送出失敗：{(submitMutation.error as Error).message}
                                </div>
                            )}
                        </>
                    )}
                </div>
            </main>
        </div>
    );
}
