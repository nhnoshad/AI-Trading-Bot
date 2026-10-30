import React from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import TradeHistory from './pages/TradeHistory'
import Settings from './pages/Settings'
import Backtesting from './pages/Backtesting'
import ModelPerformance from './pages/ModelPerformance'
import Login from './pages/Login'

export default function App() {
  const location = useLocation()
  if (location.pathname === '/login') {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
      </Routes>
    )
  }

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/history" element={<TradeHistory />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/backtest" element={<Backtesting />} />
        <Route path="/model" element={<ModelPerformance />} />
      </Routes>
    </Layout>
  )
}
