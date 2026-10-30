import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Lock, Mail, ShieldCheck, KeyRound } from 'lucide-react'

export default function Login() {
  const navigate = useNavigate()
  const [step, setStep] = useState('login') // 'login' | 'otp' | 'reset'
  const [email, setEmail] = useState('trader@antigravity.ai')
  const [password, setPassword] = useState('••••••••')
  const [rememberMe, setRememberMe] = useState(true)
  const [otp, setOtp] = useState('123456')
  const [message, setMessage] = useState('')

  const handleLogin = (e) => {
    e.preventDefault()
    setStep('otp')
    setMessage('Demo OTP code pre-filled: 123456')
  }

  const handleVerifyOtp = (e) => {
    e.preventDefault()
    if (otp.trim().length >= 4) {
      localStorage.setItem('ai_bot_auth', JSON.stringify({ email, rememberMe, loggedInAt: Date.now() }))
      navigate('/dashboard')
    } else {
      setMessage('Please enter a valid 6-digit OTP code.')
    }
  }

  const handleReset = (e) => {
    e.preventDefault()
    setMessage(`Password reset link sent to ${email}`)
    setTimeout(() => setStep('login'), 2000)
  }

  return (
    <div className="min-h-screen bg-[#0d0d1a] flex items-center justify-center p-4 text-gray-200">
      <div className="w-full max-w-md bg-[#1a1a2e] border border-[#2a2a3e] rounded-2xl p-8 shadow-2xl">
        <div className="text-center mb-6">
          <div className="text-4xl mb-2">🤖</div>
          <h1 className="text-2xl font-bold text-[#00d4ff]">AI Trading Signal Bot</h1>
          <p className="text-xs text-gray-400 mt-1">Quotex ML Overlay & Performance Monitor</p>
        </div>

        {message && (
          <div className="mb-4 p-3 rounded-lg bg-[#00d4ff]/10 border border-[#00d4ff]/30 text-xs text-[#00d4ff] text-center">
            {message}
          </div>
        )}

        {step === 'login' && (
          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="text-xs text-gray-400 block mb-1">Email Address</label>
              <div className="relative">
                <Mail size={16} className="absolute left-3 top-3 text-gray-500" />
                <input
                  type="email"
                  required
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  className="w-full bg-[#0d0d1a] border border-[#2a2a3e] rounded-lg pl-10 pr-3 py-2 text-sm text-white"
                />
              </div>
            </div>

            <div>
              <label className="text-xs text-gray-400 block mb-1">Password</label>
              <div className="relative">
                <Lock size={16} className="absolute left-3 top-3 text-gray-500" />
                <input
                  type="password"
                  required
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className="w-full bg-[#0d0d1a] border border-[#2a2a3e] rounded-lg pl-10 pr-3 py-2 text-sm text-white"
                />
              </div>
            </div>

            <div className="flex items-center justify-between text-xs">
              <label className="flex items-center gap-2 text-gray-400 cursor-pointer">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={e => setRememberMe(e.target.checked)}
                  className="accent-[#00d4ff]"
                />
                Remember me
              </label>
              <button
                type="button"
                onClick={() => { setStep('reset'); setMessage(''); }}
                className="text-[#00d4ff] hover:underline"
              >
                Forgot password?
              </button>
            </div>

            <button
              type="submit"
              className="w-full py-2.5 bg-gradient-to-r from-[#00ff88] to-[#00d4ff] text-[#0d0d1a] font-bold rounded-lg text-sm"
            >
              Sign In & Send OTP
            </button>
          </form>
        )}

        {step === 'otp' && (
          <form onSubmit={handleVerifyOtp} className="space-y-4">
            <div>
              <label className="text-xs text-gray-400 block mb-1">6-Digit OTP Verification</label>
              <div className="relative">
                <ShieldCheck size={16} className="absolute left-3 top-3 text-green-400" />
                <input
                  type="text"
                  maxLength={6}
                  required
                  value={otp}
                  onChange={e => setOtp(e.target.value)}
                  className="w-full bg-[#0d0d1a] border border-[#2a2a3e] rounded-lg pl-10 pr-3 py-2 text-sm tracking-widest font-mono text-white"
                />
              </div>
            </div>

            <button
              type="submit"
              className="w-full py-2.5 bg-green-500 text-[#0d0d1a] font-bold rounded-lg text-sm"
            >
              Verify OTP & Enter Dashboard
            </button>
            <button
              type="button"
              onClick={() => setStep('login')}
              className="w-full py-1.5 text-xs text-gray-400 hover:text-white"
            >
              ← Back to Login
            </button>
          </form>
        )}

        {step === 'reset' && (
          <form onSubmit={handleReset} className="space-y-4">
            <div>
              <label className="text-xs text-gray-400 block mb-1">Account Email for Password Reset</label>
              <div className="relative">
                <KeyRound size={16} className="absolute left-3 top-3 text-yellow-400" />
                <input
                  type="email"
                  required
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  className="w-full bg-[#0d0d1a] border border-[#2a2a3e] rounded-lg pl-10 pr-3 py-2 text-sm text-white"
                />
              </div>
            </div>
            <button
              type="submit"
              className="w-full py-2.5 bg-[#00d4ff] text-[#0d0d1a] font-bold rounded-lg text-sm"
            >
              Send Reset Link
            </button>
            <button
              type="button"
              onClick={() => setStep('login')}
              className="w-full py-1.5 text-xs text-gray-400 hover:text-white"
            >
              ← Back to Login
            </button>
          </form>
        )}
      </div>
    </div>
  )
}
