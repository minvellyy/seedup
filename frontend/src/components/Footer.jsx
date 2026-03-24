import React from 'react'
import './Footer.css'

function Footer() {
  return (
    <footer className="footer">
      <div className="footer-disclaimer-row">
        <span className="footer-disclaimer">
          본 정보는 투자 판단의 참고 자료이며, 투자 결과에 대한 책임은 본인에게 있습니다.
        </span>
      </div>
      <div className="footer-inner">
        <div className="footer-left">
          <span className="footer-brand">SeedUP</span>
          <span className="footer-copy">© 2026 SeedUP Editorial. All rights reserved.</span>
        </div>
        <div className="footer-right">
          <a href="#">Privacy Policy</a>
          <a href="#">Terms of Service</a>
          <a href="#">Financial Disclaimer</a>
          <a href="#">Contact Us</a>
          <a href="#">Ad Choices</a>
        </div>
      </div>
    </footer>
  )
}

export default Footer
