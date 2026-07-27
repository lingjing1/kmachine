import React, { useState, useEffect, useRef, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useNavigate, useParams } from 'react-router-dom';
import { FaSpinner, FaCheckCircle, FaPencilAlt, FaTimesCircle, FaExclamationCircle, FaChevronRight, FaChevronLeft, FaClock, FaCommentDots, FaLightbulb } from 'react-icons/fa';
import { RiMarkPenFill } from 'react-icons/ri';
import {
  submitQuestionLog,
  batchEvaluate,
  submitAssignment,
  submitExam,
  getSubmission,
  evaluateMastery,
  EvaluationResult,
  QuestionItem
} from '../../services/studentApi';
import { formatDateTime } from '../../utils/dateUtils';
interface ShortAnswerQuizSectionProps {
  knowledgePointId: number;
  questions: QuestionItem[];
  onCitationClick?: (
    chunkId: number | string,
    evidence: string,
    matchScore?: number,
    fullChunk?: any,
    questionId?: number,
    refType?: 'question' | 'section'
  ) => void;
  onEvaluationComplete: (results: EvaluationResult[]) => void;
  onReturnToCourse?: () => void;
  contentType?: 'assignment' | 'exam' | 'practice';
  contentId?: number;
  showAnswersAfter?: string | null;
  durationMinutes?: number | null;

  nextItem?: any;
  prevItem?: any;
  onNavigateToItem?: (item: any) => void;
  unitSessionId?: string;
  knowledgePointName?: string;
  isExpired?: boolean;
  onScoreLoaded?: (scoreInfo: { score?: number; is_manual?: boolean; includeInGrade?: boolean }) => void;
}

