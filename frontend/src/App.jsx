import React from 'react'
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import Header from './components/Header'
import MainPage from './pages/MainPage'
import TermsPage from './pages/TermsPage'
import LoginPage from './pages/LoginPage'
import SignupPage from './pages/SignupPage'
import SurveyPage from './pages/SurveyPage'
import DashboardPage from './pages/DashboardPage'
import './App.css'

function App() {
  return (
    <Router>
      <AuthProvider>
        <div className="app">
          <Header />
          <Routes>
            <Route path="/" element={<MainPage />} />
            <Route path="/terms" element={<TermsPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<SignupPage />} />
            <Route path="/survey" element={<SurveyPage />} />
            <Route path="/dashboard" element={<DashboardPage />} />
          </Routes>
        </div>
      </AuthProvider>
    </Router>
  )
}

export default App
