import { useState } from 'react'
import axios from 'axios'

export default function CreativeDashboard({ visible, apiBase }) {
  if (!visible) return null

  // ─── IMAGE GENERATION ───
  const [imagePrompt, setImagePrompt] = useState('')
  const [generatedImage, setGeneratedImage] = useState(null)
  const [imageLoading, setImageLoading] = useState(false)

  // ─── CONTENT WRITING ───
  const [writeTopic, setWriteTopic] = useState('')
  const [writeFormat, setWriteFormat] = useState('linkedin_post')
  const [writeResult, setWriteResult] = useState(null)
  const [writeLoading, setWriteLoading] = useState(false)

  const handleGenerateImage = async () => {
    if (!imagePrompt.trim()) return
    setImageLoading(true)
    setGeneratedImage(null)
    try {
      const res = await axios.post(`${apiBase}/creative/images`, {
        prompt: imagePrompt
      })
      if (res.data.status === 'success') {
        setGeneratedImage(res.data)
      } else {
        alert(res.data.message || 'Failed to generate image')
      }
    } catch (err) {
      alert('Error calling image generator')
    } finally {
      setImageLoading(false)
    }
  }

  const handleGenerateContent = async () => {
    if (!writeTopic.trim()) return
    setWriteLoading(true)
    setWriteResult(null)
    try {
      const res = await axios.post(`${apiBase}/creative/writing`, {
        topic: writeTopic,
        format: writeFormat,
        export_type: 'md'
      })
      if (res.data.status === 'success') {
        setWriteResult(res.data)
      } else {
        alert(res.data.message || 'Failed to generate writing')
      }
    } catch (err) {
      alert('Error calling writing generator')
    } finally {
      setWriteLoading(false)
    }
  }

  return (
    <div className="sys-dashboard" style={{ padding: '24px' }}>
      
      {/* ─── IMAGE GENERATOR ─── */}
      <div className="sys-section" style={{ marginBottom: '24px' }}>
        <p className="sys-section-title">🎨 AI Image Generator (Imagen 4)</p>
        <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
          <input
            className="input-box"
            style={{ flex: 1, padding: '10px' }}
            placeholder="Describe the image you want to generate..."
            value={imagePrompt}
            onChange={e => setImagePrompt(e.target.value)}
          />
          <button className="new-chat-btn" onClick={handleGenerateImage} disabled={imageLoading}>
            {imageLoading ? '⏳ Generating...' : 'Generate Image'}
          </button>
        </div>

        {generatedImage && (
          <div style={{ background: '#0f172a', padding: '16px', borderRadius: '8px', textAlign: 'center' }}>
            <p style={{ margin: '0 0 12px 0', fontSize: '13px', color: '#10b981' }}>✓ Generated successfully using {generatedImage.provider}</p>
            <img
              src={`${apiBase}${generatedImage.url}`}
              alt={generatedImage.prompt}
              style={{ maxWidth: '100%', maxHeight: '400px', borderRadius: '6px', border: '1px solid #1e293b' }}
            />
            <p style={{ margin: '8px 0 0 0', fontSize: '12px', color: '#64748b' }}>Saved locally to: {generatedImage.url}</p>
          </div>
        )}
      </div>

      {/* ─── CONTENT WRITER ─── */}
      <div className="sys-section">
        <p className="sys-section-title">📝 Creative Writing &amp; Drafts</p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '16px' }}>
          <select
            className="input-box"
            style={{ padding: '10px', background: '#1e293b' }}
            value={writeFormat}
            onChange={e => setWriteFormat(e.target.value)}
          >
            <option value="linkedin_post">LinkedIn Post</option>
            <option value="blog">Blog Post</option>
            <option value="email">Professional Email</option>
            <option value="essay">Essay</option>
          </select>
          <textarea
            className="input-box"
            style={{ padding: '10px', height: '80px' }}
            placeholder="What should ARIS write about? Provide details..."
            value={writeTopic}
            onChange={e => setWriteTopic(e.target.value)}
          />
          <button className="new-chat-btn" style={{ alignSelf: 'flex-start' }} onClick={handleGenerateContent} disabled={writeLoading}>
            {writeLoading ? '⏳ Writing...' : 'Write Content'}
          </button>
        </div>

        {writeResult && (
          <div style={{ background: '#0f172a', padding: '16px', borderRadius: '8px' }}>
            <p style={{ margin: '0 0 8px 0', fontSize: '13px', color: '#10b981' }}>✓ Content exported to: {writeResult.file_path}</p>
            <div style={{ background: '#1e293b', padding: '12px', borderRadius: '6px', fontSize: '13px', lineHeight: '1.6', whiteSpace: 'pre-line', maxHeight: '300px', overflowY: 'auto' }}>
              {writeResult.content}
            </div>
          </div>
        )}
      </div>

    </div>
  )
}
