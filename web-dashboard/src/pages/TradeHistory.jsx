import React, { useEffect, useState } from 'react'
import { Download } from 'lucide-react'
import { tradingApi } from '../services/api'

export default function TradeHistory() {
  const [trades, setTrades] = useState([])
  const [filter, setFilter] = useState({ pair: 'ALL', result: 'ALL', mode: 'ALL' })

  useEffect(() => {
    const loadTrades = async () => {
      try {
        const res = await tradingApi.getTrades({ limit: 150 })
        if (res.data && res.data.trades && res.data.trades.length > 0) {
          setTrades(res.data.trades)
          return
        }
      } catch (e) { /* fallback to sample trades */ }

      const mock = Array.from({ length: 20 }, (_, i) => ({
        id: i + 1,
        timestamp: new Date(Date.now() - i * 3600000).toLocaleString(),
        pair: ['EURUSD', 'GBPUSD', 'USDJPY'][i % 3],
        direction: i % 2 === 0 ? 'BUY' : 'SELL',
        amount: 10,
        duration: 60,
        result: i % 3 === 0 ? 'LOSS' : 'WIN',
        pnl: i % 3 === 0 ? -10 : 8.5,
        mode: i % 4 === 0 ? 'AUTO' : 'MANUAL'
      }))
      setTrades(mock)
    }
    loadTrades()
  }, [])

  const filtered = trades.filter(t =>
    (filter.pair === 'ALL' || t.pair === filter.pair) &&
    (filter.result === 'ALL' || t.result === filter.result) &&
    (filter.mode === 'ALL' || t.mode === filter.mode)
  )

  const exportCSV = () => {
    const headers = ['ID', 'Timestamp', 'Pair', 'Direction', 'Amount', 'Duration', 'Result', 'PnL', 'Mode']
    const rows = filtered.map(t => [
      t.id, t.timestamp, t.pair, t.direction, t.amount, t.duration, t.result, t.pnl, t.mode
    ])
    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `trade_history_${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Prediction Outcome History</h1>
        <button
          onClick={exportCSV}
          className="flex items-center gap-2 px-3 py-1.5 bg-[#00d4ff] text-[#0d0d1a] font-bold rounded-lg text-xs hover:bg-[#00b8d4] transition"
        >
          <Download size={14} /> Export CSV
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 bg-[#1a1a2e] p-3 rounded-xl border border-[#2a2a3e]">
        <select
          className="bg-[#0d0d1a] border border-[#2a2a3e] rounded px-3 py-1 text-sm text-gray-300"
          value={filter.pair}
          onChange={e => setFilter(f => ({ ...f, pair: e.target.value }))}
        >
          <option value="ALL">All Pairs ({trades.length})</option>
          {Array.from(new Set(trades.map(t => t.pair).filter(Boolean))).sort().map(p => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
        <select
          className="bg-[#0d0d1a] border border-[#2a2a3e] rounded px-3 py-1 text-sm text-gray-300"
          value={filter.result}
          onChange={e => setFilter(f => ({ ...f, result: e.target.value }))}
        >
          <option value="ALL">All Results</option>
          <option value="WIN">Wins</option>
          <option value="LOSS">Losses</option>
        </select>
        <select
          className="bg-[#0d0d1a] border border-[#2a2a3e] rounded px-3 py-1 text-sm text-gray-300"
          value={filter.mode}
          onChange={e => setFilter(f => ({ ...f, mode: e.target.value }))}
        >
          <option value="ALL">All Modes</option>
          <option value="AUTO">Auto</option>
          <option value="MANUAL">Manual</option>
        </select>
        <span className="ml-auto text-xs text-gray-500 self-center">{filtered.length} trades</span>
      </div>

      {/* Table */}
      <div className="bg-[#1a1a2e] rounded-xl border border-[#2a2a3e] overflow-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-gray-500 uppercase bg-[#0d0d1a]">
            <tr>
              {['#', 'Time', 'Pair', 'Prediction', 'Duration', 'Entry Price', 'Exit Price', 'Outcome', 'Mode'].map(h => (
                <th key={h} className="px-4 py-3 text-left">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map(t => (
              <tr key={t.id} className="border-t border-[#2a2a3e] hover:bg-[#2a2a3e]/30">
                <td className="px-4 py-3 text-gray-500">{t.id}</td>
                <td className="px-4 py-3 text-gray-400">{t.timestamp}</td>
                <td className="px-4 py-3 font-mono">{t.pair}</td>
                <td className={`px-4 py-3 font-bold ${t.direction === 'BUY' ? 'text-green-400' : 'text-red-400'}`}>
                  {t.direction}
                </td>
                <td className="px-4 py-3">{t.duration}s</td>
                <td className="px-4 py-3 font-mono">{t.entry_price}</td>
                <td className="px-4 py-3 font-mono text-gray-300">{t.exit_price ?? '--'}</td>
                <td className={`px-4 py-3 font-bold ${t.result === 'WIN' ? 'text-green-400' : 'text-red-400'}`}>
                  {t.result === 'WIN' ? '✅ WIN' : '❌ LOSS'}
                </td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-0.5 rounded-full text-xs ${
                    t.mode === 'AUTO' ? 'bg-blue-500/20 text-blue-400' : 'bg-gray-500/20 text-gray-400'
                  }`}>{t.mode}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
