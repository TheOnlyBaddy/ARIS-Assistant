import React, { useState, useEffect } from "react";
import axios from "axios";

export default function FinetuneDashboard({ visible, apiBase }) {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [retraining, setRetraining] = useState(false);
  const [dryRun, setDryRun] = useState(false);
  const [force, setForce] = useState(true); // default to true so user can trigger easily
  const [testPrompt, setTestPrompt] = useState("");
  const [testResponse, setTestResponse] = useState("");
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    if (visible) {
      fetchStatus();
      const interval = setInterval(fetchStatus, 15000); // refresh status every 15s
      return () => clearInterval(interval);
    }
  }, [visible]);

  const fetchStatus = async () => {
    try {
      setLoading(true);
      const res = await axios.get(`${apiBase}/finetune/status`);
      setStatus(res.data);
    } catch (err) {
      console.error("Failed to fetch finetuning status:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleRetrain = async () => {
    try {
      setRetraining(true);
      await axios.post(`${apiBase}/finetune/retrain`, null, {
        params: { force, dry_run: dryRun }
      });
      alert("Retraining pipeline queued successfully in the background!");
      // Poll status immediately
      setTimeout(fetchStatus, 3000);
    } catch (err) {
      alert("Failed to start retraining: " + (err.response?.data?.detail || err.message));
    } finally {
      setRetraining(false);
    }
  };

  const handleRollback = async (modelType) => {
    if (!window.confirm(`Are you sure you want to rollback the ${modelType} model to its previous version?`)) {
      return;
    }
    try {
      setLoading(true);
      const res = await axios.post(`${apiBase}/finetune/rollback`, null, {
        params: { model_type: modelType }
      });
      alert(res.data.message);
      fetchStatus();
    } catch (err) {
      alert("Rollback failed: " + (err.response?.data?.detail || err.message));
    } finally {
      setLoading(false);
    }
  };

  const handleTest = async () => {
    if (!testPrompt.trim()) return;
    try {
      setTesting(true);
      setTestResponse("");
      const res = await axios.post(`${apiBase}/chat`, {
        message: testPrompt,
        session_id: "finetune_test_session"
      });
      setTestResponse(res.data.response);
    } catch (err) {
      setTestResponse("Error: " + (err.response?.data?.detail || err.message));
    } finally {
      setTesting(false);
    }
  };

  if (!visible) return null;

  return (
    <div style={styles.container}>
      <style>{animations}</style>
      
      <div style={styles.header}>
        <h2 style={styles.title}>🎯 Local Weight Fine-Tuning Hub</h2>
        <p style={styles.subtitle}>
          Fine-tune ARIS models on SQLite logs and user feedback to match your communication preferences.
        </p>
      </div>

      {/* Main Status Cards */}
      <div style={styles.grid}>
        <div style={styles.card}>
          <div style={styles.cardHeader}>
            <span style={styles.icon}>📊</span>
            <h3 style={styles.cardTitle}>Pipeline Status</h3>
          </div>
          {status ? (
            <div style={styles.stats}>
              <div style={styles.statItem}>
                <span style={styles.statLabel}>Last Trained:</span>
                <span style={styles.statVal}>
                  {status.last_trained !== "1970-01-01T00:00:00Z" 
                    ? new Date(status.last_trained).toLocaleString() 
                    : "Never trained"}
                </span>
              </div>
              <div style={styles.statItem}>
                <span style={styles.statLabel}>Total Trained Examples:</span>
                <span style={styles.statVal}>{status.examples_at_last_train}</span>
              </div>
              <div style={styles.statItem}>
                <span style={styles.statLabel}>New Examples (since last run):</span>
                <span style={{ ...styles.statVal, color: status.new_examples_collected >= 50 ? "#10b981" : "#f59e0b" }}>
                  {status.new_examples_collected} / 50
                </span>
              </div>
            </div>
          ) : (
            <div style={styles.loadingText}>Loading metadata...</div>
          )}
        </div>

        {/* Retraining Form Controls */}
        <div style={styles.card}>
          <div style={styles.cardHeader}>
            <span style={styles.icon}>⚙️</span>
            <h3 style={styles.cardTitle}>Training Trigger</h3>
          </div>
          <div style={styles.form}>
            <label style={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={force}
                onChange={(e) => setForce(e.target.checked)}
                style={styles.checkbox}
              />
              Force Retrain (bypass 50-example minimum)
            </label>
            <label style={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={dryRun}
                onChange={(e) => setDryRun(e.target.checked)}
                style={styles.checkbox}
              />
              Pipeline Dry-Run (use tiny 0.5B base models for verification)
            </label>
            
            <button
              onClick={handleRetrain}
              disabled={retraining || (status && status.new_examples_collected < 50 && !force)}
              style={{
                ...styles.btn,
                opacity: retraining ? 0.7 : 1,
                cursor: retraining ? "not-allowed" : "pointer",
                background: "linear-gradient(135deg, #6366f1 0%, #a855f7 100%)"
              }}
            >
              {retraining ? "Queuing training..." : "🚀 Trigger Retraining Cycle"}
            </button>
          </div>
        </div>
      </div>

      {/* Model Versions Grid */}
      <h3 style={styles.sectionTitle}>🛠️ Model Registry & Rollback Controls</h3>
      <div style={styles.grid}>
        {status && Object.entries(status.model_versions).map(([key, val]) => {
          const rollbacks = status.rollback_versions[key] || [];
          const ollamaName = key === "llama3.2" ? "aris-llama" : (key === "mistral" ? "aris-mistral" : "aris-gemma");
          return (
            <div key={key} style={styles.modelCard}>
              <div style={styles.modelHeader}>
                <h4 style={styles.modelName}>{key.toUpperCase()} Routing</h4>
                <span style={styles.versionBadge}>{val}</span>
              </div>
              <p style={styles.modelMeta}>Active Ollama Alias: <strong style={styles.glowText}>{ollamaName}</strong></p>
              
              <div style={styles.rollbackSection}>
                <h5 style={styles.rollbackTitle}>Available Rollbacks:</h5>
                {rollbacks.length > 0 ? (
                  <div style={styles.rollbackList}>
                    {rollbacks.map((v, i) => (
                      <div key={i} style={styles.rollbackItem}>
                        <span>{v}</span>
                        <button
                          onClick={() => handleRollback(key)}
                          style={styles.miniBtn}
                        >
                          Revert
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <span style={styles.noRollback}>No rollback snapshots found.</span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Diagnostic & Alignment Playground */}
      <h3 style={styles.sectionTitle}>🔮 Diagnostic Alignment Playground</h3>
      <div style={styles.cardFull}>
        <div style={styles.cardHeader}>
          <span style={styles.icon}>🎭</span>
          <h3 style={styles.cardTitle}>Prompt Alignment Test</h3>
        </div>
        <p style={styles.subtitle}>
          Test prompt responses locally to verify vocabulary, style, and tone preferences.
        </p>
        
        <div style={styles.playground}>
          <textarea
            value={testPrompt}
            onChange={(e) => setTestPrompt(e.target.value)}
            placeholder="Type a test prompt (e.g. Write a quick email summary, or say hi)..."
            style={styles.textarea}
          />
          <div style={styles.playgroundActions}>
            <button
              onClick={handleTest}
              disabled={testing}
              style={{
                ...styles.btn,
                flex: 1,
                background: "linear-gradient(135deg, #10b981 0%, #059669 100%)"
              }}
            >
              {testing ? "Waiting for local inference..." : "⚡ Execute Local Test Run"}
            </button>
          </div>
          
          {testResponse && (
            <div style={styles.responseBox}>
              <h4 style={styles.responseTitle}>Inference Output:</h4>
              <pre style={styles.responseContent}>{testResponse}</pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const styles = {
  container: {
    padding: "20px",
    fontFamily: "'Inter', sans-serif",
    color: "#fff",
    background: "rgba(10, 10, 15, 0.6)",
    borderRadius: "16px",
    border: "1px solid rgba(255, 255, 255, 0.1)",
    backdropFilter: "blur(20px)",
    animation: "fadeIn 0.5s ease-out"
  },
  header: {
    marginBottom: "24px"
  },
  title: {
    margin: 0,
    fontSize: "24px",
    fontWeight: "700",
    letterSpacing: "-0.5px",
    background: "linear-gradient(135deg, #818cf8 0%, #c084fc 100%)",
    WebkitBackgroundClip: "text",
    WebkitTextFillColor: "transparent"
  },
  subtitle: {
    margin: "8px 0 0 0",
    color: "rgba(255, 255, 255, 0.6)",
    fontSize: "14px"
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
    gap: "20px",
    marginBottom: "24px"
  },
  card: {
    background: "rgba(255, 255, 255, 0.03)",
    border: "1px solid rgba(255, 255, 255, 0.05)",
    borderRadius: "12px",
    padding: "20px",
    display: "flex",
    flexDirection: "column"
  },
  cardFull: {
    background: "rgba(255, 255, 255, 0.03)",
    border: "1px solid rgba(255, 255, 255, 0.05)",
    borderRadius: "12px",
    padding: "20px",
    marginBottom: "24px"
  },
  cardHeader: {
    display: "flex",
    alignItems: "center",
    marginBottom: "16px",
    gap: "10px"
  },
  icon: {
    fontSize: "20px"
  },
  cardTitle: {
    margin: 0,
    fontSize: "16px",
    fontWeight: "600",
    color: "#e2e8f0"
  },
  stats: {
    display: "flex",
    flexDirection: "column",
    gap: "12px"
  },
  statItem: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    borderBottom: "1px solid rgba(255, 255, 255, 0.03)",
    paddingBottom: "8px"
  },
  statLabel: {
    color: "rgba(255, 255, 255, 0.5)",
    fontSize: "13px"
  },
  statVal: {
    fontWeight: "600",
    fontSize: "13px",
    color: "#fff"
  },
  form: {
    display: "flex",
    flexDirection: "column",
    gap: "14px",
    flex: 1,
    justifyContent: "center"
  },
  checkboxLabel: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    fontSize: "13px",
    color: "rgba(255, 255, 255, 0.8)",
    cursor: "pointer"
  },
  checkbox: {
    cursor: "pointer"
  },
  btn: {
    border: "none",
    borderRadius: "8px",
    padding: "12px",
    color: "#fff",
    fontWeight: "600",
    fontSize: "14px",
    transition: "transform 0.2s, filter 0.2s"
  },
  sectionTitle: {
    margin: "0 0 16px 0",
    fontSize: "16px",
    fontWeight: "600",
    color: "#fff"
  },
  modelCard: {
    background: "rgba(255, 255, 255, 0.02)",
    border: "1px solid rgba(255, 255, 255, 0.04)",
    borderRadius: "12px",
    padding: "16px"
  },
  modelHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "12px"
  },
  modelName: {
    margin: 0,
    fontSize: "14px",
    fontWeight: "600",
    color: "#a5b4fc"
  },
  versionBadge: {
    background: "rgba(99, 102, 241, 0.15)",
    border: "1px solid rgba(99, 102, 241, 0.3)",
    color: "#c7d2fe",
    borderRadius: "20px",
    padding: "2px 8px",
    fontSize: "11px",
    fontWeight: "600"
  },
  modelMeta: {
    margin: "0 0 16px 0",
    fontSize: "12px",
    color: "rgba(255, 255, 255, 0.6)"
  },
  glowText: {
    color: "#a855f7",
    textShadow: "0 0 8px rgba(168, 85, 247, 0.5)"
  },
  rollbackSection: {
    borderTop: "1px solid rgba(255, 255, 255, 0.05)",
    paddingTop: "12px"
  },
  rollbackTitle: {
    margin: "0 0 8px 0",
    fontSize: "12px",
    fontWeight: "600",
    color: "rgba(255, 255, 255, 0.4)"
  },
  rollbackList: {
    display: "flex",
    flexDirection: "column",
    gap: "6px"
  },
  rollbackItem: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    background: "rgba(255, 255, 255, 0.02)",
    padding: "6px 10px",
    borderRadius: "6px",
    fontSize: "12px"
  },
  miniBtn: {
    border: "1px solid rgba(239, 68, 68, 0.3)",
    background: "rgba(239, 68, 68, 0.05)",
    color: "#fca5a5",
    padding: "2px 8px",
    borderRadius: "4px",
    cursor: "pointer",
    fontSize: "11px",
    fontWeight: "600"
  },
  noRollback: {
    fontSize: "12px",
    color: "rgba(255, 255, 255, 0.3)"
  },
  playground: {
    display: "flex",
    flexDirection: "column",
    gap: "12px"
  },
  textarea: {
    background: "rgba(0, 0, 0, 0.2)",
    border: "1px solid rgba(255, 255, 255, 0.05)",
    borderRadius: "8px",
    color: "#fff",
    padding: "12px",
    fontSize: "13px",
    minHeight: "80px",
    outline: "none",
    resize: "vertical"
  },
  playgroundActions: {
    display: "flex",
    gap: "10px"
  },
  responseBox: {
    background: "rgba(0, 0, 0, 0.25)",
    border: "1px solid rgba(255, 255, 255, 0.05)",
    borderRadius: "8px",
    padding: "14px"
  },
  responseTitle: {
    margin: "0 0 8px 0",
    fontSize: "13px",
    fontWeight: "600",
    color: "#34d399"
  },
  responseContent: {
    margin: 0,
    fontFamily: "monospace",
    whiteSpace: "pre-wrap",
    wordBreak: "break-all",
    fontSize: "12px",
    color: "#e2e8f0"
  },
  loadingText: {
    color: "rgba(255, 255, 255, 0.4)",
    fontSize: "13px"
  }
};

const animations = `
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
  }
`;
