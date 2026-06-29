import { useState, useEffect } from 'react'
import axios from 'axios'

export default function IntelligenceDashboard({ visible, apiBase }) {
  if (!visible) return null

  const [docs, setDocs] = useState([])
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [newNote, setNewNote] = useState({ title: '', content: '' })

  const [tutorTopic, setTutorTopic] = useState('Python decorators')
  const [lessonText, setLessonText] = useState('')
  const [flashcards, setFlashcards] = useState([])
  const [tutorProgress, setTutorProgress] = useState([])
  
  const [quizQuestions, setQuizQuestions] = useState([])
  const [quizId, setQuizId] = useState(null)
  const [quizAnswers, setQuizAnswers] = useState({})
  const [quizResult, setQuizResult] = useState(null)

  useEffect(() => {
    fetchDocs()
    fetchTutorProgress()
  }, [])

  const fetchDocs = async () => {
    try {
      const res = await axios.get(`${apiBase}/intelligence/knowledge/list`)
      setDocs(res.data.documents || [])
    } catch (err) {
      console.error(err)
    }
  }

  const fetchTutorProgress = async () => {
    try {
      const res = await axios.get(`${apiBase}/intelligence/tutor/progress`)
      setTutorProgress(res.data.progress || [])
    } catch (err) {
      console.error(err)
    }
  }

  const handleSearch = async () => {
    if (!searchQuery.trim()) return
    try {
      const res = await axios.post(`${apiBase}/intelligence/knowledge/search`, {
        query: searchQuery,
        limit: 3
      })
      setSearchResults(res.data.results || [])
    } catch (err) {
      alert('Search failed')
    }
  }

  const handleAddNote = async () => {
    if (!newNote.content.trim()) return
    try {
      await axios.post(`${apiBase}/intelligence/knowledge/add`, {
        type: 'text',
        content: newNote.content,
        title: newNote.title || 'Untitled Note'
      })
      setNewNote({ title: '', content: '' })
      fetchDocs()
      alert('Note saved to Knowledge Base!')
    } catch (err) {
      alert('Failed to save note')
    }
  }

  const handleDeleteDoc = async (source) => {
    try {
      await axios.delete(`${apiBase}/intelligence/knowledge/delete`, {
        data: { source }
      })
      fetchDocs()
      alert('Document deleted')
    } catch (err) {
      alert('Delete failed')
    }
  }

  const handleStartLesson = async () => {
    try {
      setLessonText('Loading lesson from ARIS...')
      const res = await axios.post(`${apiBase}/intelligence/tutor/learn`, {
        topic: tutorTopic,
        difficulty: 'beginner'
      })
      setLessonText(res.data.lesson)
      fetchTutorProgress()
    } catch (err) {
      alert('Failed to start lesson')
    }
  }

  const handleGetFlashcards = async () => {
    try {
      setFlashcards([])
      const res = await axios.post(`${apiBase}/intelligence/tutor/flashcards`, {
        topic: tutorTopic,
        count: 3
      })
      setFlashcards(res.data.flashcards || [])
    } catch (err) {
      alert('Failed to generate flashcards')
    }
  }

  const handleStartQuiz = async () => {
    try {
      setQuizQuestions([])
      setQuizAnswers({})
      setQuizResult(null)
      const res = await axios.post(`${apiBase}/intelligence/tutor/quiz`, {
        topic: tutorTopic,
        difficulty: 'easy',
        count: 3
      })
      setQuizQuestions(res.data.questions || [])
      setQuizId(res.data.quiz_id)
    } catch (err) {
      alert('Failed to start quiz')
    }
  }

  const handleSelectQuizOption = (qIndex, option) => {
    setQuizAnswers(prev => ({ ...prev, [qIndex]: option }))
  }

  const handleSubmitQuiz = async () => {
    const answersList = Object.keys(quizAnswers)
      .sort()
      .map(k => quizAnswers[k])

    if (answersList.length < quizQuestions.length) {
      alert('Please answer all questions before submitting.')
      return
    }

    try {
      const res = await axios.post(`${apiBase}/intelligence/tutor/quiz/submit`, {
        quiz_id: quizId,
        answers: answersList
      })
      setQuizResult(res.data)
      fetchTutorProgress()
    } catch (err) {
      alert('Failed to submit quiz')
    }
  }

  return (
    <div className="sys-dashboard" style={{ padding: '24px' }}>
      
      {/* ─── KNOWLEDGE BASE ─── */}
      <div className="sys-section" style={{ marginBottom: '24px' }}>
        <p className="sys-section-title">📦 Personal Knowledge Base</p>
        
        {/* Add Note */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '16px' }}>
          <input
            className="input-box"
            style={{ width: '100%', padding: '10px' }}
            placeholder="Note Title (e.g. My Server Setup)"
            value={newNote.title}
            onChange={e => setNewNote(prev => ({ ...prev, title: e.target.value }))}
          />
          <textarea
            className="input-box"
            style={{ width: '100%', padding: '10px', height: '80px' }}
            placeholder="Write a fact or document content for ARIS to index..."
            value={newNote.content}
            onChange={e => setNewNote(prev => ({ ...prev, content: e.target.value }))}
          />
          <button className="new-chat-btn" style={{ alignSelf: 'flex-start' }} onClick={handleAddNote}>
            Remember Note
          </button>
        </div>

        {/* Search Docs */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
          <input
            className="input-box"
            style={{ flex: 1, padding: '10px' }}
            placeholder="Search indexed notes and docs..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
          />
          <button className="new-chat-btn" onClick={handleSearch}>Search</button>
        </div>

        {searchResults.length > 0 && (
          <div style={{ background: '#1e293b', padding: '12px', borderRadius: '8px', marginBottom: '16px' }}>
            <p style={{ margin: '0 0 8px 0', fontSize: '14px', color: '#94a3b8' }}>Search Results:</p>
            {searchResults.map((r, i) => (
              <div key={i} style={{ padding: '8px', borderBottom: '1px solid #334155', fontSize: '13px' }}>
                <strong>{r.title}</strong> <span style={{ color: '#64748b' }}>({r.source})</span>
                <p style={{ margin: '4px 0 0 0', color: '#cbd5e1' }}>{r.text}</p>
              </div>
            ))}
          </div>
        )}

        {/* List Docs */}
        <p style={{ margin: '0 0 8px 0', fontSize: '14px', color: '#94a3b8' }}>Indexed Documents:</p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {docs.length === 0 ? (
            <p style={{ color: '#475569', fontSize: '13px', margin: 0 }}>No documents stored yet.</p>
          ) : (
            docs.map((doc, idx) => (
              <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#0f172a', padding: '8px 12px', borderRadius: '6px', fontSize: '13px' }}>
                <div>
                  <strong>{doc.title}</strong> <span style={{ color: '#475569' }}>({doc.type})</span>
                </div>
                <button
                  style={{ background: 'transparent', border: 'none', color: '#ef4444', cursor: 'pointer' }}
                  onClick={() => handleDeleteDoc(doc.source)}
                >
                  Delete
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* ─── PERSONAL TUTOR ─── */}
      <div className="sys-section">
        <p className="sys-section-title">🎓 Socratic Tutor &amp; Quizzes</p>
        
        {/* Topic Input */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
          <input
            className="input-box"
            style={{ flex: 1, padding: '10px' }}
            placeholder="Enter topic to study (e.g. Machine Learning)"
            value={tutorTopic}
            onChange={e => setTutorTopic(e.target.value)}
          />
          <button className="new-chat-btn" onClick={handleStartLesson}>Start Lesson</button>
          <button className="new-chat-btn" onClick={handleGetFlashcards}>Flashcards</button>
          <button className="new-chat-btn" onClick={handleStartQuiz}>Quiz Me</button>
        </div>

        {/* Lesson output */}
        {lessonText && (
          <div style={{ background: '#1e293b', padding: '16px', borderRadius: '8px', marginBottom: '16px', fontSize: '14px', lineHeight: '1.6' }}>
            <p style={{ margin: '0 0 8px 0', fontWeight: 'bold' }}>Lesson Content:</p>
            <div style={{ whiteSpace: 'pre-line', color: '#cbd5e1' }}>{lessonText}</div>
          </div>
        )}

        {/* Flashcards output */}
        {flashcards.length > 0 && (
          <div style={{ marginBottom: '16px' }}>
            <p style={{ margin: '0 0 8px 0', fontSize: '14px', color: '#94a3b8' }}>Flashcards:</p>
            <div style={{ display: 'flex', gap: '12px', overflowX: 'auto', paddingBottom: '8px' }}>
              {flashcards.map((c, idx) => (
                <div key={idx} style={{ minWidth: '220px', background: '#0f172a', border: '1px solid #1e293b', padding: '12px', borderRadius: '8px' }}>
                  <div style={{ color: '#38bdf8', fontSize: '11px', marginBottom: '4px' }}>FRONT</div>
                  <p style={{ margin: '0 0 12px 0', fontSize: '13px', fontWeight: 'bold' }}>{c.front}</p>
                  <div style={{ color: '#10b981', fontSize: '11px', marginBottom: '4px' }}>BACK</div>
                  <p style={{ margin: 0, fontSize: '13px', color: '#cbd5e1' }}>{c.back}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Quiz execution */}
        {quizQuestions.length > 0 && !quizResult && (
          <div style={{ background: '#1e293b', padding: '16px', borderRadius: '8px', marginBottom: '16px' }}>
            <p style={{ margin: '0 0 12px 0', fontWeight: 'bold' }}>📝 Quiz Mode</p>
            {quizQuestions.map((q, idx) => (
              <div key={idx} style={{ marginBottom: '16px', fontSize: '13px' }}>
                <p style={{ fontWeight: 'bold', margin: '0 0 8px 0' }}>{idx + 1}. {q.question}</p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {q.options.map(opt => (
                    <label key={opt} style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', color: quizAnswers[idx] === opt ? '#38bdf8' : '#cbd5e1' }}>
                      <input
                        type="radio"
                        name={`q-${idx}`}
                        value={opt}
                        checked={quizAnswers[idx] === opt}
                        onChange={() => handleSelectQuizOption(idx, opt)}
                      />
                      {opt}
                    </label>
                  ))}
                </div>
              </div>
            ))}
            <button className="new-chat-btn" onClick={handleSubmitQuiz}>Submit Answers</button>
          </div>
        )}

        {/* Quiz results */}
        {quizResult && (
          <div style={{ background: '#022c22', border: '1px solid #065f46', padding: '16px', borderRadius: '8px', marginBottom: '16px', fontSize: '13px' }}>
            <p style={{ margin: '0 0 8px 0', fontWeight: 'bold', color: '#34d399' }}>
              Quiz Finished! Score: {quizResult.score} / {quizResult.total} ({quizResult.percentage}%)
            </p>
            <p style={{ color: '#a7f3d0', margin: '0 0 12px 0' }}>Next level recommendation: {quizResult.suggested_next_difficulty}</p>
            {quizResult.feedback.map((f, idx) => (
              <div key={idx} style={{ padding: '6px 0', borderBottom: '1px solid #065f46' }}>
                <p style={{ margin: 0, fontWeight: 'bold' }}>Q: {f.question}</p>
                <p style={{ margin: '2px 0 0 0', color: f.is_correct ? '#34d399' : '#f87171' }}>
                  Your answer: {f.user_answer} {f.is_correct ? '✓' : '✗'}
                </p>
                {!f.is_correct && <p style={{ margin: '2px 0 0 0', color: '#34d399' }}>Correct: {f.correct_answer}</p>}
              </div>
            ))}
          </div>
        )}

        {/* Progress list */}
        <p style={{ margin: '16px 0 8px 0', fontSize: '14px', color: '#94a3b8' }}>Learning Progress:</p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {tutorProgress.length === 0 ? (
            <p style={{ color: '#475569', fontSize: '13px', margin: 0 }}>No progress logged yet.</p>
          ) : (
            tutorProgress.map((p, idx) => (
              <div key={idx} style={{ background: '#0f172a', padding: '12px', borderRadius: '8px', fontSize: '13px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                  <strong>{p.topic}</strong>
                  <span style={{ color: '#38bdf8' }}>Mastery: {p.mastery}%</span>
                </div>
                <div style={{ width: '100%', height: '6px', background: '#1e293b', borderRadius: '3px', overflow: 'hidden' }}>
                  <div style={{ width: `${p.mastery}%`, height: '100%', background: '#38bdf8' }} />
                </div>
                <div style={{ display: 'flex', gap: '16px', marginTop: '6px', color: '#64748b', fontSize: '11px' }}>
                  <span>Lessons read: {p.lessons_read}</span>
                  <span>Quizzes taken: {p.quizzes_taken}</span>
                  <span>Average score: {p.avg_score}%</span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

    </div>
  )
}
