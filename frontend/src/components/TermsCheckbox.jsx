import React, { useState } from 'react'
import './TermsCheckbox.css'

function TermsCheckbox({ id, type, title, content, checked, onChange }) {
  const [isExpanded, setIsExpanded] = useState(false)

  const handleRowClick = () => {
    onChange()
  }

  const handleContentClick = (e) => {
    e.stopPropagation()
  }

  return (
    <div className="terms-checkbox-wrapper">
      <div 
        className={`terms-checkbox-row ${checked ? 'checked' : ''}`}
        onClick={handleRowClick}
      >
        <div className="checkbox-container">
          <input
            type="checkbox"
            id={id}
            checked={checked}
            onChange={onChange}
            className="checkbox-input"
            onClick={(e) => e.stopPropagation()}
          />
          <label htmlFor={id} className="checkbox-label"></label>
        </div>
        
        <div className="terms-info-section">
          <div className="terms-title-row">
            <span className={`terms-type ${type}`}>[{type}]</span>
            <span className="terms-title">{title}</span>
          </div>
        </div>

        <button 
          className="expand-button"
          onClick={(e) => {
            e.stopPropagation()
            setIsExpanded(!isExpanded)
          }}
          aria-expanded={isExpanded}
        >
          {isExpanded ? '▼' : '▶'}
        </button>
      </div>

      {isExpanded && (
        <div 
          className="terms-content"
          onClick={handleContentClick}
        >
          <div className="content-text">
            {content}
          </div>
        </div>
      )}
    </div>
  )
}

export default TermsCheckbox
