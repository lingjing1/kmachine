import React, { useState, useEffect, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import API_BASE_URL from '../../config/api';
import ReactMarkdown from 'react-markdown';
import { FaChevronLeft, FaChevronRight, FaCheckCircle, FaRobot, FaChevronDown, FaChevronUp } from 'react-icons/fa';
import { FaArrowLeft } from 'react-icons/fa6';
import { LuTextCursorInput, LuLightbulb } from 'react-icons/lu';
import { useOutletContext, useNavigate } from 'react-router-dom';
import Toast from '../../components/common/Toast';
import { SummaryContentView } from '../../components/reports/SummaryContentView';
import { ReferenceDrawer } from '../../components/teacher/ReferenceDrawer';

interface EvaluationResponse {
  id: number;
  exp_generated_content_id: number;
  human_fact_score?: number;
  human_quality_scores?: Record<string, number>;
  llm_agreement_status?: string;
  llm_agreement_feedback?: string;
}

interface ExperimentContentResponse {
  id: number;
  course_name: string;
  ablation_group: string;
  content_type: string;
  content: any;
  rag_metrics: any;
  critic_scores: any;
  evaluation?: EvaluationResponse;
  input_config?: Record<string, any>;
}

interface RubricItem {
  key: string;
  label: string;
  shortDesc: string;
  detailedRubric: Record<number, string>;
}

const RUBRICS: RubricItem[] = [
  {
    key: 'Faithfulness',
    label: '事實正確與忠實度 (Faithfulness)',
    shortDesc: '內容是否無事實錯誤或幻覺，且高度忠實於參考資料',
    detailedRubric: {
      1: "內容嚴重偏離事實，存在大量幻覺或錯誤資訊，與參考資料完全不符。",
      2: "存在明顯的事實錯誤或部分幻覺，雖部分基於參考資料，但有多處誤導性陳述。",
      3: "基本符合事實與參考資料，但包含少許未經證實的細節或輕微的推論過度。",
      4: "內容大致準確且忠實於參考資料，無明顯事實錯誤，僅少數細節不夠精確。",
      5: "內容完全正確，無任何幻覺，且百分之百忠實於教材與參考資料，事實無可挑剔。"
    }
  },
  {
    key: 'Understandable',
    label: '可理解性 (Understandable)',
    shortDesc: '情境設定是否完整，且專有名詞符合學生的認知與學習範圍',
    detailedRubric: {
      1: "缺乏必要情境說明，學生無法理解「為什麼要問這個問題」。或使用大量教材（RAG context）中完全未出現的專業術語（4個以上），超出學生學習範圍。",
      2: "情境說明嚴重不足，僅提供片段訊息。或使用 3 個以上超出教材範圍的專業術語，學生需要額外背景知識才能理解。",
      3: "提供基本情境，但不夠完整。或有 1-2 個術語超出教材範圍，學生經過推敲可理解題意。",
      4: "情境說明充足，學生能理解問題背景和目的。所有術語都在教材（RAG context）範圍內，符合學生程度。",
      5: "提供完整情境和背景說明，學生能清楚理解問題的來龍去脈。術語使用精準且完全符合教材內容和學生程度。"
    }
  },
  {
    key: 'Grammatical',
    label: '語法與通順度 (Grammatical & Fluency)',
    shortDesc: '行文是否自然通順，語氣如人類編寫，無拼寫或標點符號錯誤',
    detailedRubric: {
      1: "存在多個嚴重拼寫錯誤（3個以上），或出現亂碼、無意義中英文嚴重破壞閱讀。或帶有極其強烈的 AI 機器生成感或翻譯腔，句型刻板生硬，閱讀起來極度不通順，完全不像專業教師撰寫。",
      2: "有一定的 AI 痕跡（例如生硬的過渡詞），或存在 2-3 個明顯的拼寫/錯別字，或含有引起閱讀突兀的多餘字元。標點使用不當影響閱讀流暢度。句子結構基本正確但略顯生硬。",
      3: "沒有明顯的 AI 生成感，但行文風格平淡。有 1 個輕微的拼寫錯誤或標點瑕疵，但不影響整體理解。句子結構通順，文筆尚可。無亂碼或明顯無意義字眼。",
      4: "無明顯拼寫或標點錯誤，句子結構流暢自然，行文具有溫度，像是由專業教師親自撰寫。無多餘或奇怪的字元。語法與格式符合學術標準。",
      5: "語法與格式卓越，文筆極度流暢且完全正確。標點使用精準，專業術語拼寫完全正確，句子結構優美易讀，能展現出優秀教育者的專業感。"
    }
  },
  {
    key: 'Logical_Consistency',
    label: '邏輯一致性 (Logical Consistency)',
    shortDesc: '敘述邏輯是否清晰嚴謹，且與參考資料完美契合無矛盾',
    detailedRubric: {
      1: "內容與參考資料嚴重矛盾，答案明確錯誤。或敘述邏輯混亂，選項之間互相矛盾。",
      2: "內容與參考資料部分矛盾，或敘述邏輯有明顯漏洞。選項設計不當，可能有多個合理答案或無正確答案。",
      3: "內容與參考資料基本一致，但存在輕微的邏輯瑕疵或不夠精確的表述。選項設計尚可。",
      4: "內容與參考資料完全一致，邏輯清晰正確。選項設計合理，干擾項有辨識度。",
      5: "內容與參考資料完美對應，邏輯嚴謹無誤。選項設計優秀，每個選項都有明確的邏輯依據。"
    }
  },
  {
    key: 'Phrasing',
    label: '措辭正當性 (Phrasing)',
    shortDesc: '語法、用語自然且具專業度，無簡體字、大陸慣用語或過度口語化',
    detailedRubric: {
      1: "出現任何未轉化為繁體的「簡體中文字」（一票否決，給1分）。或含多個嚴重的大陸慣用語（數據、質量、智能等）。或用詞極度不符合專業教育規範（過度口語化）。",
      2: "沒有簡體字，但含有少量大陸慣用語（包含轉為繁體的如『數據』等），或出現少許不專業的口語表達。或連接詞使用重複性高，用詞顯得匱乏。",
      3: "沒有簡體字，用詞尚可，無明顯口語化或無意義字眼，但可能有 1-2 處繁體化的大陸慣用語未正確轉換為台式用語。遣詞造句缺乏變化，專業度一般。",
      4: "完全沒有簡體字或大陸慣用語，用詞清晰恰當，具有教育專業度，完全符合台灣學術用語習慣（如精準使用『資料』而非『數據』）。無不當口語表達。",
      5: "用詞精準優美，完美契合嚴謹的學術與教育規範，具備極高的教育行文水準。無任何不當字眼、簡體字或慣用語瑕疵。"
    }
  },
  {
    key: 'Core_Concept_Focus',
    label: '核心概念聚焦性 (Core Concept Focus)',
    shortDesc: '內容精準對齊並聚焦於教師選擇的目標知識點，無偏離或失焦',
    detailedRubric: {
      1: "完全偏離教師選擇的「目標知識點 (Knowledge Points)」，都在討論次要或無關的細節。分析中必須明確指出內容偏離了哪些知識點。",
      2: "有提到目標知識點，但花費過多篇幅在無關的參考資料細節上，未能妥善聚焦於該知識點的核心概念。",
      3: "基本呈現了目標知識點，但可能稍有失焦，部分內容與該知識點關聯性不大。",
      4: "清楚且準確地圍繞目標知識點進行論述，能區分主次，與學習目標緊密結合。",
      5: "完美聚焦於目標知識點，所有內容都為闡述該知識點服務，與教學目標高度對齊，沒有任何多餘或偏題的篇幅。"
    }
  },
  {
    key: 'Would_You_Use_It',
    label: '採用意願 (Would You Use It)',
    shortDesc: '生成結果是否遵循教師指示與意圖，具備教學價值',
    detailedRubric: {
      1: "完全不會。完全無視「教師自訂指令」（例如要求範例卻只給定義）。分析必須明確指出「哪一部分完全沒達到教師意圖」，並給出具體的重寫建議。",
      2: "不會。對教師指令的執行流於表面，或僅死板地貼上參考資料，失去真正的教學引導意義。分析中必須自我反省哪裡未滿足要求並說明如何修改。",
      3: "會。基本遵循教師指令，但在引導思考或應用範例等深層次意圖上尚有不足。分析必須點出「還少做什麼，可以怎麼優化才能更貼近原意」。",
      4: "會。確實遵循教師指令與意圖，只需要進行微小的內容潤飾即可完美達到教學目標。分析中需具體說明如何進一步提升效果。",
      5: "絕對會。完美執行教師的所有意圖，無論是利用參考資料、提供範例或引導思考，皆處理得完美無缺，深度與引導性兼具，無需任何修改即可直接採用。"
    }
  }
];

const MASCOTS = [
  'fill_in_blank.png',
  'planner.png',
  'quiz_master.png',
  'retriever.png',
  'short_answer.png',
  'summarizer.png',
  'true_false.png'
];

const EvaluationExperiment: React.FC = () => {
  const queryClient = useQueryClient();
  const [currentIndex, setCurrentIndex] = useState(0);
  const [initialIndexSet, setInitialIndexSet] = useState(false);
  const [allCompleted, setAllCompleted] = useState(false);
  const [randomMascot, setRandomMascot] = useState('');

  const [refDrawer, setRefDrawer] = useState<{
    isOpen: boolean;
    chunkId?: number | string;
    evidence?: string;
    matchScore?: number;
    fullChunk?: any;
    questionId?: number;
    refType?: 'question' | 'section';
  }>({
    isOpen: false
  });

  // Phase 1 State
  const [qualityScores, setQualityScores] = useState<Record<string, number>>({});

  // Phase 2 State
  const [agreementStatus, setAgreementStatus] = useState<string>('');
  const [agreementFeedback, setAgreementFeedback] = useState<string>('');

  const [toast, setToast] = useState<{ show: boolean; message: string; type: 'success' | 'error' | 'info' }>({ show: false, message: '', type: 'success' });
  const [promptExpanded, setPromptExpanded] = useState(false);
  const rightPanelRef = useRef<HTMLDivElement>(null);
  const leftPanelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    rightPanelRef.current?.scrollTo({ top: 0, behavior: 'auto' });
    leftPanelRef.current?.scrollTo({ top: 0, behavior: 'auto' });
    setPromptExpanded(false);
  }, [currentIndex]);

  // Fetch Evaluations
  const { data: contents = [], isLoading, isError } = useQuery<ExperimentContentResponse[]>({
    queryKey: ['experimentEvaluations'],
    queryFn: async () => {
      const token = localStorage.getItem('access_token');
      const res = await fetch(`${API_BASE_URL}/api/teacher/experiment/evaluations`, {
        cache: 'no-store',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (!res.ok) throw new Error('Failed to fetch evaluations');
      return res.json();
    },
    staleTime: 0 // Always fetch latest to reflect updates
  });

  const currentItem = contents[currentIndex];

  // Initialize to first incomplete task
  useEffect(() => {
    if (contents.length > 0 && !initialIndexSet) {
      const firstUnfinishedIndex = contents.findIndex(c => !c.evaluation?.llm_agreement_status);
      if (firstUnfinishedIndex !== -1) {
        setCurrentIndex(firstUnfinishedIndex);
      } else {
        setAllCompleted(true);
        setRandomMascot(MASCOTS[Math.floor(Math.random() * MASCOTS.length)]);
      }
      setInitialIndexSet(true);
    }
  }, [contents, initialIndexSet]);

  // Reset or initialize local state when item changes
  useEffect(() => {
    if (currentItem?.evaluation) {
      setQualityScores({
        ...(currentItem.evaluation.human_quality_scores || {}),
        Faithfulness: currentItem.evaluation.human_fact_score || 0
      });
      setAgreementStatus(currentItem.evaluation.llm_agreement_status || '');
      setAgreementFeedback(currentItem.evaluation.llm_agreement_feedback || '');
    } else {
      setQualityScores({});
      setAgreementStatus('');
      setAgreementFeedback('');
    }
  }, [currentIndex, currentItem]);

  const { setHeaderActions } = useOutletContext<any>();
  const navigate = useNavigate();

  useEffect(() => {
    // Determine course ID from input_config, fallback to just /teacher
    let courseId = null;
    if (currentItem && currentItem.input_config) {
      if (typeof currentItem.input_config === 'string') {
        try {
          const config = JSON.parse(currentItem.input_config);
          courseId = config.course_id;
        } catch (e) {
          console.error('Error parsing input_config', e);
        }
      } else {
        courseId = currentItem.input_config.course_id;
      }
    }

    const handleReturn = () => {
      if (courseId) {
        navigate(`/teacher/courses/${courseId}`);
      } else {
        navigate('/teacher');
      }
    };
    setHeaderActions(
      <button
        onClick={handleReturn}
        className="
          flex items-center gap-2 text-neutral-text-secondary font-medium
          transition-all duration-200 hover:text-blue-700 group
        "
        title="返回課程頁面"
      >
        <div className="w-10 h-10 rounded-xl bg-white border border-gray-200 shadow-sm flex items-center justify-center transition-all duration-200 group-hover:bg-blue-50 group-hover:border-blue-200">
          <FaArrowLeft className="w-4 h-4 flex-shrink-0 group-hover:scale-110 transition-transform" />
        </div>
        <span className="max-lg:hidden whitespace-nowrap">返回課程</span>
      </button>
    );

    return () => setHeaderActions(null);
  }, [currentItem, navigate, setHeaderActions]);

  const submitPhase1 = useMutation({
    mutationFn: async () => {
      const token = localStorage.getItem('access_token');
      const { Faithfulness, ...restQualityScores } = qualityScores;

      const res = await fetch(`${API_BASE_URL}/api/teacher/experiment/evaluations/submit`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          exp_generated_content_id: currentItem.id,
          human_fact_score: Faithfulness || 0,
          human_quality_scores: restQualityScores
        })
      });
      if (!res.ok) throw new Error('Submit failed');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['experimentEvaluations'] });
      setToast({ show: true, message: '第一階段評分已儲存！', type: 'success' });
    },
    onError: () => {
      setToast({ show: true, message: '儲存失敗', type: 'error' });
    }
  });

  const submitPhase2 = useMutation({
    mutationFn: async (evalId: number) => {
      const token = localStorage.getItem('access_token');
      const res = await fetch(`${API_BASE_URL}/api/teacher/experiment/evaluations/feedback`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          evaluation_id: evalId,
          llm_agreement_status: agreementStatus,
          llm_agreement_feedback: agreementFeedback
        })
      });
      if (!res.ok) throw new Error('Feedback failed');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['experimentEvaluations'] });
      setToast({ show: true, message: '第二階段回饋已儲存！', type: 'success' });
      setTimeout(() => {
        if (currentIndex < contents.length - 1) {
          setCurrentIndex(prev => prev + 1);
        } else {
          setRandomMascot(MASCOTS[Math.floor(Math.random() * MASCOTS.length)]);
          setAllCompleted(true);
        }
      }, 1500);
    },
    onError: () => {
      setToast({ show: true, message: '儲存失敗', type: 'error' });
    }
  });

  if (isLoading) return <div className="p-8 text-center text-gray-500">載入實驗資料中...</div>;
  if (isError) return <div className="p-8 text-center text-red-500">無法讀取實驗資料。</div>;
  if (contents.length === 0 || allCompleted) return (
    <div className="flex flex-col items-center justify-center p-12 h-full bg-slate-50">
      <div className="bg-white rounded-3xl p-10 shadow-xl max-w-lg w-full flex flex-col items-center animate-in zoom-in duration-500">
        <div className="relative w-48 h-48 mb-6">
          <img
            src={`/images/mascots/${randomMascot || 'planner.png'}`}
            alt="Success Mascot"
            className="w-full h-full object-contain drop-shadow-xl"
          />
        </div>
        <h3 className="text-2xl font-bold text-blue-600 mb-3">所有實驗評估已完成！</h3>
        <p className="text-slate-500 text-center leading-relaxed">
          感謝您用心完成本次的所有專家生成結果評分!
        </p>
        <button
          onClick={() => {
            let courseId = null;
            if (contents.length > 0 && contents[0].input_config) {
              if (typeof contents[0].input_config === 'string') {
                try { courseId = JSON.parse(contents[0].input_config).course_id; } catch (e) { }
              } else {
                courseId = contents[0].input_config.course_id;
              }
            }
            if (courseId) navigate(`/teacher/courses/${courseId}`);
            else navigate('/teacher');
          }}
          className="mt-8 px-8 py-3 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-xl shadow-md hover:shadow-lg transition-all active:scale-95"
        >
          返回課程頁面
        </button>
      </div>
    </div>
  );

  const isPhase1Done = !!currentItem.evaluation;
  const isPhase2Done = isPhase1Done && !!currentItem.evaluation?.llm_agreement_status;

  const handlePhase1Submit = () => {
    if (Object.keys(qualityScores).length < RUBRICS.length) {
      setToast({ show: true, message: '請完成所有評分項目！', type: 'error' });
      return;
    }
    submitPhase1.mutate();
  };

  const extractMainText = (content: any) => {
    if (!content) return '';
    if (typeof content === 'string') return content;
    if (content.text_content) return content.text_content;
    if (content.value) return content.value;
    if (content.data && content.data.text_content) return content.data.text_content;
    if (content.data && content.data.value) return content.data.value;
    return JSON.stringify(content, null, 2);
  };

  const getCriticData = (criticName: string) => {
    if (!currentItem.critic_scores) return null;
    return currentItem.critic_scores[criticName];
  };

  const factCritic = getCriticData('fact_critic');
  const qualityDetails = getCriticData('quality_details');
  const qualityAvg = getCriticData('quality_avg');

  return (
    <div className="flex h-full w-full bg-transparent relative overflow-hidden">

      {/* Left Panel: Content Viewer */}
      <div className="flex flex-col w-3/5 min-w-0 border-r border-gray-200 bg-transparent relative">
        {/* Content Area */}
        <div ref={leftPanelRef} className="flex-1 overflow-y-auto custom-scrollbar relative">

          {/* Sticky Header */}
          <div className="sticky top-0 z-20 flex items-center p-4 px-6 border-b border-blue-50/50 bg-transparent backdrop-blur-md">
            <div className="flex items-center gap-3 w-full max-w-5xl mx-auto">
              <span className="px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm font-bold shadow-sm whitespace-nowrap">
                評估任務 {currentIndex + 1} / {contents.length}
              </span>
              <h1 className="text-lg font-bold text-slate-800 flex items-center truncate">
                {currentItem.course_name}
                {currentItem.input_config?.unit_name && (
                  <>
                    <span className="mx-2 text-slate-300 font-normal">/</span>
                    <span className="text-slate-600 truncate">{currentItem.input_config.unit_name}</span>
                  </>
                )}
              </h1>
            </div>
          </div>

          <div className="max-w-5xl mx-auto p-6 pt-6">
            {/* AI Generation Context Box */}
            <div className="mb-6 py-2">
              <div className="flex flex-col gap-6 text-base mt-2">
                {currentItem.input_config?.prompt && (
                  <div>
                    <button
                      type="button"
                      onClick={() => setPromptExpanded((v) => !v)}
                      className="w-full flex items-center justify-between gap-2 mb-3 text-left hover:opacity-80 transition-opacity"
                      aria-expanded={promptExpanded}
                    >
                      <h3 className="font-bold text-slate-800 text-base flex items-center gap-2">
                        <LuTextCursorInput className="text-blue-600 text-lg" />
                        使用者指令 (User Prompt)
                      </h3>
                      {promptExpanded ? (
                        <FaChevronUp className="text-slate-500 text-sm" />
                      ) : (
                        <FaChevronDown className="text-slate-500 text-sm" />
                      )}
                    </button>
                    <div
                      onClick={() => !promptExpanded && setPromptExpanded(true)}
                      className={`font-medium text-slate-700 bg-white rounded-xl border border-slate-200 shadow-sm italic ${
                        promptExpanded
                          ? 'p-4 whitespace-pre-wrap leading-relaxed'
                          : 'px-4 py-2 overflow-hidden cursor-pointer hover:border-blue-300'
                      }`}
                      style={
                        promptExpanded
                          ? undefined
                          : {
                              display: '-webkit-box',
                              WebkitLineClamp: 4,
                              WebkitBoxOrient: 'vertical',
                              whiteSpace: 'pre-wrap',
                              lineHeight: '1.6rem',
                              maxHeight: 'calc(1.8rem * 4)',
                            }
                      }
                    >
                      {currentItem.input_config.prompt}
                    </div>
                  </div>
                )}
                {(currentItem.input_config?.selected_kp_names || currentItem.input_config?.selected_knowledge) && (
                  <div>
                    <h3 className="font-bold text-slate-800 mb-3 text-base flex items-center gap-2">
                      <LuLightbulb className="text-yellow-500 text-lg" />
                      選擇的知識點 (Selected Knowledge Points)
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      {(() => {
                        const kps = currentItem.input_config.selected_kp_names || currentItem.input_config.selected_knowledge;
                        if (Array.isArray(kps)) {
                          return kps.map((k: any, i: number) => {
                            const label = typeof k === 'string' ? k : k.title || k.name || JSON.stringify(k);
                            return (
                              <span key={i} className="px-4 py-1.5 bg-amber-50/80 text-amber-800 border border-amber-200/60 rounded-full text-sm font-bold shadow-sm">
                                {label}
                              </span>
                            );
                          });
                        }
                        return (
                          <span className="px-4 py-1.5 bg-amber-50/80 text-amber-800 border border-amber-200/60 rounded-full text-sm font-bold shadow-sm">
                            {String(kps)}
                          </span>
                        );
                      })()}
                    </div>
                  </div>
                )}
              </div>
            </div>

            <h2 className="text-xl font-bold mb-4 text-gray-800 pt-4 border-t border-gray-100">
              {currentItem.content?.title || "AI 生成教材內容"}
              <span className="ml-3 px-2.5 py-1 bg-blue-50 text-blue-700 rounded-lg text-sm font-bold border border-blue-200 align-middle shadow-sm">
                {(() => {
                  const typeValue = currentItem.content?.subtype || currentItem.content_type;
                  if (typeValue === 'preview') return '預習教材';
                  if (typeValue === 'review') return '複習教材';
                  return typeValue;
                })()}
              </span>
            </h2>

            <div className="prose prose-blue max-w-none prose-sm leading-relaxed mb-8">
              {(typeof currentItem.content === 'object' && currentItem.content?.sections) ? (
                <SummaryContentView
                  summary={currentItem.content}
                  materialType="preview"
                  editable={false}
                  courseId=""
                  unitId=""
                  contentId={currentItem.id}
                  onReferenceClick={(chunkId, evidence, matchScore, fullChunk, questionId, refType) => {
                    setRefDrawer({
                      isOpen: true,
                      chunkId,
                      evidence,
                      matchScore,
                      fullChunk,
                      questionId,
                      refType
                    });
                  }}
                />
              ) : (
                <ReactMarkdown>
                  {extractMainText(currentItem.content)}
                </ReactMarkdown>
              )}
            </div>



            {/* Pagination Buttons */}
            <div className="mt-12 pt-6 border-t border-gray-200 flex justify-between items-center pb-8">
              <button
                onClick={() => setCurrentIndex(prev => Math.max(0, prev - 1))}
                disabled={currentIndex === 0}
                className="px-5 py-2.5 flex items-center gap-2 font-medium text-slate-700 bg-white border border-slate-200 rounded-lg shadow-sm hover:bg-slate-50 hover:text-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <FaChevronLeft className="text-sm" /> 上一份教材
              </button>
              <button
                onClick={() => setCurrentIndex(prev => Math.min(contents.length - 1, prev + 1))}
                disabled={currentIndex === contents.length - 1 || !isPhase2Done}
                className="px-5 py-2.5 flex items-center gap-2 font-medium text-white bg-blue-600 border border-transparent rounded-lg shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-slate-300 disabled:shadow-none disabled:cursor-not-allowed transition-colors"
                title={!isPhase2Done ? "請先完成目前教材的所有評分步驟" : "下一份教材"}
              >
                下一份教材 <FaChevronRight className="text-sm" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Right Panel: Evaluation Area */}
      <div className="flex flex-col w-2/5 flex-shrink-0 bg-transparent relative z-10">
        <div ref={rightPanelRef} className="flex-1 overflow-y-auto p-6 pt-6 custom-scrollbar space-y-6 pb-24">

          {/* Phase 1: Human Evaluation */}
          <div className={`bg-white rounded-xl border p-5 shadow-sm transition-all duration-300 ${isPhase1Done ? 'border-green-200 opacity-90' : 'border-blue-200 shadow-blue-100'}`}>
            <div className="flex items-center justify-between mb-4 border-b border-gray-100 pb-3">
              <h3 className="font-bold text-gray-800 flex items-center gap-2">
                1. 教材品質評分
                {isPhase1Done && <FaCheckCircle className="text-green-500" />}
              </h3>
            </div>

            {/* Rubrics Form */}
            <div className="space-y-2 mb-6">
              {RUBRICS.map((dim, idx) => {
                const currentScore = isPhase1Done
                  ? (dim.key === 'Faithfulness'
                      ? currentItem.evaluation?.human_fact_score
                      : currentItem.evaluation?.human_quality_scores?.[dim.key])
                  : qualityScores[dim.key];
                return (
                  <div key={dim.key} className={`flex flex-col transition-all pb-6 pt-4 ${idx < RUBRICS.length - 1 ? 'border-b-2 border-gray-100' : ''}`}>
                    {/* Header Row: Title & Buttons */}
                    <div className="flex justify-between items-center mb-4">
                      <span className="font-bold text-base text-slate-800 pr-4 leading-tight">{dim.label}</span>

                      <div className="flex gap-2 shrink-0">
                        {[1, 2, 3, 4, 5].map(score => (
                          <button
                            key={score}
                            onClick={() => !isPhase1Done && setQualityScores(prev => ({ ...prev, [dim.key]: score }))}
                            disabled={isPhase1Done}
                            className={`w-11 h-11 flex items-center justify-center text-base font-bold rounded-lg transition-all 
                              ${currentScore === score
                                ? 'bg-blue-600 text-white shadow-sm ring-2 ring-blue-600/20 shadow-blue-500/30 scale-105'
                                : 'bg-white text-gray-500 border border-gray-200 hover:bg-blue-50 hover:border-blue-300 hover:text-blue-600'
                              } ${isPhase1Done && 'opacity-70 cursor-default hover:bg-white hover:border-gray-200 hover:text-gray-500'}`}
                          >
                            {score}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div className="flex flex-col gap-3">
                      <span className="text-sm font-medium text-slate-600">{dim.shortDesc}</span>

                      {/* Detailed Rubric (Default Expanded per user request) */}
                      <div className="p-4 bg-slate-50 border border-slate-100/80 rounded-xl text-sm text-slate-700 space-y-3 leading-relaxed">
                        {[5, 4, 3, 2, 1].map(score => (
                          <div key={score} className="flex gap-3 items-start transition-opacity">
                            <span className={`font-bold min-w-[36px] shrink-0 pt-0.5 ${currentScore === score ? 'text-blue-700' : 'text-slate-500'}`}>{score} 分</span>
                            <span className={currentScore === score ? 'font-medium text-blue-900' : ''}>{dim.detailedRubric[score as keyof typeof dim.detailedRubric]}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {!isPhase1Done && (
              <button
                onClick={handlePhase1Submit}
                disabled={submitPhase1.isPending}
                className="w-full mt-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-lg shadow-sm transition-colors flex items-center justify-center gap-2"
              >
                {submitPhase1.isPending ? '儲存中...' : '提交評分並解鎖 AI 短評'}
              </button>
            )}
          </div>

          {/* Phase 2: LLM Critic Reveal & Agreement */}
          <div className={`bg-white rounded-xl border p-5 shadow-sm transition-all duration-500 overflow-hidden
            ${isPhase1Done ? (isPhase2Done ? 'border-green-200 opacity-90' : 'border-indigo-200 shadow-indigo-100') : 'h-24 opacity-50 select-none grayscale cursor-not-allowed border-gray-200'}
          `}>
            <div className="flex items-center justify-between mb-4 border-b border-gray-100 pb-3">
              <h3 className="font-bold text-gray-800 flex items-center gap-2 text-lg">
                2. LLM Critic 評估結果驗證
                {isPhase2Done && <FaCheckCircle className="text-green-500 ml-1" />}
              </h3>
              {!isPhase1Done && <span className="text-xs px-2 py-1 bg-gray-100 text-gray-500 rounded font-medium">請先完成步驟 1</span>}
            </div>

            {isPhase1Done && (
              <div className="animate-in fade-in slide-in-from-top-4 duration-500">
                {/* AI Critic Output Viewer */}
                <div className="mb-6 space-y-4 bg-slate-50/50 p-2 rounded-lg">

                  {/* Fact Critic */}
                  {factCritic && factCritic.faithfulness && (
                    <div className="bg-white p-4 rounded border border-gray-100 shadow-sm">
                      <div className="flex justify-between items-center mb-2">
                        <div className="flex items-center gap-3">
                          <span className="text-sm font-bold text-gray-600">Faithfulness 評分 (5分制)</span>
                          {(() => {
                            const factHumanScore = currentItem.evaluation?.human_fact_score;
                            if (factHumanScore != null && factHumanScore > 0) {
                              return (
                                <span className="text-xs text-slate-500 font-medium bg-slate-100 px-2 py-0.5 rounded border border-slate-200 tracking-wide">
                                  您的評分: <span className="text-slate-700 font-bold ml-0.5">{factHumanScore}</span>
                                </span>
                              );
                            }
                            return null;
                          })()}
                        </div>
                        <span className={`text-base font-bold ${factCritic.passed ? 'text-green-600' : 'text-red-500'}`}>
                          {factCritic.faithfulness.score} / 5
                        </span>
                      </div>
                      <p className="text-sm text-gray-700 italic whitespace-pre-wrap leading-relaxed">{factCritic.faithfulness.analysis}</p>
                    </div>
                  )}

                  {/* Quality Critic */}
                  {qualityDetails && qualityDetails.length > 0 && (
                    <div className="bg-white p-4 rounded border border-gray-100 shadow-sm mt-4">
                      <div className="flex justify-between items-center mb-2">
                        <span className="text-sm font-bold text-gray-600">Quality Critic 評分 (平均)</span>
                        <span className="text-base font-bold text-indigo-600">
                          {qualityAvg ? Number(qualityAvg).toFixed(1) : '-'} / 5
                        </span>
                      </div>
                      <div className="space-y-4 mt-4">
                        {qualityDetails.map((detail: any, idx: number) => (
                          <div key={idx} className="text-sm text-gray-600 border-t border-gray-100 pt-3">
                            <div className="flex justify-between mb-2 items-center">
                              <div className="flex items-center gap-3">
                                <span className="font-bold text-gray-700 text-base">{detail.criteria || '綜合評估'}</span>
                                {(() => {
                                  const criteriaStr = detail.criteria || '';
                                  const matchedDim = RUBRICS.find(r => r.label === criteriaStr || r.key === criteriaStr || criteriaStr.includes(r.key));
                                  const humanScore = matchedDim && currentItem.evaluation?.human_quality_scores?.[matchedDim.key];
                                  if (humanScore) {
                                    return (
                                      <span className="text-xs text-slate-500 font-medium bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                                        您的評分: {humanScore}
                                      </span>
                                    );
                                  }
                                  return null;
                                })()}
                              </div>
                              <span className={`font-bold text-base ${detail.rating >= 4 ? 'text-green-600' : (detail.rating >= 3 ? 'text-yellow-600' : 'text-red-500')}`}>
                                {detail.rating} / 5
                              </span>
                            </div>
                            <p className="italic whitespace-pre-wrap text-gray-700 leading-relaxed">{detail.analysis}</p>
                            {detail.suggestions && detail.suggestions.length > 0 && (
                              <div className="mt-2 text-indigo-600">
                                <span className="font-semibold">建議: </span>
                                {detail.suggestions.join(" ")}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {!factCritic && (!qualityDetails || qualityDetails.length === 0) && (
                    <p className="text-sm text-gray-500 italic">無 AI 自評數據</p>
                  )}
                </div>

                {/* Agreement Form */}
                <div className="space-y-4">
                  <div>
                    <span className="font-bold text-sm text-slate-700 block mb-2">您認同 AI 的批判與評分嗎？</span>
                    <div className="flex gap-3">
                      {['Agree', 'Partially Agree', 'Disagree'].map(status => (
                        <button
                          key={status}
                          onClick={() => !isPhase2Done && setAgreementStatus(status)}
                          disabled={isPhase2Done}
                          className={`flex-1 py-2 text-sm font-medium rounded-lg border transition 
                            ${(isPhase2Done ? currentItem.evaluation?.llm_agreement_status : agreementStatus) === status
                              ? 'bg-indigo-600 text-white border-indigo-600 shadow-md'
                              : 'bg-white text-gray-600 border-gray-200 hover:bg-slate-50'
                            } ${isPhase2Done && 'cursor-default'}`}
                        >
                          {status === 'Agree' ? '👍 完全認同' : status === 'Partially Agree' ? '🤔 部分認同' : '👎 不認同'}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div>
                    <span className="font-bold text-sm text-slate-700 block mb-2">其他意見或回饋 (選填)</span>
                    <textarea
                      value={isPhase2Done ? (currentItem.evaluation?.llm_agreement_feedback || '') : agreementFeedback}
                      onChange={(e) => setAgreementFeedback(e.target.value)}
                      disabled={isPhase2Done}
                      placeholder="AI 分析哪裡好？哪裡不好？"
                      className="w-full p-3 text-sm border border-gray-200 rounded-lg outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 bg-white transition-all disabled:bg-gray-50 disabled:text-gray-500"
                      rows={3}
                    />
                  </div>
                </div>

                {!isPhase2Done && (
                  <button
                    onClick={() => {
                      if (!agreementStatus) {
                        setToast({ show: true, message: '請選擇是否認同', type: 'error' });
                        return;
                      }
                      submitPhase2.mutate(currentItem.evaluation!.id);
                    }}
                    disabled={submitPhase2.isPending}
                    className="w-full mt-6 py-3 bg-indigo-600 hover:bg-indigo-700 text-white font-bold rounded-lg shadow-sm transition-colors flex items-center justify-center gap-2"
                  >
                    {submitPhase2.isPending ? '儲存中...' : '送出回饋紀錄'}
                  </button>
                )}
              </div>
            )}
          </div>

        </div>
      </div>

      <ReferenceDrawer
        isOpen={refDrawer.isOpen}
        onClose={() => setRefDrawer(prev => ({ ...prev, isOpen: false }))}
        chunk={refDrawer.fullChunk}
        evidence={refDrawer.evidence}
        matchScore={refDrawer.matchScore}
        defaultWidthRatio={0.4}
      />

      {toast.show && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={() => setToast({ ...toast, show: false })}
        />
      )}
    </div>
  );
};

export default EvaluationExperiment;
