import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' }
})

export const tradingApi = {
  health: () => api.get('/api/health'),
  predict: (payload) => api.post('/api/predict', payload),
  logTrade: (payload) => api.post('/api/log-trade', payload),
  getStats: () => api.get('/api/stats'),
  getTrades: (params) => api.get('/api/trades', { params }),
  getSignals: (limit = 50) => api.get(`/api/signals?limit=${limit}`),
  getIndicators: () => api.get('/api/indicators'),
  getModelPerformance: () => api.get('/api/model-performance'),
  retrain: () => api.post('/api/retrain'),
  backtest: (payload) => api.post('/api/backtest', payload),
}

export default api
