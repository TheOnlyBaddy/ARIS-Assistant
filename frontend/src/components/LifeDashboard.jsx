import { useState, useEffect } from 'react'
import axios from 'axios'

export default function LifeDashboard({ visible, apiBase }) {
  if (!visible) return null

  // ─── HABITS STATE ───
  const [habits, setHabits] = useState([])
  const [streaks, setStreaks] = useState([])
  const [newHabit, setNewHabit] = useState({ name: '', target: '' })

  // ─── HEALTH STATE ───
  const [healthSummary, setHealthSummary] = useState(null)
  const [healthLog, setHealthLog] = useState({
    sleep_hours: '', mood: 'good', energy: '7', water_litres: '', exercise_mins: '', notes: ''
  })
  const [healthTrends, setHealthTrends] = useState('')

  // ─── FINANCE STATE ───
  const [financeSummary, setFinanceSummary] = useState(null)
  const [budgets, setBudgets] = useState([])
  const [savings, setSavings] = useState([])
  const [newTxn, setNewTxn] = useState({ amount: '', category: 'food', description: '', type: 'expense' })
  const [newBudget, setNewBudget] = useState({ category: 'food', limit: '' })

  // ─── MEALS STATE ───
  const [mealsToday, setMealsToday] = useState(null)
  const [mealPlan, setMealPlan] = useState('')
  const [mealSuggestions, setMealSuggestions] = useState('')
  const [newMeal, setNewMeal] = useState({ name: '', type: 'lunch', calories: '' })

  useEffect(() => {
    fetchHabits()
    fetchHealthSummary()
    fetchFinanceData()
    fetchMealsData()
  }, [])

  // ─── HABITS FUNCTIONS ───
  const fetchHabits = async () => {
    try {
      const res = await axios.get(`${apiBase}/life/habits/list`)
      setHabits(res.data.habits || [])
      const sRes = await axios.get(`${apiBase}/life/habits/streaks`)
      setStreaks(sRes.data.streaks || [])
    } catch (err) {
      console.error(err)
    }
  }

  const handleCreateHabit = async () => {
    if (!newHabit.name.trim()) return
    try {
      await axios.post(`${apiBase}/life/habits/create`, {
        name: newHabit.name,
        target: newHabit.target
      })
      setNewHabit({ name: '', target: '' })
      fetchHabits()
    } catch (err) {
      alert('Failed to create habit')
    }
  }

  const handleLogHabit = async (habitId) => {
    try {
      await axios.post(`${apiBase}/life/habits/log`, { habit_id: habitId })
      fetchHabits()
      alert('Habit completed for today!')
    } catch (err) {
      alert('Failed to log habit')
    }
  }

  // ─── HEALTH FUNCTIONS ───
  const fetchHealthSummary = async () => {
    try {
      const res = await axios.get(`${apiBase}/life/health/summary`)
      setHealthSummary(res.data)
    } catch (err) {
      console.error(err)
    }
  }

  const handleLogHealth = async () => {
    try {
      await axios.post(`${apiBase}/life/health/log`, {
        sleep_hours: healthLog.sleep_hours ? parseFloat(healthLog.sleep_hours) : null,
        mood: healthLog.mood,
        energy: parseInt(healthLog.energy),
        water_litres: healthLog.water_litres ? parseFloat(healthLog.water_litres) : null,
        exercise_mins: healthLog.exercise_mins ? parseInt(healthLog.exercise_mins) : null,
        notes: healthLog.notes
      })
      setHealthLog({ sleep_hours: '', mood: 'good', energy: '7', water_litres: '', exercise_mins: '', notes: '' })
      fetchHealthSummary()
      alert('Health metrics logged!')
    } catch (err) {
      alert('Failed to log health metrics')
    }
  }

  const handleAnalyzeTrends = async () => {
    try {
      setHealthTrends('ARIS is analyzing your health logs...')
      const res = await axios.get(`${apiBase}/life/health/trends?days=7`)
      setHealthTrends(res.data.analysis)
    } catch (err) {
      alert('Failed to fetch AI health trends')
    }
  }

  // ─── FINANCE FUNCTIONS ───
  const fetchFinanceData = async () => {
    try {
      const sRes = await axios.get(`${apiBase}/life/finance/summary`)
      setFinanceSummary(sRes.data)
      const bRes = await axios.get(`${apiBase}/life/finance/budgets`)
      setBudgets(bRes.data.budgets || [])
      const gRes = await axios.get(`${apiBase}/life/finance/savings`)
      setSavings(gRes.data.goals || [])
    } catch (err) {
      console.error(err)
    }
  }

  const handleLogTxn = async () => {
    if (!newTxn.amount) return
    try {
      await axios.post(`${apiBase}/life/finance/log`, {
        amount: parseFloat(newTxn.amount),
        category: newTxn.category,
        description: newTxn.description,
        type: newTxn.type
      })
      setNewTxn({ amount: '', category: 'food', description: '', type: 'expense' })
      fetchFinanceData()
      alert('Transaction logged successfully!')
    } catch (err) {
      alert('Failed to log transaction')
    }
  }

  const handleSetBudget = async () => {
    if (!newBudget.limit) return
    try {
      await axios.post(`${apiBase}/life/finance/budget`, {
        category: newBudget.category,
        monthly_limit: parseFloat(newBudget.limit)
      })
      setNewBudget(prev => ({ ...prev, limit: '' }))
      fetchFinanceData()
      alert('Budget updated!')
    } catch (err) {
      alert('Failed to update budget')
    }
  }

  // ─── MEALS FUNCTIONS ───
  const fetchMealsData = async () => {
    try {
      const res = await axios.get(`${apiBase}/life/meals/today`)
      setMealsToday(res.data)
    } catch (err) {
      console.error(err)
    }
  }

  const handleLogMeal = async () => {
    if (!newMeal.name.trim()) return
    try {
      await axios.post(`${apiBase}/life/meals/log`, {
        name: newMeal.name,
        type: newMeal.type,
        calories: newMeal.calories ? parseInt(newMeal.calories) : null
      })
      setNewMeal({ name: '', type: 'lunch', calories: '' })
      fetchMealsData()
      alert('Meal logged!')
    } catch (err) {
      alert('Failed to log meal')
    }
  }

  const handleSuggestMeals = async () => {
    try {
      setMealSuggestions('Fetching ideas from ARIS...')
      const res = await axios.post(`${apiBase}/life/meals/suggest`, {
        meal_type: 'dinner',
        preferences: 'something light'
      })
      setMealSuggestions(res.data.suggestions)
    } catch (err) {
      alert('Failed to suggest meals')
    }
  }

  const handlePlanWeekly = async () => {
    try {
      setMealPlan('ARIS is cooking up a weekly meal plan...')
      const res = await axios.post(`${apiBase}/life/meals/plan`)
      setMealPlan(res.data.plan)
    } catch (err) {
      alert('Failed to generate weekly plan')
    }
  }

  return (
    <div className="sys-dashboard" style={{ padding: '24px' }}>
      
      {/* ─── HABITS & GOALS ─── */}
      <div className="sys-section" style={{ marginBottom: '24px' }}>
        <p className="sys-section-title">⏱️ Habits &amp; Daily Streaks</p>
        
        {/* Create Habit */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
          <input
            className="input-box"
            style={{ flex: 2, padding: '10px' }}
            placeholder="New Habit Name (e.g. Exercise 30m)"
            value={newHabit.name}
            onChange={e => setNewHabit(prev => ({ ...prev, name: e.target.value }))}
          />
          <input
            className="input-box"
            style={{ flex: 1, padding: '10px' }}
            placeholder="Target e.g. Daily"
            value={newHabit.target}
            onChange={e => setNewHabit(prev => ({ ...prev, target: e.target.value }))}
          />
          <button className="new-chat-btn" onClick={handleCreateHabit}>Add Habit</button>
        </div>

        {/* List and Log habits */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {habits.length === 0 ? (
            <p style={{ color: '#475569', fontSize: '13px', margin: 0 }}>No habits tracked. Add one above!</p>
          ) : (
            habits.map((h) => {
              const streakInfo = streaks.find(s => s.id === h.id)
              const streakCount = streakInfo ? streakInfo.streak : 0
              const completedToday = streakInfo ? streakInfo.completed_today : false

              return (
                <div key={h.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#0f172a', padding: '10px 14px', borderRadius: '8px', fontSize: '13px' }}>
                  <div>
                    <strong>{h.name}</strong> <span style={{ color: '#64748b' }}>({h.target || h.frequency})</span>
                    <span style={{ marginLeft: '12px', color: '#f59e0b' }}>🔥 {streakCount} day streak</span>
                  </div>
                  <button
                    className="new-chat-btn"
                    style={{ background: completedToday ? '#10b981' : '#38bdf8', padding: '6px 12px', border: 'none' }}
                    onClick={() => handleLogHabit(h.id)}
                    disabled={completedToday}
                  >
                    {completedToday ? 'Done ✓' : 'Complete'}
                  </button>
                </div>
              )
            })
          )}
        </div>
      </div>

      {/* ─── HEALTH LOGGING ─── */}
      <div className="sys-section" style={{ marginBottom: '24px' }}>
        <p className="sys-section-title">🏥 Health &amp; Wellbeing Log</p>
        
        {/* Weekly Stats Averages */}
        {healthSummary && healthSummary.week_averages && (
          <div style={{ display: 'flex', gap: '16px', background: '#0f172a', padding: '12px', borderRadius: '8px', marginBottom: '16px', fontSize: '12px', color: '#94a3b8' }}>
            <div>💤 Sleep: <strong>{healthSummary.week_averages.sleep_hours || 0}h</strong></div>
            <div>⚡ Energy: <strong>{healthSummary.week_averages.energy || 0}/10</strong></div>
            <div>💧 Water: <strong>{healthSummary.week_averages.water_litres || 0}L</strong></div>
            <div>🏋️ Exercise: <strong>{healthSummary.week_averages.exercise_mins || 0}m</strong></div>
          </div>
        )}

        {/* Log Entry Form */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '12px' }}>
          <input
            className="input-box"
            style={{ padding: '8px' }}
            placeholder="Sleep Hours (e.g. 7.5)"
            value={healthLog.sleep_hours}
            onChange={e => setHealthLog(prev => ({ ...prev, sleep_hours: e.target.value }))}
          />
          <input
            className="input-box"
            style={{ padding: '8px' }}
            placeholder="Water consumed in Litres (e.g. 2.5)"
            value={healthLog.water_litres}
            onChange={e => setHealthLog(prev => ({ ...prev, water_litres: e.target.value }))}
          />
          <input
            className="input-box"
            style={{ padding: '8px' }}
            placeholder="Exercise duration in Mins"
            value={healthLog.exercise_mins}
            onChange={e => setHealthLog(prev => ({ ...prev, exercise_mins: e.target.value }))}
          />
          <select
            className="input-box"
            style={{ padding: '8px', background: '#1e293b' }}
            value={healthLog.mood}
            onChange={e => setHealthLog(prev => ({ ...prev, mood: e.target.value }))}
          >
            <option value="great">Great</option>
            <option value="good">Good</option>
            <option value="tired">Tired</option>
            <option value="stressed">Stressed</option>
          </select>
        </div>
        <input
          className="input-box"
          style={{ width: '100%', padding: '8px', marginBottom: '12px' }}
          placeholder="Optional notes..."
          value={healthLog.notes}
          onChange={e => setHealthLog(prev => ({ ...prev, notes: e.target.value }))}
        />
        
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="new-chat-btn" onClick={handleLogHealth}>Log Metrics</button>
          <button className="new-chat-btn" onClick={handleAnalyzeTrends}>Analyze Trends</button>
        </div>

        {healthTrends && (
          <div style={{ background: '#1e293b', padding: '12px', borderRadius: '8px', marginTop: '16px', fontSize: '13px', lineHeight: '1.5', whiteSpace: 'pre-line' }}>
            {healthTrends}
          </div>
        )}
      </div>

      {/* ─── FINANCE AWARENESS ─── */}
      <div className="sys-section" style={{ marginBottom: '24px' }}>
        <p className="sys-section-title">🪙 Finance &amp; Budgets (₹ INR)</p>
        
        {financeSummary && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px', background: '#0f172a', padding: '12px', borderRadius: '8px', marginBottom: '16px', fontSize: '12px', textAlign: 'center' }}>
            <div style={{ borderRight: '1px solid #1e293b' }}>
              <span style={{ color: '#10b981' }}>Income</span>
              <p style={{ margin: '4px 0 0 0', fontWeight: 'bold', fontSize: '14px' }}>₹{financeSummary.total_income}</p>
            </div>
            <div style={{ borderRight: '1px solid #1e293b' }}>
              <span style={{ color: '#ef4444' }}>Expense</span>
              <p style={{ margin: '4px 0 0 0', fontWeight: 'bold', fontSize: '14px' }}>₹{financeSummary.total_expense}</p>
            </div>
            <div>
              <span style={{ color: '#38bdf8' }}>Net</span>
              <p style={{ margin: '4px 0 0 0', fontWeight: 'bold', fontSize: '14px' }}>₹{financeSummary.net}</p>
            </div>
          </div>
        )}

        {/* Log Transaction */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
          <input
            className="input-box"
            style={{ flex: 1, padding: '8px' }}
            placeholder="Amount ₹"
            value={newTxn.amount}
            onChange={e => setNewTxn(prev => ({ ...prev, amount: e.target.value }))}
          />
          <input
            className="input-box"
            style={{ flex: 2, padding: '8px' }}
            placeholder="Description (e.g. Coffee)"
            value={newTxn.description}
            onChange={e => setNewTxn(prev => ({ ...prev, description: e.target.value }))}
          />
          <select
            className="input-box"
            style={{ flex: 1.5, padding: '8px', background: '#1e293b' }}
            value={newTxn.category}
            onChange={e => setNewTxn(prev => ({ ...prev, category: e.target.value }))}
          >
            <option value="food">Food</option>
            <option value="transport">Transport</option>
            <option value="entertainment">Entertainment</option>
            <option value="shopping">Shopping</option>
            <option value="bills">Bills</option>
            <option value="salary">Salary</option>
            <option value="other">Other</option>
          </select>
          <button className="new-chat-btn" onClick={handleLogTxn}>Log</button>
        </div>

        {/* Budgets list */}
        <div style={{ marginBottom: '16px' }}>
          <p style={{ margin: '0 0 8px 0', fontSize: '14px', color: '#94a3b8' }}>Budgets:</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {budgets.map((b, idx) => (
              <div key={idx} style={{ background: '#0f172a', padding: '8px 12px', borderRadius: '6px', fontSize: '12px', display: 'flex', justifyContent: 'space-between' }}>
                <span>{b.category.toUpperCase()}: ₹{b.spent} / ₹{b.monthly_limit} limit</span>
                <span style={{ color: b.over_budget ? '#ef4444' : '#10b981' }}>{b.over_budget ? 'Over Budget!' : `₹${b.remaining} left`}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Set Budget */}
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <span style={{ fontSize: '12px', color: '#64748b' }}>Set limit:</span>
          <select
            className="input-box"
            style={{ padding: '6px', background: '#1e293b' }}
            value={newBudget.category}
            onChange={e => setNewBudget(prev => ({ ...prev, category: e.target.value }))}
          >
            <option value="food">Food</option>
            <option value="transport">Transport</option>
            <option value="entertainment">Entertainment</option>
            <option value="shopping">Shopping</option>
            <option value="bills">Bills</option>
          </select>
          <input
            className="input-box"
            style={{ width: '100px', padding: '6px' }}
            placeholder="Limit ₹"
            value={newBudget.limit}
            onChange={e => setNewBudget(prev => ({ ...prev, limit: e.target.value }))}
          />
          <button className="new-chat-btn" style={{ padding: '6px 12px' }} onClick={handleSetBudget}>Set</button>
        </div>
      </div>

      {/* ─── MEAL PLANNING ─── */}
      <div className="sys-section">
        <p className="sys-section-title">🍛 Meal Planner</p>
        
        {/* Today's Calories */}
        {mealsToday && (
          <div style={{ background: '#0f172a', padding: '12px', borderRadius: '8px', marginBottom: '16px', fontSize: '13px' }}>
            <strong>Today's Meals:</strong> {mealsToday.meal_count} logged · <strong>{mealsToday.total_calories} kcal</strong> consumed.
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '8px' }}>
              {mealsToday.meals.map((m, idx) => (
                <span key={idx} style={{ background: '#1e293b', padding: '4px 8px', borderRadius: '4px', fontSize: '11px' }}>
                  {m.meal_type.toUpperCase()}: {m.name} ({m.calories} kcal)
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Log Meal Form */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
          <input
            className="input-box"
            style={{ flex: 2, padding: '8px' }}
            placeholder="Meal Name (e.g. Idli with sambar)"
            value={newMeal.name}
            onChange={e => setNewMeal(prev => ({ ...prev, name: e.target.value }))}
          />
          <input
            className="input-box"
            style={{ flex: 1, padding: '8px' }}
            placeholder="Calories"
            value={newMeal.calories}
            onChange={e => setNewMeal(prev => ({ ...prev, calories: e.target.value }))}
          />
          <select
            className="input-box"
            style={{ flex: 1.2, padding: '8px', background: '#1e293b' }}
            value={newMeal.type}
            onChange={e => setNewMeal(prev => ({ ...prev, type: e.target.value }))}
          >
            <option value="breakfast">Breakfast</option>
            <option value="lunch">Lunch</option>
            <option value="dinner">Dinner</option>
            <option value="snack">Snack</option>
          </select>
          <button className="new-chat-btn" onClick={handleLogMeal}>Log Meal</button>
        </div>

        {/* Plan Actions */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
          <button className="new-chat-btn" onClick={handleSuggestMeals}>Suggest Dinner</button>
          <button className="new-chat-btn" onClick={handlePlanWeekly}>Weekly Plan</button>
        </div>

        {mealSuggestions && (
          <div style={{ background: '#1e293b', padding: '12px', borderRadius: '8px', marginBottom: '12px', fontSize: '13px', whiteSpace: 'pre-line' }}>
            {mealSuggestions}
          </div>
        )}

        {mealPlan && (
          <div style={{ background: '#1e293b', padding: '12px', borderRadius: '8px', fontSize: '13px', whiteSpace: 'pre-line' }}>
            {mealPlan}
          </div>
        )}
      </div>

    </div>
  )
}
