/**
 * Task C1 · Fine-tune 掌握度評估
 *
 * 教師讀整列 CSV（含 Short_Answer_Log），判定 待加強/尚可/精熟
 */
import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { FaArrowLeft, FaCheckCircle, FaRegCircle, FaChevronLeft, FaChevronRight } from 'react-icons/fa';
import { useUser } from '../../../contexts/UserContext';
import {
    getFinetuneMastery,
    isAllowedForKappaEval,
    listFinetuneMastery,
    submitFinetuneMastery,
} from '../../../services/kappaEvalApi';
import { useBeforeUnloadGuard } from './useBeforeUnloadGuard';

const MASTERY_LEVELS = ['待加強', '尚可', '精熟'] as const;

export default function FinetuneMasteryPage() {
    const { user } = useUser();
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const [searchParams, setSearchParams] = useSearchParams();
    const currentId = Number(searchParams.get('id') || 0);

    const [mastery, setMastery] = useState<string>('');
    const [note, setNote] = useState<string>('');

    if (user && !isAllowedForKappaEval(user.user_id)) {
        return <div className="p-8 text-red-700">無權存取此頁面</div>;
    }

    const listQuery = useQuery({
        queryKey: ['kappa-eval', 'finetune-mastery', 'list'],
        queryFn: listFinetuneMastery,
        enabled: !!user && isAllowedForKappaEval(user.user_id),
    });

    useEffect(() => {
        if (!currentId && listQuery.data?.items.length) {
            const firstUnfinished = listQuery.data.items.find((x) => !x.is_completed) || listQuery.data.items[0];
            setSearchParams({ id: String(firstUnfinished.id) }, { replace: true });
        }
    }, [listQuery.data, currentId]);

    const sampleQuery = useQuery({
        queryKey: ['kappa-eval', 'finetune-mastery', 'sample', currentId],
        queryFn: () => getFinetuneMastery(currentId),
        enabled: currentId > 0,
    });

    // 切換題目時帶入教師現有答案
    useEffect(() => {
        if (sampleQuery.data) {
            setMastery(sampleQuery.data.teacher_mastery || '');
            setNote(sampleQuery.data.teacher_note || '');
        }
    }, [sampleQuery.data?.id]);

    const items = listQuery.data?.items || [];
    const currentIdx = items.findIndex((x) => x.id === currentId);
    const prevItem = currentIdx > 0 ? items[currentIdx - 1] : null;
    const nextItem = currentIdx >= 0 && currentIdx < items.length - 1 ? items[currentIdx + 1] : null;

    // 未送出草稿保護：若當前表單內容跟 DB 最後一次送出不同，離開前警告
    const isDirty =
        sampleQuery.data !== undefined &&
        (mastery !== (sampleQuery.data.teacher_mastery || '') ||
            note !== (sampleQuery.data.teacher_note || ''));
    useBeforeUnloadGuard(isDirty);
    // 站內導航前的確認（翻頁、側邊欄跳題、返回鈕）
    const confirmNav = (): boolean =>
        !isDirty || window.confirm('此題有未送出的變更，確定要離開嗎？未送出的選擇會遺失。');

    const submitMutation = useMutation({
        mutationFn: ({ id, body }: { id: number; body: { teacher_mastery: string; teacher_note: string } }) =>
            submitFinetuneMastery(id, body),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['kappa-eval'] });
            // 送出成功 → 自動跳下一個未完成題（無則跳下一位），最後一題停留
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
            {/* 左側清單 */}
            <aside className="w-64 border-r border-gray-200 bg-gray-50 overflow-y-auto">
                <div className="p-4 border-b border-gray-200 bg-white">
                    <button
                        onClick={() => { if (confirmNav()) navigate('/teacher/kappa-evaluation'); }}
                        className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900"
                    >
                        <FaArrowLeft /> 返回評估中心
                    </button>
                    <h2 className="mt-3 font-semibold text-gray-900">Task C1 Fine-tune 掌握度</h2>
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
                                        ? 'bg-white border-amber-500 font-medium'
                                        : 'border-transparent hover:bg-white')
                                }
                            >
                                {it.is_completed ? (
                                    <FaCheckCircle className="text-green-500 shrink-0" />
                                ) : (
                                    <FaRegCircle className="text-gray-300 shrink-0" />
                                )}
                                <span className="font-mono text-xs text-gray-500">#{String(it.display_order).padStart(2, '0')}</span>
                                <span className="text-xs text-gray-500">{it.stratum}</span>
                            </button>
                        </li>
                    ))}
                </ul>
            </aside>

            <main className="flex-1 overflow-y-auto bg-gray-50">
                <div className="max-w-4xl mx-auto p-6 space-y-5">
                    <div className="flex items-center justify-between">
                        <h1 className="text-xl font-bold text-gray-900">
                            Task C1 · Fine-tune 掌握度評估
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
                            {/* AI 判定 */}
                            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-sm">
                                <div className="font-semibold text-amber-900 mb-1">AI (LLM) 判定參考</div>
                                <div className="text-amber-800">
                                    Mastery Label：<span className="font-mono font-semibold">{s.ai_mastery}</span>
                                    {s.csv_row.Mastery_Ratio != null && (
                                        <span className="ml-3 text-amber-700">Ratio {s.csv_row.Mastery_Ratio}</span>
                                    )}
                                </div>
                            </div>

                            {/* 學生資訊 */}
                            <section className="bg-white border border-gray-200 rounded-lg p-5 text-sm">
                                <div className="grid grid-cols-2 gap-3">
                                    <div>
                                        <span className="text-gray-500">學生</span>
                                        <div className="font-medium">
                                            {s.csv_row.username}（#{s.csv_row.user_id}）
                                        </div>
                                    </div>
                                    <div>
                                        <span className="text-gray-500">章節</span>
                                        <div className="font-medium">{s.csv_row.chapter}</div>
                                    </div>
                                    <div>
                                        <span className="text-gray-500">節次</span>
                                        <div className="font-medium">{s.csv_row.section}</div>
                                    </div>
                                </div>
                            </section>

                            {/* Short_Answer_Log */}
                            <section>
                                <h2 className="text-sm font-semibold text-gray-700 mb-2">簡答題作答紀錄</h2>
                                <pre className="whitespace-pre-wrap font-sans text-sm leading-6 bg-white rounded-lg p-4 border border-gray-200 max-h-[60vh] overflow-y-auto">
                                    {s.csv_row.Short_Answer_Log || '（無資料）'}
                                </pre>
                            </section>

                            {/* 評分區 */}
                            <div className="bg-white border border-gray-200 rounded-lg p-5 space-y-4">
                                <div>
                                    <h3 className="font-semibold text-gray-900">您判定的掌握度</h3>
                                    <p className="text-xs text-gray-500 mt-1">綜合學生作答狀況，您認為最合適的等級</p>
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
                                                    ? 'bg-amber-600 text-white border-amber-600'
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
                                        disabled={!mastery || submitMutation.isPending}
                                        onClick={() =>
                                            submitMutation.mutate({
                                                id: s.id,
                                                body: { teacher_mastery: mastery, teacher_note: note },
                                            })
                                        }
                                        className={
                                            'px-4 py-2 rounded-md text-sm font-medium ' +
                                            (!mastery || submitMutation.isPending
                                                ? 'bg-gray-200 text-gray-500 cursor-not-allowed'
                                                : 'bg-amber-600 text-white hover:bg-amber-700')
                                        }
                                    >
                                        {submitMutation.isPending ? '送出中...' : s.teacher_mastery ? '更新' : '送出'}
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
