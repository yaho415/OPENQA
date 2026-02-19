import React, { useState } from 'react';
import './App.css';

interface Recommendation {
  id: number;
  projectName: string;
  grade: string;
  department: string;
  industry: string;
  businessOverview: string;
  score: number;
  matchedKeywords: string[];
}

interface ApiResponse {
  success: boolean;
  prompt: string;
  llm?: string;
  keywords: string[];
  recommendations: Recommendation[];
  total: number;
}

type LLMOption = 'qwen' | 'gpt-4' | 'claude' | 'gemini';

function App() {
  const [prompt, setPrompt] = useState('');
  const [selectedLLM, setSelectedLLM] = useState<LLMOption>('qwen');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ApiResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) {
      setError('프롬프트를 입력해주세요.');
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await fetch('/api/recommend', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          prompt: prompt.trim(),
          maxResults: 3,
          llm: selectedLLM,
        }),
      });

      if (!response.ok) {
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
          try {
            const errorData = await response.json();
            throw new Error(errorData.error || `서버 오류 (${response.status})`);
          } catch {
            throw new Error(`서버 오류 (${response.status}): ${response.statusText}`);
          }
        } else {
          throw new Error(`서버 오류 (${response.status}): ${response.statusText}`);
        }
      }

      const contentType = response.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
        throw new Error('서버가 JSON 형식의 응답을 반환하지 않았습니다.');
      }

      const text = await response.text();
      if (!text || text.trim().length === 0) {
        throw new Error('서버가 빈 응답을 반환했습니다. 백엔드 서버가 실행 중인지 확인해주세요.');
      }

      let data: ApiResponse;
      try {
        data = JSON.parse(text);
      } catch {
        throw new Error(`JSON 파싱 오류: ${text.substring(0, 100)}`);
      }

      setResult(data);
    } catch (err) {
      const errorMessage = err instanceof Error 
        ? err.message 
        : '알 수 없는 오류가 발생했습니다.';
      setError(errorMessage);
      console.error('API 요청 오류:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <header className="header">
        <h1>오늘은 어떤 프로젝트를 추천받고 싶으세요?</h1>
        <p className="header-subtitle">프로젝트 정보를 입력하시면 OpenQA+에 축적된 유사 프로젝트 리스트를 추천해드립니다.</p>
      </header>

      <div className="main-content">
        <div className="llm-selector">
          <button 
            className={`llm-tab ${selectedLLM === 'qwen' ? 'active' : ''}`}
            onClick={() => setSelectedLLM('qwen')}
            disabled={loading}
          >
            <span className="tab-icon">✨</span>
            <span>Qwen</span>
          </button>
          <button 
            className={`llm-tab ${selectedLLM === 'gpt-4' ? 'active' : ''}`}
            onClick={() => setSelectedLLM('gpt-4')}
            disabled={loading}
          >
            <span className="tab-icon"></span>
            <span>GPT</span>
          </button>
          <button 
            className={`llm-tab ${selectedLLM === 'claude' ? 'active' : ''}`}
            onClick={() => setSelectedLLM('claude')}
            disabled={loading}
          >
            <span className="tab-icon"></span>
            <span>Claude</span>
          </button>
        </div>

        <form onSubmit={handleSubmit} className="search-form">
          <div className="search-container">
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="프로젝트 정보를 입력하시면 OpenQA+에 축적된 유사 프로젝트 리스트를 추천해드립니다."
              rows={2}
              className="prompt-input"
              disabled={loading}
            />
            <div className="search-actions">
              <button type="submit" className="search-submit-btn" disabled={loading}>
                {loading ? (
                  <span className="loading-spinner">⏳</span>
                ) : (
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                    <path d="M7 4l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                )}
              </button>
            </div>
          </div>
        </form>

        {error && (
          <div className="error-message">
            ❌ {error}
          </div>
        )}

        {result && (
          <div className="results">
            <div className="recommendations-table-container">
              <table className="recommendations-table">
                <thead>
                  <tr>
                    <th>No</th>
                    <th>프로젝트명</th>
                    <th>프로젝트 개요</th>
                    <th>유사도</th>
                  </tr>
                </thead>
                <tbody>
                  {result.recommendations.slice(0, 3).map((rec, idx) => (
                    <tr key={rec.id}>
                      <td className="project-no-cell">{idx + 1}</td>
                      <td className="project-name-cell">{rec.projectName}</td>
                      <td className="project-overview-cell">
                        {(() => {
                          const overview = rec.businessOverview.replace(/^프로젝트 배경 및 요약:\s*/, '');
                          return overview.length > 50 ? `${overview.substring(0, 50)}...` : overview;
                        })()}
                      </td>
                      <td className="project-score-cell">{rec.score.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
