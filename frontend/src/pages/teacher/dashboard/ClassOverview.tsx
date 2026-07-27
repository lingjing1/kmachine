import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { FaChartBar, FaBook, FaListOl, FaChevronDown, FaChevronUp } from 'react-icons/fa';

import { getDashboardOverview, getAtRiskStudents, DashboardData, AtRiskStudent, KnowledgePointMastery } from '../../../services/teacherDashboardApi';
import { authClient } from '../../../services/authClient';

export default function ClassOverview() {
   const navigate = useNavigate();
   const { courseId } = useParams();
   const [activeTab, setActiveTab] = useState<'pre-class' | 'post-class'>('pre-class');
   const [loading, setLoading] = useState(true);

   // Selector States
   const [units, setUnits] = useState<{ id: number; name: string }[]>([]);
   const [selectedUnitId, setSelectedUnitId] = useState<number | null>(null);
   const [courseName, setCourseName] = useState<string>("");

   // Data States
   const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
   const [atRiskStudents, setAtRiskStudents] = useState<AtRiskStudent[]>([]);

   // Expandable Card State
   const [expandedStudentId, setExpandedStudentId] = useState<number | null>(null);
   const [showOnlyAtRisk, setShowOnlyAtRisk] = useState(false);

   useEffect(() => {
      const fetchData = async () => {
         if (!selectedUnitId) return;

         setLoading(true);
         try {
            // Determine stage from activeTab
            const stage = activeTab === 'pre-class' ? 'preview' : 'review';

            // Fetch Overview Data
            try {
               const overviewJson = await getDashboardOverview(selectedUnitId, stage);
               setDashboardData(overviewJson);
            } catch (error) {
               console.error("Overview API returned error:", error);
               setDashboardData(null);
            }

            // Fetch At-Risk Students (Fetch all by passing true for showAll)
            try {
               const studentsJson = await getAtRiskStudents(selectedUnitId, stage, 2, true);
               if (Array.isArray(studentsJson)) {
                  setAtRiskStudents(studentsJson);
               } else {
                  setAtRiskStudents([]);
               }
            } catch (error) {
               console.error("Students API returned error:", error);
               setAtRiskStudents([]);
            }

         } catch (error) {
            console.error("Failed to fetch dashboard data:", error);
         } finally {
            setLoading(false);
         }
      };

      fetchData();
   }, [selectedUnitId, activeTab]);



   // Fetch Course & Units on Mount
   useEffect(() => {
      const fetchCourseData = async () => {
         if (!courseId) return;
         try {
            // Fetch Course Details
            const courseJson = await authClient.get<{ name: string }>(`/api/courses/${courseId}`);
            setCourseName(courseJson.name);

            // Fetch Units
            const unitsJson = await authClient.get<{ id: number; name: string }[]>(`/api/courses/${courseId}/units`);
            setUnits(unitsJson);
            if (unitsJson.length > 0) {
               // Default to first unit
               setSelectedUnitId(unitsJson[0].id);
            }
         } catch (err) {
            console.error("Failed to load course data", err);
         }
      };
      fetchCourseData();
   }, [courseId]);

   // Helper to determine dominant color
   const getDominantColorClass = (kp: KnowledgePointMastery) => {
      // If no data, return gray
      if (kp.mastered === 0 && kp.moderate === 0 && kp.weak === 0) return 'bg-slate-300';

      // Softer colors (300 scale for lower saturation)
      if (kp.mastered >= kp.moderate && kp.mastered >= kp.weak) return 'bg-emerald-300';
      if (kp.moderate >= kp.mastered && kp.moderate >= kp.weak) return 'bg-amber-300';
      return 'bg-rose-300';
   };

   const getDominantTextClass = (kp: KnowledgePointMastery) => {
      const colorClass = getDominantColorClass(kp);
      return colorClass.replace('bg-', 'text-');
   };


   return (
      <div className="p-6 max-w-[1440px] mx-auto space-y-8 font-sans text-slate-800">
         {/* Header Area */}
         <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-6 bg-white p-5 rounded-2xl shadow-sm border border-slate-100">
            <div className="flex flex-col gap-1">
               <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">學生學習儀表板</h1>
               <div className="flex items-center gap-2 text-slate-500 text-sm font-medium">
                  <FaBook className="text-blue-500/80" />
                  <span>目前課程：</span>
                  <span className="text-slate-700 bg-slate-100 px-2 py-0.5 rounded text-xs">{courseName || "載入中..."}</span>
               </div>
            </div>

            {/* Controls Group */}
            <div className="flex flex-wrap items-center gap-4">
               {/* Unit Selector */}
               <div className="relative">
                  <div className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none">
                     <FaListOl />
                  </div>
                  <select
                     value={selectedUnitId || ''}
                     onChange={(e) => setSelectedUnitId(Number(e.target.value))}
                     disabled={units.length === 0}
                     className="pl-9 pr-8 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm font-bold text-slate-700 focus:ring-2 focus:ring-blue-100 focus:border-blue-400 outline-none transition-all appearance-none cursor-pointer min-w-[240px]"
                     style={{ backgroundImage: 'none' }} // Remove default arrow if we add custom one, or keep native
                  >
                     {units.length === 0 ? <option>無單元</option> : units.map(u => (
                        <option key={u.id} value={u.id}>{u.name}</option>
                     ))}
                  </select>
                  <div className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none text-xs">
                     <FaChevronDown />
                  </div>
               </div>

               {/* Divider */}
               <div className="h-8 w-px bg-slate-200 hidden md:block"></div>

               {/* Tab Switcher */}
               <div className="bg-slate-100/80 p-1 rounded-xl flex gap-1">
                  <button
                     onClick={() => setActiveTab('pre-class')}
                     className={`px-4 py-2 text-sm font-bold rounded-lg transition-all duration-200 ${activeTab === 'pre-class'
                        ? 'bg-white text-blue-600 shadow-sm ring-1 ring-black/5'
                        : 'text-slate-500 hover:text-slate-700 hover:bg-slate-200/50'
                        }`}
                  >
                     課前診斷
                  </button>
                  <button
                     onClick={() => setActiveTab('post-class')}
                     className={`px-4 py-2 text-sm font-bold rounded-lg transition-all duration-200 ${activeTab === 'post-class'
                        ? 'bg-white text-blue-600 shadow-sm ring-1 ring-black/5'
                        : 'text-slate-500 hover:text-slate-700 hover:bg-slate-200/50'
                        }`}
                  >
                     課後追蹤
                  </button>
               </div>

               {/* Completion Stats Badge */}
               <div className="flex flex-col items-end min-w-[100px]">
                  <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">
                     {activeTab === 'pre-class' ? '預習進度' : '複習進度'}
                  </span>
                  <div className="flex items-baseline gap-1 text-slate-700">
                     <span className="text-xl font-extrabold text-blue-600">
                        {dashboardData ? (activeTab === 'pre-class' ? dashboardData?.summary?.preview_count ?? '-' : dashboardData?.summary?.review_count ?? '-') : '-'}
                     </span>
                     <span className="text-xs font-bold text-slate-400">
                        / {dashboardData?.summary?.total_students ?? '-'} 人
                     </span>
                  </div>
               </div>
            </div>
         </div>

         <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
            {/* Left Column: Mastery Analysis (8/12 width) */}
            <div className="xl:col-span-8 space-y-6">
               {/* Section 1: Knowledge Points */}
               <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6">
                  <div className="flex items-center justify-between mb-8">
                     <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
                        <div className="p-2 bg-blue-50 rounded-lg text-blue-500">
                           <FaChartBar />
                        </div>
                        全班知識點掌握度分析
                     </h2>
                     <div className="flex items-center gap-4 text-xs font-bold bg-slate-50 px-4 py-2 rounded-full border border-slate-100">
                        <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-emerald-300 shadow-sm shadow-emerald-100"></div>精熟</div>
                        <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-amber-300 shadow-sm shadow-amber-100"></div>尚可</div>
                        <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-rose-300 shadow-sm shadow-rose-100"></div>待加強</div>
                     </div>
                  </div>

                  {/* Chart Grid */}
                  <div className="space-y-6">
                     {loading ? (
                        <div className="h-64 flex flex-col items-center justify-center text-slate-400 gap-2">
                           <div className="w-8 h-8 border-4 border-blue-100 border-t-blue-500 rounded-full animate-spin"></div>
                           <span className="text-sm font-medium">分析數據中...</span>
                        </div>
                     ) : (
                        dashboardData?.knowledge_points?.length === 0 ? (
                           <div className="h-64 flex items-center justify-center text-slate-400 bg-slate-50 rounded-xl border border-dashed border-slate-200">
                              無數據顯示
                           </div>
                        ) :
                           dashboardData?.knowledge_points?.map(kp => {
                              const barColorClass = getDominantColorClass(kp);
                              const dominantTextClass = getDominantTextClass(kp);
                              const isNoData = kp.mastered === 0 && kp.moderate === 0 && kp.weak === 0;

                              return (
                                 <div key={kp.id} className="group hover:bg-slate-50/50 p-4 rounded-xl transition-colors border border-transparent hover:border-slate-100">
                                    <div className="flex justify-between items-end mb-3">
                                       <div className="flex items-center gap-3">
                                          <div className={`w-1.5 h-8 rounded-full ${barColorClass}`}></div>
                                          <h3 className="font-bold text-slate-800 text-sm tracking-wide">{kp.name}</h3>
                                       </div>
                                       <span className={`text-sm font-bold px-2 py-0.5 rounded-md bg-opacity-10 ${barColorClass.replace('bg-', 'bg-')} ${dominantTextClass}`}>
                                          {isNoData ? '尚未學習' : `${Math.max(kp.mastered, kp.moderate, kp.weak)}% 多數`}
                                       </span>
                                    </div>

                                    {/* Main Progress Bar */}
                                    <div className="w-full h-3 bg-slate-100 rounded-full overflow-hidden shadow-inner relative">
                                       <div
                                          className={`h-full ${barColorClass} transition-all duration-1000 ease-out`}
                                          style={{ width: '100%' }}
                                       >
                                          {/* Glossy effect overlay */}
                                          <div className="absolute top-0 left-0 w-full h-1/2 bg-white/20"></div>
                                       </div>
                                    </div>

                                    {/* Detailed Stats Row */}
                                    <div className="flex gap-6 mt-3 px-2">
                                       <div className="flex flex-col items-start">
                                          <span className="text-[10px] text-slate-400 uppercase font-bold tracking-wider mb-0.5">精熟</span>
                                          <span className="text-xs font-bold text-slate-600">{kp.mastered}%</span>
                                       </div>
                                       <div className="flex flex-col items-start border-l border-slate-100 pl-6">
                                          <span className="text-[10px] text-slate-400 uppercase font-bold tracking-wider mb-0.5">普通</span>
                                          <span className="text-xs font-bold text-slate-600">{kp.moderate}%</span>
                                       </div>
                                       <div className="flex flex-col items-start border-l border-slate-100 pl-6">
                                          <span className="text-[10px] text-slate-400 uppercase font-bold tracking-wider mb-0.5">待加強</span>
                                          <span className="text-xs font-bold text-red-500">{kp.weak}%</span>
                                       </div>
                                    </div>
                                 </div>
                              )
                           })
                     )}
                  </div>
               </div>


            </div>

            {/* Right Column: AI Analysis & Actions (3/12 width) */}
            <div className="xl:col-span-4 space-y-6">


               {/* AI Analysis Card */}
               <div className="bg-gradient-to-b from-blue-50 to-white rounded-2xl border border-blue-100 p-6 shadow-sm">
                  <h2 className="text-lg font-bold text-slate-800 mb-4 flex items-center gap-2">
                     <div className="w-2 h-5 bg-blue-500 rounded-full"></div>
                     AI 學情分析
                  </h2>
                  <div className="bg-white/80 p-4 rounded-xl border border-blue-100/50 shadow-sm text-sm text-slate-600 leading-relaxed mb-6 font-medium text-justify"
                     dangerouslySetInnerHTML={{ __html: dashboardData?.ai_analysis?.content || '全班學習狀況良好，請繼續保持！' }}
                  >
                  </div>

                  <h3 className="font-bold text-slate-700 mb-3 text-xs uppercase tracking-wider flex items-center gap-2">
                     <span className="text-blue-500">●</span>
                     教學重點建議
                  </h3>
                  <ul className="space-y-3">
                     {dashboardData?.ai_analysis?.suggestions?.map((suggestion, idx) => (
                        <li key={idx} className="flex gap-3 text-sm text-slate-600 bg-white p-3 rounded-lg border border-slate-100 shadow-sm">
                           <span className="mt-1 w-1.5 h-1.5 rounded-full bg-blue-400 flex-shrink-0"></span>
                           <span>{suggestion}</span>
                        </li>
                     )) || (
                           <li className="flex gap-3 text-sm text-slate-600 bg-white p-3 rounded-lg border border-slate-100 shadow-sm">
                              <span className="mt-1 w-1.5 h-1.5 rounded-full bg-blue-400 flex-shrink-0"></span>
                              <span>暫無建議</span>
                           </li>
                        )}
                  </ul>
               </div>

               {/* Actions */}
               <div className="space-y-4">
                  <div className="flex items-center justify-between text-slate-800">
                     <h2 className="font-bold text-lg">行動建議</h2>
                     <span className="text-xs font-bold px-2 py-0.5 bg-orange-100 text-orange-600 rounded">AI 推薦</span>
                  </div>

                  <div className="grid grid-cols-1 gap-3">
                     <button className="group bg-white rounded-xl border border-slate-200 p-4 hover:border-orange-300 hover:shadow-md transition-all text-left relative overflow-hidden">
                        <div className="absolute right-0 top-0 w-16 h-16 bg-orange-50 rounded-bl-[60px] -mr-8 -mt-8 opacity-50 group-hover:scale-110 transition-transform"></div>
                        <div className="flex items-center gap-3 mb-2 relative z-10">
                           <div className="w-10 h-10 bg-orange-50 rounded-xl flex items-center justify-center text-orange-500 group-hover:text-white group-hover:bg-orange-500 transition-colors shadow-sm">
                              <FaBook size={16} />
                           </div>
                           <h3 className="font-bold text-slate-700 text-sm group-hover:text-orange-600">生成重點複習教材</h3>
                        </div>
                        <p className="text-slate-400 text-xs pl-[52px]">針對「數據標註」的補救教材</p>
                     </button>

                     <button className="group bg-white rounded-xl border border-slate-200 p-4 hover:border-blue-300 hover:shadow-md transition-all text-left relative overflow-hidden">
                        <div className="absolute right-0 top-0 w-16 h-16 bg-blue-50 rounded-bl-[60px] -mr-8 -mt-8 opacity-50 group-hover:scale-110 transition-transform"></div>
                        <div className="flex items-center gap-3 mb-2 relative z-10">
                           <div className="w-10 h-10 bg-blue-50 rounded-xl flex items-center justify-center text-blue-500 group-hover:text-white group-hover:bg-blue-500 transition-colors shadow-sm">
                              <FaListOl size={16} />
                           </div>
                           <h3 className="font-bold text-slate-700 text-sm group-hover:text-blue-600">生成隨堂測驗 (5題)</h3>
                        </div>
                        <p className="text-slate-400 text-xs pl-[52px]">針對弱點生成選擇題</p>
                     </button>
                  </div>
               </div>
            </div>
         </div>

         {/* Section 2: At-Risk Students (Full Width Bottom) - Moved Outside Grid */}
         <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6 relative overflow-hidden">
            <div className="flex flex-col md:flex-row md:items-center justify-between mb-4 gap-4 relative z-10">
               <div className="flex items-center gap-2">
                  <div className="p-2 bg-blue-50 rounded-lg text-blue-500">
                     <FaListOl />
                  </div>
                  <h2 className="text-lg font-bold text-slate-800">學生學習清單</h2>
               </div>

               <div className="flex items-center gap-4">
                  <label className="flex items-center gap-2 cursor-pointer bg-slate-50 px-3 py-1.5 rounded-lg border border-slate-200">
                     <input
                        type="checkbox"
                        checked={showOnlyAtRisk}
                        onChange={(e) => setShowOnlyAtRisk(e.target.checked)}
                        className="w-4 h-4 text-blue-600 rounded focus:ring-blue-500"
                     />
                     <span className="text-sm font-bold text-slate-600">僅顯示需關注學生</span>
                  </label>
                  <span className="bg-red-100 text-red-600 text-xs font-bold px-3 py-1 rounded-full border border-red-200">
                     需關注 {atRiskStudents.filter(s => s.status === 'at-risk').length} 人
                  </span>
               </div>
            </div>

            <div className="border-t border-slate-100 my-4 pt-4">
               <h3 className="text-sm font-bold text-slate-500 mb-3">學生詳細報告</h3>

               {atRiskStudents.length === 0 ? (
                  <div className="text-center py-12 text-slate-400 text-sm font-medium bg-slate-50 rounded-xl border border-dashed border-slate-200">
                     太棒了！目前沒有需要特別關注的學生。
                  </div>
               ) : (
                  <div className="grid grid-cols-1 gap-4 relative z-10">
                     {atRiskStudents
                        .filter(student => !showOnlyAtRisk || student.status === 'at-risk')
                        .map(student => (
                           <div key={student.id} className={`bg-white rounded-xl border transition-all duration-300 ${expandedStudentId === student.id ? (student.status === 'at-risk' ? 'border-red-300 shadow-md ring-1 ring-red-100' : 'border-blue-300 shadow-md ring-1 ring-blue-100') : (student.status === 'at-risk' ? 'border-red-200 bg-red-50/10' : 'border-slate-200 hover:border-blue-200 hover:shadow-sm')}`}>

                              <div
                                 className="p-4 flex items-center justify-between cursor-pointer"
                                 onClick={() => setExpandedStudentId(expandedStudentId === student.id ? null : student.id)}
                              >
                                 <div className="flex items-center gap-3">
                                    <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm shadow-inner ${student.status === 'at-risk' ? 'bg-gradient-to-br from-red-100 to-red-50 text-red-600' : 'bg-gradient-to-br from-blue-100 to-blue-50 text-blue-600'}`}>
                                       {student.name.charAt(0)}
                                    </div>
                                    <div className="flex flex-col">
                                       <div className="flex items-center gap-2">
                                          <div className="font-bold text-slate-800 text-sm">{student.name}</div>
                                          {student.status === 'at-risk' && (
                                             <span className="text-[10px] bg-red-500 text-white px-1.5 py-0.5 rounded font-black uppercase">需關注</span>
                                          )}
                                       </div>
                                       <div className="text-[10px] uppercase font-bold text-slate-400 tracking-wide">ID: {student.student_id}</div>
                                    </div>
                                 </div>
                                 <div className="flex flex-col items-end gap-1">
                                    <span className={`${student.status === 'at-risk' ? 'text-red-500 bg-red-50 border-red-100' : 'text-blue-500 bg-blue-50 border-blue-100'} text-xs font-bold px-2 py-0.5 rounded border`}>
                                       {student.weak_points_count} 弱項
                                    </span>
                                    {expandedStudentId === student.id
                                       ? <FaChevronUp className="text-slate-300 text-xs" />
                                       : <FaChevronDown className="text-slate-300 text-xs" />}
                                 </div>
                              </div>

                              {/* Expanded Content */}
                              <div className={`overflow-hidden transition-all duration-300 ease-in-out ${expandedStudentId === student.id ? 'max-h-48 opacity-100' : 'max-h-0 opacity-0'}`}>
                                 <div className="bg-slate-50/80 p-4 border-t border-slate-100 text-sm space-y-3 mx-1 mb-1 rounded-b-lg">
                                    <p className="text-slate-500 font-bold text-xs uppercase tracking-wide">需加強知識點</p>
                                    <ul className="text-slate-600 text-xs space-y-1.5 pl-1">
                                       {student.weak_knowledge_points?.map((kpName, idx) => (
                                          <li key={idx} className="flex items-center gap-2">
                                             <span className="w-1.5 h-1.5 rounded-full bg-red-400"></span>
                                             {kpName}
                                          </li>
                                       )) || <li>無資料</li>}
                                    </ul>
                                    <button
                                       onClick={(e) => {
                                          e.stopPropagation();
                                          navigate(`/teacher/courses/${courseId}/dashboard/student/${student.id}?unit_id=${selectedUnitId}&name=${encodeURIComponent(student.name)}&sid=${encodeURIComponent(student.student_id)}`);
                                       }}
                                       className="w-full mt-2 py-2 bg-white border border-slate-200 rounded-lg text-center text-xs font-bold text-slate-600 hover:text-blue-600 hover:border-blue-200 transition-colors shadow-sm"
                                    >
                                       查看個人詳細報告
                                    </button>
                                 </div>
                              </div>
                           </div>
                        ))}
                  </div>
               )}
            </div>
         </div>
      </div>
   );
}
