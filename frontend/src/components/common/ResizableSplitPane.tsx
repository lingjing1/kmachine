import React, { useState, useRef, useEffect } from 'react';

interface ResizableSplitPaneProps {
    left: React.ReactNode;
    right: React.ReactNode;
    initialRightWidth?: number;
    minRightWidth?: number;
    maxRightWidth?: number;
    className?: string;
}

export default function ResizableSplitPane({
    left,
    right,
    initialRightWidth = 450,
    minRightWidth = 300,
    maxRightWidth = 800,
    className = ''
}: ResizableSplitPaneProps) {
    const [rightWidth, setRightWidth] = useState(initialRightWidth);
    const [isDragging, setIsDragging] = useState(false);
    const containerRef = useRef<HTMLDivElement>(null);

    const handleMouseDown = (e: React.MouseEvent) => {
        e.preventDefault();
        setIsDragging(true);
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';

        // Add a class to body to prevent iframe pointer events if any
        document.body.classList.add('resizing');
    };

    useEffect(() => {
        const handleMouseMove = (e: MouseEvent) => {
            if (!isDragging || !containerRef.current) return;

            const containerRect = containerRef.current.getBoundingClientRect();
            // Calculate new width relative to the container's right edge
            const newRightWidth = containerRect.right - e.clientX;

            if (newRightWidth >= minRightWidth && newRightWidth <= maxRightWidth) {
                requestAnimationFrame(() => {
                    setRightWidth(newRightWidth);
                });
            }
        };

        const handleMouseUp = () => {
            setIsDragging(false);
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            document.body.classList.remove('resizing');
        };

        if (isDragging) {
            window.addEventListener('mousemove', handleMouseMove);
            window.addEventListener('mouseup', handleMouseUp);
        }

        return () => {
            window.removeEventListener('mousemove', handleMouseMove);
            window.removeEventListener('mouseup', handleMouseUp);
        };
    }, [isDragging, minRightWidth, maxRightWidth]);

    return (
        <div
            ref={containerRef}
            className={`flex w-full h-full overflow-hidden ${className}`}
        >
            {/* Left Pane (Flexible) */}
            <div className="flex-1 min-w-0 overflow-hidden relative z-10">
                {left}
            </div>

            {/* Resizer Handle - Floats over the boundary */}
            <div
                className={`
                    w-4 -ml-2 hover:-ml-2 cursor-col-resize z-50 flex-shrink-0
                    relative group flex items-center justify-center
                    transition-colors duration-200 outline-none
                `}
                onMouseDown={handleMouseDown}
            >
                {/* Visual Line (Only visible on hover/drag) */}
                <div className={`
                    absolute left-1/2 top-0 bottom-0 w-[1px] -translate-x-1/2
                    transition-colors duration-200
                    ${isDragging ? 'bg-theme-primary opacity-100' : 'bg-gray-200 opacity-0 group-hover:opacity-100'}
                `} />

                {/* Pill Handle (Center) */}
                <div className={`
                    w-1.5 h-12 rounded-full shadow-sm border border-gray-200
                    flex items-center justify-center transition-all duration-200
                    ${isDragging
                        ? 'bg-theme-primary border-theme-primary scale-110'
                        : 'bg-white group-hover:border-theme-primary/50'
                    }
                `}>
                    {/* Inner Dot/Line */}
                    <div className={`
                        w-0.5 h-4 rounded-full transition-colors
                        ${isDragging ? 'bg-white' : 'bg-gray-300 group-hover:bg-theme-primary/50'}
                     `} />
                </div>
            </div>

            {/* Right Pane (Fixed Width, Resizable) */}
            <div
                style={{ width: rightWidth }}
                className="flex-shrink-0 overflow-hidden relative bg-white z-20 flex flex-col border-l border-transparent"
            >
                {right}
            </div>
        </div>
    );
}
