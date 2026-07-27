import React, { useState, useEffect } from 'react';
import { FaSpinner, FaCheckCircle, FaTimesCircle, FaExclamationCircle, FaStar, FaSyncAlt } from 'react-icons/fa';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  MasteredChallengeQuestion,
  ChallengeEvaluationResult,
  ChallengeHistoryItem,
  studentApi,
} from '../../services/studentApi';
import { formatDateTime } from '../../utils/dateUtils';

interface ReviewMasteredQuestionsSectionProps {
  unitId: number;
  countPerKp?: number;
  unitSessionId?: string; // [NEW] 學習路徑 Session ID
  onComplete?: (results: ChallengeEvaluationResult[]) => void;
}

const difficultyBadge = (level?: string) => {
  const map: Record<string, string> = {
    hard: 'bg-red-100 text-red-700',
    medium: 'bg-yellow-100 text-yellow-700',
    easy: 'bg-green-100 text-green-700',
  };
  return map[level ?? ''] ?? 'bg-gray-100 text-gray-500';
};

const difficultyLabel = (level?: string) => ({
  hard: '難', medium: '中', easy: '易'
}[level ?? ''] ?? level ?? '–');

const ReviewMasteredQuestionsSection: React.FC<ReviewMasteredQuestionsSectionProps> = ({
  unitId,
  countPerKp = 2,
  unitSessionId,
  onComplete,
}) => {
  const [questions, setQuestions] = useState<MasteredChallengeQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [evalResults, setEvalResults] = useState<Record<number, ChallengeEvaluationResult>>({});
  // 歷史紀錄：key 為 question_id（string 因後端回傳 string key）
  const [history, setHistory] = useState<Record<string, ChallengeHistoryItem>>({});
  const [historyLoaded, setHistoryLoaded] = useState(false);

  useEffect(() => {
    fetchQuestions();
  }, [unitId, countPerKp]);

  const fetchQuestions = async () => {
    setIsLoading(true);
    setError(null);
    setHistoryLoaded(false);
    try {
      const res = await studentApi.getReviewMasteredKpQuestions(unitId, { countPerKp });
      setQuestions(res.mastered_kp_questions);

      // 查詢歷史紀錄
      const qIds = res.mastered_kp_questions.map((q: MasteredChallengeQuestion) => q.question_id);
      if (qIds.length > 0) {
        try {
          const hist = await studentApi.getChallengeHistory(qIds);
          setHistory(hist);
        } catch {
          // 歷史查詢失敗不影響主流程
        }
      }
      setHistoryLoaded(true);
    } catch (err: any) {
      setError('無法載入挑戰題目');
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRefresh = () => {
    setIsSubmitted(false);
    setEvalResults({});
    setHistory({});
    setHistoryLoaded(false);
    setAnswers({});
    setError(null);
    fetchQuestions();
  };

  const handleSubmit = async () => {
    const unanswered = questions.filter(q => !answers[q.question_id]?.trim());
    if (unanswered.length > 0) {
      setError(`還有 ${unanswered.length} 題尚未作答`);
      return;
    }

    try {
      setIsSubmitting(true);
      setError(null);

      // 單一請求：提交所有作答 + LLM 評估 → 後端純 INSERT 至 student_challenge_logs
      // ⚠️ 刻意不呼叫 evaluateMastery，避免觸發 BERT/LIME
      const batchResult = await studentApi.submitChallenges({
        answers: questions.map(q => ({
          question_id: q.question_id,
          knowledge_point_id: q.kp_id,
          answer: answers[q.question_id].trim(),
          difficulty_level: q.difficulty_level,
          question_type: q.question_type,
          question_text: q.question_text,
        })),
        unit_session_id: unitSessionId
      });

      const resultsMap: Record<number, ChallengeEvaluationResult> = {};
      batchResult.results.forEach((r: ChallengeEvaluationResult) => {
        resultsMap[r.question_id] = r;
      });
      setEvalResults(resultsMap);
      setIsSubmitted(true);

      onComplete?.(batchResult.results);
    } catch (err: any) {
      setError(err.message || '提交失敗，請稍後再試');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="mt-8 p-8 bg-purple-50 rounded-2xl border border-purple-100 flex items-center justify-center gap-3 text-purple-600">
        <FaSpinner className="animate-spin" size={20} />
        <span className="font-medium">載入精熟挑戰題中...</span>
      </div>
    );
  }

  if (!questions.length) {
    return (
      <div className="mt-8 p-6 bg-purple-50 rounded-2xl border border-purple-100 text-center">
        <FaStar className="mx-auto mb-3 text-3xl text-purple-300" />
        <p className="font-semibold text-purple-700">目前無精熟知識點的 AI 挑戰題</p>
        <p className="text-sm text-purple-500 mt-1">可能尚無 AI 生成題目，或所有題目已挑戰過</p>
      </div>
    );
  }

  return (
    <div className="mt-8 bg-gradient-to-br from-purple-50 via-indigo-50 to-blue-50 rounded-2xl border border-purple-100 shadow-sm p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-purple-100 flex items-center justify-center text-purple-600 shadow-sm">
            <FaStar size={16} />
          </div>
          <div>
            <h3 className="text-lg font-bold text-gray-800">精熟知識點挑戰題</h3>
            <p className="text-sm text-gray-500">恭喜！以下為你已精熟的知識點 AI 進階挑戰</p>
          </div>
        </div>
        {!isSubmitted && (
          <button
            onClick={handleRefresh}
            disabled={isLoading || isSubmitting}
            className="p-2 text-purple-600 hover:bg-purple-100 rounded-lg transition-colors disabled:opacity-50 flex items-center gap-1.5 text-sm font-medium"
            title="換一批題目"
          >
            <FaSyncAlt size={14} /> 換題
          </button>
        )}
      </div>

      {/* Questions */}
      <div className="space-y-4">
        {questions.map((q, idx) => {
          const eval_ = evalResults[q.question_id];
          const hasEval = isSubmitted && eval_;

          let borderCls = 'border-purple-100 bg-white';
          let statusIcon = null;

          if (hasEval) {
            if (eval_.correctness === 'correct') {
              borderCls = 'border-green-200 bg-green-50';
              statusIcon = <FaCheckCircle className="text-green-600" />;
            } else if (eval_.correctness === 'partially_correct') {
              borderCls = 'border-yellow-200 bg-yellow-50';
              statusIcon = <FaExclamationCircle className="text-yellow-600" />;
            } else {
              borderCls = 'border-red-200 bg-red-50';
              statusIcon = <FaTimesCircle className="text-red-600" />;
            }
          }

          return (
            <div key={q.question_id} className={`rounded-xl border p-5 transition-all ${borderCls}`}>
              <div className="flex gap-4">
                <span className="flex-shrink-0 w-7 h-7 rounded-full bg-purple-100 flex items-center justify-center text-purple-600 font-bold text-sm">
                  {idx + 1}
                </span>
                <div className="flex-grow">
                  {/* Meta badges */}
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <div className="text-base font-medium text-gray-800 leading-relaxed prose prose-sm max-w-none">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{q.question_text}</ReactMarkdown>
                      </div>
                      <div className="flex gap-2 mt-1.5 flex-wrap">
                        <span className="text-xs px-2 py-0.5 bg-purple-100 text-purple-700 rounded-full">
                          {q.kp_name}
                        </span>
                        <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${difficultyBadge(q.difficulty_level)}`}>
                          {difficultyLabel(q.difficulty_level)}
                        </span>
                        <span className="text-xs px-2 py-0.5 bg-indigo-100 text-indigo-600 rounded-full">
                          🤖 AI 生成
                        </span>
                      </div>
                    </div>
                    {hasEval && <div className="ml-3 flex-shrink-0">{statusIcon}</div>}
                  </div>

                  {/* Answer Input — same 4-case renderer as RecommendedQuestionsSection */}
                  {(() => {
                    const qType = q.question_type;

                    // 1. Multiple Choice — A/B/C/D radio grid with actual option text
                    if (qType === 'multiple_choice') {
                      // Normalise options: dict {A: '...', B: '...'} or array ['...', '...']
                      const rawOpts = q.options;
                      const optEntries: { key: string; text: string }[] = (['A', 'B', 'C', 'D'] as const).map((k, i) => {
                        let text = '';
                        if (Array.isArray(rawOpts)) text = String(rawOpts[i] ?? '');
                        else if (rawOpts && typeof rawOpts === 'object') text = String((rawOpts as Record<string, string>)[k] ?? '');
                        return { key: k, text };
                      });
                      return (
                        <div className="grid grid-cols-2 gap-3 mt-4">
                          {optEntries.map(({ key: option, text: optText }) => {
                            const isSelected = answers[q.question_id] === option;
                            return (
                              <label key={option} className={`
                                flex items-center gap-3 p-3 rounded-xl border-2 cursor-pointer transition-all
                                ${isSubmitted ? 'cursor-not-allowed' : 'hover:border-purple-300 hover:bg-purple-50/50'}
                                ${isSelected && !isSubmitted ? 'border-purple-400 bg-purple-50' : 'border-gray-100 bg-white'}
                              `}>
                                <input
                                  type="radio"
                                  name={`mastered-q-${q.question_id}`}
                                  value={option}
                                  checked={isSelected}
                                  onChange={e => setAnswers(prev => ({ ...prev, [q.question_id]: e.target.value }))}
                                  disabled={isSubmitted || isSubmitting}
                                  className="w-4 h-4 text-purple-600 focus:ring-purple-500"
                                />
                                <span className={`font-bold flex-shrink-0 ${isSelected ? 'text-purple-700' : 'text-gray-500'}`}>{option}.</span>
                                {optText && <span className={`text-sm ${isSelected ? 'text-purple-800' : 'text-gray-700'}`}>{optText}</span>}
                              </label>
                            );
                          })}
                        </div>
                      );
                    }


                    // 2. True/False — 是 / 否
                    if (qType === 'true_false') {
                      const tfOptions = [{ key: 'true', label: '是' }, { key: 'false', label: '否' }];
                      return (
                        <div className="flex gap-4 mt-4">
                          {tfOptions.map(opt => {
                            const isSelected = String(answers[q.question_id] || '').toLowerCase() === opt.key;
                            return (
                              <button
                                key={opt.key}
                                onClick={() => setAnswers(prev => ({ ...prev, [q.question_id]: opt.key }))}
                                disabled={isSubmitted || isSubmitting}
                                className={`
                                  flex-1 py-3 px-6 rounded-xl border-2 font-bold transition-all
                                  ${isSubmitted ? 'cursor-not-allowed opacity-80' : 'hover:scale-[1.02] active:scale-[0.98]'}
                                  ${isSelected && !isSubmitted ? 'border-purple-500 bg-purple-50 text-purple-700' : 'border-gray-100 bg-white text-gray-500'}
                                `}
                              >
                                {opt.label} {isSelected ? '✓' : ''}
                              </button>
                            );
                          })}
                        </div>
                      );
                    }

                    // 3. Fill in the Blank
                    if (qType === 'fill_in_blank') {
                      return (
                        <div className="mt-4">
                          <input
                            type="text"
                            value={answers[q.question_id] || ''}
                            onChange={e => setAnswers(prev => ({ ...prev, [q.question_id]: e.target.value }))}
                            disabled={isSubmitted || isSubmitting}
                            placeholder="請在此輸入答案..."
                            className={`
                              w-full px-5 py-3 rounded-xl border-2 font-medium transition-all
                              focus:outline-none focus:ring-4
                              ${isSubmitted
                                ? 'bg-gray-50 border-gray-100 text-gray-700 cursor-not-allowed'
                                : 'border-purple-50 focus:border-purple-400 focus:ring-purple-50/50'}
                            `}
                          />
                        </div>
                      );
                    }

                    // 4. Short Answer (Default)
                    return (
                      <div className="mt-4 space-y-2">
                        <textarea
                          value={answers[q.question_id] || ''}
                          onChange={e => setAnswers(prev => ({ ...prev, [q.question_id]: e.target.value }))}
                          disabled={isSubmitted || isSubmitting}
                          placeholder="請在此輸入你的答案..."
                          className={`
                            w-full px-4 py-3 rounded-xl border-2 resize-none text-sm
                            focus:outline-none focus:ring-4 transition-all
                            ${isSubmitted
                              ? 'bg-gray-50 border-gray-200 cursor-not-allowed'
                              : 'border-gray-100 focus:border-purple-400 focus:ring-purple-200'}
                          `}
                          rows={3}
                        />
                        <div className="flex justify-end">
                          <span className="text-[10px] font-bold text-gray-400 bg-gray-50 px-2 py-0.5 rounded-full">
                            {answers[q.question_id]?.length || 0} 字
                          </span>
                        </div>
                      </div>
                    );
                  })()}



                  {/* Feedback + Explanation — 和推薦題相同的雙區塊渲染 */}
                  {(() => {
                    // 來源優先序：(1) 剛繳交的評估結果 (2) 歷史紀錄
                    const hist = history[String(q.question_id)];
                    const source = hasEval ? eval_ : (historyLoaded && hist ? hist : null);
                    if (!source) return null;

                    // 解析出純 feedback（去掉 ### 題目解析 後面的部分）
                    const rawFeedback = source.feedback || '';
                    const splitIdx = rawFeedback.indexOf('### 題目解析');
                    const pureFeedback = splitIdx >= 0 ? rawFeedback.slice(0, splitIdx).trim() : rawFeedback.trim();
                    // explanation 優先用獨立欄位，否則從 feedback 解析
                    const explanation = source.explanation
                      || (splitIdx >= 0 ? rawFeedback.slice(splitIdx + '### 題目解析'.length).trim() : '');

                    const isHistory = !hasEval && !!hist;

                    return (
                      <div className="space-y-3 mt-4">
                        {isHistory && (
                          <div className="text-xs text-gray-400 italic flex items-center gap-1">
                            🕐 上次作答：{formatDateTime(hist.answered_at)}
                            {hist.answer && <span className="ml-2 text-gray-500">（你的答案：<span className="font-medium text-gray-600">{hist.answer}</span>）</span>}
                          </div>
                        )}

                        {/* 教師回饋（藍色）*/}
                        {pureFeedback && (
                          <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                            <div className="flex items-start gap-2">
                              <span className="text-blue-600 font-semibold text-sm flex-shrink-0">💡 教師回饋:</span>
                              <div className="text-sm text-gray-700 leading-relaxed prose prose-sm max-w-none">
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>{pureFeedback}</ReactMarkdown>
                              </div>
                            </div>
                          </div>
                        )}

                        {/* 題目解析（綠色）*/}
                        {explanation && (
                          <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg">
                            <div className="flex items-start gap-2">
                              <span className="text-emerald-700 font-semibold text-sm flex-shrink-0">📘 題目解析:</span>
                              <div className="text-sm text-gray-700 leading-relaxed prose prose-sm max-w-none
                                            prose-headings:text-emerald-900 prose-headings:font-bold
                                            prose-p:text-gray-600">
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>{explanation}</ReactMarkdown>
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })()}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Error */}
      {error && (
        <div className="mt-4 p-3 bg-red-50 border border-red-100 rounded-xl text-red-600 text-sm flex items-center gap-2">
          <FaExclamationCircle /> {error}
        </div>
      )}

      {/* Submit / After submit */}
      <div className="flex justify-center pt-6 gap-4">
        {!isSubmitted ? (
          <button
            onClick={handleSubmit}
            disabled={isSubmitting}
            className={`px-8 py-3 rounded-xl font-bold shadow-md transition-all min-w-[180px] flex items-center justify-center gap-2 ${isSubmitting
              ? 'bg-gray-300 cursor-not-allowed text-gray-500'
              : 'bg-gradient-to-r from-purple-500 to-indigo-500 text-white hover:shadow-lg hover:-translate-y-0.5'
              }`}
          >
            {isSubmitting ? <><FaSpinner className="animate-spin" /> 評估中...</> : '送出挑戰答案'}
          </button>
        ) : (
          <div className="text-center space-y-3">
            <div className="flex items-center gap-2 text-green-700 font-semibold justify-center">
              <FaCheckCircle /> 挑戰完成！
            </div>
            <button
              onClick={handleRefresh}
              className="px-6 py-2 rounded-lg font-medium text-white bg-purple-600 hover:bg-purple-700 shadow-md transition-all flex items-center gap-2 mx-auto"
            >
              <FaSyncAlt size={13} /> 換一批挑戰
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default ReviewMasteredQuestionsSection;
