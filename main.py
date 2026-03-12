import sqlite3
import pandas as pd
from datetime import date, timedelta
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional

app = FastAPI()
templates = Jinja2Templates(directory="templates")
DB_FILENAME = 'financial_management.db'

def get_connection():
    return sqlite3.connect(DB_FILENAME, check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS initial_balance (
            id INTEGER PRIMARY KEY,
            balance REAL NOT NULL
        )
    ''')
    conn.commit()
    
    c.execute('SELECT COUNT(*) FROM initial_balance')
    if c.fetchone()[0] == 0:
        c.execute('INSERT INTO initial_balance (balance) VALUES (0.0)')
        conn.commit()
    conn.close()

init_db()

class Transaction(BaseModel):
    date: str
    description: str
    amount: float
    category: str

@app.get("/", response_class=HTMLResponse)
async def serve_home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/perfil", response_class=HTMLResponse)
async def serve_perfil(request: Request):
    return templates.TemplateResponse("perfil.html", {"request": request})

@app.get("/extrato", response_class=HTMLResponse)
async def serve_extrato(request: Request):
    return templates.TemplateResponse("extrato.html", {"request": request})

@app.get("/carteiras", response_class=HTMLResponse)
async def serve_carteiras(request: Request):
    return templates.TemplateResponse("carteiras.html", {"request": request})

@app.get("/relatorios", response_class=HTMLResponse)
async def serve_relatorios(request: Request):
    return templates.TemplateResponse("relatorios.html", {"request": request})

@app.get("/api/transactions")
def get_all_transactions():
    conn = get_connection()
    try:
        df = pd.read_sql_query('SELECT * FROM transactions ORDER BY date DESC, id DESC', conn)
    finally:
        conn.close()
    
    if df.empty:
        return {"transactions": []}
    
    return {"transactions": df.to_dict('records')}

@app.get("/api/data")
def get_dashboard_data(year: Optional[int] = None, month: Optional[int] = None):
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT balance FROM initial_balance ORDER BY id LIMIT 1')
    res = c.fetchone()
    initial_balance = res[0] if res else 0.0
    
    df = pd.read_sql_query('SELECT * FROM transactions ORDER BY date DESC', conn)
    conn.close()
    
    if df.empty:
        return {
            "summary": {"entradas": 0, "saidas": 0, "diarios": 0, "investido": 0, "saldo": initial_balance},
            "history": [],
            "projection": [],
            "thermometer": []
        }
        
    df['date_obj'] = pd.to_datetime(df['date']).dt.date
    today = date.today()
    
    # 1. Summary Calculation (Totals to date)
    entradas = df[df['category'] == "Entradas (Receitas)"]['amount'].sum()
    saidas = df[df['category'] == "Saídas (Despesas fixas programadas)"]['amount'].sum()
    diarios = df[df['category'] == "Gastos Diários (Despesas variáveis)"]['amount'].sum()
    investimentos = df[df['category'] == "Investimento"]['amount'].sum()
    
    # Investimentos também reduzem o saldo disponível no bolso (caixa livre), mas entram pro total investido.
    saldo_atual = initial_balance + entradas - saidas - diarios - investimentos
    
    # 2. History
    history = df.head(10).to_dict('records')
    for h in history:
        h.pop('date_obj', None)
        
    # Conselho de saúde financeira
    advice = "Seu fluxo de caixa está saudável. Continue assim!"
    if saldo_atual < 0:
        advice = "Atenção: Seu saldo disponível está negativo. Revise seus próximos gastos!"
    elif entradas > 0 and (saidas + diarios) > entradas * 0.9:
        advice = "Cuidado: Seus gastos estão muito próximos do total de suas receitas."
    if (saidas + diarios) == 0 and entradas == 0:
        advice = "Adicione mais lançamentos para receber conselhos mais precisos."

    target_year = year if year else today.year
    target_month = month if month else today.month

    meses_pt = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    mes_atual_nome = f"{meses_pt[target_month]} de {target_year}"

    # 3. Thermometer (current month calendar)
    import calendar
    month_days = calendar.monthrange(target_year, target_month)[1]
    start_date = date(target_year, target_month, 1)
    
    thermometer_data = []
    running_balance = initial_balance
    past_tx = df[df['date_obj'] < start_date]
    for _, row in past_tx.iterrows():
        if row['category'] == "Entradas (Receitas)":
            running_balance += row['amount']
        else:
            running_balance -= row['amount']
            
    weekdays_pt = ["SEG", "TER", "QUA", "QUI", "SEX", "SAB", "DOM"]
            
    for i in range(month_days):
        d = start_date + timedelta(days=i)
        day_tx = df[df['date_obj'] == d]
        ent_day = day_tx[day_tx['category'] == "Entradas (Receitas)"]['amount'].sum()
        out_day = day_tx[day_tx['category'] != "Entradas (Receitas)"]['amount'].sum()
        
        flow = ent_day - out_day
        running_balance = running_balance + flow
        
        thermometer_data.append({
            "dateStr": d.strftime("%Y-%m-%d"),
            "dayName": weekdays_pt[d.weekday()],
            "dayNum": d.strftime("%d"),
            "flow": float(flow),
            "balance": float(running_balance),
            "isToday": d == today
        })

    # 4. Projection Algorithm (next 90 days / 3 months)
    projection_data = []
    end_of_period = today + timedelta(days=90)
    delta = end_of_period - today
    
    proj_balance = saldo_atual
    if delta.days >= 0:
        dates_to_project = [today + timedelta(days=i) for i in range(delta.days + 1)]
        for d in dates_to_project:
            if d == today:
                # today is already calculated in saldo_atual
                pass
            else:
                day_tx = df[df['date_obj'] == d]
                ent_day = day_tx[day_tx['category'] == "Entradas (Receitas)"]['amount'].sum()
                out_day = day_tx[day_tx['category'] != "Entradas (Receitas)"]['amount'].sum()
                
                proj_balance = proj_balance + ent_day - out_day
            
            label = d.strftime("%d/%m")
            projection_data.append({
                "label": label,
                "saldo": float(proj_balance)
            })

    return {
        "summary": {
            "entradas": float(entradas),
            "saidas": float(saidas),
            "diarios": float(diarios),
            "investido": float(investimentos),
            "saldo": float(saldo_atual)
        },
        "history": history,
        "thermometer": thermometer_data,
        "projection": projection_data,
        "monthName": mes_atual_nome,
        "advice": advice
    }

@app.post("/api/transaction")
def add_transaction(t: Transaction):
    conn = get_connection()
    c = conn.cursor()
    c.execute('INSERT INTO transactions (date, description, amount, category) VALUES (?, ?, ?, ?)',
              (t.date, t.description, t.amount, t.category))
    conn.commit()
    conn.close()
    return {"status": "success"}
