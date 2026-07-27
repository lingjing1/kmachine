/**
 * Kappa Evaluation Center（Dashboard）
 *
 * 教師 Kappa 評估中心首頁，顯示 4 個任務的進度與入口。
 * 只有白名單 (user_id 34 / 6) 能進入。
 */
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { FaArrowLeft } from 'react-icons/fa';
import { useUser } from '../../../contexts/UserContext';
import {
    getOverview,
    isAllowedForKappaEval,
    type TaskName,
    type TaskProgress,
} from '../../../services/kappaEvalApi';

interface TaskCardMeta {
    task: TaskName;
    title: string;
    subtitle: string;
    path: string;
    accent: string; // tailwind bg class for header bar
}

// 卡片順序：由負擔最輕的 C2 起，依序 C2 → C1 → B → A，讓教師好上手
const TASK_META: TaskCardMeta[] = [
    {
        task: 'finetune_performance',
        title: 'Task C2 · Fine-tune 學生表現',
        subtitle: 'CSV 單題學生表現 (Correct/Partially/Incorrect)',
        path: '/teacher/kappa-evaluation/finetune-performance',
        accent: 'bg-rose-500',
    },
    {
        task: 'finetune_mastery',
        title: 'Task C1 · Fine-tune 掌握度',
        subtitle: 'CSV Mastery_Label 合理性 (待加強/尚可/精熟)',
        path: '/teacher/kappa-evaluation/finetune-mastery',
        accent: 'bg-amber-500',
    },
    {
        task: 'course62_polarity',
        title: 'Task B · LIME 極性評估',
        subtitle: 'course 62 LIME 關鍵字極性 (+/−)',
        path: '/teacher/kappa-evaluation/course62-lime?mode=polarity',
        accent: 'bg-emerald-500',
    },
    {
        task: 'course62_mastery',
        title: 'Task A · 掌握度判定',
        subtitle: 'course 62 LIME 紀錄 × RoBERTa 掌握度 (待加強/尚可/精熟)',
        path: '/teacher/kappa-evaluation/course62-lime?mode=mastery',
        accent: 'bg-indigo-500',
    },
];

function ProgressBar({ total, completed, accent }: { total: number; completed: number; accent: string }) {
    const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
    return (
        <div className="w-full">
            <div className="flex justify-between text-sm text-gray-600 mb-1">
                <span>進度</span>
                <span className="font-mono">{completed} / {total}（{pct}%）</span>
            </div>
            <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
                <div className={`h-full ${accent} transition-all`} style={{ width: `${pct}%` }} />
            </div>
        </div>
    );
}

function TaskCard({ meta, progress }: { meta: TaskCardMeta; progress?: TaskProgress }) {
    const done = progress?.completed === progress?.total && progress && progress.total > 0;
    return (
        <Link
            to={meta.path}
            className="block bg-white rounded-lg shadow-sm hover:shadow-md transition-shadow border border-gray-200 overflow-hidden"
        >
            <div className={`h-2 ${meta.accent}`} />
            <div className="p-5 space-y-3">
                <div className="flex items-start justify-between gap-3">
                    <div>
                        <h3 className="text-lg font-semibold text-gray-900">{meta.title}</h3>
                        <p className="text-sm text-gray-500 mt-0.5">{meta.subtitle}</p>
                    </div>
                    {done && (
                        <span className="shrink-0 text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full">
                            已完成
                        </span>
                    )}
                </div>
                {progress ? (
                    <ProgressBar total={progress.total} completed={progress.completed} accent={meta.accent} />
                ) : (
                    <div className="text-sm text-gray-400">載入進度中...</div>
                )}
                <div className="pt-2 text-sm text-indigo-600 font-medium">進入評估 →</div>
            </div>
        </Link>
    );
}

export default function KappaEvaluationCenter() {
    const { user } = useUser();
    const navigate = useNavigate();

    const { data, isLoading, error } = useQuery({
        queryKey: ['kappa-eval', 'overview'],
        queryFn: getOverview,
        enabled: isAllowedForKappaEval(user?.user_id),
    });

    // ---- 白名單守門 ----
    if (!user) {
        return (
            <div className="max-w-4xl mx-auto p-8">
                <p className="text-gray-500">載入使用者資料中...</p>
            </div>
        );
    }
    if (!isAllowedForKappaEval(user.user_id)) {
        return (
            <div className="max-w-4xl mx-auto p-8">
                <div className="bg-red-50 border border-red-200 rounded-lg p-6">
                    <h2 className="text-lg font-semibold text-red-800 mb-2">無權存取</h2>
                    <p className="text-sm text-red-700">
                        您的帳號未在 Kappa 評估中心的授權名單中。若有疑問請聯絡管理者。
                    </p>
                    <button
                        onClick={() => navigate('/teacher')}
                        className="mt-4 text-sm text-red-700 underline hover:text-red-900"
                    >
                        返回教師首頁
                    </button>
                </div>
            </div>
        );
    }

    // ---- 內容 ----
    const progressMap = new Map<TaskName, TaskProgress>();
    data?.tasks.forEach((t) => progressMap.set(t.task, t));

    // 返回首頁路徑依 role 動態決定
    const homePath = user.role === 'teacher' ? '/teacher' : '/student';

    return (
        <div className="min-h-screen bg-gray-50 relative z-10">
            <div className="max-w-5xl mx-auto p-8">
                <button
                    onClick={() => navigate(homePath)}
                    className="mb-4 flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900"
                >
                    <FaArrowLeft /> 返回{user.role === 'teacher' ? '教師' : '學生'}首頁
                </button>

                <div className="mb-8">
                    <h1 className="text-2xl font-bold text-gray-900 mb-2">Kappa 評估中心</h1>
                    <p className="text-sm text-gray-600">
                        四個獨立評估任務，收集完畢後離線計算 Cohen&apos;s κ。
                        目前以 <span className="font-mono text-indigo-600">teacher_id = {user.user_id}</span> 登入（{user.full_name}）。
                    </p>
                </div>

                {error && (
                    <div className="mb-6 bg-red-50 border border-red-200 text-red-700 rounded-lg p-4 text-sm">
                        載入進度失敗：{(error as Error).message}
                    </div>
                )}

                <div className="grid gap-4 md:grid-cols-2">
                    {TASK_META.map((meta) => (
                        <TaskCard key={meta.task} meta={meta} progress={progressMap.get(meta.task)} />
                    ))}
                </div>

                {isLoading && (
                    <div className="mt-6 text-sm text-gray-500 text-center">載入中…</div>
                )}
            </div>
        </div>
    );
}
