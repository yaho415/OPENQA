import React, { useState, useRef, useEffect } from 'react';
import './App.css';

// ──────────────────────────────────────────────────────────
// 타입 정의
// ──────────────────────────────────────────────────────────
interface Recommendation {
  projectCode: string;
  projectName: string;
  gradeCode: string;
  salesDeptCode: string;
  contractAccount: string;
  industryDetail: string;
  businessType: string;
  summary: string;
  methodologyValue: string;
  score: number;
  matchedKeywords: string[];
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  recommendations?: Recommendation[] | null;
  timing?: number;
  attachedFileName?: string;
}

interface AttachedFile {
  file: File;
  uploadedPath?: string;
}

function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [attachedFile, setAttachedFile] = useState<AttachedFile | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 메시지 목록 하단으로 자동 스크롤
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // textarea 자동 높이 조절
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 120)}px`;
    }
  }, [input]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    
    // 입력이 비어있고 파일도 첨부되지 않았으면 리턴
    if ((!trimmed && !attachedFile) || loading) return;

    // 파일이 첨부되어 있으면 파일 먼저 업로드
    let filePath: string | null = null;
    if (attachedFile && !attachedFile.uploadedPath) {
      // 파일이 아직 업로드되지 않은 경우 업로드
      filePath = await uploadFile(attachedFile.file);
      if (filePath) {
        setAttachedFile({ ...attachedFile, uploadedPath: filePath });
      } else {
        // 파일 업로드 실패 시 전송 중단
        return;
      }
    } else if (attachedFile?.uploadedPath) {
      filePath = attachedFile.uploadedPath;
    }

    // 사용자 메시지 (입력이 없으면 빈 문자열)
    const userMessageContent = trimmed || (attachedFile ? "사용자가 첨부한 프로젝트 현황 파일을 반영해줘" : "");
    
    const userMessage: ChatMessage = { 
      role: 'user', 
      content: userMessageContent,
      attachedFileName: attachedFile ? attachedFile.file.name : undefined,
    };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    // 파일 첨부 상태 즉시 초기화 (메시지에 이미 파일명이 저장됨)
    setAttachedFile(null);
    setLoading(true);

    try {
      // 대화 히스토리 구성 (recommendations 제외)
      const history = messages.map(m => ({
        role: m.role,
        content: m.content,
      }));

      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMessageContent,
          history,
          attached_file_path: filePath, // 파일 경로 전달
        }),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => null);
        throw new Error(errData?.detail || `서버 오류 (${response.status})`);
      }

      const data = await response.json();

      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: data.message,
        recommendations: data.recommendations || null,
        timing: data.timing,
      };

      setMessages(prev => [...prev, assistantMessage]);
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '알 수 없는 오류가 발생했습니다.';
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: `오류가 발생했습니다: ${errorMsg}` },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleNewChat = () => {
    setMessages([]);
    setInput('');
    textareaRef.current?.focus();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleFileSelect = () => {
    fileInputRef.current?.click();
  };

  const uploadFile = async (file: File): Promise<string | null> => {
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);

      console.log('[UPLOAD] 파일 업로드 시작:', file.name, file.size, 'bytes');

      const response = await fetch('/api/upload-file', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => null);
        const errorMsg = errData?.detail || `서버 오류 (${response.status})`;
        console.error('[UPLOAD] 파일 업로드 실패:', errorMsg);
        throw new Error(errorMsg);
      }

      const data = await response.json();
      console.log('[UPLOAD] 파일 업로드 성공:', data);
      
      if (!data.file_path) {
        console.error('[UPLOAD] 파일 경로가 반환되지 않음:', data);
        throw new Error('파일 경로를 받지 못했습니다.');
      }
      
      return data.file_path;
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '알 수 없는 오류가 발생했습니다.';
      console.error('[UPLOAD] 파일 업로드 오류:', err);
      setMessages(prev => [
        ...prev,
        { 
          role: 'assistant', 
          content: `❌ 파일 업로드 오류: ${errorMsg}` 
        },
      ]);
      return null;
    } finally {
      setUploading(false);
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // 파일 형식 검증
    if (!file.name.match(/\.(xlsx|xls)$/i)) {
      setMessages(prev => [
        ...prev,
        { 
          role: 'assistant', 
          content: '오류: .xlsx 또는 .xls 파일만 업로드할 수 있습니다.' 
        },
      ]);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
      return;
    }

    // 파일 첨부 상태에 저장 (아직 업로드하지 않음)
    setAttachedFile({ file, uploadedPath: undefined });

    // 파일 input 초기화
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleRemoveFile = () => {
    setAttachedFile(null);
  };

  return (
    <div className="copilot-app">
      {/* 사이드바 / 헤더 */}
      <header className="copilot-header">
        <div className="header-left">
          <div className="logo">
            <img src="/logo.svg" alt="OpenQA+" className="logo-icon-img" />
            <span className="logo-text">OpenQA+</span>
          </div>
        </div>
        <div className="header-right">
          <button className="new-chat-btn" onClick={handleNewChat} title="새 대화" disabled={uploading || loading}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"></line>
              <line x1="5" y1="12" x2="19" y2="12"></line>
            </svg>
            <span>새 대화</span>
          </button>
        </div>
      </header>

      {/* 채팅 영역 */}
      <main className="chat-area">
        {messages.length === 0 ? (
          <div className="welcome-screen">
            <img src="/logo.svg" alt="OpenQA+" className="welcome-logo-img" />
            <h1 className="welcome-title">오늘은 어떤 프로젝트를 추천받고 싶으세요?</h1>
            <p className="welcome-subtitle">
              프로젝트 정보를 입력하시면 OpenQA+에 축적된 유사 프로젝트 리스트를 추천해드립니다.<br />
            </p>
            <div className="suggestion-chips">
              <button
                className="suggestion-chip"
                onClick={() => setInput('공공기관 인사급여 시스템 구축 프로젝트를 찾아줘')}
              >
                공공기관 인사급여 시스템 구축 프로젝트를 찾아줘
              </button>
              <button
                className="suggestion-chip"
                onClick={() => setInput('금융권 차세대 시스템 구축 사례가 있을까?')}
              >
                금융권 차세대 시스템 구축 사례가 있을까?
              </button>
              <button
                className="suggestion-chip"
                onClick={() => setInput('반도체 생산 품질 관리 시스템 고도화 관련 유사 프로젝트 정보를 찾아줘')}
              >
                반도체 생산 품질 관리 시스템 고도화 관련 유사 프로젝트 정보를 찾아줘
              </button>
              <button
                className="suggestion-chip"
                onClick={() => {
                  handleFileSelect();
                  setInput('첨부한 파일로 프로젝트 현황을 업데이트 해줘');
                }}
              >
                첨부한 파일로 프로젝트 현황을 업데이트 해줘
              </button>
            </div>
          </div>
        ) : (
          <div className="messages-container">
            {messages.map((msg, idx) => (
              <div key={idx} className={`message-row ${msg.role}`}>
                {msg.role === 'assistant' && (
                  <div className="avatar assistant-avatar"><img src="/logo.svg" alt="" className="avatar-logo" /></div>
                )}
                <div className={`message-bubble-group ${msg.role}`}>
                  {/* 첨부 파일 카드 (사용자 메시지에만) */}
                  {msg.role === 'user' && msg.attachedFileName && (
                    <div className="message-file-card">
                      <div className="message-file-icon">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                          <rect width="24" height="24" rx="6" fill="#22c55e"/>
                          <path d="M7 8h4v4H7V8zm0 5h4v3H7v-3zm5-5h5v3h-5V8zm0 4h5v4h-5v-4z" fill="white" opacity="0.9"/>
                        </svg>
                      </div>
                      <div className="message-file-info">
                        <div className="message-file-name">{msg.attachedFileName}</div>
                        <div className="message-file-type">스프레드시트</div>
                      </div>
                    </div>
                  )}
                  
                  <div className={`message-bubble ${msg.role}`}>
                    <div className="message-content">
                      {msg.content.split('\n').map((line, i) => (
                        <React.Fragment key={i}>
                          {line}
                          {i < msg.content.split('\n').length - 1 && <br />}
                        </React.Fragment>
                      ))}
                    </div>

                  {/* 추천 결과 테이블 */}
                  {msg.recommendations && msg.recommendations.length > 0 && (
                    <div className="recommendation-table-wrap">
                      <table className="recommendation-table">
                        <thead>
                          <tr>
                            <th>No</th>
                            <th>프로젝트명</th>
                            <th>사업개요</th>
                            <th>유사도</th>
                          </tr>
                        </thead>
                        <tbody>
                          {msg.recommendations.map((rec, rIdx) => (
                            <tr key={rec.projectCode}>
                              <td className="cell-no">{rIdx + 1}</td>
                              <td className="cell-name" title={rec.projectName}>
                                {rec.projectName.length > 20 ? `${rec.projectName.substring(0, 20)}...` : rec.projectName}
                              </td>
                              <td className="cell-overview">
                                {(rec.summary || '').replace(/^프로젝트 배경 및 요약:\s*/, '')}
                              </td>
                              <td className="cell-score">{rec.score.toFixed(2)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {msg.role === 'assistant' && msg.timing && (
                    <div className="message-timing">{msg.timing}초</div>
                  )}
                </div>
                </div>
                {msg.role === 'user' && (
                  <div className="avatar user-avatar">U</div>
                )}
              </div>
            ))}

            {/* 로딩 인디케이터 */}
            {loading && (
              <div className="message-row assistant">
                <div className="avatar assistant-avatar"><img src="/logo.svg" alt="" className="avatar-logo" /></div>
                <div className="message-bubble assistant loading-bubble">
                  <div className="typing-indicator">
                    <span></span><span></span><span></span>
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        )}
      </main>

      {/* 입력 영역 */}
      <footer className="input-area">
        <form onSubmit={handleSubmit} className="input-form">
          <div className="input-container">
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx,.xls"
              style={{ display: 'none' }}
              onChange={handleFileChange}
              disabled={uploading || loading}
            />
            
            {/* 파일 첨부 버튼 (+ 아이콘) */}
            <button
              type="button"
              className="attach-file-btn"
              onClick={handleFileSelect}
              disabled={uploading || loading}
              title="Excel 파일 첨부 (.xlsx)"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19"></line>
                <line x1="5" y1="12" x2="19" y2="12"></line>
              </svg>
            </button>

            {/* 입력 필드 내부 컨텐츠 */}
            <div className="input-content">
              {/* 첨부된 파일 표시 (입력 필드 내부) */}
              {attachedFile && (
                <div className="attached-file-card">
                  <div className="file-icon-wrapper">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                      <polyline points="14 2 14 8 20 8"></polyline>
                      <line x1="16" y1="13" x2="8" y2="13"></line>
                      <line x1="16" y1="17" x2="8" y2="17"></line>
                    </svg>
                  </div>
                  <div className="file-info">
                    <div className="file-name">{attachedFile.file.name}</div>
                    <div className="file-type">스프레드시트</div>
                  </div>
                  <button
                    type="button"
                    className="file-remove-btn-large"
                    onClick={handleRemoveFile}
                    title="파일 제거"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="18" y1="6" x2="6" y2="18"></line>
                      <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                  </button>
                </div>
              )}
              
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={attachedFile ? "" : "무엇이든 물어보세요"}
                rows={1}
                className="chat-input"
                disabled={loading}
              />
            </div>

            {/* 전송 버튼 */}
            <button
              type="submit"
              className="send-btn"
              disabled={loading || (!input.trim() && !attachedFile)}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
              </svg>
            </button>
          </div>
          
          {/* 하단 힌트 텍스트 */}
          <div className="input-footer">
            <span className="input-hint-text">무엇이든 물어보세요</span>
          </div>
        </form>
      </footer>
    </div>
  );
}

export default App;
