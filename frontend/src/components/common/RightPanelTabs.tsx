import { useState } from 'react';

export interface RightPanelTab {
    id: string;
    label: React.ReactNode;
    icon?: React.ReactNode;
    content: React.ReactNode;
    badge?: number;
    activeColorClass?: string; // e.g. "text-green-600 border-green-600 bg-green-50/50"
}

interface RightPanelTabsProps {
    tabs: RightPanelTab[];
    defaultTab?: string;
    activeTab?: string; // Controlled mode
    onChange?: (tabId: string) => void;
    className?: string;
}

export default function RightPanelTabs({
    tabs,
    defaultTab,
    activeTab: controlledActiveTab,
    onChange,
    className = ''
}: RightPanelTabsProps) {
    const [internalActiveTab, setInternalActiveTab] = useState(defaultTab || tabs[0]?.id || '');

    // Use controlled value if provided, otherwise internal state
    const activeTab = controlledActiveTab !== undefined ? controlledActiveTab : internalActiveTab;

    const handleTabChange = (tabId: string) => {
        if (controlledActiveTab === undefined) {
            setInternalActiveTab(tabId);
        }
        onChange?.(tabId);
    };

    const activeTabContent = tabs.find(tab => tab.id === activeTab)?.content;

    return (
        <div className={`rounded-xl border border-gray-200 shadow-sm flex flex-col overflow-hidden ${className}`}>
            {/* Tab Headers */}
            <div className="flex border-b border-gray-200 shrink-0">
                {tabs.map((tab) => (
                    <button
                        key={tab.id}
                        onClick={() => handleTabChange(tab.id)}
                        className={`flex-1 px-4 py-4 text-base font-bold transition-all relative ${activeTab === tab.id
                            ? (tab.activeColorClass || 'text-theme-primary border-b-2 border-theme-primary bg-blue-50/30')
                            : 'text-gray-600 hover:text-gray-800 hover:bg-gray-50'
                            }`}
                    >
                        <div className="flex items-center justify-center gap-2">
                            {tab.icon && <span className="text-xl">{tab.icon}</span>}
                            <span>{tab.label}</span>
                            {tab.badge !== undefined && tab.badge > 0 && (
                                <span className="ml-1 px-1.5 py-0.5 text-xs font-bold bg-red-500 text-white rounded-full min-w-[18px] text-center">
                                    {tab.badge}
                                </span>
                            )}
                        </div>
                    </button>
                ))}
            </div>

            {/* Tab Content - Must allow child to control its own scrolling */}
            <div className="flex-1 min-h-0 overflow-y-auto rounded-b-xl">
                {activeTabContent}
            </div>
        </div>
    );
}
