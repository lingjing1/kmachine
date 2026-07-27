import React, { useState, useEffect, useRef } from 'react';
import { FaSpinner, FaCheckCircle, FaLightbulb, FaTimesCircle, FaExclamationCircle, FaSyncAlt, FaCommentDots } from 'react-icons/fa';
import { MdQuiz } from 'react-icons/md';
import { RiMarkPenFill } from 'react-icons/ri';
import { LuListRestart } from 'react-icons/lu';
import {
  getRecommendedQuestions,
  submitQuestionLog,
  batchEvaluate,
  evaluateMastery,
  getKPQuestionLogs,
  RecommendedQuestionItem,
  EvaluationResult
} from '../../services/studentApi';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import Toast from '../common/Toast';

interface RecommendedQuestionsSectionProps {
  knowledgePointIds: number[];
  courseId?: number | string;
  stage: 'preview' | 'review';
  countPerKp?: number;
  totalMax?: number;
  unitSessionId?: string; // [NEW] 學習路徑 Session ID
  onComplete?: (results: EvaluationResult[]) => void;
}

const RecommendedQuestionsSection: React.FC<RecommendedQuestionsSectionProps> = ({
  knowledgePointIds,
  courseId,
  stage,
  countPerKp = 2,
  totalMax = 10,
  unitSessionId,
  onComplete
}) => {
  // Keep a stable ref to onComplete so useEffect doesn't re-run when parent re-renders
  const onCompleteRef = useRef(onComplete);
  useEffect(() => { onCompleteRef.current = onComplete; }, [onComplete]);
  const [questions, setQuestions] = useState<RecommendedQuestionItem[]>([]);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [evaluationResults, setEvaluationResults] = useState<Record<number, EvaluationResult>>({});
  const [showToast, setShowToast] = useState(false);

  // Fetch recommended questions on mount
  useEffect(() => {
    const fetchData = async () => {
      if (knowledgePointIds.length === 0) {
        setIsLoading(false);
        return;
      }

      try {
        setIsLoading(true);
        setError(null);

        // 1. Fetch current logs for these KPs to see if already answered
        const logsRes = await getKPQuestionLogs(knowledgePointIds, stage);
        const existingLogs = logsRes.logs;

        // 2. Fetch recommended questions
        const response = await getRecommendedQuestions(knowledgePointIds, courseId, {
          question_type: 'short_answer',
          count_per_kp: countPerKp,
          total_max: totalMax
        });

        if (existingLogs && existingLogs.length > 0) {
          // If we have logs, it means student has participated
          setIsSubmitted(true);

          // Deduplicate by question_id: keep only the latest record per question.
          // Backend returns logs in DESC order (newest first), so keep the first occurrence.
          const latestLogMap = new Map<number, any>();
          existingLogs.forEach((log: any) => {
            if (!latestLogMap.has(log.question_id)) {
              latestLogMap.set(log.question_id, log);
            }
          });
          const uniqueLogs = Array.from(latestLogMap.values());

          const historyQuestions: RecommendedQuestionItem[] = [];
          const historyAnswers: Record<number, string> = {};
          const historyEvaluations: Record<number, EvaluationResult> = {};

          uniqueLogs.forEach((log: any) => {
            // Reconstruct question item
            historyQuestions.push({
              id: log.question_id,
              question: log.question_text,
              question_type: 'short_answer',
              knowledge_point_id: log.knowledge_point_id || 0,
              knowledge_point_name: log.knowledge_point_name || '',
              detailed_explanation: log.detailed_explanation || undefined,
            });

            historyAnswers[log.question_id] = log.student_answer;
            historyEvaluations[log.question_id] = {
              log_id: log.log_id,
              question_id: log.question_id,
              correctness: log.correctness,
              feedback: log.feedback,
              evaluated_at: log.evaluated_at
            };
          });

          setQuestions(historyQuestions);
          setAnswers(historyAnswers);
          setEvaluationResults(historyEvaluations);

          // If we have history, we might not need to show "new" recommended questions 
          // unless there's many more KPs. For now, showing history is priority.
        } else {
          setQuestions(response.questions);
        }
      } catch (err: any) {
        console.error('Failed to fetch practice data:', err);
        setError('無法載入推薦題目');
      } finally {
        setIsLoading(false);
      }
    };

    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [knowledgePointIds, countPerKp, totalMax, courseId, stage]);

  const handleAnswerChange = (questionId: number, value: string) => {
    setAnswers(prev => ({
      ...prev,
      [questionId]: value
    }));
    setError(null);
  };

  const handleRefresh = async () => {
    setIsLoading(true);
    setIsSubmitted(false);
    setEvaluationResults({});
    setAnswers({});

    try {
      const response = await getRecommendedQuestions(knowledgePointIds, courseId, {
        question_type: 'short_answer',
        count_per_kp: countPerKp
      });
      setQuestions(response.questions);
      setError(null);
    } catch (err: any) {
      console.error('Failed to refresh questions:', err);
      setError('無法重新載入題目');
    } finally {
      setIsLoading(false);
    }
  };

  const handleRetry = () => {
    setIsSubmitted(false);
    setEvaluationResults({});
    // Optional: Clear answers or keep them for refinement? 
    // Usually retry means "try again", so maybe keep answers is better UX for minor fixes
    // creating a new log entry on submit.
    // If user wants to clear, they can manually clear. 
    // Let's keep answers for now as 'refining' answer.
    setError(null);
  };

  const handleSubmit = async () => {
    // Validate all questions are answered
    const unansweredCount = questions.length - Object.keys(answers).length;
    if (unansweredCount > 0) {
      setError(`還有 ${unansweredCount} 題尚未作答，請完成所有題目後再送出。`);
      return;
    }

    // Check for empty answers
    const emptyAnswers = questions.filter(q => !answers[q.id]?.trim());
    if (emptyAnswers.length > 0) {
      setError('請確保所有答案都有填寫內容。');
      return;
    }

    try {
      setIsSubmitting(true);
      setError(null);

      // Submit each answer to student_question_logs
      const logPromises = questions.map(question =>
        submitQuestionLog({
          question_id: question.id,
          knowledge_point_id: question.knowledge_point_id,
          stage: stage,
          answer: answers[question.id].trim(),
          question_type: question.question_type,
          question_text: question.question,
          unit_session_id: unitSessionId
        })
      );

      const logResponses = await Promise.all(logPromises);
      const logIds = logResponses.map(res => res.log_id);
      console.log('✅ 答案提交成功，log_ids:', logIds);

      // Batch evaluate using LLM
      console.log('🤖 LLM 評估中...');
      const batchResult = await batchEvaluate(logIds);
      console.log('✅ LLM 評估完成:', batchResult);

      const resultsMap: Record<number, EvaluationResult> = {};
      batchResult.results.forEach(result => {
        resultsMap[result.question_id] = result;
      });

      setEvaluationResults(resultsMap);
      setIsSubmitted(true);
      setShowToast(true);

      // Mark knowledge points as completed in student_knowledge_mastery
      try {
        const evaluationPromises = knowledgePointIds.map(kpId =>
          evaluateMastery(kpId, {
            stage: stage,
            unit_session_id: unitSessionId
          })
        );
        await Promise.all(evaluationPromises);
        console.log('✅ 知識點精熟度評估完成並標記為已完成');
      } catch (evalErr) {
        console.error('❌ 標記知識點完成失敗:', evalErr);
      }

      onCompleteRef.current?.(batchResult.results);

    } catch (err: any) {
      console.error('❌ 提交失敗:', err);
      setError('網路不穩或系統忙碌中，請稍後再試。');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Don't hide completely if no knowledge points - user wants to see the section
  // if (knowledgePointIds.length === 0) {
  //   return null;
  // }

  // Loading state
  if (isLoading) {
    return (
      <div className="mt-8 py-8 transition-all">
        <div className="flex items-center justify-center gap-3 text-blue-600">
          <FaSpinner className="animate-spin" size={20} />
          <span className="font-medium">正在載入推薦練習題目...</span>
        </div>
      </div>
    );
  }

  if (knowledgePointIds.length === 0 || questions.length === 0) {
    return null;
  }

  return (
    <div className="py-6 transition-all">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 shadow-sm border border-blue-200">
            <MdQuiz size={20} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-bold text-gray-800">推薦練習題目</h3>
            </div>
            <p className="text-sm text-gray-500">
              根據本教材知識點，從題庫推薦 {questions.length} 題相關練習題
            </p>
          </div>
        </div>

        {!isSubmitted && (
          <button
            onClick={handleRefresh}
            disabled={isLoading || isSubmitting}
            className="p-2 text-blue-600 hover:bg-blue-100 rounded-lg transition-colors disabled:opacity-50"
            title="換一批題目"
          >
            <FaSyncAlt size={16} />
          </button>
        )}
      </div>

      {/* Questions */}
      <div className="space-y-4">
        {questions.map((question, index) => {
          const evaluation = evaluationResults[question.id];
          const hasEvaluation = isSubmitted && evaluation;

          // Determine correctness styling
          let correctnessIcon = null;
          let correctnessText = '';
          let statusColorClass = 'bg-gray-200'; // Default gray for side bar

          if (hasEvaluation) {
            if (evaluation.correctness === 'correct') {
              statusColorClass = 'bg-green-500';
              correctnessIcon = <FaCheckCircle className="text-green-500" />;
              correctnessText = '回答正確';
            } else if (evaluation.correctness === 'partially_correct') {
              statusColorClass = 'bg-yellow-500';
              correctnessIcon = <FaExclamationCircle className="text-yellow-500" />;
              correctnessText = '部分正確';
            } else {
              statusColorClass = 'bg-red-500';
              correctnessIcon = <FaTimesCircle className="text-red-500" />;
              correctnessText = '需要改進';
            }
          }

          return (
            <div
              key={question.id}
              className={`relative rounded-xl border border-gray-100 bg-white p-5 transition-all shadow-sm hover:shadow-md overflow-hidden`}
            >
              {/* Right Side Status Bar */}
              {hasEvaluation && (
                <div className={`absolute right-0 top-0 bottom-0 w-1 ${statusColorClass}`} />
              )}
              <div className="flex gap-4">
                <span className="flex-shrink-0 w-7 h-7 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 font-bold text-sm">
                  {index + 1}
                </span>
                <div className="flex-grow">
                  {/* Question Header */}
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex-grow">
                      <div className="text-base font-medium text-gray-800 leading-relaxed prose prose-blue max-w-none prose-p:my-0 prose-headings:my-1 prose-strong:text-blue-700">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {question.question}
                        </ReactMarkdown>
                      </div>
                      <div className="flex flex-wrap items-center gap-2 mt-2">
                        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 bg-amber-50 text-amber-700 border border-amber-200 rounded text-[10px] font-bold uppercase tracking-wider">
                          <FaLightbulb size={10} className="text-amber-500" />
                          {question.knowledge_point_name || '知識點'}
                        </span>
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-1.5 ml-4 flex-shrink-0 min-w-[70px]">
                      {hasEvaluation && (
                        <div className="flex items-center gap-2">
                          {correctnessIcon}
                          <span className="text-sm font-semibold whitespace-nowrap">{correctnessText}</span>
                        </div>
                      )}
                      {(question.question_type === 'short_answer' || question.question_type === 'fill_in_blank') && (
                        <span className="px-2 py-0.5 bg-gray-50 text-gray-400 rounded text-[10px] font-bold border border-gray-100">
                          {answers[question.id]?.length || 0} 字
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Answer Input based on Type */}
                  {(() => {
                    const qType = question.question_type;

                    // 1. Multiple Choice
                    if (qType === 'multiple_choice') {
                      return (
                        <div className="grid grid-cols-2 gap-3 mt-3">
                          {['A', 'B', 'C', 'D'].map(option => {
                            const isSelected = answers[question.id] === option;
                            const isSubmittedQ = isSubmitted;

                            return (
                              <label key={option} className={`
                                flex items-center gap-3 p-3 rounded-xl border-2 cursor-pointer transition-all
                                ${isSubmittedQ ? 'cursor-not-allowed' : 'hover:border-blue-300 hover:bg-blue-50/50'}
                                ${isSelected && !isSubmittedQ ? 'border-blue-400 bg-blue-50' : 'border-gray-100 bg-white'}
                              `}>
                                <input
                                  type="radio"
                                  name={`question-${question.id}`}
                                  value={option}
                                  checked={isSelected}
                                  onChange={(e) => handleAnswerChange(question.id, e.target.value)}
                                  disabled={isSubmittedQ || isSubmitting}
                                  className="w-4 h-4 text-blue-600 focus:ring-blue-500"
                                />
                                <span className={`font-bold ${isSelected ? 'text-blue-700' : 'text-gray-500'}`}>{option}</span>
                              </label>
                            );
                          })}
                        </div>
                      );
                    }

                    // 2. True/False
                    if (qType === 'true_false') {
                      const options = [
                        { key: 'true', label: '是' },
                        { key: 'false', label: '否' }
                      ];
                      return (
                        <div className="flex gap-4 mt-3">
                          {options.map((opt) => {
                            const isSelected = String(answers[question.id] || '').toLowerCase() === opt.key;
                            return (
                              <button
                                key={opt.key}
                                onClick={() => handleAnswerChange(question.id, opt.key)}
                                disabled={isSubmitted || isSubmitting}
                                className={`
                                  flex-1 py-3 px-6 rounded-xl border-2 font-bold transition-all
                                  ${isSubmitted ? 'cursor-not-allowed opacity-80' : 'hover:scale-[1.02] active:scale-[0.98]'}
                                  ${isSelected && !isSubmitted ? 'border-blue-500 bg-blue-50 text-blue-700' : 'border-gray-100 bg-white text-gray-500'}
                                `}
                              >
                                {opt.label}
                              </button>
                            );
                          })}
                        </div>
                      );
                    }

                    // 3. Fill in the Blank
                    if (qType === 'fill_in_blank') {
                      return (
                        <div className="mt-3">
                          <input
                            type="text"
                            value={answers[question.id] || ''}
                            onChange={(e) => handleAnswerChange(question.id, e.target.value)}
                            disabled={isSubmitted || isSubmitting}
                            placeholder="請在此輸入答案..."
                            className={`
                              w-full px-5 py-3 rounded-xl border-2 font-medium transition-all
                              focus:outline-none focus:ring-4
                              ${isSubmitted
                                ? 'bg-gray-50 border-gray-100 text-gray-700 cursor-not-allowed'
                                : 'border-blue-50 focus:border-blue-400 focus:ring-blue-50/50'
                              }
                            `}
                          />
                        </div>
                      );
                    }

                    // 4. Short Answer (Default)
                    return (
                      <div className="mt-3 space-y-1">
                        <textarea
                          value={answers[question.id] || ''}
                          onChange={(e) => handleAnswerChange(question.id, e.target.value)}
                          disabled={isSubmitted || isSubmitting}
                          placeholder="請在此輸入你的答案..."
                          className={`
                              w-full px-4 py-3 rounded-xl border-2 resize-none text-sm
                              focus:outline-none focus:ring-4 transition-all
                              ${isSubmitted
                              ? 'bg-gray-50 border-gray-100 text-gray-400 italic cursor-not-allowed'
                              : 'border-gray-100 focus:border-blue-400 focus:ring-blue-200'
                            }
                            `}
                          rows={2}
                        />
                      </div>
                    );
                  })()}

                  {/* LLM Feedback & Detailed Explanation */}
                  {hasEvaluation && (
                    <div className="space-y-3 mt-2">
                      {/* Teacher Feedback (💡) - Reference ExamContentView Style */}
                      {evaluation.feedback && (
                        <div className="pl-4 border-l-4 border-blue-200 bg-blue-50/20 py-1">
                          <div className="flex items-center gap-2 mb-2">
                            <FaCommentDots className="text-blue-400" size={14} />
                            <span className="text-[11px] font-bold text-blue-400 uppercase tracking-widest">
                              教師回饋
                            </span>
                          </div>
                          <div className="text-sm text-blue-900/80 font-medium leading-relaxed prose prose-sm max-w-none">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {evaluation.feedback}
                            </ReactMarkdown>
                          </div>
                        </div>
                      )}

                      {/* Detailed Explanation (題目引導) - Reference ExamContentView Style */}
                      {question.detailed_explanation && (
                        <div className="pl-4 border-l-4 border-emerald-200 bg-emerald-50/20 py-1">
                          <div className="flex items-center gap-2 mb-2">
                            <RiMarkPenFill className="text-emerald-500" size={14} />
                            <span className="text-[11px] font-bold text-emerald-500 uppercase tracking-widest">
                              深度解析與引導
                            </span>
                          </div>
                          <div className="text-sm text-emerald-900/80 font-medium leading-relaxed prose prose-sm max-w-none">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {question.detailed_explanation}
                            </ReactMarkdown>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Error Message */}
      {error && (
        <div className="mt-4 text-red-600 bg-red-50 border border-red-100 p-3 rounded-xl flex items-center gap-3 justify-center">
          <span className="font-semibold">⚠️</span>
          {error}
        </div>
      )}

      {/* Submit Button */}
      {!isSubmitted ? (
        <div className="flex justify-center pt-6">
          <button
            onClick={handleSubmit}
            disabled={isSubmitting}
            className={`
              px-8 py-3 rounded-xl font-bold shadow-md
              transition-all min-w-[200px] flex items-center justify-center gap-2
              ${isSubmitting
                ? 'bg-gray-300 cursor-not-allowed'
                : 'bg-gradient-to-r from-blue-500 to-blue-600 text-white hover:shadow-lg hover:-translate-y-0.5 active:translate-y-0'
              }
            `}
          >
            {isSubmitting ? (
              <>
                <FaSpinner className="animate-spin" />
                評估中...
              </>
            ) : (
              <>送出答案</>
            )}
          </button>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-4 pt-8">
          <div className="flex items-center gap-3">
            <button
              onClick={handleRetry}
              className="px-5 py-2.5 rounded-xl font-bold text-white bg-blue-600 hover:bg-blue-700 shadow-sm hover:shadow-md transition-all flex items-center gap-2 text-sm"
            >
              <LuListRestart size={16} />
              重新作答此題組
            </button>

            <button
              onClick={handleRefresh}
              className="px-5 py-2.5 rounded-xl font-bold text-blue-600 bg-white border border-blue-200 hover:bg-blue-50 shadow-sm transition-all flex items-center gap-2 text-sm"
            >
              <FaSyncAlt size={12} />
              換一批題目
            </button>
          </div>
          <p className="text-xs text-gray-400 font-medium">您可以選擇重新作答以精進答案，或挑戰新的一批題目</p>
        </div>
      )}

      {/* Success Toast */}
      {showToast && (
        <Toast
          message="評估已完成！已收到 AI 教師的回饋。"
          type="success"
          onClose={() => setShowToast(false)}
        />
      )}
    </div>
  );
};

export default RecommendedQuestionsSection;
