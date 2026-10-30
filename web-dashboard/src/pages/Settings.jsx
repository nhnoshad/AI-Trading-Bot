import React from 'react'
import { useStore } from '../store/useStore'

export default function Settings() {
  const { settings, updateSettings } = useStore()

  const handleChange = (key, value) => updateSettings({ [key]: parseFloat(value) || value })

  const fields = [
    { key: 'tradeAmount', label: 'Default Trade Amount ($)', type: 'number', min: 1, max: 10000 },
    { key: 'tradeDuration', label: 'Default Trade Duration (s)', type: 'number', min: 30, max: 3600 },
    { key: 'minConfidence', label: 'Min Confidence Threshold (%)', type: 'number', min: 50, max: 95 },
    { key: 'maxTradesPerHour', label: 'Max Trades Per Hour', type: 'number', min: 1, max: 50 },
    { key: 'maxConsecutiveLosses', label: 'Max Consecutive Losses', type: 'number', min: 1, max: 10 },
    { key: 'dailyLossLimit', label: 'Daily Loss Limit ($)', type: 'number', min: 10, max: 10000 },
    { key: 'dailyProfitTarget', label: 'Daily Profit Target ($)', type: 'number', min: 10, max: 10000 },
    { key: 'cooldownSeconds', label: 'Cooldown Between Trades (s)', type: 'number', min: 0, max: 300 },
  ]

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-xl font-bold text-white">Settings</h1>
      <div className="bg-[#1a1a2e] rounded-xl p-6 border border-[#2a2a3e] space-y-4">
        <h2 className="font-semibold text-[#00d4ff]">🤖 Bot Settings</h2>
        {fields.map(f => (
          <div key={f.key} className="flex items-center justify-between gap-4">
            <label className="text-sm text-gray-400 flex-1">{f.label}</label>
            <input
              type={f.type}
              min={f.min}
              max={f.max}
              value={settings[f.key]}
              onChange={e => handleChange(f.key, e.target.value)}
              className="bg-[#0d0d1a] border border-[#2a2a3e] rounded px-3 py-1.5 text-sm text-white w-32"
            />
          </div>
        ))}
      </div>
    </div>
  )
}
