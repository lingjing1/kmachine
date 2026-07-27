import { useEffect, useState, useRef } from 'react';
import { createPortal } from 'react-dom';
import { FaCalendarAlt, FaClock, FaEye, FaEyeSlash, FaListOl, FaChevronDown, FaCloudUploadAlt, FaClipboardList, FaCalculator } from 'react-icons/fa';
import { GrPowerReset } from "react-icons/gr";

export interface PublishingSettings {
    is_visible: boolean;
    content_subtype?: string | null;
    start_time?: string | null;
    end_time?: string | null;
    duration_minutes?: number | null;
    allow_review?: boolean;
    show_answers_after?: string | null;
    assignment_type?: string;  // 'questions' | 'file_upload'
    description?: string | null;  // Assignment description (Markdown)
}

// Helper Custom Select Component to match QuestionBank style
// "Replicate style of Figure 2"
const CustomSelect = ({
    value,
    onChange,
    options,
    placeholder
}: {
    value: string;
    onChange: (val: string) => void;
    options: { value: string; label: string }[];
    placeholder: string;
}) => {
    const [isOpen, setIsOpen] = useState(false);
    const ref = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (ref.current && !ref.current.contains(event.target as Node)) {
                setIsOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const selectedLabel = options.find(o => o.value === value)?.label || placeholder;

    return (
        <div className="relative" ref={ref}>
            <button
                onClick={() => setIsOpen(!isOpen)}
                className={`w-full flex items-center justify-between gap-2 px-4 py-3 border rounded-xl text-sm font-medium bg-white transition-all ${isOpen
                    ? 'border-blue-400 ring-4 ring-blue-50/50'
                    : 'border-gray-200 hover:border-blue-300 hover:bg-gray-50'
                    } ${value ? 'text-gray-800' : 'text-gray-500'}`}
            >
                <span className="truncate">{selectedLabel}</span>
                <FaChevronDown className={`text-gray-400 text-xs transition-transform ${isOpen ? 'rotate-180' : ''}`} />
            </button>

            {isOpen && (
                <div className="absolute top-full left-0 right-0 mt-2 bg-white border border-gray-100 rounded-xl shadow-xl z-50 py-1 overflow-hidden divide-y divide-gray-50">
                    {options.map(opt => (
                        <div
                            key={opt.value}
                            className={`px-4 py-3 text-sm cursor-pointer transition-colors ${value === opt.value
                                ? 'bg-blue-50 text-blue-600 font-bold'
                                : 'text-gray-700 hover:bg-gray-50'
                                }`}
                            onClick={() => { onChange(opt.value); setIsOpen(false); }}
                        >
                            {opt.label}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};

// --- New DateTimeSelector Component (Split Date/Time) ---
interface DateTimeSelectorProps {
    label: string;
    value?: string | null;
    onChange: (val: string | null) => void;
    min?: string;
    helperText?: string;
}

const DateTimeSelector = ({ label, value, onChange, min, helperText }: DateTimeSelectorProps) => {
    const [datePart, setDatePart] = useState('');
    const [timePart, setTimePart] = useState('');
    const [isTimePickerOpen, setIsTimePickerOpen] = useState(false);
    const [pickerPosition, setPickerPosition] = useState<{ left: number; width: number; bottom: number } | null>(null);

    const timeRef = useRef<HTMLDivElement>(null);
    const dropdownRef = useRef<HTMLDivElement>(null);

    // Generate time options (every 30 mins)
    const timeOptions = [];
    for (let h = 0; h < 24; h++) {
        for (let m = 0; m < 60; m += 30) {
            const timeStr = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
            timeOptions.push(timeStr);
        }
    }
    // Add end of day
    timeOptions.push("23:59");

    // Handle click outside for time picker (including portal)
    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            const isClickInInput = timeRef.current && timeRef.current.contains(event.target as Node);
            const isClickInDropdown = dropdownRef.current && dropdownRef.current.contains(event.target as Node);

            if (!isClickInInput && !isClickInDropdown) {
                setIsTimePickerOpen(false);
            }
        };

        const handleScroll = (event: Event) => {
            // Prevent closing if scrolling inside the dropdown
            if (dropdownRef.current && dropdownRef.current.contains(event.target as Node)) {
                return;
            }
            setIsTimePickerOpen(false);
        };

        if (isTimePickerOpen) {
            document.addEventListener('mousedown', handleClickOutside);
            window.addEventListener('scroll', handleScroll, true);
            window.addEventListener('resize', () => setIsTimePickerOpen(false));

            return () => {
                document.removeEventListener('mousedown', handleClickOutside);
                window.removeEventListener('scroll', handleScroll, true);
                window.removeEventListener('resize', () => setIsTimePickerOpen(false));
            };
        }
    }, [isTimePickerOpen]);

    // Calculate position when opening (UPWARDS)
    useEffect(() => {
        if (isTimePickerOpen && timeRef.current) {
            const rect = timeRef.current.getBoundingClientRect();
            // User requested opening UPWARDS to avoid hitting bottom
            // We use fixed positioning relative to viewport
            // bottom = viewport height - rect.top + gap
            setPickerPosition({
                left: rect.left,
                width: rect.width,
                bottom: window.innerHeight - rect.top + 4
            });
        }
    }, [isTimePickerOpen]);

    // Parse value into date and time parts
    useEffect(() => {
        if (value) {
            const dt = new Date(value);
            if (!isNaN(dt.getTime())) {
                if (value.includes('T')) {
                    const [d, t] = value.split('T');
                    setDatePart(d);
                    setTimePart(t.substring(0, 5));
                } else {
                    const y = dt.getFullYear();
                    const m = String(dt.getMonth() + 1).padStart(2, '0');
                    const d = String(dt.getDate()).padStart(2, '0');
                    const h = String(dt.getHours()).padStart(2, '0');
                    const min = String(dt.getMinutes()).padStart(2, '0');
                    setDatePart(`${y}-${m}-${d}`);
                    setTimePart(`${h}:${min}`);
                }
            }
        } else {
            setDatePart('');
            setTimePart('');
        }
    }, [value]);

    const updateValue = (newDate: string, newTime: string) => {
        if (!newDate) {
            onChange(null);
            return;
        }

        let effectiveTime = newTime;
        if (!effectiveTime) effectiveTime = '00:00';

        onChange(`${newDate}T${effectiveTime}`);
    };

    const handleDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const val = e.target.value;
        setDatePart(val);
        updateValue(val, timePart);
    };

    const handleTimeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        setTimePart(e.target.value);
    };

    // Select from dropdown
    const handleTimeSelect = (t: string) => {
        setTimePart(t);
        updateValue(datePart, t);
        setIsTimePickerOpen(false);
    };

    const handleTimeBlur = () => {
        let val = timePart.trim();
        if (!val) {
            val = '00:00';
        } else {
            let h = 0;
            let m = 0;
            if (val.includes(':')) {
                const parts = val.split(':');
                h = parseInt(parts[0]) || 0;
                m = parseInt(parts[1]) || 0;
            } else if (val.length <= 2) {
                h = parseInt(val) || 0;
            } else if (val.length === 3) {
                h = parseInt(val.substring(0, 1)) || 0;
                m = parseInt(val.substring(1)) || 0;
            } else {
                h = parseInt(val.substring(0, 2)) || 0;
                m = parseInt(val.substring(2, 4)) || 0;
            }
            if (h < 0) h = 0;
            if (h > 23) h = 23;
            if (m < 0) m = 0;
            if (m > 59) m = 59;

            val = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
        }

        setTimePart(val);
        updateValue(datePart, val);
    };

    const handleClear = () => {
        onChange(null);
        setDatePart('');
        setTimePart('');
    };

    return (
        <div className="space-y-1">
            <div className="flex justify-between items-center mb-1">
                <label className="block text-sm font-medium text-neutral-text-secondary">{label}</label>
                {value && (
                    <button
                        type="button"
                        onClick={handleClear}
                        className="p-1 px-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-md transition-all flex items-center gap-1 text-xs font-medium"
                        title="Clear Date/Time"
                    >
                        <GrPowerReset />
                        <span>重置</span>
                    </button>
                )}
            </div>

            <div className="flex gap-2">
                <div className="relative flex-1">
                    <input
                        type="date"
                        className="w-full px-3 py-2 border border-neutral-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-colors"
                        value={datePart}
                        min={min ? min.split('T')[0] : undefined}
                        onChange={handleDateChange}
                    />
                </div>

                <div className="relative w-32 shrink-0" ref={timeRef}>
                    <input
                        type="text"
                        className="w-full pl-3 pr-8 py-2 border border-neutral-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-colors text-center font-mono placeholder:font-sans"
                        placeholder="23:59"
                        value={timePart}
                        onChange={handleTimeChange}
                        onBlur={handleTimeBlur}
                        onFocus={() => setIsTimePickerOpen(true)}
                        maxLength={5}
                        disabled={!datePart}
                    />
                    <button
                        type="button"
                        className="absolute right-0 top-0 bottom-0 px-2 text-gray-400 hover:text-blue-500 transition-colors flex items-center justify-center cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
                        onClick={() => !(!datePart) && setIsTimePickerOpen(!isTimePickerOpen)}
                        disabled={!datePart}
                    >
                        <FaClock size={12} />
                    </button>

                    {isTimePickerOpen && pickerPosition && createPortal(
                        <div
                            ref={dropdownRef}
                            className="fixed max-h-48 overflow-y-auto bg-white border border-gray-200 rounded-xl shadow-xl z-[9999] divide-y divide-gray-50 custom-scrollbar flex flex-col"
                            style={{
                                bottom: pickerPosition.bottom,
                                left: pickerPosition.left,
                                width: pickerPosition.width,
                            }}
                        >
                            {/* Standard list order: 00:00 -> 23:59 */}
                            <div className="flex flex-col">
                                {timeOptions.map((t) => (
                                    <div
                                        key={t}
                                        className={`px-3 py-2 text-sm text-center cursor-pointer hover:bg-blue-50 hover:text-blue-600 ${t === timePart ? 'bg-blue-50 text-blue-600 font-bold' : 'text-gray-700'}`}
                                        onMouseDown={(e) => {
                                            e.preventDefault();
                                            handleTimeSelect(t);
                                        }}
                                    >
                                        {t}
                                    </div>
                                ))}
                            </div>
                        </div>,
                        document.body
                    )}
                </div>
            </div>

            {!value && helperText && (
                <p className="text-xs text-gray-500 italic mt-1">
                    {helperText}
                </p>
            )}
        </div>
    );
};


interface PublishSettingsPanelProps {
    contentType: 'material' | 'exam';
    settings: PublishingSettings;
    onSettingsChange: (newSettings: PublishingSettings) => void;
    includeInGrade?: boolean;
    onIncludeInGradeChange?: (value: boolean) => void;
    weight?: number;
    onWeightChange?: (value: number) => void;
}

export default function PublishSettingsPanel({
    contentType,
    settings,
    onSettingsChange,
    includeInGrade = true,
    onIncludeInGradeChange,
    weight = 0,
    onWeightChange
}: PublishSettingsPanelProps) {
    const isExamOrAssignment = contentType === 'exam';
    const isFileUpload = settings.assignment_type === 'file_upload';

    // Determine effective subtype
    // Prioritize existing setting, fallback to defaults based on contentType
    const effectiveSubtype = settings.content_subtype || 'quiz';
    const isHomework = effectiveSubtype === 'homework';

    const handleChange = (field: keyof PublishingSettings, value: any) => {
        // Enforce branding rules: Quiz/Midterm/Final MUST have grading enabled
        if (field === 'content_subtype') {
            if (value !== 'homework' && onIncludeInGradeChange) {
                onIncludeInGradeChange(true);
            }
        }

        onSettingsChange({
            ...settings,
            [field]: value
        });
    };

    // Auto-set subtype if needed when loading
    useEffect(() => {
        if (!settings.content_subtype) {
            if (contentType === 'exam') {
                handleChange('content_subtype', 'quiz');
            }
        }
    }, [contentType, settings.content_subtype, handleChange]);

    // Helper to format date for reuse in min attributes
    const formatMinDate = (dateString?: string | null) => {
        if (!dateString) return undefined;
        return dateString.substring(0, 16);
    };

    return (
        <div className="space-y-6">

            {/* Visibility Toggle */}
            <div className="bg-white rounded-xl border border-neutral-border p-5">
                <div className="flex items-center justify-between mb-2">
                    <h3 className="text-lg font-bold text-neutral-text-main flex items-center gap-2">
                        {settings.is_visible ? <FaEye className="text-blue-500" /> : <FaEyeSlash className="text-gray-400" />}
                        可見性
                    </h3>
                    <label className="relative inline-flex items-center cursor-pointer">
                        <input
                            type="checkbox"
                            className="sr-only peer"
                            checked={settings.is_visible}
                            onChange={(e) => handleChange('is_visible', e.target.checked)}
                        />
                        <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
                    </label>
                </div>
                <p className="text-sm text-neutral-text-secondary">
                    {settings.is_visible
                        ? '若在開放時間內，學生可查看此內容。'
                        : '此內容目前已隱藏，學生無法查看。'}
                </p>
            </div>

            {/* Exam/Assignment Subtype Selection - hidden for file_upload */}
            {isExamOrAssignment && !isFileUpload && (
                <div className="bg-white rounded-xl border border-neutral-border p-5">
                    <div className="flex items-center justify-between mb-2">
                        <h3 className="text-lg font-bold text-neutral-text-main flex items-center gap-2">
                            <FaListOl className="text-blue-500" />
                            試卷類型
                        </h3>
                        <div className="w-48">
                            <CustomSelect
                                value={effectiveSubtype || 'homework'}
                                onChange={(val) => handleChange('content_subtype', val)}
                                placeholder="選擇類型"
                                options={[
                                    { value: 'homework', label: '作業 (Homework)' },
                                    { value: 'quiz', label: '小考 (Quiz)' },
                                    { value: 'midterm', label: '期中考 (Midterm)' },
                                    { value: 'final', label: '期末考 (Final)' }
                                ]}
                            />
                        </div>
                    </div>

                    {/* Grading Toggle - Only for Homework */}
                    {isHomework && onIncludeInGradeChange && (
                        <div className="mt-4 pt-4 border-t border-gray-100">
                            <label className="flex items-center justify-between cursor-pointer group">
                                <div className="flex flex-col">
                                    <span className="text-sm font-bold text-gray-700 group-hover:text-blue-600 transition-colors">是否配分</span>
                                </div>
                                <div className="relative inline-flex items-center cursor-pointer">
                                    <input
                                        type="checkbox"
                                        className="sr-only peer"
                                        checked={includeInGrade}
                                        onChange={(e) => onIncludeInGradeChange(e.target.checked)}
                                    />
                                    <div className="w-9 h-5 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-blue-600"></div>
                                </div>
                            </label>
                        </div>
                    )}

                    {/* Weight Input - Only if Grading is Enabled and onWeightChange provided */}
                    {isExamOrAssignment && includeInGrade && onWeightChange && (
                        <div className="mt-4 pt-4 border-t border-gray-100">
                            <div className="flex items-center justify-between">
                                <div className="flex flex-col">
                                    <span className="text-sm font-bold text-gray-700">
                                        學期成績權重 <span className="text-red-500">*</span>
                                    </span>
                                    <span className="text-xs text-gray-400">佔學期總成績的百分比</span>
                                </div>
                                <div className="relative w-24">
                                    <input
                                        type="number"
                                        min="0"
                                        max="100"
                                        step="1"
                                        value={weight}
                                        onChange={(e) => {
                                            let val = parseFloat(e.target.value);
                                            if (isNaN(val)) val = 0;
                                            if (val < 0) val = 0;
                                            if (val > 100) val = 100;
                                            onWeightChange(val);
                                        }}
                                        className="w-full pl-3 pr-8 py-2 border border-neutral-border rounded-lg text-right font-medium focus:ring-2 focus:ring-blue-500 outline-none"
                                    />
                                    <span className="absolute right-3 top-2 text-gray-400 font-medium">%</span>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* Grading settings for file_upload (simplified card, no subtype) */}
            {isExamOrAssignment && isFileUpload && onIncludeInGradeChange && (
                <div className="bg-white rounded-xl border border-neutral-border p-5">
                    <div className="flex items-center justify-between mb-2">
                        <h3 className="text-lg font-bold text-neutral-text-main flex items-center gap-2">
                            <FaCalculator className="text-blue-500" />
                            成績設定
                        </h3>
                    </div>
                    {/* Grading Toggle */}
                    <div className="mt-2">
                        <label className="flex items-center justify-between cursor-pointer group">
                            <div className="flex flex-col">
                                <span className="text-sm font-bold text-gray-700 group-hover:text-blue-600 transition-colors">是否配分</span>
                            </div>
                            <div className="relative inline-flex items-center cursor-pointer">
                                <input
                                    type="checkbox"
                                    className="sr-only peer"
                                    checked={includeInGrade}
                                    onChange={(e) => onIncludeInGradeChange(e.target.checked)}
                                />
                                <div className="w-9 h-5 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-blue-600"></div>
                            </div>
                        </label>
                    </div>
                    {/* Weight Input */}
                    {includeInGrade && onWeightChange && (
                        <div className="mt-4 pt-4 border-t border-gray-100">
                            <div className="flex items-center justify-between">
                                <div className="flex flex-col">
                                    <span className="text-sm font-bold text-gray-700">
                                        學期成績權重 <span className="text-red-500">*</span>
                                    </span>
                                    <span className="text-xs text-gray-400">佔學期總成績的百分比</span>
                                </div>
                                <div className="relative w-24">
                                    <input
                                        type="number"
                                        min="0"
                                        max="100"
                                        step="1"
                                        value={weight}
                                        onChange={(e) => {
                                            let val = parseFloat(e.target.value);
                                            if (isNaN(val)) val = 0;
                                            if (val < 0) val = 0;
                                            if (val > 100) val = 100;
                                            onWeightChange(val);
                                        }}
                                        className="w-full pl-3 pr-8 py-2 border border-neutral-border rounded-lg text-right font-medium focus:ring-2 focus:ring-blue-500 outline-none"
                                    />
                                    <span className="absolute right-3 top-2 text-gray-400 font-medium">%</span>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* Assignment Type Selection - only for homework */}
            {isExamOrAssignment && isHomework && (
                <div className="bg-white rounded-xl border border-neutral-border p-5">
                    <h3 className="text-lg font-bold text-neutral-text-main flex items-center gap-2 mb-3">
                        <FaClipboardList className="text-blue-500" />
                        繳交方式
                    </h3>
                    <div className="flex gap-3">
                        <button
                            type="button"
                            className={`flex-1 flex items-center gap-2 px-4 py-3.5 border-2 rounded-xl text-sm font-semibold transition-all ${(settings.assignment_type || 'questions') === 'questions'
                                ? 'border-blue-500 bg-blue-50 text-blue-700 shadow-sm'
                                : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300 hover:bg-gray-50'
                                }`}
                            onClick={() => handleChange('assignment_type', 'questions')}
                        >
                            <FaClipboardList className="text-lg flex-shrink-0" />
                            <div className="text-left">
                                <div>線上作答</div>
                                <div className="text-xs font-normal text-gray-500 mt-0.5">學生在平台上直接作答題目</div>
                            </div>
                        </button>
                        <button
                            type="button"
                            className={`flex-1 flex items-center gap-2 px-4 py-3.5 border-2 rounded-xl text-sm font-semibold transition-all ${settings.assignment_type === 'file_upload'
                                ? 'border-blue-500 bg-blue-50 text-blue-700 shadow-sm'
                                : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300 hover:bg-gray-50'
                                }`}
                            onClick={() => handleChange('assignment_type', 'file_upload')}
                        >
                            <FaCloudUploadAlt className="text-lg flex-shrink-0" />
                            <div className="text-left">
                                <div>檔案上傳</div>
                                <div className="text-xs font-normal text-gray-500 mt-0.5">學生上傳檔案作為繳交內容</div>
                            </div>
                        </button>
                    </div>
                </div>
            )}


            {/* Time Settings */}
            <div className="bg-white rounded-xl border border-neutral-border p-5 space-y-4">
                <h3 className="text-lg font-bold text-neutral-text-main flex items-center gap-2 mb-4">
                    <FaCalendarAlt className="text-blue-500" />
                    發布時間
                </h3>

                <div className="grid grid-cols-1 gap-6">
                    {/* Start Time */}
                    <DateTimeSelector
                        label="開放時間 (Open)"
                        value={settings.start_time}
                        onChange={(val) => handleChange('start_time', val)}
                        helperText="若未設定，則建立後立刻開放 (Immediate)"
                    />

                    {/* End/Due Logic based on Type */}
                    <DateTimeSelector
                        label={isHomework ? "繳交期限 (Due)" : "結束/關閉時間 (Close)"}
                        value={settings.end_time}
                        onChange={(val) => handleChange('end_time', val)}
                        min={formatMinDate(settings.start_time)}
                        helperText="若未設定，則無結束時間限制 (No time limit)"
                    />
                </div>

                {/* Advanced Settings (Hidden for Homework) */}
                {isExamOrAssignment && !isHomework && (
                    <>
                        <div className="border-t border-gray-100 mt-4 pt-4"></div>

                        <div className="flex flex-col md:flex-row gap-4 items-end mb-4">
                            {/* Duration Minutes */}
                            <div className="space-y-1 w-full md:w-32 shrink-0">
                                <label className="block text-sm font-medium text-neutral-text-secondary">作答時長限制 (分鐘)</label>
                                <div className="relative">
                                    <input
                                        type="number"
                                        min="0"
                                        className="w-full pl-10 pr-3 py-2 border border-neutral-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-colors"
                                        placeholder="60"
                                        value={settings.duration_minutes || ''}
                                        onChange={(e) => handleChange('duration_minutes', e.target.value ? parseInt(e.target.value) : null)}
                                    />
                                    <div className="absolute left-3 top-2.5 text-gray-400">
                                        <FaClock />
                                    </div>
                                </div>
                            </div>

                            <div className="flex-1 w-full md:w-auto pb-1">
                                <label className="flex items-center gap-2 p-2 border border-transparent hover:bg-gray-50 rounded-lg transition-colors cursor-pointer -ml-2 whitespace-nowrap">
                                    <div className="relative inline-flex items-center cursor-pointer shrink-0">
                                        <input
                                            type="checkbox"
                                            className="sr-only peer"
                                            checked={settings.allow_review !== false} // Default to true if undefined
                                            onChange={(e) => handleChange('allow_review', e.target.checked)}
                                        />
                                        <div className="w-9 h-5 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-blue-600"></div>
                                    </div>
                                    <span className="text-sm font-medium text-neutral-text-main tracking-tight">
                                        允許學生繳卷後檢視
                                    </span>
                                </label>
                            </div>
                        </div>

                        {/* Answer Reveal Time - Full Width */}
                        <DateTimeSelector
                            label="答案公布時間"
                            value={settings.show_answers_after}
                            onChange={(val) => handleChange('show_answers_after', val)}
                            min={formatMinDate(settings.end_time)}
                            helperText="若未設定，則依考試結束規則顯示"
                        />
                    </>
                )}
            </div>
        </div >
    );
}
