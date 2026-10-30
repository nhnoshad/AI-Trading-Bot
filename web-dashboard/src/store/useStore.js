import { create } from 'zustand'

export const useStore = create((set, get) => ({
  // Connection
  connected: false,
  serverUrl: 'http://localhost:8000',

  // Current Signal
  currentSignal: null,

  // Stats
  stats: {
    total_trades: 0, wins: 0, losses: 0,
    win_rate: 0, total_pnl: 0, best_pair: null
  },

  // Trade History
  trades: [],

  // Settings
  settings: {
    tradeAmount: 10, tradeDuration: 60,
    minConfidence: 65, maxTradesPerHour: 10,
    maxConsecutiveLosses: 3, dailyLossLimit: 50,
    dailyProfitTarget: 100, cooldownSeconds: 30
  },

  // Actions
  setConnected: (v) => set({ connected: v }),
  setCurrentSignal: (s) => set({ currentSignal: s }),
  setStats: (s) => set({ stats: s }),
  setTrades: (t) => set({ trades: t }),
  updateSettings: (s) => set((state) => ({ settings: { ...state.settings, ...s } })),
  addTrade: (t) => set((state) => ({ trades: [t, ...state.trades].slice(0, 200) })),
}))
