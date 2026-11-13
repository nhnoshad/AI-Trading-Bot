import React, { useState } from 'react'
import { tradingApi } from '../services/api'

export default function Backtesting() {
  const [form, setForm] = useState({ pair: 'EURUSD', timeframe: '1m', period: '30d', strategy: 'default' })
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  const runBacktest = async () => {
    setLoading(true)
    try {
      const res = await tradingApi.backtest(form)
      setResult(res.data)
    } catch (e) {
      alert('Backtest failed: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <h1 className="text-xl font-bold text-white">Backtesting</h1>
      <div className="bg-[#1a1a2e] rounded-xl p-6 border border-[#2a2a3e] space-y-4">
        <h2 className="font-semibold text-[#00d4ff]">⚙️ Backtest Configuration</h2>
        <div className="grid grid-cols-2 gap-4">
          {[{label:'Pair', key:'pair', opts:['EURUSD','GBPUSD','USDJPY','AUDUSD']},
            {label:'Timeframe', key:'timeframe', opts:['1m','5m','15m','1h']},
            {label:'Period', key:'period', opts:['7d','30d','90d','180d']},
            {label:'Strategy', key:'strategy', opts:['default','conservative','aggressive']}
          ].map(f => (
            <div key={f.key}>
              <label className="text-xs text-gray-500 block mb-1">{f.label}</label>
              <select
                className="w-full bg-[#0d0d1a] border border-[#2a2a3e] rounded px-3 py-2 text-sm text-white"
                value={form[f.key]}
                onChange={e => setForm(v => ({ ...v, [f.key]: e.target.value }))}
              >
                {f.opts.map(o => <option key={o}>{o}</option>)}
              </select>
            </div>
          ))}
        </div>
        <button
          onClick={runBacktest}
          disabled={loading}
          className="w-full py-2 bg-[#00d4ff] text-[#0d0d1a] font-bold rounded-lg hover:bg-[#00b8d4] disabled:opacity-50 transition-colors"
        >
          {loading ? 'Running...' : '▶ Run Backtest'}
        </button>
      </div>

      {result && (
        <div className="bg-[#1a1a2e] rounded-xl p-6 border border-[#2a2a3e] space-y-4">
          <h2 className="font-semibold text-[#00d4ff]">📊 Results</h2>
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: 'Win Rate', value: result.win_rate + '%', color: 'text-green-400' },
              { label: 'Predictions Evaluated', value: result.total_trades },
              { label: 'Profit Factor', value: result.profit_factor },
              { label: 'Win/Loss Ratio', value: ((result.win_rate || 50) / Math.max(1, 100 - (result.win_rate || 50))).toFixed(2) + 'x', color: 'text-[#00d4ff]' },
              { label: 'Consistency Ratio', value: result.sharpe_ratio },
              { label: 'Net Win Score', value: `${Math.round((result.total_trades || 0) * (result.win_rate || 0) / 100) - ((result.total_trades || 0) - Math.round((result.total_trades || 0) * (result.win_rate || 0) / 100))} Wins`, color: 'text-green-400' }
            ].map(m => (
              <div key={m.label} className="bg-[#0d0d1a] rounded-lg p-3 text-center">
                <div className={`text-xl font-bold ${m.color || 'text-white'}`}>{m.value}</div>
                <div className="text-xs text-gray-500 mt-1">{m.label}</div>
              </div>
            ))}
          </div>
          {result.note && <p className="text-xs text-gray-500">{result.note}</p>}
        </div>
      )}
    </div>
  )
}
