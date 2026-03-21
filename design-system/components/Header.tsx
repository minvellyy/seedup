import React from 'react';
import '../../styles/tokens.css';
import '../../styles/globals.css';
import './Header.css';
import { useLocation } from 'react-router-dom';

export default function Header({ currentPath }) {
  const getHeaderText = () => {
    if (currentPath.startsWith('/survey/invest-type')) {
      return (
        <nav className="ds-nav">
          <a href="/">홈</a>
          <a href="/portfolio">포트폴리오</a>
          <a href="/investment">개별종목</a>
          <a href="/chatbot">Chatbot</a>
          <a href="/support">고객센터</a>
          <a href="/mypage">마이페이지</a>
        </nav>
      );
    }
    return (
      <nav className="ds-nav">
        <a href="/about">서비스 소개</a>
        <a href="/support">고객센터</a>
        <a href="/login">로그인</a>
        <a href="/signup">회원가입</a>
      </nav>
    );
  };

  return (
    <header className="ds-header">
      <div className="ds-inner">
        <a href="/" className="ds-logo">SeedUp</a>
        {getHeaderText()}
      </div>
    </header>
  );
}
