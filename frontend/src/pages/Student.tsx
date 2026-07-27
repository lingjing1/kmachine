import { useState, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Outlet, useLocation } from 'react-router-dom';
import Header from '../components/common/Header';
import StudentSidebar from '../components/student/StudentSidebar';
import Footer from '../components/common/Footer';
import { getEnrolledCourses } from '../services/studentApi';
import { useUser } from '../contexts/UserContext';

// Define the type for a single breadcrumb path item
interface BreadcrumbPath {
  name: string;
  path: string;
}

// Define the type for the Outlet context
interface OutletContext {
  setBreadcrumbPaths: React.Dispatch<React.SetStateAction<BreadcrumbPath[] | null>>;
  breadcrumbPaths: BreadcrumbPath[] | null;
  setHeaderActions: React.Dispatch<React.SetStateAction<React.ReactNode>>;
}

const BREADCRUMB_MAP: Record<string, string> = {
  'coding': '程式練習',
  'grades': '成績概覽',
};

function Student() {
  const { user } = useUser();
  const [breadcrumbPaths, setBreadcrumbPaths] = useState<BreadcrumbPath[] | null>(null);
  const [headerActions, setHeaderActions] = useState<React.ReactNode>(null);
  const location = useLocation();
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [courseName, setCourseName] = useState<string>('課程內容');

  const toggleSidebar = () => setIsSidebarOpen(!isSidebarOpen);

  // Extract courseId from path if present
  const courseIdMatch = location.pathname.match(/\/student\/course\/(\d+)/);
  const courseId = courseIdMatch ? courseIdMatch[1] : undefined;

  // Scroll to top on route change
  useEffect(() => {
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTo(0, 0);
    }
  }, [location.pathname]);

  useEffect(() => {
    // Always keep sidebar open for course pages
    if (location.pathname.includes('/course/')) {
      setIsSidebarOpen(true);
    }
  }, [location.pathname]);

  // Determine if we should show Sidebar
  // Hide for: Student Overview (index), Preview pages, and Feedback Center
  const shouldHideSidebar =
    location.pathname === '/student' ||
    location.pathname === '/student/' ||
    location.pathname.includes('/preview') ||
    location.pathname.includes('/attachment/') ||
    location.pathname.includes('/feedback');

  const { data: coursesData } = useQuery({
    queryKey: ['enrolled-courses', user?.user_id],
    queryFn: () => getEnrolledCourses(),
    enabled: !!user?.user_id,
    staleTime: 5 * 60 * 1000,
  });

  // Fetch course name when courseId changes
  useEffect(() => {
    if (courseId && Array.isArray(coursesData)) {
      const course = coursesData.find((c: any) => c.id === parseInt(courseId));
      if (course) {
        setCourseName(course.name);
      }
    }
  }, [courseId, coursesData]);

  // Set breadcrumb paths for course pages
  useEffect(() => {
    if (courseId) {
      const currentPath = location.pathname.split('/').pop() || '';
      const pageName = BREADCRUMB_MAP[currentPath];

      const basePaths = [
        { name: '我的課程', path: '/student' },
        { name: courseName, path: `/student/course/${courseId}` },
      ];

      if (pageName) {
        setBreadcrumbPaths([...basePaths, { name: pageName, path: location.pathname }]);
      } else {
        setBreadcrumbPaths(basePaths);
      }
    } else {
      // Reset breadcrumb for non-course pages
      setBreadcrumbPaths(null);
    }
  }, [courseId, courseName, location.pathname]);

  // Layout with Sidebar
  const SidebarLayout = (
    <div className="grid grid-cols-[auto_1fr] grid-rows-[1fr_auto] min-h-full relative">
      {/* Sidebar Column - row-span-2 ensures it stays sticky for the entire scrollable height */}
      <div className="row-span-2 sticky top-0 self-start" style={{ height: 'calc(100vh - 80px)' }}>
        <StudentSidebar
          courseId={courseId}
          isSidebarOpen={isSidebarOpen}
          onToggle={toggleSidebar}
        />
      </div>

      {/* Main Content Area */}
      <main className="min-w-0 relative">
        <Outlet context={{ setBreadcrumbPaths, breadcrumbPaths, setHeaderActions } as OutletContext} />
      </main>

      {/* Global Footer - col-span-2 allows it to cover the sidebar area at the bottom */}
      <div id="app-footer" className="col-start-1 col-span-2 relative z-40 bg-white border-t border-gray-100 mt-auto">
        <Footer />
      </div>
    </div>
  );

  // Layout without Sidebar
  const isFeedbackPage = location.pathname.includes('/feedback');
  const FullWidthLayout = (
    <div className="flex flex-col min-h-full">
      <main className="flex-1 min-w-0 relative">
        <Outlet context={{ setBreadcrumbPaths, breadcrumbPaths, setHeaderActions } as OutletContext} />
      </main>
      {!isFeedbackPage && (
        <div id="app-footer" className="relative z-40 bg-white border-t border-gray-100">
          <Footer />
        </div>
      )}
    </div>
  );

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-slate-50 relative">
      {/* Global Background Gradient */}
      <div className="absolute top-0 left-0 w-full h-[500px] bg-[linear-gradient(to_right,#DBEAFE,#eff6ff,#DBEAFE)] [mask-image:linear-gradient(to_bottom,white,transparent)] pointer-events-none rounded-b-[30%] scale-x-125 z-0" />

      <div className="flex-shrink-0 relative z-10">
        <Header paths={breadcrumbPaths} actions={headerActions} />
      </div>

      {/* Scrollable container for the entire layout area under the header */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto relative z-10 custom-scrollbar"
      >
        {shouldHideSidebar ? FullWidthLayout : SidebarLayout}
      </div>
    </div>
  );
}

export default Student;