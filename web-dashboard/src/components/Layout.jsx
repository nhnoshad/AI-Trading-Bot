import React, { useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, History, Settings, TestTube2,
  Brain, Menu, X, Activity, Wifi, WifiOff
} from 'lucide-react'
import { useStore } from '../store/useStore'

const navItems = [
  { path: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { path: '/history', icon: History, label: 'Prediction History' },
  { path: '/backtest', icon: TestTube2, label: 'Backtesting' },
  { path: '/model', icon: Brain, label: 'AI Model' },
  { path: '/settings', icon: Settings, label: 'Settings' },
]

export default function Layout({ children }) {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const connected = useStore(s => s.connected)
  const currentSignal = useStore(s => s.currentSignal)

  return (
    <div className="flex h-screen bg-[#0d0d1a] text-gray-200">
      {/* Sidebar */}
      <aside className={`${
        sidebarOpen ? 'w-56' : 'w-16'
      } flex-shrink-0 bg-[#1a1a2e] border-r border-[#2a2a3e] transition-all duration-300 flex flex-col`}>
        {/* Logo */}
        <div className="flex items-center gap-3 p-4 border-b border-[#2a2a3e]">
          <span className="text-2xl">🤖</span>
          {sidebarOpen && <span className="font-bold text-[#00d4ff] text-sm">AI Trading Bot</span>}
        </div>
        {/* Nav */}
        <nav className="flex-1 p-2 space-y-1">
          {navItems.map(({ path, icon: Icon, label }) => (
            <NavLink
              key={path}
              to={path}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all ${
                  isActive
                    ? 'bg-[#00d4ff]/10 text-[#00d4ff] font-semibold'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-[#2a2a3e]'
                }`
              }
            >
              <Icon size={18} />
              {sidebarOpen && label}
            </NavLink>
          ))}
        </nav>
        {/* Status */}
        <div className="p-3 border-t border-[#2a2a3e]">
          <div className="flex items-center gap-2 text-xs">
            {connected
              ? <Wifi size={14} className="text-green-400" />
              : <WifiOff size={14} className="text-red-400" />}
            {sidebarOpen && (
              <span className={connected ? 'text-green-400' : 'text-red-400'}>
                {connected ? 'Server Online' : 'Disconnected'}
              </span>
            )}
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Topbar */}
        <header className="h-14 bg-[#1a1a2e] border-b border-[#2a2a3e] flex items-center px-4 gap-4">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="text-gray-400 hover:text-white"
          >
            {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
          <span className="font-semibold text-gray-200 flex-1">AI Trading Signal Dashboard</span>
          {currentSignal && (
            <div className={`px-3 py-1 rounded-full text-xs font-bold ${
              currentSignal.signal === 'BUY' ? 'bg-green-500/20 text-green-400' :
              currentSignal.signal === 'SELL' ? 'bg-red-500/20 text-red-400' :
              'bg-yellow-500/20 text-yellow-400'
            }`}>
              {currentSignal.signal} {currentSignal.confidence?.toFixed(1)}%
            </div>
          )}
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <Activity size={14} className="text-[#00d4ff]" />
            v1.0.0
          </div>
        </header>
        {/* Page Content */}
        <main className="flex-1 overflow-auto p-6">
          {children}
        </main>
      </div>
    </div>
  )
}
