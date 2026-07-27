import { useState, useEffect } from 'react';
import API_BASE_URL from '../../config/api';

interface ForgotPasswordModalProps {
  isOpen: boolean;
  onClose: () => void;
}

type Step = 'email' | 'verify' | 'reset' | 'success';

export default function ForgotPasswordModal({ isOpen, onClose }: ForgotPasswordModalProps) {
  const [step, setStep] = useState<Step>('email');
  const [email, setEmail] = useState('');
  const [verificationCode, setVerificationCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [countdown, setCountdown] = useState(0);

  // 倒數計時
  useEffect(() => {
    if (countdown > 0) {
      const timer = setTimeout(() => setCountdown(countdown - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [countdown]);

  if (!isOpen) return null;

  const handleClose = () => {
    setStep('email');
    setEmail('');
    setVerificationCode('');
    setNewPassword('');
    setConfirmPassword('');
    setError('');
    setCountdown(0);
    onClose();
  };

  // Step 1: 發送驗證碼
  const handleSendCode = async () => {
    if (!email) {
      setError('請輸入 Email');
      return;
    }

    setIsLoading(true);
    setError('');

    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/send-password-reset-code`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || '發送驗證碼失敗');
      }

      setStep('verify');
      setCountdown(300);
    } catch (err: any) {
      setError(err.message || '發送驗證碼失敗，請稍後再試');
    } finally {
      setIsLoading(false);
    }
  };

  // Step 2: 驗證驗證碼
  const handleVerifyCode = async () => {
    if (!verificationCode || verificationCode.length !== 6) {
      setError('請輸入 6 位數驗證碼');
      return;
    }

    // 驗證碼由後端在 reset-password 時一起驗證
    setError('');
    setStep('reset');
  };

  // Step 3: 重設密碼
  const handleResetPassword = async () => {
    if (!newPassword) {
      setError('請輸入新密碼');
      return;
    }
    if (newPassword.length < 6) {
      setError('密碼至少需要 6 個字元');
      return;
    }
    if (newPassword !== confirmPassword) {
      setError('密碼不一致');
      return;
    }

    setIsLoading(true);
    setError('');

    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email,
          code: verificationCode,
          new_password: newPassword,
        }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || '重設密碼失敗');
      }

      setStep('success');
    } catch (err: any) {
      setError(err.message || '重設密碼失敗，請稍後再試');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div className="bg-white rounded-2xl shadow-xl max-w-md w-full mx-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200">
          <h2 className="text-2xl font-bold text-gray-800">忘記密碼</h2>
          <button
            onClick={handleClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
            aria-label="關閉"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="p-6">
          {error && (
            <div className="mb-4 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center">
              <svg className="w-5 h-5 mr-2 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                  clipRule="evenodd"
                />
              </svg>
              <span>{error}</span>
            </div>
          )}

          {/* Step 1: 輸入 Email */}
          {step === 'email' && (
            <div className="space-y-4">
              <p className="text-gray-600 text-sm">
                請輸入您註冊時使用的 Email，我們將發送驗證碼到您的信箱。
              </p>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Email
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="your.email@example.com"
                  disabled={isLoading}
                />
              </div>
              <button
                onClick={handleSendCode}
                disabled={isLoading || !email}
                className="w-full py-3 px-4 rounded-lg font-medium text-white transition-all bg-gradient-to-r from-blue-600 to-cyan-600 hover:shadow-lg hover:-translate-y-0.5 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0 disabled:hover:shadow-none"
              >
                {isLoading ? '發送中...' : '發送驗證碼'}
              </button>
              <p className="text-xs text-gray-500 text-center mt-2">
                💡 如果您忘記了註冊的 Email（帳號），請聯繫您的老師或管理員協助。
              </p>
            </div>
          )}

          {/* Step 2: 輸入驗證碼 */}
          {step === 'verify' && (
            <div className="space-y-4">
              <p className="text-gray-600 text-sm">
                驗證碼已發送至 <strong>{email}</strong>，請查收信箱。
              </p>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  驗證碼
                </label>
                <input
                  type="text"
                  value={verificationCode}
                  onChange={(e) => {
                    const value = e.target.value.replace(/\D/g, '').slice(0, 6);
                    setVerificationCode(value);
                  }}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-center text-2xl tracking-widest"
                  placeholder="000000"
                  maxLength={6}
                />
              </div>
              <button
                onClick={handleVerifyCode}
                disabled={verificationCode.length !== 6}
                className="w-full py-3 px-4 rounded-lg font-medium text-white transition-all bg-gradient-to-r from-blue-600 to-cyan-600 hover:shadow-lg hover:-translate-y-0.5 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0 disabled:hover:shadow-none"
              >
                下一步
              </button>
              <button
                onClick={handleSendCode}
                disabled={countdown > 0 || isLoading}
                className="w-full text-sm text-blue-600 hover:text-blue-800 disabled:text-gray-400 disabled:cursor-not-allowed"
              >
                {countdown > 0 ? `${Math.floor(countdown / 60)}:${String(countdown % 60).padStart(2, '0')} 後可重新發送` : '重新發送驗證碼'}
              </button>
            </div>
          )}

          {/* Step 3: 設定新密碼 */}
          {step === 'reset' && (
            <div className="space-y-4">
              <p className="text-gray-600 text-sm">
                請設定您的新密碼。
              </p>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  新密碼
                </label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="至少 6 個字元"
                  disabled={isLoading}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  確認新密碼
                </label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="再次輸入新密碼"
                  disabled={isLoading}
                />
              </div>
              <button
                onClick={handleResetPassword}
                disabled={isLoading || !newPassword || !confirmPassword}
                className="w-full py-3 px-4 rounded-lg font-medium text-white transition-all bg-gradient-to-r from-blue-600 to-cyan-600 hover:shadow-lg hover:-translate-y-0.5 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0 disabled:hover:shadow-none"
              >
                {isLoading ? '重設中...' : '重設密碼'}
              </button>
            </div>
          )}

          {/* Step 4: 成功 */}
          {step === 'success' && (
            <div className="text-center space-y-4">
              <div className="w-16 h-16 mx-auto bg-green-100 rounded-full flex items-center justify-center">
                <svg className="w-8 h-8 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-gray-800">密碼重設成功！</h3>
              <p className="text-gray-600 text-sm">
                您的密碼已更新，請使用新密碼登入。
              </p>
              <button
                onClick={handleClose}
                className="w-full py-3 px-4 rounded-lg font-medium text-white transition-all bg-gradient-to-r from-green-500 to-emerald-600 hover:shadow-lg hover:-translate-y-0.5"
              >
                返回登入
              </button>
            </div>
          )}
        </div>

        {/* Footer - 步驟指示 */}
        {step !== 'success' && (
          <div className="px-6 pb-6">
            <div className="flex items-center justify-center gap-2">
              {(['email', 'verify', 'reset'] as Step[]).map((s, i) => (
                <div key={s} className="flex items-center">
                  <div
                    className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${step === s
                        ? 'bg-blue-600 text-white'
                        : ['email', 'verify', 'reset'].indexOf(step) > i
                          ? 'bg-green-500 text-white'
                          : 'bg-gray-200 text-gray-500'
                      }`}
                  >
                    {['email', 'verify', 'reset'].indexOf(step) > i ? '✓' : i + 1}
                  </div>
                  {i < 2 && (
                    <div className={`w-8 h-0.5 ${['email', 'verify', 'reset'].indexOf(step) > i ? 'bg-green-500' : 'bg-gray-200'}`} />
                  )}
                </div>
              ))}
            </div>
            <div className="flex justify-center gap-6 mt-2">
              <span className="text-xs text-gray-500">輸入 Email</span>
              <span className="text-xs text-gray-500">驗證碼</span>
              <span className="text-xs text-gray-500">新密碼</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
