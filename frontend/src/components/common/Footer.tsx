import React from 'react';

const Footer: React.FC = () => {
  return (
    <footer className="w-full bg-gradient-to-br from-slate-800 via-slate-700 to-slate-900 border-t border-slate-700 text-white py-4 px-4 text-sm shrink-0">
      <div className="max-w-7xl mx-auto flex flex-wrap justify-center items-center gap-x-8 gap-y-4">

        {/* Lab info */}
        <div className="flex flex-col items-center gap-1 text-center">
          <p className="font-medium text-neutral-text-on-dark whitespace-nowrap">國立中央大學 人工智慧與知識系統實驗室</p>
          <p className="text-neutral-footer-text text-xs opacity-80 whitespace-nowrap">NCU Artificial Intelligence & Knowledge System Lab</p>
        </div>

        {/* Divider - Hidden on mobile wrap */}
        <div className="hidden md:block h-8 w-px bg-neutral-footer-border/30"></div>

        {/* Developers */}
        <div className="flex flex-col items-center gap-1 text-center">
          <p className="text-neutral-footer-text text-xs whitespace-nowrap">開發者：陳淳瑜、陳玟樺、劉品媛</p>
          <p className="text-neutral-footer-text text-xs whitespace-nowrap">指導教授：楊鎮華 教授</p>
        </div>

        {/* Divider - Hidden on mobile wrap */}
        <div className="hidden md:block h-8 w-px bg-neutral-footer-border/30"></div>

        {/* Contact */}
        <div className="flex flex-col items-center gap-1 text-center">
          <p className="text-neutral-text-tertiary text-[10px] sm:text-xs">地址：(320317) 桃園市中壢區中大路300號 國立中央大學工程五館 E6-B320</p>
          <p className="text-neutral-text-tertiary text-[10px] sm:text-xs">Tel：03 - 4227151 分機 : 35353</p>
        </div>

      </div>
    </footer>
  );
};

export default Footer;