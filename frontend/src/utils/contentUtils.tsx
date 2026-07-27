import { FaBookOpenReader } from 'react-icons/fa6';
import { MdRateReview } from 'react-icons/md';
import {
    FaEdit,
    FaClipboardCheck,
    FaFilePdf,
    FaGlobe,
    FaFileWord,
    FaFilePowerpoint,
    FaFileExcel,
    FaFileImage,
    FaFileArchive,
    FaFileAlt,
    FaFile
} from 'react-icons/fa';

export const getSubtypeLabel = (type: string, subtype?: string | null) => {
    if (!subtype) {
        if (type === 'material') return '教材';
        if (type === 'exam') return '考試';
        return '內容';
    }

    const map: Record<string, string> = {
        'preview': '預習教材',
        'review': '複習教材',
        'quiz': '小考',
        'homework': '作業',
        'midterm': '期中考',
        'final': '期末考'
    };

    return map[subtype] || subtype;
};

export const getFileIcon = (
    fileType: string,
    fileName: string,
    iconSize: number = 14,
    containerClass: string = "p-1.5 rounded-md bg-gray-50 flex items-center justify-center",
    subtype?: string | null
) => {
    const extension = fileName?.split('.').pop()?.toLowerCase() || '';

    let icon;

    // Handle subtypes for materials
    if (subtype === 'preview' || subtype === 'preview_material') {
        icon = <FaBookOpenReader size={iconSize} />;
    } else if (subtype === 'review' || subtype === 'review_material') {
        icon = <MdRateReview size={iconSize} />;
    } else if (subtype === 'homework') {
        icon = <FaEdit size={iconSize} />;
    } else if (subtype === 'quiz' || subtype === 'midterm' || subtype === 'final' || fileType === 'exam') {
        icon = <FaClipboardCheck size={iconSize} />;
    } else if (fileType.includes('pdf') || extension === 'pdf') {
        icon = <FaFilePdf className="text-red-500" size={iconSize} />;
    } else if (fileType?.includes('url') || fileType?.includes('web') || extension === 'html' || fileName?.startsWith('http')) {
        icon = <FaGlobe className="text-emerald-500" size={iconSize} />;
    } else if (fileType.includes('word') || ['doc', 'docx'].includes(extension)) {
        icon = <FaFileWord className="text-blue-600" size={iconSize} />;
    } else if (fileType.includes('powerpoint') || fileType.includes('presentation') || ['ppt', 'pptx'].includes(extension)) {
        icon = <FaFilePowerpoint className="text-orange-600" size={iconSize} />;
    } else if (fileType.includes('excel') || fileType.includes('spreadsheet') || ['xls', 'xlsx'].includes(extension)) {
        icon = <FaFileExcel className="text-green-600" size={iconSize} />;
    } else if (fileType.includes('image') || ['jpg', 'jpeg', 'png', 'gif'].includes(extension)) {
        icon = <FaFileImage className="text-purple-500" size={iconSize} />;
    } else if (['zip', 'rar', '7z'].includes(extension)) {
        icon = <FaFileArchive className="text-yellow-600" size={iconSize} />;
    } else if (['txt', 'text'].includes(extension) || fileType.includes('text/plain')) {
        icon = <FaFileAlt className="text-gray-600" size={iconSize} />;
    } else {
        icon = <FaFile size={iconSize} />;
    }

    return (
        <div className={containerClass}>
            {icon}
        </div>
    );
};
