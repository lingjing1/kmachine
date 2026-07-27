import React, { useState, useEffect } from 'react';
import { FaSpinner, FaCheckCircle, FaTimesCircle, FaExclamationCircle, FaRedo } from 'react-icons/fa';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  PersonalMaterialKP,
  PersonalMaterialQuestion,
  EvaluationResult,
  studentApi,
  submitQuestionLog,
  batchEvaluate,
  evaluateMastery,
  getKPQuestionLogs,
} from '../../services/studentApi';
import { formatDateTime } from '../../utils/dateUtils';

interface ReviewPersonalMaterialsSectionProps {
  unitId: number;
  countPerKp?: number;
  unitSessionId?: string; // [NEW] 學習路徑 Session ID
  onComplete?: (results: EvaluationResult[]) => void;
}

// History log type from getKPQuestionLogs
interface QuestionLogEntry {
  log_id: number;
  question_id: number;
  student_answer: string;
  correctness: string;
  feedback: string;
  answered_at: string | null;
  explanation?: string;
  detailed_explanation?: string;
}

const masteryBadge = (level: string) => {
  const colors: Record<string, string> = {
    '待加強': 'bg-red-100 text-red-700 border-red-200',
    '尚可': 'bg-yellow-100 text-yellow-700 border-yellow-200',
  };
  return colors[level] ?? 'bg-gray-100 text-gray-600 border-gray-200';
};

