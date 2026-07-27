import { useState, useEffect } from 'react';
import { useSearchParams, useParams } from 'react-router-dom';
import TeacherDashboardLayout from './TeacherDashboardLayout';
import { getStudentDashboard, DashboardResponse } from '../../../services/studentApi';
import { FaSpinner, FaChartLine, FaChevronDown, FaListOl } from 'react-icons/fa';
import API_BASE_URL from '../../../config/api';
import LimeReportModal from '../../../components/student/LimeReportModal';

export default function StudentProgress() {
  const { courseId: routeCourseId, studentId: routeStudentId } = useParams<{ courseId: string; studentId: string }>();
  const [searchParams] = useSearchParams();
  
  const courseId = routeCourseId ? parseInt(routeCourseId) : 3;
  const studentId = routeStudentId ? parseInt(routeStudentId) : 6;
  const initialUnitId = searchParams.get('unit_id') ? parseInt(searchParams.get('unit_id')!) : null;
  
  // Read student info from query params (passed from ClassOverview)
  const studentName = searchParams.get('name') || '學生';
  const studentSid = searchParams.get('sid') || '';

  const [activeTab, setActiveTab] = useState<'pre-class' | 'post-class'>('pre-class');
  const [dashboardData, setDashboardData] = useState<DashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  
  // Unit Selector
  const [units, setUnits] = useState<{ id: number; name: string }[]>([]);
  const [selectedUnitId, setSelectedUnitId] = useState<number | null>(initialUnitId);

  // LIME Report Modal
  const [limeModalOpen, setLimeModalOpen] = useState(false);
  const [selectedKpId, setSelectedKpId] = useState<number | null>(null);
  const [selectedKpName, setSelectedKpName] = useState<string>("");

  // Fetch Units on mount
  useEffect(() => {
    const fetchUnits = async () => {
      try {
        const unitsRes = await fetch(`${API_BASE_URL}/api/courses/${courseId}/units`);
        if (unitsRes.ok) {
          const unitsJson = await unitsRes.json();
          setUnits(unitsJson);
          
          if (!selectedUnitId && unitsJson.length > 0) {
            setSelectedUnitId(unitsJson[0].id);
          }
        }
      } catch (err) {
        console.error("Failed to load units", err);
      }
    };
    
    fetchUnits();
  }, [courseId]);

  // Fetch Dashboard Data when unit or tab changes
  useEffect(() => {
    const fetchData = async () => {
      if (!selectedUnitId) return;
      
      setLoading(true);
      const stage = activeTab === 'pre-class' ? 'preview' : 'review';
      
      try {
        const data = await getStudentDashboard(courseId, selectedUnitId, { 
          stage, 
          teacherOverrideStudentId: studentId 
        });
        setDashboardData(data);
      } catch (e: any) {
        console.error(e);
        setDashboardData(null);
      } finally {
        setLoading(false);
      }
    };
    
    fetchData();
  }, [courseId, selectedUnitId, studentId, activeTab]);

  const getMasteryColor = (level: string) => {
    switch (level) {
      case '精熟': return 'bg-emerald-50 text-emerald-700 border-emerald-300';
      case '尚可': return 'bg-amber-50 text-amber-700 border-amber-300';
      case '待加強': return 'bg-rose-50 text-rose-700 border-rose-300';
      default: return 'bg-slate-50 text-slate-600 border-slate-300';
    }
  };

  const getMasteryBorderColor = (level: string) => {
    switch (level) {
      case '精熟': return 'border-l-emerald-500';
      case '尚可': return 'border-l-amber-500';
      case '待加強': return 'border-l-rose-500';
      default: return 'border-l-slate-400';
    }
  };

  const handleViewAnalysis = (kpId: number, kpName: string) => {
    setSelectedKpId(kpId);
    setSelectedKpName(kpName);
    setLimeModalOpen(true);
  };

  const currentUnitName = units.find(u => u.id === selectedUnitId)?.name || '';

  return (
    <TeacherDashboardLayout 
      title="學生個案"
      breadcrumbs={[
        { label: '首頁', path: '/' }, 
        { label: '班級概覽', path: `/teacher/courses/${courseId}/dashboard` },
        { label: studentName }
      ]}
    >
      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6">
        {/* Header Controls */}
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-6">
            {/* Student Info Badge */}
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-full bg-gradient-to-br from-blue-100 to-blue-50 text-blue-600 flex items-center justify-center font-bold text-lg shadow-inner">
                {studentName.charAt(0)}
              </div>
              <div>
                <div className="font-bold text-slate-800">{studentName}</div>
                <div className="text-xs text-slate-400">ID: {studentSid}</div>
              </div>
            </div>
            
            {/* Controls */}
            <div className="flex flex-wrap items-center gap-4">
              {/* Unit Selector */}
              <div className="relative">
                <div className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none">
                  <FaListOl size={12} />
                </div>
                <select 
                  value={selectedUnitId || ''}
                  onChange={(e) => setSelectedUnitId(Number(e.target.value))}
                  disabled={units.length === 0}
                  className="pl-8 pr-8 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm font-bold text-slate-700 focus:ring-2 focus:ring-blue-100 focus:border-blue-400 outline-none transition-all appearance-none cursor-pointer min-w-[200px]"
                >
                  {units.length === 0 ? <option>載入中...</option> : units.map(u => (
                    <option key={u.id} value={u.id}>{u.name}</option>
                  ))}
                </select>
                <div className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none text-xs">
                  <FaChevronDown />
                </div>
              </div>
              
              {/* Tab Switcher */}
              <div className="bg-slate-100/80 p-1 rounded-xl flex gap-1">
                <button
                  onClick={() => setActiveTab('pre-class')}
                  className={`px-4 py-2 text-sm font-bold rounded-lg transition-all duration-200 ${
                    activeTab === 'pre-class' 
                    ? 'bg-white text-blue-600 shadow-sm ring-1 ring-black/5' 
                    : 'text-slate-500 hover:text-slate-700 hover:bg-slate-200/50'
                  }`}
                >
                  課前診斷
                </button>
                <button
                  onClick={() => setActiveTab('post-class')}
                  className={`px-4 py-2 text-sm font-bold rounded-lg transition-all duration-200 ${
                    activeTab === 'post-class' 
                    ? 'bg-white text-blue-600 shadow-sm ring-1 ring-black/5' 
                    : 'text-slate-500 hover:text-slate-700 hover:bg-slate-200/50'
                  }`}
                >
                  課後追蹤
                </button>
              </div>
            </div>
        </div>

        {/* Content */}
        {loading ? (
             <div className="py-16 flex flex-col items-center justify-center gap-3">
                 <FaSpinner className="animate-spin text-blue-500 text-3xl" />
                 <span className="text-sm text-slate-400 font-medium">載入學習資料中...</span>
             </div>
        ) : (
            <div className="space-y-6">
                 {/* AI Review Summary */}
                 {dashboardData?.ai_review && (
                   <div className="bg-gradient-to-r from-purple-50 to-blue-50 p-5 rounded-xl border border-purple-100">
                      <h4 className="font-bold text-purple-800 mb-2 flex items-center gap-2">
                        <span className="w-1.5 h-5 bg-purple-500 rounded-full"></span>
                        AI 學習診斷
                      </h4>
                      <p className="text-sm text-purple-900 leading-relaxed">
                          {dashboardData.ai_review}
                      </p>
                   </div>
                 )}

                 {/* Mastery List */}
                 <div>
                    <h3 className="font-bold text-slate-700 mb-4 flex items-center gap-2">
                      <span className="w-1 h-5 bg-blue-500 rounded-full"></span>
                      知識點掌握度
                    </h3>
                    
                    <div className="grid gap-4">
                       {dashboardData?.knowledge_points && dashboardData.knowledge_points.length > 0 ? (
                           dashboardData.knowledge_points.map((kp) => (
                               <div key={kp.knowledge_point_id} className={`bg-white border rounded-xl p-5 shadow-sm border-l-4 hover:shadow-md transition-shadow ${getMasteryBorderColor(kp.mastery_level)}`}>
                                   <div className="flex justify-between items-start mb-3">
                                       <h5 className="font-bold text-slate-800">{kp.name}</h5>
                                       <div className="flex items-center gap-2">
                                         <span className={`text-xs px-3 py-1 rounded-full border font-bold ${getMasteryColor(kp.mastery_level)}`}>
                                             {kp.mastery_level || '未評估'}
                                         </span>
                                         <button
                                           onClick={() => handleViewAnalysis(kp.knowledge_point_id, kp.name)}
                                           className="text-xs px-3 py-1 rounded-full bg-blue-50 text-blue-600 border border-blue-200 font-bold hover:bg-blue-100 transition-colors flex items-center gap-1"
                                         >
                                           <FaChartLine size={10} />
                                           查看分析
                                         </button>
                                       </div>
                                   </div>
                                   
                                   {/* Recent Answer */}
                                   <div className="text-xs text-slate-400 mb-2">最近作答截選：</div>
                                   {kp.recent_answers && kp.recent_answers.length > 0 ? (
                                       <div className="bg-slate-50 p-4 rounded-lg text-sm text-slate-600 border border-slate-100">
                                           {(() => {
                                               try {
                                                   const ans = kp.recent_answers[0].answer;
                                                   if (typeof ans === 'string' && ans.startsWith('{')) {
                                                     const parsed = JSON.parse(ans.replace(/'/g, '"'));
                                                     return parsed.text || ans;
                                                   }
                                                   return ans;
                                               } catch {
                                                   return kp.recent_answers[0].answer;
                                               }
                                           })()}
                                       </div>
                                   ) : (
                                       <div className="bg-slate-50 p-4 rounded-lg text-sm text-slate-400 italic border border-dashed border-slate-200">
                                           尚無作答記錄
                                       </div>
                                   )}
                               </div>
                           ))
                       ) : (
                           <div className="text-center py-12 text-slate-400 bg-slate-50 rounded-xl border border-dashed border-slate-200">
                             <p className="font-medium">目前尚無此階段的學習數據</p>
                             <p className="text-xs mt-1">學生尚未完成 {activeTab === 'pre-class' ? '課前預習' : '課後複習'}</p>
                           </div>
                       )}
                    </div>
                 </div>
            </div>
        )}
      </div>

      {/* LIME Report Modal */}
      {selectedKpId && (
        <LimeReportModal
          isOpen={limeModalOpen}
          onClose={() => setLimeModalOpen(false)}
          kpId={selectedKpId}
          studentId={studentId}
          unitName={currentUnitName}
          kpName={selectedKpName}
          stage={activeTab === 'pre-class' ? 'preview' : 'review'}
        />
      )}
    </TeacherDashboardLayout>
  );
}