const ShortAnswerQuizSection: React.FC<ShortAnswerQuizSectionProps> = ({
  knowledgePointId,
  questions,
  // studentId removed
  onEvaluationComplete,
  onCitationClick,
  onReturnToCourse,
  contentType = 'practice',
  contentId,
  showAnswersAfter,
  durationMinutes,

  nextItem,
  prevItem,
  onNavigateToItem,
  unitSessionId,
  knowledgePointName,
  isExpired = false,
  onScoreLoaded
}) => {
  const navigate = useNavigate();
  const { courseId } = useParams<{ courseId: string }>();
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [evaluationResults, setEvaluationResults] = useState<Record<number, EvaluationResult>>({});

  // 歷史記錄與重做控制
  const [canRetry, setCanRetry] = useState(true);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);

  // 倒數計時器
  const [timeRemaining, setTimeRemaining] = useState<number | null>(null); // 秒
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const hasAutoSubmitted = useRef(false);

  // 格式化時間顯示: X hr X min X sec
  const formatTime = useCallback((totalSeconds: number): string => {
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    const parts: string[] = [];
    if (hours > 0) parts.push(`${hours} hr`);
    if (minutes > 0 || hours > 0) parts.push(`${minutes} min`);
    parts.push(`${seconds} sec`);
    return parts.join(' ');
  }, []);

  // === 載入歷史提交記錄 ===
  useEffect(() => {
    // 當 contentId 改變時，重置狀態
    setAnswers({});
    setEvaluationResults({});
    setIsSubmitted(false);
    setCanRetry(true);

    setTimeRemaining(null);
    hasAutoSubmitted.current = false;
    setError(null);

    if ((contentType === 'assignment' || contentType === 'exam') && contentId) {
      const loadHistory = async () => {
        setIsLoadingHistory(true);
        try {
          const submission = await getSubmission(contentId);
          if (submission) {
            // 填入歷史答案
            const answersMap: Record<number, string> = {};
            const resultsMap: Record<number, EvaluationResult> = {};
            submission.results.forEach((r, index) => {
              const question = questions[index];
              if (question) {
                answersMap[question.id] = r.student_answer;
                resultsMap[question.id] = {
                  log_id: submission.submission_id,
                  question_id: question.id,
                  correctness: r.correctness as any,
                  feedback: r.feedback,
                  explanation: r.explanation,
                  evaluated_at: submission.submitted_at || new Date().toISOString()
                };
              }
            });
            setAnswers(answersMap);
            setEvaluationResults(resultsMap);
            setIsSubmitted(true);
            setCanRetry(submission.can_retry);

            // 成績顯示
            if (submission.include_in_grade) {

              if (onScoreLoaded) {
                onScoreLoaded({
                  score: submission.score ?? undefined,
                  is_manual: submission.is_manual,
                  includeInGrade: true
                });
              }
            }
          }
        } catch (err) {
          console.log('未找到歷史提交記錄');
        } finally {
          setIsLoadingHistory(false);
        }
      };
      loadHistory();
    }
  }, [contentType, contentId]); // 移除 questions，避免父元件 rerender 時重複觸發

  // === 倒數計時器 ===
  useEffect(() => {
    if (!durationMinutes || durationMinutes <= 0 || isSubmitted) return;

    const storageKey = `exam_start_${contentId}`;
    let startTime: number;

    const stored = localStorage.getItem(storageKey);
    if (stored) {
      startTime = parseInt(stored, 10);
    } else {
      startTime = Date.now();
      localStorage.setItem(storageKey, String(startTime));
    }

    const totalDurationMs = durationMinutes * 60 * 1000;

    const updateTimer = () => {
      const elapsed = Date.now() - startTime;
      const remaining = Math.max(0, Math.floor((totalDurationMs - elapsed) / 1000));
      setTimeRemaining(remaining);

      if (remaining <= 0 && !hasAutoSubmitted.current) {
        hasAutoSubmitted.current = true;
        // 清除計時器並自動提交
        if (timerRef.current) clearInterval(timerRef.current);
        localStorage.removeItem(storageKey);
      }
    };

    updateTimer();
    timerRef.current = setInterval(updateTimer, 1000);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [durationMinutes, contentId, isSubmitted]);

  // 時間到自動提交
  useEffect(() => {
    if (timeRemaining === 0 && hasAutoSubmitted.current && !isSubmitted && !isSubmitting) {
      handleSubmit();
    }
  }, [timeRemaining]);

  const handleAnswerChange = (questionId: number, value: string) => {
    setAnswers(prev => ({
      ...prev,
      [questionId]: value
    }));
    setError(null);
  };

  const handleRetry = () => {
    setIsSubmitted(false);
    setEvaluationResults({});
    setError(null);
    // 保留答案，讓學生可以修改後重新提交
  };

  const handleSubmit = async () => {
    if (isExpired) {
      setError('此測驗已截止，無法再提交答案。');
      return;
    }

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

      // 🔹 根據 contentType 選擇不同的提交方式
      if (contentType === 'assignment' || contentType === 'exam') {
        // === 作業/考試：使用 submissions_* 表 ===
        if (!contentId) {
          throw new Error('Missing contentId for assignment/exam submission');
        }

        console.log(`📝 提交${contentType === 'assignment' ? '作業' : '考試'}...`);

        // 準備提交資料
        const submissionData = {
          answers: questions.map(question => {
            const questionText = question.question_text || question.question;
            const questionType = question.type || question.question_type || 'short_answer';

            return {
              question_text: questionText,
              question_type: questionType,
              student_answer: answers[question.id].trim(),
              correct_answer: question.correct_answer,  // 選擇題用
              reference_answer: (question as any).sample_answer || (question as any).answer || (question as any).correct_answer,  // 簡答題/填空題用
              detailed_explanation: (question as any).detailed_explanation // 傳遞原有解析
            };
          }),
          unit_session_id: unitSessionId
        };

        // 呼叫對應的 API
        const result = contentType === 'assignment'
          ? await submitAssignment(contentId, submissionData)
          : await submitExam(contentId, submissionData);

        console.log('✅ 提交評分完成:', result);

        // 轉換結果格式以符合組件期望
        const resultsMap: Record<number, EvaluationResult> = {};
        result.results.forEach((r, index) => {
          const question = questions[index];
          resultsMap[question.id] = {
            log_id: result.submission_id,
            question_id: question.id,
            correctness: r.correctness as 'correct' | 'incorrect' | 'partially_correct',
            feedback: r.feedback,
            explanation: (r as any).explanation,
            evaluated_at: new Date().toISOString()
          };
        });

        setEvaluationResults(resultsMap);
        setIsSubmitted(true);



        onEvaluationComplete(result.results.map((r, idx) => ({
          log_id: result.submission_id,
          question_id: questions[idx].id,
          correctness: r.correctness as any,
          feedback: r.feedback,
          explanation: (r as any).explanation,
          evaluated_at: new Date().toISOString()
        })));


      } else {
        // === 練習題：使用 student_question_logs 表（原有邏輯）===
        console.log('📝 提交練習題答案...');

        const logPromises = questions.map(question => {
          const questionType = question.type || question.question_type || 'short_answer';
          const questionText = question.question_text || question.question;

          return submitQuestionLog({
            question_id: question.id || undefined,
            knowledge_point_id: knowledgePointId,
            stage: 'preview',
            answer: answers[question.id].trim(),
            question_type: questionType,
            correct_answer: question.correct_answer,
            question_text: questionText,
            detailed_explanation: (question as any).detailed_explanation,
            unit_session_id: unitSessionId
          });
        });

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
        onEvaluationComplete(batchResult.results);

        // 背景觸發 BERT/LIME 掌握度評估（不等待結果，不阻塞 UI）
        evaluateMastery(knowledgePointId, { stage: 'preview' }).catch(err =>
          console.warn('⚠️ BERT/LIME 評估失敗（不影響練習）:', err)
        );
      }

    } catch (err: any) {
      console.error('❌ 提交失敗:', err);
      setError(err.message || '提交失敗，請稍後再試。');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="max-w-full mx-auto">
      {/* Loading History */}
      {isLoadingHistory && (
        <div className="flex items-center justify-center py-8 gap-3 text-blue-600">
          <FaSpinner className="animate-spin" />
          <span className="font-medium">載入歷史紀錄中...</span>
        </div>
      )}

      {/* Timer Bar */}
      {timeRemaining !== null && !isSubmitted && (
        <div className={`mb-6 flex items-center justify-center gap-3 px-6 py-3 rounded-xl border-2 font-bold text-lg shadow-sm transition-colors ${timeRemaining <= 60 ? 'bg-red-50 border-red-300 text-red-700 animate-pulse' :
          timeRemaining <= 300 ? 'bg-amber-50 border-amber-300 text-amber-700' :
            'bg-blue-50 border-blue-200 text-blue-700'
          }`}>
          <FaClock className="text-xl" />
          <span>剩餘 {formatTime(timeRemaining)}</span>
        </div>
      )}

      {/* Score Text (Only shown after teacher verification) */}

      <div className="flex items-center gap-3 mb-8">
        <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 shadow-sm">
          <FaPencilAlt size={18} />
        </div>
        <div>
          <h3 className="text-xl font-bold text-neutral-text-main">測驗練習</h3>
          <p className="text-sm text-neutral-text-tertiary">
            共 {questions.length} 題，請仔細作答
          </p>
        </div>
      </div>

      <div className="space-y-6">
        {questions.map((question, index) => {
          const evaluation = evaluationResults[question.id];
          const hasEvaluation = isSubmitted && evaluation;

          // Check if we should show answers/feedback based on showAnswersAfter (only for exams)
          let showFeedback = true;
          if (contentType === 'exam' && showAnswersAfter) {
            const now = new Date();
            const showTime = new Date(showAnswersAfter);
            if (now < showTime) {
              showFeedback = false;
            }
          }

          if (isExpired) {
            // In expired mode, if not submitted, don't show anything besides the question
          }

          let statusColorClass = 'bg-gray-200';
          if (hasEvaluation && showFeedback) {
            if (evaluation.correctness === 'correct') {
              statusColorClass = 'bg-green-500';
            } else if (evaluation.correctness === 'partially_correct') {
              statusColorClass = 'bg-yellow-500';
            } else {
              statusColorClass = 'bg-red-500';
            }
          }

          // Get question text from either field
          const questionText = question.question_text || question.question;

          return (
            <div
              key={question.id}
              className="relative bg-white rounded-xl border border-gray-100 p-6 shadow-sm transition-all hover:shadow-md overflow-hidden"
            >
              {/* Right Side Status Bar */}
              {hasEvaluation && showFeedback && (
                <div className={`absolute right-0 top-0 bottom-0 w-1 ${statusColorClass}`} />
              )}
              <div className="flex gap-4">
                <span className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 font-bold text-sm">
                  {index + 1}
                </span>
                <div className="flex-grow">
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex-grow">
                      <h4 className="text-lg font-medium text-neutral-text-main leading-relaxed flex-grow prose prose-neutral max-w-none">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{questionText}</ReactMarkdown>
                      </h4>
                      <div className="flex flex-wrap items-center gap-2 mt-2">
                        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 bg-amber-50 text-amber-700 border border-amber-200 rounded text-[10px] font-bold uppercase tracking-wider">
                          <FaLightbulb size={10} className="text-amber-500" />
                          {(question as any).knowledge_point_name || knowledgePointName || '測驗題目'}
                        </span>
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-1.5 ml-4 flex-shrink-0 min-w-[70px]">
                      {hasEvaluation && showFeedback && (
                        <div className="flex items-center gap-2">
                          {evaluation.correctness === 'correct' ? <FaCheckCircle className="text-green-500" /> :
                            evaluation.correctness === 'partially_correct' ? <FaExclamationCircle className="text-yellow-500" /> :
                              <FaTimesCircle className="text-red-500" />}
                          <span className="text-sm font-semibold whitespace-nowrap">
                            {evaluation.correctness === 'correct' ? '回答正確' :
                              evaluation.correctness === 'partially_correct' ? '部分正確' :
                                '需要改進'}
                          </span>
                        </div>
                      )}
                      {hasEvaluation && !showFeedback && (
                        <div className="flex items-center gap-2 flex-shrink-0">
                          <span className="text-xs px-2 py-1 bg-blue-200 text-blue-800 rounded-full font-medium">已提交</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* PDF Source Reference */}
                  {question.source && question.source.filename && (
                    <div className="mb-3">
                      <button
                        onClick={() => {
                          if (onCitationClick && question.source) {
                            onCitationClick(
                              question.source.chunk_ids?.[0] || `q-${question.id}`,
                              question.source.text || questionText,
                              question.source.match_score,
                              {
                                source: question.source.filename,
                                page_number: question.source.page_number,
                                source_metadata: question.source.source_metadata
                              },
                              question.id,
                              'question'
                            );
                          }
                        }}
                        className="text-xs text-blue-600 hover:text-blue-800 hover:underline flex items-center gap-1.5 transition-colors"
                      >
                        <span className="font-semibold">📄</span>
                        <span>{question.source.filename}</span>
                        {question.source.page_number && (
                          <span className="text-gray-500">(p. {question.source.page_number})</span>
                        )}
                      </button>
                    </div>
                  )}

                  {/* Render based on question type */}
                  {(() => {
                    const questionType = question.type || question.question_type;

                    // 1. Multiple Choice Question
                    if (questionType === 'multiple_choice' && question.options) {
                      return (
                        <div className="grid grid-cols-1 gap-3">
                          {Object.entries(question.options).map(([key, value]) => {
                            const isSelected = answers[question.id] === key;
                            const isCorrect = question.correct_answer === key;
                            const showCorrectness = isSubmitted && showFeedback && (isSelected || isCorrect);

                            return (
                              <label
                                key={key}
                                className={`
                                  flex items-start gap-3 p-4 rounded-xl border-2 cursor-pointer transition-all
                                  ${isSubmitted ? 'cursor-not-allowed opacity-90' : 'hover:border-blue-300 hover:bg-blue-50/30'}
                                  ${isSelected && !isSubmitted ? 'border-blue-400 bg-blue-50' : 'border-gray-100 bg-white'}
                                  ${showCorrectness && isCorrect ? 'border-green-300 bg-green-50 shadow-sm' :
                                    showCorrectness && isSelected && !isCorrect ? 'border-red-300 bg-red-50 shadow-sm' : ''}
                                `}
                              >
                                <input
                                  type="radio"
                                  name={`question-${question.id}`}
                                  value={key}
                                  checked={isSelected}
                                  onChange={(e) => handleAnswerChange(question.id, e.target.value)}
                                  disabled={isSubmitted || isSubmitting}
                                  className="mt-1 w-4 h-4 text-blue-600 focus:ring-blue-500"
                                />
                                <div className="flex-grow flex items-center justify-between">
                                  <div className="flex gap-2">
                                    <span className="font-bold text-blue-600">{key}.</span>
                                    <span className="text-gray-700">{value}</span>
                                  </div>
                                  {showCorrectness && isCorrect && <FaCheckCircle className="text-green-500 text-lg" />}
                                  {showCorrectness && isSelected && !isCorrect && <FaTimesCircle className="text-red-500 text-lg" />}
                                </div>
                              </label>
                            );
                          })}
                        </div>
                      );
                    }

                    // 2. True/False Question
                    if (questionType === 'true_false') {
                      const options = [
                        { key: 'true', label: '是' },
                        { key: 'false', label: '否' }
                      ];

                      return (
                        <div className="flex flex-wrap gap-4">
                          {options.map((opt) => {
                            const isSelected = String(answers[question.id] || '').toLowerCase() === opt.key;
                            const isCorrect = String(question.correct_answer || '').toLowerCase() === opt.key;
                            const showCorrectness = isSubmitted && showFeedback && (isSelected || isCorrect);

                            return (
                              <button
                                key={opt.key}
                                onClick={() => handleAnswerChange(question.id, opt.key)}
                                disabled={isSubmitted || isSubmitting}
                                className={`
                                  flex-1 min-w-[120px] py-3.5 px-6 rounded-xl border-2 font-bold transition-all flex items-center justify-center gap-2
                                  ${isSubmitted ? 'cursor-not-allowed' : 'hover:scale-[1.02] active:scale-[0.98]'}
                                  ${isSelected && !isSubmitted ? 'border-blue-500 bg-blue-50 text-blue-700 shadow-md' : 'border-gray-100 bg-white text-gray-500'}
                                  ${showCorrectness && isCorrect ? 'border-green-500 bg-green-100 text-green-700 shadow-sm' :
                                    showCorrectness && isSelected && !isCorrect ? 'border-red-500 bg-red-100 text-red-700 shadow-sm' : ''}
                                `}
                              >
                                {opt.label}
                                {showCorrectness && isCorrect && <FaCheckCircle className="text-green-600" />}
                                {showCorrectness && isSelected && !isCorrect && <FaTimesCircle className="text-red-600" />}
                              </button>
                            );
                          })}
                        </div>
                      );
                    }

                    // 3. Fill in the Blank
                    if (questionType === 'fill_in_blank') {
                      return (
                        <div className="space-y-3">
                          <div className="relative">
                            <input
                              type="text"
                              value={answers[question.id] || ''}
                              onChange={(e) => handleAnswerChange(question.id, e.target.value)}
                              disabled={isSubmitted || isSubmitting}
                              placeholder="請輸入答案..."
                              className={`
                                w-full px-5 py-4 rounded-xl border-2 font-medium transition-all
                                focus:outline-none focus:ring-4
                                ${isSubmitted
                                  ? 'bg-gray-50 border-gray-100 text-gray-700 cursor-not-allowed'
                                  : 'border-blue-100 focus:border-blue-400 focus:ring-blue-50/50'
                                }
                              `}
                            />
                            {isSubmitted && evaluation && (
                              <div className="absolute right-4 top-1/2 -translate-y-1/2">
                                {evaluation.correctness === 'correct' ? (
                                  <FaCheckCircle className="text-green-500 text-xl" />
                                ) : (
                                  <FaTimesCircle className="text-red-500 text-xl" />
                                )}
                              </div>
                            )}
                          </div>
                          {isSubmitted && showFeedback && evaluation && evaluation.correctness !== 'correct' && (
                            <div className="px-4 py-2 bg-amber-50 border border-amber-100 rounded-lg text-sm text-amber-800 flex items-center gap-2 shadow-sm animate-in fade-in slide-in-from-top-1 duration-300">
                              <span className="flex-shrink-0">ℹ️</span>
                              <div className="flex items-center gap-2">
                                <span className="font-medium">正確答案：</span>
                                <code className="bg-amber-100/50 px-2 py-0.5 rounded text-amber-900 font-bold border border-amber-200/50">
                                  {question.correct_answer}
                                </code>
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    }

                    // 4. Short Answer Question (default)
                    return (
                      <div className="space-y-2">
                        <textarea
                          value={answers[question.id] || ''}
                          onChange={(e) => handleAnswerChange(question.id, e.target.value)}
                          disabled={isSubmitted || isSubmitting}
                          placeholder="請在此輸入你的答案..."
                          className={`
                            w-full px-4 py-4 rounded-xl border-2 resize-none leading-relaxed transition-all
                            focus:outline-none focus:ring-4
                            ${isSubmitted
                              ? 'bg-gray-50 border-gray-100 cursor-not-allowed'
                              : 'border-gray-100 focus:border-blue-400 focus:ring-blue-50/50'
                            }
                          `}
                          rows={4}
                        />
                        <div className="flex justify-end">
                          <span className="text-xs font-bold text-gray-400 bg-gray-50 px-3 py-1 rounded-full border border-gray-100">
                            {answers[question.id]?.length || 0} 字
                          </span>
                        </div>
                      </div>
                    );
                  })()}

                  {/* Teacher Feedback (💡) - Modern Style */}
                  {hasEvaluation && showFeedback && evaluation.feedback && (
                    <div className="mt-4 pl-4 border-l-4 border-blue-200 bg-blue-50/20 py-1">
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

                  {/* Question Explanation (深度解析與引導) - Modern Style */}
                  {hasEvaluation && showFeedback && (evaluation as any).explanation && (
                    <div className="mt-4 pl-4 border-l-4 border-emerald-200 bg-emerald-50/20 py-1">
                      <div className="flex items-center gap-2 mb-2">
                        <RiMarkPenFill className="text-emerald-500" size={14} />
                        <span className="text-[11px] font-bold text-emerald-500 uppercase tracking-widest">
                          深度解析與引導
                        </span>
                      </div>
                      <div className="text-sm text-emerald-900/80 font-medium leading-relaxed prose prose-sm max-w-none">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {(evaluation as any).explanation}
                        </ReactMarkdown>
                      </div>
                    </div>
                  )}
                  {hasEvaluation && !showFeedback && (
                    <div className="mt-4 p-4 bg-gray-50 border border-gray-200 rounded-xl">
                      <p className="text-sm text-gray-500 italic text-center">
                        答案將於 {formatDateTime(showAnswersAfter!)} 後公佈
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}

        {/* Error Message */}
        {error && (
          <div className="text-red-600 bg-red-50 border border-red-100 p-4 rounded-xl flex items-center gap-3 justify-center animate-fade-in">
            <span className="font-semibold">⚠️</span>
            {error}
          </div>
        )}

        {/* Submit Button */}
        {!isSubmitted ? (
          <div className="flex flex-col items-center gap-6 pt-6">
            {!isExpired ? (
              <button
                onClick={handleSubmit}
                disabled={isSubmitting}
                className={`
                  px-10 py-4 rounded-xl font-bold shadow-lg
                  transition-all min-w-[240px] flex items-center justify-center gap-3
                  ${isSubmitting
                    ? 'bg-gray-300 cursor-not-allowed'
                    : 'bg-gradient-to-r from-blue-500 to-blue-600 text-white hover:shadow-blue-500/40 hover:-translate-y-0.5 active:translate-y-0'
                  }
                `}
              >
                {isSubmitting ? (
                  <>
                    <FaSpinner className="animate-spin" />
                    評估中...
                  </>
                ) : (
                  <>
                    送出答案
                  </>
                )}
              </button>
            ) : (
              <div className="bg-gray-100 border border-gray-200 rounded-xl p-6 text-center shadow-sm w-full max-w-md">
                <FaTimesCircle className="mx-auto text-gray-300 mb-3" size={40} />
                <p className="font-bold text-gray-600">此測驗已截止</p>
                <p className="text-sm text-gray-400 mt-1">超過截止時間，不開放補考或提交。</p>
              </div>
            )}

            <button
              onClick={() => {
                if (onReturnToCourse) {
                  onReturnToCourse();
                } else {
                  navigate(`/student/course/${courseId}`);
                }
              }}
              className="px-8 py-3 bg-white text-gray-700 border border-gray-200 rounded-xl font-bold shadow-sm hover:bg-gray-50 transition-all flex items-center gap-2"
            >
              <FaChevronLeft size={14} className="text-gray-400" />
              <span>返回課程列表</span>
            </button>
          </div>
        ) : (
          <div className="text-center pt-6 space-y-4">
            <div className="text-neutral-text-secondary font-medium p-6 w-full mb-6">
              <h4 className="text-xl font-bold text-blue-800 flex items-center justify-center gap-2 mb-2">
                <FaCheckCircle className="text-blue-500" />
                評估完成！
              </h4>
              <p className="text-neutral-text-secondary">
                {contentType === 'exam' && showAnswersAfter && new Date() < new Date(showAnswersAfter)
                  ? `已收到您的作答。答案將於 ${formatDateTime(showAnswersAfter)} 後公佈。`
                  : "已收到 AI 教師的回饋，請查看上方每題的評語。"
                }
              </p>
            </div>

            <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mx-auto">
              {prevItem && onNavigateToItem && (
                <button
                  onClick={() => onNavigateToItem(prevItem)}
                  className="px-6 py-3 bg-white text-gray-700 border border-gray-200 rounded-xl font-bold shadow-sm hover:bg-gray-50 transition-all flex items-center gap-2 order-3 sm:order-1"
                >
                  上一份
                </button>
              )}

              {canRetry && !isExpired && (
                <button
                  onClick={handleRetry}
                  className="px-8 py-3 rounded-xl font-semibold text-blue-600 bg-white border-2 border-blue-200 hover:bg-blue-50 hover:border-blue-300 transition-all flex items-center justify-center gap-2 order-2"
                >
                  重新作答
                </button>
              )}

              {nextItem && onNavigateToItem ? (
                <button
                  onClick={() => onNavigateToItem(nextItem)}
                  className="px-8 py-3 bg-theme-primary text-white rounded-xl font-bold shadow-lg shadow-blue-500/20 hover:shadow-blue-500/30 hover:-translate-y-0.5 transition-all flex items-center justify-center gap-3 order-1 sm:order-3"
                >
                  <span>下一份：{nextItem.title}</span>
                  <FaChevronRight size={14} />
                </button>
              ) : (
                <button
                  onClick={() => {
                    if (onReturnToCourse) {
                      onReturnToCourse();
                    } else {
                      navigate(`/student/course/${courseId}`);
                    }
                  }}
                  className="px-8 py-3 bg-theme-primary text-white rounded-xl font-bold shadow-lg shadow-blue-500/20 hover:shadow-blue-500/30 hover:-translate-y-0.5 transition-all flex items-center justify-center gap-2 order-1 sm:order-3"
                >
                  <span>返回課程列表</span>
                  <FaChevronRight size={14} />
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ShortAnswerQuizSection;
