// frontend/src/App.tsx
import { Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { UserProvider } from './contexts/UserContext';
import SessionExpiryWarning from './components/auth/SessionExpiryWarning';
import Home from './pages/Home';
import TeacherPortal from './pages/Teacher';
import StudentPortal from './pages/Student';
import TeacherDashboard from './components/teacher/TeacherDashboard';
import Courses from './pages/teacher/Courses';
import GeneratorSettings from './pages/teacher/GeneratorSettings';
import ContentEditor from './pages/teacher/ContentEditor';
import GradesOverview from './pages/teacher/GradesOverview';
import CourseMembersPage from './pages/teacher/CourseMembers';
import ClassOverview from './pages/teacher/dashboard/ClassOverview';
import StudentProgress from './pages/teacher/dashboard/StudentProgress';

import Overview from './pages/student/Overview';
import Course from './pages/student/Course';
import TopicPreview from './pages/student/TopicPreview';
import Dashboard from './pages/student/Dashboard';
import AttachmentViewer from './pages/student/AttachmentViewer';
import StudentGradesOverview from './pages/student/GradesOverview';
import FeedbackCenter from './pages/common/FeedbackCenter';
import AdminPage from './pages/Admin';
import EvaluationExperiment from './pages/teacher/EvaluationExperiment';
import KappaEvaluationCenter from './pages/teacher/kappa_evaluation/KappaEvaluationCenter';
import Course62LimeEvalPage from './pages/teacher/kappa_evaluation/Course62LimeEvalPage';
import FinetuneMasteryPage from './pages/teacher/kappa_evaluation/FinetuneMasteryPage';
import FinetunePerformancePage from './pages/teacher/kappa_evaluation/FinetunePerformancePage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60, // 1 minute
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <UserProvider>
        <SessionExpiryWarning />
        <Routes>
          <Route path="/" element={<Home />} />

          <Route path="/teacher" element={<TeacherPortal />}>
            <Route index element={<TeacherDashboard />} />

            {/* Generation and Editing Routes */}
            <Route path="courses/:courseId/generate/:jobId" element={<ContentEditor />} />
            <Route path="courses/:courseId/generate" element={<GeneratorSettings />} />
            <Route path="courses/:courseId/content/new" element={<ContentEditor />} />
            <Route path="courses/:courseId/content/edit/:contentId" element={<ContentEditor />} />
            <Route path="courses/:courseId" element={<Courses />} />
            <Route path="courses/:courseId/grades" element={<GradesOverview />} />
            <Route path="courses/:courseId/members" element={<CourseMembersPage />} />
            <Route path="courses/:courseId/dashboard" element={<ClassOverview />} />
            <Route path="courses/:courseId/dashboard/student/:studentId" element={<StudentProgress />} />
            <Route path="feedback" element={<FeedbackCenter />} />
            <Route path="experiment/evaluations" element={<EvaluationExperiment />} />

            {/* Kappa 評估中心（與 experiment/evaluations 完全獨立，白名單 user_id 34 / 6）*/}
            <Route path="kappa-evaluation" element={<KappaEvaluationCenter />} />
            <Route path="kappa-evaluation/course62-lime" element={<Course62LimeEvalPage />} />
            <Route path="kappa-evaluation/finetune-mastery" element={<FinetuneMasteryPage />} />
            <Route path="kappa-evaluation/finetune-performance" element={<FinetunePerformancePage />} />
          </Route>

          <Route path="/student" element={<StudentPortal />}>
            <Route index element={<Overview />} />
            <Route path="course/:courseId" element={<Course />} />
            <Route path="course/:courseId/units/:unitId/preview" element={<TopicPreview />} />
            <Route path="course/:courseId/units/:unitId/attachment/:attachmentId" element={<AttachmentViewer />} />
            <Route path="course/:courseId/dashboard" element={<Dashboard />} />
            <Route path="course/:courseId/grades" element={<StudentGradesOverview />} />
            <Route path="feedback" element={<FeedbackCenter />} />
          </Route>

          <Route path="/admin" element={<AdminPage />} />
        </Routes>
      </UserProvider>
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}

export default App;