const ReviewPersonalMaterialsSection: React.FC<ReviewPersonalMaterialsSectionProps> = ({
  unitId,
  countPerKp = 2,
  unitSessionId,
  onComplete,
}) => {
  const [kpMaterials, setKpMaterials] = useState<PersonalMaterialKP[]>([]);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [evalResults, setEvalResults] = useState<Record<number, EvaluationResult>>({});
  // History: latest log per question_id
  const [history, setHistory] = useState<Record<number, QuestionLogEntry>>({});
  const [historyLoaded, setHistoryLoaded] = useState(false);

  // Flatten questions for easy access
  const allQuestions: (PersonalMaterialQuestion & { kp_id: number; kp_name: string })[] =
    kpMaterials.flatMap(kp =>
      kp.questions.map(q => ({ ...q, kp_id: kp.kp_id, kp_name: kp.kp_name }))
    );

  useEffect(() => {
    fetchMaterials();
  }, [unitId, countPerKp]);

  const fetchMaterials = async () => {
    setIsLoading(true);
    setError(null);
    setHistoryLoaded(false);
    try {
      const res = await studentApi.getReviewPersonalMaterials(unitId, { countPerKp });
      setKpMaterials(res.kp_materials);

      // Fetch history logs for all KPs in this review
      const kpIds = res.kp_materials.map((kp: PersonalMaterialKP) => kp.kp_id);
      if (kpIds.length > 0) {
        try {
          const logsRes = await getKPQuestionLogs(kpIds, 'review');
          // Build map: question_id → latest log (logs are already sorted DESC by answered_at)
          const logMap: Record<number, QuestionLogEntry> = {};
          for (const log of logsRes.logs) {
            if (!logMap[log.question_id]) {
              logMap[log.question_id] = log;
            }
          }
          setHistory(logMap);
        } catch {
          // History fetch failure doesn't block the main flow
        }
      }
      setHistoryLoaded(true);
    } catch (err: any) {
      setError('無法載入個人化複習題目');
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRetry = () => {
    setIsSubmitted(false);
    setEvalResults({});
    setHistory({});
    setHistoryLoaded(false);
    setError(null);
    fetchMaterials();
  };

  const handleSubmit = async () => {
    const unanswered = allQuestions.filter(q => !answers[q.question_id]?.trim());
    if (unanswered.length > 0) {
      setError(`還有 ${unanswered.length} 題尚未作答`);
      return;
    }

    try {
      setIsSubmitting(true);
      setError(null);

      // Log all answers
      const logPromises = allQuestions.map(q =>
        submitQuestionLog({
          question_id: q.question_id,
          knowledge_point_id: q.kp_id,
          stage: 'review',
          answer: answers[q.question_id].trim(),
          question_type: q.question_type,
          question_text: q.question_text,
          unit_session_id: unitSessionId
        })
      );
      const logResponses = await Promise.all(logPromises);
      const logIds = logResponses.map(r => r.log_id);

      // Batch evaluate
      const batchResult = await batchEvaluate(logIds);
      const resultsMap: Record<number, EvaluationResult> = {};
      batchResult.results.forEach(r => { resultsMap[r.question_id] = r; });
      setEvalResults(resultsMap);
      setIsSubmitted(true);

      // Trigger mastery re-evaluation
      const kpIds = [...new Set(allQuestions.map(q => q.kp_id))];
      await Promise.allSettled(kpIds.map(kpId =>
        evaluateMastery(kpId, {
          stage: 'review',
          unit_session_id: unitSessionId
        })
      ));

      onComplete?.(batchResult.results);
    } catch (err: any) {
      setError(err.message || '提交失敗，請稍後再試');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="mt-8 p-8 bg-orange-50 rounded-2xl border border-orange-100 flex items-center justify-center gap-3 text-orange-600">
        <FaSpinner className="animate-spin" size={20} />
        <span className="font-medium">載入個人化複習題目中...</span>
      </div>
    );
  }

  if (!kpMaterials.length) {
    return (
      <div className="mt-8 p-6 bg-green-50 rounded-2xl border border-green-100 text-center">
        <FaCheckCircle className="mx-auto mb-3 text-3xl text-green-400" />
        <p className="font-semibold text-green-700">目前所有知識點均已精熟 🎉</p>
        <p className="text-sm text-green-600 mt-1">沒有個人化弱點練習題，繼續保持！</p>
      </div>
    );
  }

  return (
    <div className="mt-8 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-full bg-orange-100 flex items-center justify-center text-orange-600 shadow-sm flex-shrink-0">
          <FaRedo size={16} />
        </div>
        <div>
          <h3 className="text-lg font-bold text-gray-800">個人化弱點複習</h3>
          <p className="text-sm text-gray-500">針對你尚未精熟的知識點，重新練習以加深理解</p>
        </div>
      </div>

      {/* KP Groups */}
      {kpMaterials.map(kp => (
        <div key={kp.kp_id} className="bg-gradient-to-br from-orange-50 to-amber-50 rounded-2xl border border-orange-100 p-5 shadow-sm">
          {/* KP Header */}
          <div className="flex items-center gap-3 mb-4">
            <span className={`text-xs font-bold px-2.5 py-1 rounded-full border ${masteryBadge(kp.mastery_level)}`}>
              {kp.mastery_level}
            </span>
            <h4 className="font-semibold text-gray-800">{kp.kp_name}</h4>
          </div>

          {/* Questions */}
          <div className="space-y-4">
            {kp.questions.map((q, idx) => {
              const eval_ = evalResults[q.question_id];
              const hist = history[q.question_id];
              const hasEval = isSubmitted && eval_;
              // Use eval result first, then history for display
              const displaySource = hasEval ? eval_ : (historyLoaded && hist ? hist : null);
              const displayCorrectness = displaySource?.correctness;

              let borderCls = 'border-orange-100 bg-white';
              let iconEl = null;

              if (displayCorrectness) {
                if (displayCorrectness === 'correct') {
                  borderCls = 'border-green-200 bg-green-50';
                  iconEl = <FaCheckCircle className="text-green-600" />;
                } else if (displayCorrectness === 'partially_correct') {
                  borderCls = 'border-yellow-200 bg-yellow-50';
                  iconEl = <FaExclamationCircle className="text-yellow-600" />;
                } else {
                  borderCls = 'border-red-200 bg-red-50';
                  iconEl = <FaTimesCircle className="text-red-600" />;
                }
              }

              return (
                <div key={q.question_id} className={`rounded-xl border p-4 transition-all ${borderCls}`}>
                  <div className="flex gap-3">
                    <span className="flex-shrink-0 w-6 h-6 rounded-full bg-orange-100 flex items-center justify-center text-orange-600 font-bold text-xs">
                      {idx + 1}
                    </span>
                    <div className="flex-grow">
                      {/* Source badge */}
                      <div className="flex items-center justify-between mb-2">
                        <div className="text-sm font-medium text-gray-800 leading-relaxed prose prose-sm max-w-none">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{q.question_text}</ReactMarkdown>
                        </div>
                        {displayCorrectness && (
                          <div className="ml-3 flex items-center gap-1 flex-shrink-0">
                            {iconEl}
                          </div>
                        )}
                      </div>
                      <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full mr-2 ${q.source === 'retry'
                        ? 'bg-red-100 text-red-600'
                        : 'bg-gray-100 text-gray-500'
                        }`}>
                        {q.source === 'retry' ? '🔁 預習錯題' : '📚 隨機練習'}
                      </span>

                      {/* Answer textarea */}
                      <textarea
                        value={answers[q.question_id] || ''}
                        onChange={e => setAnswers(prev => ({ ...prev, [q.question_id]: e.target.value }))}
                        disabled={isSubmitted || isSubmitting}
                        placeholder="請在此輸入你的答案..."
                        className={`mt-3 w-full px-4 py-3 rounded-xl border-2 resize-none text-sm focus:outline-none focus:ring-4 transition-all ${isSubmitted
                          ? 'bg-gray-50 border-gray-200 cursor-not-allowed'
                          : 'border-orange-100 focus:border-orange-400 focus:ring-orange-100'
                          }`}
                        rows={3}
                      />

                      {/* History info (from previous attempts) */}
                      {!hasEval && historyLoaded && hist && (
                        <div className="mt-3 space-y-2">
                          <div className="text-xs text-gray-400 italic flex items-center gap-1">
                            🕐 上次作答：{formatDateTime(hist.answered_at)}
                            {hist.student_answer && (
                              <span className="ml-2 text-gray-500">（你的答案：<span className="font-medium text-gray-600">{hist.student_answer}</span>）</span>
                            )}
                          </div>

                          {/* History feedback */}
                          {hist.feedback && (
                            <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-sm text-gray-700">
                              <span className="font-semibold text-blue-700">💡 教師回饋：</span>
                              <div className="mt-1 prose prose-sm max-w-none">
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>{hist.feedback}</ReactMarkdown>
                              </div>
                            </div>
                          )}

                          {/* History explanation */}
                          {(hist.explanation || hist.detailed_explanation) && (
                            <div className="p-3 bg-indigo-50 border border-indigo-200 rounded-lg text-sm text-gray-700">
                              <span className="font-semibold text-indigo-700">📘 題目解析：</span>
                              <div className="mt-1 prose prose-sm max-w-none">
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>{hist.explanation || hist.detailed_explanation || ''}</ReactMarkdown>
                              </div>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Current submission feedback */}
                      {hasEval && eval_.feedback && (
                        <div className="mt-3 p-3 bg-blue-50 border border-blue-200 rounded-lg text-sm text-gray-700">
                          <span className="font-semibold text-blue-700">💡 教師回饋：</span>
                          <div className="mt-1 prose prose-sm max-w-none">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>{eval_.feedback}</ReactMarkdown>
                          </div>
                        </div>
                      )}
                      {hasEval && eval_.explanation && (
                        <div className="mt-2 p-3 bg-indigo-50 border border-indigo-200 rounded-lg text-sm text-gray-700">
                          <span className="font-semibold text-indigo-700">📘 題目解析：</span>
                          <div className="mt-1 prose prose-sm max-w-none">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>{eval_.explanation}</ReactMarkdown>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}

      {/* Error */}
      {error && (
        <div className="p-3 bg-red-50 border border-red-100 rounded-xl text-red-600 text-sm flex items-center gap-2">
          <FaExclamationCircle /> {error}
        </div>
      )}

      {/* Submit / Retry */}
      <div className="flex justify-center pt-2 gap-4">
        {!isSubmitted ? (
          <button
            onClick={handleSubmit}
            disabled={isSubmitting}
            className={`px-8 py-3 rounded-xl font-bold shadow-md transition-all min-w-[180px] flex items-center justify-center gap-2 ${isSubmitting
              ? 'bg-gray-300 cursor-not-allowed text-gray-500'
              : 'bg-gradient-to-r from-orange-500 to-amber-500 text-white hover:shadow-lg hover:-translate-y-0.5'
              }`}
          >
            {isSubmitting ? <><FaSpinner className="animate-spin" /> 評估中...</> : '送出答案'}
          </button>
        ) : (
          <>
            <div className="text-center">
              <div className="flex items-center gap-2 text-green-700 font-semibold mb-3">
                <FaCheckCircle /> 評估完成！
              </div>
              <button
                onClick={handleRetry}
                className="px-6 py-2 rounded-lg font-medium text-white bg-orange-500 hover:bg-orange-600 shadow-md transition-all flex items-center gap-2 mx-auto"
              >
                <FaRedo size={13} /> 重新練習
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default ReviewPersonalMaterialsSection;
