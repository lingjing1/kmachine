import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams, useParams, useOutletContext } from 'react-router-dom';
import { FaChartLine, FaCheckCircle, FaRobot, FaHeadphones, FaChevronDown, FaSpinner, FaArrowUp, FaArrowDown } from 'react-icons/fa';
import { getStudentDashboard, getCourseUnits, DashboardResponse, Unit, getEnrolledCourses } from '../../services/studentApi';
import LimeReportModal from '../../components/student/LimeReportModal';

// Types
interface OutletContext {
  setBreadcrumbPaths: React.Dispatch<React.SetStateAction<Array<{ name: string; path: string }> | null>>;
}

function Dashboard() {
  const [activeTab, setActiveTab] = useState<'pre-class' | 'post-class'>('pre-class');
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const context = useOutletContext<OutletContext>();



  const [dashboardData, setDashboardData] = useState<DashboardResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true); // Start loading immediately
  const [error, setError] = useState<string | null>(null);
  const [courseName, setCourseName] = useState<string>('課程');

  // State for LIME Modal
  const [selectedKp, setSelectedKp] = useState<{ id: number, name: string } | null>(null);

  // State for Unit Selector
  const [units, setUnits] = useState<Unit[]>([]);
  const [isUnitsOpen, setIsUnitsOpen] = useState(false);

  /* eslint-disable @typescript-eslint/no-unused-vars */
  const { courseId: routeCourseId } = useParams<{ courseId: string }>();
  /* eslint-enable @typescript-eslint/no-unused-vars */

  // Parse IDs from URL or use context
  // Rely on JWT for student identity: student_id is managed by the backend
  const courseId = routeCourseId ? parseInt(routeCourseId) : (searchParams.get('course_id') ? parseInt(searchParams.get('course_id')!) : null);
  const unitId = searchParams.get('unit_id') ? parseInt(searchParams.get('unit_id')!) : null;

  // Fetch dashboard data on mount or when IDs/Tab change
  useEffect(() => {
    const fetchData = async () => {
      if (courseId === null || unitId === null) return; // Wait for IDs to be ready
      setLoading(true);
      setError(null);
      setDashboardData(null); // Reset data to ensure clean state
      try {
        const stage = activeTab === 'pre-class' ? 'preview' : 'review';
        const data = await getStudentDashboard(courseId, unitId, { stage });
        console.log('Dashboard Data:', data);
        setDashboardData(data);
      } catch (e: any) {
        setError(e.message || '取得儀表板資料失敗');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [courseId, unitId, activeTab]);

  // Fetch units when courseID changes
  useEffect(() => {
    const fetchUnits = async () => {
      if (courseId === null) return;
      const safeCourseId = courseId; // Type narrowing
      
      try {
        const data = await getCourseUnits(safeCourseId);
        setUnits(data);
        
        // Auto-select first unit if none selected
        if (unitId === null && data.length > 0) {
          navigate(`/student/course/${safeCourseId}/dashboard?unit_id=${data[0].id}`, { replace: true });
        }
      } catch (e) {
        console.error('Failed to fetch units', e);
      }
    };
    fetchUnits();
  }, [courseId, unitId, navigate]);

  // Fetch course name
  useEffect(() => {
    const fetchCourseName = async () => {
      if (!courseId) return;
      try {
        const courses = await getEnrolledCourses();
        const course = courses.find((c: any) => c.id === courseId);
        if (course) {
          setCourseName(course.name);
        }
      } catch (e) {
        console.error('Failed to fetch course name:', e);
      }
    };
    fetchCourseName();
  }, [courseId]);

  // Set breadcrumb paths
  useEffect(() => {
    if (context?.setBreadcrumbPaths) {
      context.setBreadcrumbPaths([
        { name: '我的課程', path: '/student' },
        { name: courseName, path: `/student/course/${courseId}` },
        { name: '學習儀表板', path: `/student/course/${courseId}/dashboard` }
      ]);
    }
  }, [courseId, courseName, context?.setBreadcrumbPaths]); // Use stable dispatch function

  const getMasteryColor = (level: string) => {
    switch (level) {
      case '精熟': return 'bg-green-100 text-green-700 border-green-300';
      case '尚可': return 'bg-yellow-100 text-yellow-700 border-yellow-300';
      case '待加強': return 'bg-orange-100 text-orange-700 border-orange-300';
      default: return 'bg-gray-100 text-gray-700 border-gray-300';
    }
  };

  const getMasteryBorderColor = (level: string) => {
    switch (level) {
      case '精熟': return 'border-l-green-500';
      case '尚可': return 'border-l-yellow-500';
      case '待加強': return 'border-l-orange-500';
      default: return 'border-l-gray-400';
    }
  };

  // if (loading) { ... } removed to allow layout rendering
  // if (error) { ... } handled inline
  // if (!dashboardData) { ... } removed

  // Map backend data to UI structures
  // Map backend data to UI structures (Safe mapping)
  const analysisData = (dashboardData?.knowledge_points || []).map((kp) => {
    // Parse answer if it's a stringified JSON like "{'text': '...'}"
    let displayAnswer = '尚未作答';
    const rawAnswer = kp.recent_answers && kp.recent_answers.length > 0 ? kp.recent_answers[0].answer : null;

    if (rawAnswer) {
      try {
        const jsonStr = rawAnswer.replace(/'/g, '"');
        const parsed = JSON.parse(jsonStr);
        displayAnswer = parsed.text || rawAnswer;
      } catch (e) {
        displayAnswer = rawAnswer;
      }
    }

    const unit = units.find(u => u.id === (dashboardData?.unit_id || unitId));
    const uName = unit ? `單元 ${unit.topic_id || unit.id} ${unit.name}` : `單元 ${dashboardData?.unit_id || unitId}`;

    return {
      id: kp.knowledge_point_id,
      unitName: uName,
      knowledgePointName: kp.name,
      question: `針對 ${kp.name} 的核心概念...`,
      studentAnswer: displayAnswer,
      masteryLevel: kp.mastery_level,
      masteryLabel: `掌握度：${kp.mastery_level || '未知'}`,
      hasLime: !!kp.lime_summary
    };
  });

  const masteryStatus = (dashboardData?.knowledge_points || []).map(kp => ({
    name: kp.name,
    status: kp.mastery_level,
  }));

  // Placeholder name or ID for display
  const currentUnit = units && Array.isArray(units) ? units.find(u => u.id === unitId) : null;
  const displayUnitName = currentUnit ? currentUnit.name : `單元 ${unitId}`;

  return (
    <div className="w-full min-h-full bg-transparent relative">
      <div className="relative z-10 p-6 space-y-8">
        {/* Page Header with integrated tabs */}
        <div className="mb-6">
          <div className="flex items-center justify-between">
            <h1 className="text-3xl font-bold text-neutral-text-main flex items-center gap-3">
              <FaChartLine className="text-theme-primary" />
              學習儀表板
            </h1>

            {/* Compact Toggle - Same style as GradingEditor */}
            <div className="bg-gray-100 p-1 rounded-full flex relative shadow-inner" style={{ width: '360px' }}>
              {[{ id: 'pre-class', label: '課前診斷分析' }, { id: 'post-class', label: '課後成效追蹤' }].map((opt) => (
                <button
                  key={opt.id}
                  onClick={() => setActiveTab(opt.id as 'pre-class' | 'post-class')}
                  className={`flex-1 py-1.5 px-3 rounded-full text-base font-bold transition-all duration-200 ${activeTab === opt.id
                    ? 'bg-white text-blue-700 shadow-sm ring-1 ring-black/5'
                    : 'text-gray-500 hover:text-gray-700'
                    }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Main Content Grid */}
        <div className="flex gap-6">
          {/* Left: Analysis Area */}
          <div className="flex-1 space-y-4">
            {/* Section Header with Legend */}
            <div className="bg-theme-primary-light/50 rounded-lg px-4 py-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="font-bold text-theme-primary text-lg">關注詞彙分析：</span>
                <span className="text-sm text-neutral-text-secondary">視覺化關注詞彙</span>
              </div>
              <div className="flex items-center gap-4 text-sm">
                <div className="flex items-center gap-1.5">
                  <FaArrowUp className="text-green-600" />
                  <span className="text-neutral-text-secondary">提升掌握度</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <FaArrowDown className="text-orange-600" />
                  <span className="text-neutral-text-secondary">降低掌握度</span>
                </div>
              </div>
            </div>

            {/* Analysis Cards */}
            <div className="space-y-4">
              {loading ? (
                <div className="flex items-center justify-center py-12 bg-white rounded-lg border border-neutral-border">
                  <FaSpinner className="animate-spin text-theme-primary text-2xl" />
                  <span className="ml-2 text-theme-primary">正在分析學習數據...</span>
                </div>
              ) : error ? (
                <div className="p-4 bg-red-100 text-red-700 rounded-lg">
                  <p>⚠️ {error}</p>
                </div>
              ) : analysisData.length > 0 ? (
                analysisData.map((item) => (
                  <div
                    key={item.id}
                    className={`bg-white rounded-lg border border-neutral-border shadow-sm overflow-hidden border-l-4 ${getMasteryBorderColor(item.masteryLevel)}`}
                  >
                    {/* Card Header */}
                    <div className="px-4 py-3 bg-gray-50 border-b border-neutral-border flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <h4 className="text-lg font-bold text-theme-primary">
                          知識點：{item.knowledgePointName}
                        </h4>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className={`px-3 py-1 rounded-full text-xs font-medium border ${getMasteryColor(item.masteryLevel)}`}>
                          {item.masteryLabel}
                        </span>
                        <button
                          onClick={() => setSelectedKp({ id: item.id, name: item.knowledgePointName })}
                          className="text-xs bg-white border border-theme-primary text-theme-primary hover:bg-theme-primary hover:text-white px-3 py-1 rounded-full transition-colors flex items-center gap-1"
                        >
                          <FaChartLine /> 查看分析
                        </button>
                      </div>
                    </div>

                    {/* Card Body */}
                    <div className="p-4 space-y-4">
                      <div>
                        <p className="text-xs text-neutral-text-secondary mb-1.5 font-medium">最近作答截選：</p>
                        <div className="bg-slate-50 rounded-lg p-3 border border-slate-100">
                          <p className="text-sm text-neutral-text-main">
                            {item.studentAnswer}
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="p-8 text-center bg-white rounded-lg border border-neutral-border text-neutral-text-secondary">
                  此單元尚無學習數據。
                </div>
              )}
            </div>
          </div>

          {/* Right Sidebar */}
          <div className="w-96 space-y-4 flex-shrink-0">
            {/* Unit Selector */}
            <div className="relative bg-white rounded-lg border border-neutral-border shadow-sm p-4 z-10">
              <button
                onClick={() => setIsUnitsOpen(!isUnitsOpen)}
                className="w-full flex items-center justify-between px-4 py-2.5 bg-gray-50 rounded-lg border border-neutral-border hover:bg-gray-100 transition-colors"
              >
                <span className="font-medium text-neutral-text-main">
                  {currentUnit ? `單元 ${currentUnit.topic_id || currentUnit.id} ${currentUnit.name}` : `單元 ${unitId}`}
                </span>
                <FaChevronDown className={`text-neutral-text-tertiary transition-transform ${isUnitsOpen ? 'rotate-180' : ''}`} />
              </button>

              {isUnitsOpen && (
                <div className="absolute top-[calc(100%-1rem)] left-0 w-full mt-2 bg-white rounded-lg border border-neutral-border shadow-lg overflow-hidden max-h-60 overflow-y-auto z-20 mx-4" style={{ width: 'calc(100% - 2rem)' }}>
                  {units.length > 0 ? (
                    units.map((unit) => (
                      <button
                        key={unit.id}
                        onClick={() => {
                          setIsUnitsOpen(false);
                          navigate(`/student/course/${courseId}/dashboard?unit_id=${unit.id}`);
                        }}
                        className={`w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors border-b border-gray-100 last:border-0 text-sm ${unit.id === unitId ? 'bg-theme-secondary/10 text-theme-primary font-medium' : 'text-neutral-text-secondary'}`}
                      >
                        {`單元 ${unit.topic_id || unit.id} ${unit.name}`}
                      </button>
                    ))
                  ) : (
                    <div className="px-4 py-3 text-sm text-gray-500 text-center">
                      載入中...
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Knowledge Point Mastery */}
            <div className="bg-white rounded-lg border border-neutral-border shadow-sm overflow-hidden">
              <div className="px-4 py-3 bg-gradient-to-r from-theme-primary/10 to-transparent border-b border-neutral-border">
                <h3 className="font-bold text-neutral-text-main flex items-center gap-2">
                  <FaCheckCircle className="text-theme-primary" />
                  知識點掌握度
                </h3>
              </div>
              <div className="p-4 space-y-2">
                {loading ? (
                  <div className="py-4 text-center text-neutral-text-secondary text-sm">
                    <FaSpinner className="animate-spin inline-block mr-1" /> 載入中...
                  </div>
                ) : masteryStatus.length > 0 ? (
                  masteryStatus.map((item, idx) => (
                    <div key={idx} className="flex items-center justify-between py-2 border-b border-neutral-border/50 last:border-0">
                      <span className="text-sm text-neutral-text-main">{item.name}</span>
                      <span className={`text-xs font-medium px-2 py-1 rounded border ${getMasteryColor(item.status)}`}>
                        {item.status}
                      </span>
                    </div>
                  ))
                ) : (
                  <div className="text-xs text-gray-400 text-center py-2">尚無資料</div>
                )}
              </div>
            </div>

            {/* AI Diagnosis */}
            <div className="bg-white rounded-lg border border-neutral-border shadow-sm overflow-hidden">
              <div className="px-4 py-3 bg-gradient-to-r from-purple-500/10 to-transparent border-b border-neutral-border">
                <h3 className="font-bold text-neutral-text-main flex items-center gap-2">
                  <FaRobot className="text-purple-600" />
                  AI 診斷說明
                </h3>
              </div>
              <div className="p-6">
                {loading ? (
                  <div className="py-2 text-neutral-text-secondary text-sm">
                    <FaSpinner className="animate-spin inline-block mr-1" /> 系統分析診斷中...
                  </div>
                ) : (
                  <div className="relative">
                    <div className="absolute -top-3 -left-2 text-purple-200 text-3xl font-serif">"</div>
                    <p className="text-sm text-neutral-text-main leading-relaxed pl-4 italic text-purple-900">
                      {dashboardData?.ai_review || '尚無診斷數據。請完成單元內容以生成學習診斷報告。'}
                    </p>
                  </div>
                )}
              </div>
            </div>

            {/* Class Notes */}
            <div className="bg-white rounded-lg border border-neutral-border shadow-sm overflow-hidden">
              <div className="px-4 py-3 bg-gradient-to-r from-blue-500/10 to-transparent border-b border-neutral-border">
                <h3 className="font-bold text-neutral-text-main flex items-center gap-2">
                  <FaHeadphones className="text-blue-600" />
                  {activeTab === 'pre-class' ? '課堂聆聽重點' : '課後複習重點'}
                </h3>
              </div>
              <div className="p-4">
                {loading ? (
                  <div className="py-2 text-neutral-text-secondary text-sm">
                    <FaSpinner className="animate-spin inline-block mr-1" /> 整理中...
                  </div>
                ) : (
                  <ul className="space-y-3">
                    {dashboardData?.listening_highlights && dashboardData.listening_highlights.length > 0 ? (
                      dashboardData.listening_highlights.map((note, idx) => (
                        <li key={idx} className="flex gap-2 text-sm text-neutral-text-secondary">
                          <span className="text-theme-primary font-bold">•</span>
                          <span className="leading-relaxed">{note}</span>
                        </li>
                      ))
                    ) : (
                      <p className="text-xs text-gray-400">尚無建議</p>
                    )}
                  </ul>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* LIME Report Modal */}
        {selectedKp && (
          <LimeReportModal
            isOpen={true}
            onClose={() => setSelectedKp(null)}
            kpId={selectedKp.id}
            kpName={selectedKp.name}
            unitName={displayUnitName}
            stage={activeTab === 'pre-class' ? 'preview' : 'review'}
          />
        )}
      </div>
    </div>
  );
}

export default Dashboard;
