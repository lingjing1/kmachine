import React, { useState, useRef, useEffect } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import API_BASE_URL from '../../config/api';
import { FaFilePdf, FaChevronLeft, FaChevronRight, FaExpand, FaCompress, FaDownload, FaSpinner, FaExclamationTriangle } from 'react-icons/fa';
import 'react-pdf/dist/Page/TextLayer.css';
import 'react-pdf/dist/Page/AnnotationLayer.css';

// Configure PDF.js worker - use version from pdfjs to ensure compatibility
pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

interface PDFViewerProps {
  documentId?: string | number;
  documentName?: string;
  pageNumber?: string | number;
  className?: string;
  fallbackContent?: string;
}

export function PDFViewer({ documentId, documentName, pageNumber, className = '', fallbackContent }: PDFViewerProps) {
  const [numPages, setNumPages] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [containerWidth, setContainerWidth] = useState<number>(500); // Default fallback
  const containerRef = useRef<HTMLDivElement>(null);

  // Resize observer to adjust PDF width dynamically
  useEffect(() => {
    if (!containerRef.current) return;

    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (entry.contentBoxSize) {
          // Subtract padding/margins if needed, here we use full width minus a small buffer
          setContainerWidth(entry.contentRect.width - 32); // -32 for padding
        }
      }
    });

    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
    };
  }, []);

  // Parse page number string into an array of page numbers
  const getPagesToDisplay = (): number[] => {
    if (!pageNumber) return [1];

    const pageStr = pageNumber.toString();

    // If it's a range like "7-8", generate array [7, 8]
    if (pageStr.includes('-')) {
      const parts = pageStr.split('-').map(p => p.trim());
      const start = parseInt(parts[0]);
      const end = parseInt(parts[1]);

      if (!isNaN(start) && !isNaN(end) && end >= start) {
        const pages = [];
        // Limit to reasonable number of pages to prevent performance issues
        const maxPages = Math.min(end, start + 10);
        for (let i = start; i <= maxPages; i++) {
          pages.push(i);
        }
        return pages;
      }
      return [parseInt(parts[0]) || 1];
    }

    return [parseInt(pageStr) || 1];
  };

  const displayPages = getPagesToDisplay();

  // Construct PDF URL - use the source filename directly
  let pdfUrl = '';
  if (documentName) {
    // Use the source name from citation (e.g., "1132 0 CA CourseOverview.pdf")
    pdfUrl = `${API_BASE_URL}/api/documents/by-name/${encodeURIComponent(documentName)}?inline=true`;
  } else if (documentId) {
    // Fallback to ID (currently not reliable)
    pdfUrl = `${API_BASE_URL}/api/documents/${documentId}?inline=true`;
  }

  function onDocumentLoadSuccess({ numPages }: { numPages: number }) {
    setNumPages(numPages);
    setLoading(false);
    setError(null);
  }

  function onDocumentLoadError(error: Error) {
    console.error('[PDFViewer] PDF load error:', error, 'URL:', pdfUrl);
    setError(`無法載入 PDF: ${error.message}`);
    setLoading(false);
  }

  if (!documentId && !documentName) {
    if (fallbackContent) {
      return (
        <div className={`pdf-viewer w-full h-full p-6 overflow-y-auto bg-gray-50 ${className}`}>
          <div className="bg-white p-6 rounded-lg shadow-sm border border-orange-100">
            <h4 className="text-orange-800 text-sm font-bold mb-3 flex items-center gap-2">
              <span>⚠️ 無法預覽原始文件，顯示摘錄內容：</span>
            </h4>
            <div className="text-gray-700 text-sm leading-relaxed whitespace-pre-wrap font-serif">
              {fallbackContent}
            </div>
          </div>
        </div>
      );
    }
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 text-sm">
        無法載入 PDF: 缺少文檔資訊
      </div>
    );
  }

  // If there's an error and we have fallback content, show it
  if (error && fallbackContent) {
    // Split content into logical sections (cards) based on markdown headers
    // We look for headers at the start of lines: #, ##, ###
    const sections = fallbackContent
      .split(/(?=\n#{1,3}\s|^#{1,3}\s)/g)
      .map(s => s.trim())
      .filter(s => s.length > 0);

    return (
      <div ref={containerRef} className={`pdf-viewer w-full ${className} flex flex-col bg-gray-50/50`}>
        <div className="flex-1 p-6 overflow-y-auto custom-scrollbar">
          <div className="max-w-prose mx-auto">
            {/* Elegant Top Label */}
            <div className="flex items-center gap-3 mb-10">
              <div className="h-px flex-1 bg-blue-100/60"></div>
              <div className="flex items-center gap-2 px-3 py-1 bg-white/80 rounded-full border border-blue-100/50 shadow-sm backdrop-blur-sm">
                <div className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse"></div>
                <span className="text-[10px] font-bold text-blue-700/80 uppercase tracking-widest">參考教材內容摘要</span>
              </div>
              <div className="h-px flex-1 bg-blue-100/60"></div>
            </div>

            <div className="space-y-10">
              {sections.map((section, idx) => (
                <div key={idx} className="bg-white rounded-2xl p-8 shadow-sm border border-gray-100 relative overflow-hidden group animate-in fade-in slide-in-from-bottom-4 duration-500 fill-mode-both" style={{ animationDelay: `${idx * 100}ms` }}>
                  {/* Card background decoration - Subtle accent */}
                  <div className="absolute top-0 right-0 w-24 h-24 bg-blue-50/30 rounded-full -mr-12 -mt-12 transition-transform group-hover:scale-125 duration-1000"></div>

                  <div className="prose prose-sm prose-slate max-w-none relative z-10 
                    prose-headings:text-neutral-800 prose-headings:font-black prose-headings:tracking-tight
                    prose-h1:text-base prose-h1:mt-2 prose-h1:mb-10 prose-h1:border-b prose-h1:pb-4 prose-h1:border-gray-50
                    prose-h2:text-[15px] prose-h2:mt-2 prose-h2:mb-8
                    prose-h3:text-sm prose-h3:mt-2 prose-h3:mb-6
                    prose-p:text-[13px] prose-p:leading-loose prose-p:mb-10 prose-p:text-neutral-600
                    prose-li:text-[13px] prose-li:leading-loose prose-li:my-3 prose-li:text-neutral-600
                    prose-strong:text-blue-700/90 prose-strong:font-bold
                    prose-blockquote:border-l-4 prose-blockquote:border-blue-100 prose-blockquote:bg-blue-50/20 prose-blockquote:p-4 prose-blockquote:rounded-r-lg
                  ">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        p: ({ children }) => {
                          const text = String(children);
                          if (text.includes('圖片描述') || text.includes('圖表描述')) {
                            const cleanText = text.replace(/<.*?>/g, '').replace(/圖(片|表)描述[:：]?/g, '').trim();
                            if (!cleanText) return null;
                            return (
                              <div className="my-10 p-6 bg-orange-50/40 border border-orange-100/60 rounded-2xl text-[12px] text-orange-900/80 leading-loose flex flex-col gap-3 shadow-sm shadow-orange-100/20">
                                <div className="flex items-center gap-2 font-black uppercase tracking-widest text-[9px] text-orange-400">
                                  <span className="block w-2.5 h-0.5 bg-orange-300"></span>
                                  視覺資料詳情
                                </div>
                                {cleanText}
                              </div>
                            );
                          }
                          return <p className="mb-10">{children}</p>;
                        },
                        ul: ({ children }) => <ul className="list-disc pl-5 mt-6 mb-10 space-y-4">{children}</ul>,
                        ol: ({ children }) => <ol className="list-decimal pl-5 mt-6 mb-10 space-y-4">{children}</ol>,
                        li: ({ children }) => <li className="text-[13px] leading-loose">{children}</li>
                      }}
                    >
                      {section.replace(/<\/?[a-zA-Z\u4e00-\u9fa5]+描述>/g, '')}
                    </ReactMarkdown>
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-16 mb-12 text-center">
              <div className="inline-block px-5 py-2.5 bg-blue-50/40 rounded-xl border border-blue-100/30">
                <p className="text-[11px] text-blue-400/80 leading-relaxed font-medium">
                  以上為 AI 從原始文件 (Word/PPT) 中自動提取的知識分區。<br />
                  若需查看完整格式，請聯繫教師或建立 PDF 預覽版本。
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div ref={containerRef} className={`pdf-viewer w-full ${className}`}>
      {loading && (
        <div className="flex items-center justify-center p-8 text-gray-500">
          <div className="animate-spin mr-2">⏳</div>
          <span>載入 PDF 中...</span>
        </div>
      )}

      {error && !fallbackContent && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 text-sm">
          {error}
        </div>
      )}

      <Document
        file={pdfUrl}
        onLoadSuccess={onDocumentLoadSuccess}
        onLoadError={onDocumentLoadError}
        className="flex flex-col items-center gap-4"
        loading={null}
      >
        {displayPages.map((pageNum) => (
          <div key={pageNum} className="relative group">
            <Page
              pageNumber={pageNum}
              renderTextLayer={true}
              renderAnnotationLayer={true}
              className="shadow-lg border border-gray-100"
              width={containerWidth > 0 ? containerWidth : 300}
              loading={
                <div className="h-96 w-full flex items-center justify-center bg-gray-50 text-gray-400">
                  Loading page {pageNum}...
                </div>
              }
            />
            <div className="absolute top-2 right-2 bg-black/50 text-white text-xs px-2 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity">
              第 {pageNum} 頁
            </div>
          </div>
        ))}
      </Document>

      {numPages && !error && (
        <div className="text-center pb-2 text-xs text-gray-500 sticky bottom-0 bg-white/90 py-2 w-full backdrop-blur-sm z-10">
          顯示第 {displayPages.join('-')} 頁 / 共 {numPages} 頁
        </div>
      )}
    </div>
  );
}

