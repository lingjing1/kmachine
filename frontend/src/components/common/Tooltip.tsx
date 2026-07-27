import React, { useState, useRef, useLayoutEffect } from 'react';
import { createPortal } from 'react-dom';

interface TooltipProps {
    content: React.ReactNode;
    children: React.ReactNode;
    position?: 'top' | 'bottom' | 'left' | 'right';
    className?: string;
}

export const Tooltip: React.FC<TooltipProps> = ({
    content,
    children,
    position = 'top',
    className = ''
}) => {
    const [isHovered, setIsHovered] = useState(false);
    const [tooltipCoords, setTooltipCoords] = useState({ top: 0, left: 0 });
    const targetRef = useRef<HTMLDivElement>(null);
    const tooltipRef = useRef<HTMLDivElement>(null);

    const updatePosition = () => {
        if (!targetRef.current || !tooltipRef.current) return;

        const targetRect = targetRef.current.getBoundingClientRect();
        const tooltipRect = tooltipRef.current.getBoundingClientRect();

        let top = 0;
        let left = 0;

        switch (position) {
            case 'top':
                top = targetRect.top - tooltipRect.height - 8;
                left = targetRect.left + (targetRect.width / 2) - (tooltipRect.width / 2);
                break;
            case 'bottom':
                top = targetRect.bottom + 8;
                left = targetRect.left + (targetRect.width / 2) - (tooltipRect.width / 2);
                break;
            case 'left':
                top = targetRect.top + (targetRect.height / 2) - (tooltipRect.height / 2);
                left = targetRect.left - tooltipRect.width - 8;
                break;
            case 'right':
                top = targetRect.top + (targetRect.height / 2) - (tooltipRect.height / 2);
                left = targetRect.right + 8;
                break;
        }

        setTooltipCoords({ top, left });
    };

    useLayoutEffect(() => {
        if (isHovered) {
            updatePosition();
            // Handle window resize or scroll
            window.addEventListener('scroll', updatePosition, true);
            window.addEventListener('resize', updatePosition);
            return () => {
                window.removeEventListener('scroll', updatePosition, true);
                window.removeEventListener('resize', updatePosition);
            };
        }
    }, [isHovered, position]);

    return (
        <div
            ref={targetRef}
            className={`relative inline-block ${className}`}
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => setIsHovered(false)}
        >
            {children}
            {isHovered && createPortal(
                <div
                    ref={tooltipRef}
                    className={`
                        fixed px-3 py-2 bg-gray-800 text-white text-xs font-medium rounded-md shadow-xl 
                        whitespace-nowrap pointer-events-none z-[9999] transition-opacity duration-200
                        ${isHovered ? 'opacity-100' : 'opacity-0'}
                    `}
                    style={{
                        top: tooltipCoords.top,
                        left: tooltipCoords.left,
                        // Ensure it's not shown before coords are calculated
                        visibility: tooltipCoords.top === 0 && tooltipCoords.left === 0 ? 'hidden' : 'visible'
                    }}
                >
                    {content}
                    {/* Simplified Arrow - can be skipped for portal if complex, but adding a basic one */}
                    <div className={`absolute w-0 h-0 border-solid ${position === 'top' ? 'top-full left-1/2 -translate-x-1/2 -mt-1 border-t-gray-800 border-x-transparent border-b-transparent border-[6px]' :
                        position === 'bottom' ? 'bottom-full left-1/2 -translate-x-1/2 -mb-1 border-b-gray-800 border-x-transparent border-t-transparent border-[6px]' :
                            position === 'left' ? 'left-full top-1/2 -translate-y-1/2 -ml-1 border-l-gray-800 border-y-transparent border-r-transparent border-[6px]' :
                                'right-full top-1/2 -translate-y-1/2 -mr-1 border-r-gray-800 border-y-transparent border-l-transparent border-[6px]'
                        }`}></div>
                </div>,
                document.body
            )}
        </div>
    );
};

export default Tooltip;
