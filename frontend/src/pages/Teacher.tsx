import { useState, useEffect, useRef } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import Header from '../components/common/Header';
import TeacherSidebar from '../components/teacher/TeacherSidebar';
import Footer from '../components/common/Footer';
import { useQuery } from '@tanstack/react-query';
import API_BASE_URL from '../config/api';

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



function Teacher() {
  const [breadcrumbPaths, setBreadcrumbPaths] = useState<BreadcrumbPath[] | null>(null);
  const [headerActions, setHeaderActions] = useState<React.ReactNode>(null);
  const location = useLocation();

  useEffect(() => {
    console.log('[Teacher Layout] Path changed:', location.pathname);
  }, [location.pathname]);

  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Scroll to top on route change
  useEffect(() => {
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTo(0, 0);
    }
  }, [location.pathname]);

  const toggleSidebar = () => setIsSidebarOpen(!isSidebarOpen);

  // Extract courseId from path if present
  const courseIdMatch = location.pathname.match(/\/teacher\/courses\/(\d+)/);
  const courseId = courseIdMatch ? courseIdMatch[1] : undefined;

  // Determine if we should show Sidebar and Footer
  // Hide for: generate pages, content editor pages
  const shouldShowSidebarAndFooter = courseId && !location.pathname.includes('/generate') && !location.pathname.includes('/content/');

  // Fetch course details if courseId is present
  const { data: courseData } = useQuery({
    queryKey: ['course', courseId],
    queryFn: async () => {
      if (!courseId) return null;
      const res = await fetch(`${API_BASE_URL}/api/courses/${courseId}`);
      if (!res.ok) return null;
      return res.json();
    },
    enabled: !!courseId
  });

  const courseName = courseData?.name;

  // Set breadcrumb paths
  useEffect(() => {
    if (courseId) {
      const basePaths = [
        { name: `課程: ${courseName || '載入中...'}`, path: `/teacher/courses/${courseId}` },
      ];

      if (location.pathname.includes('/generate')) {
        // ... (rest of logic)
        const parts = location.pathname.split('/generate');
        const hasJobId = parts[1] && parts[1].length > 1;

        if (hasJobId) {
          setBreadcrumbPaths([
            ...basePaths,
            { name: '設定生成參數', path: `/teacher/courses/${courseId}/generate${location.search}` },
            { name: '生成結果編修', path: '' }
          ]);
        } else {
          setBreadcrumbPaths([
            ...basePaths,
            { name: '設定生成參數', path: '' }
          ]);
        }
      } else if (location.pathname.includes('/content/new')) {
        const searchParams = new URLSearchParams(location.search);
        const type = searchParams.get('type');
        const label = type === 'material' ? '新增教材' : '新增試卷';

        setBreadcrumbPaths([
          ...basePaths,
          { name: label, path: '' }
        ]);
      } else if (location.pathname.includes('/content/edit/')) {
        setBreadcrumbPaths([
          ...basePaths,
          { name: '編輯內容', path: '' }
        ]);
      } else if (location.pathname.includes('/dashboard')) {
        setBreadcrumbPaths([
          ...basePaths,
          { name: '課程儀表板', path: '' }
        ]);
      } else if (location.pathname.includes('/grades')) {
        setBreadcrumbPaths([
          ...basePaths,
          { name: '成績總覽', path: '' }
        ]);
      } else {
        // Course root
        setBreadcrumbPaths([
          { name: `課程: ${courseName || '載入中...'}`, path: '' }
        ]);
      }
    } else {
      setBreadcrumbPaths(null);
    }
  }, [courseId, location.pathname, location.search, courseName]);

  // If Sidebar and Footer should be shown, use the full layout
  if (shouldShowSidebarAndFooter) {
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
          {/* Using a grid where the sidebar spans both the content and footer rows */}
          <div className="grid grid-cols-[auto_1fr] grid-rows-[1fr_auto] min-h-full relative">

            {/* Sidebar Column - row-span-2 ensures it stays sticky for the entire scrollable height */}
            <div className="row-span-2 sticky top-0 self-start" style={{ height: 'calc(100vh - 80px)' }}>
              <TeacherSidebar
                courseId={courseId}
                isSidebarOpen={isSidebarOpen}
                onToggle={toggleSidebar}
              />
            </div>

            {/* Main Content Area */}
            <main className="min-w-0 relative">
              <Outlet key={location.pathname} context={{ setBreadcrumbPaths, breadcrumbPaths, setHeaderActions } as OutletContext} />
            </main>

            {/* Global Footer - col-span-2 allows it to cover the sidebar area at the bottom */}
            <div id="app-footer" className="col-start-1 col-span-2 relative z-40 bg-white border-t border-gray-100 mt-auto">
              <Footer />
            </div>
          </div>
        </div>
      </div>
    );
  }

  // For pages without Sidebar/Footer (generate, content editor)
  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-slate-50 relative isolation-auto">
      {/* Global Background Gradient */}
      <div className="absolute top-0 left-0 w-full h-[500px] bg-[linear-gradient(to_right,#DBEAFE,#eff6ff,#DBEAFE)] [mask-image:linear-gradient(to_bottom,white,transparent)] pointer-events-none rounded-b-[30%] scale-x-125 z-0" />

      <Header paths={breadcrumbPaths} actions={headerActions} />
      <main className="flex-1 overflow-y-auto">
        <Outlet key={location.pathname} context={{ setBreadcrumbPaths, breadcrumbPaths, setHeaderActions } as OutletContext} />
      </main>
    </div>
  );
}

export default Teacher;