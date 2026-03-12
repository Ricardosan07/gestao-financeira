import streamlit as st
import sqlite3
import pandas as pd
from datetime import date, timedelta
import os

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
    
    # Initialize initial balance if not exists
    c.execute('SELECT COUNT(*) FROM initial_balance')
    if c.fetchone()[0] == 0:
        c.execute('INSERT INTO initial_balance (balance) VALUES (0.0)')
        conn.commit()
    conn.close()

def get_initial_balance():
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT balance FROM initial_balance ORDER BY id LIMIT 1')
    result = c.fetchone()
    conn.close()
    return result[0] if result else 0.0

def update_initial_balance(new_balance):
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE initial_balance SET balance = ?', (new_balance,))
    conn.commit()
    conn.close()

def add_transaction(date_str, description, amount, category):
    conn = get_connection()
    c = conn.cursor()
    c.execute('INSERT INTO transactions (date, description, amount, category) VALUES (?, ?, ?, ?)',
              (date_str, description, amount, category))
    conn.commit()
    conn.close()

def get_all_transactions():
    conn = get_connection()
    df = pd.read_sql_query('SELECT * FROM transactions', conn)
    conn.close()
    return df

def delete_transaction(tx_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM transactions WHERE id = ?', (tx_id,))
    conn.commit()
    conn.close()

st.set_page_config(page_title="Gestão Financeira", layout="wide")
init_db()

st.title("Sistema de Gestão Financeira Pessoal")

with st.sidebar:
    st.header("Configurações Iniciais")
    current_balance = get_initial_balance()
    new_balance = st.number_input("Saldo Inicial / Atual (R$)", value=float(current_balance), step=10.0)
    if st.button("Atualizar Saldo"):
        update_initial_balance(new_balance)
        st.success("Saldo atualizado!")
        st.rerun()

    st.divider()
    
    st.header("Novo Lançamento")
    with st.form("transaction_form"):
        tx_date = st.date_input("Data do Registro")
        tx_desc = st.text_input("Descrição")
        tx_amount = st.number_input("Valor (R$)", min_value=0.01, step=10.0)
        tx_cat = st.selectbox("Categoria", ["Entradas (Receitas)", "Saídas (Despesas fixas programadas)", "Gastos Diários (Despesas variáveis)"])
        submitted = st.form_submit_button("Adicionar")
        
        if submitted:
            add_transaction(tx_date.strftime("%Y-%m-%d"), tx_desc, tx_amount, tx_cat)
            st.success("Registro adicionado com sucesso!")
            st.rerun()

df_tx = get_all_transactions()

st.header("Resumo dos Lançamentos")
if not df_tx.empty:
    st.dataframe(df_tx, use_container_width=True, hide_index=True)
    
    # Form to delete records
    st.subheader("Excluir Lançamento")
    with st.form("delete_form"):
        tx_id_to_delete = st.number_input("ID do registro a excluir", min_value=1, step=1)
        delete_submit = st.form_submit_button("Excluir")
        if delete_submit:
            delete_transaction(tx_id_to_delete)
            st.success("Registro excluído!")
            st.rerun()
else:
    st.info("Nenhum lançamento registrado ainda.")
    
st.divider()

st.header("Projeção de Fluxo de Caixa (Até o fim do ano)")

# Logic for projection
if not df_tx.empty:
    df_tx['date'] = pd.to_datetime(df_tx['date']).dt.date
    
    # Generate dates until the end of the year
    today = date.today()
    end_of_year = date(today.year, 12, 31)
    delta = end_of_year - today
    
    if delta.days >= 0:
        dates = [today + timedelta(days=i) for i in range(delta.days + 1)]
        
        projection_data = []
        running_balance = get_initial_balance()
        
        # Calculate balance up to yesterday based on initial balance + past transactions
        past_tx = df_tx[df_tx['date'] < today]
        for _, row in past_tx.iterrows():
            if row['category'] == "Entradas (Receitas)":
                running_balance += row['amount']
            else:
                running_balance -= row['amount']
                
        for d in dates:
            day_tx = df_tx[df_tx['date'] == d]
            
            entradas = day_tx[day_tx['category'] == "Entradas (Receitas)"]['amount'].sum()
            saidas = day_tx[day_tx['category'] == "Saídas (Despesas fixas programadas)"]['amount'].sum()
            gastos = day_tx[day_tx['category'] == "Gastos Diários (Despesas variáveis)"]['amount'].sum()
            
            # Cálculo Diário: Saldo Atual + Entradas - Saídas - Gastos
            running_balance = running_balance + entradas - saidas - gastos
            
            projection_data.append({
                "Data": d.strftime("%d/%m/%Y"),
                "Entradas Projetadas (R$)": entradas,
                "Saídas Projetadas (R$)": saidas,
                "Gastos Diários (R$)": gastos,
                "Saldo Projetado (R$)": running_balance
            })
            
        df_proj = pd.DataFrame(projection_data)
        
        # Apply conditional formatting
        def color_saldo(val):
            color = 'green' if val >= 0 else 'red'
            return f'color: {color}'
            
        st.dataframe(df_proj.style.applymap(color_saldo, subset=['Saldo Projetado (R$)']), use_container_width=True)
    else:
        st.info("O ano atual já terminou.")
else:
    st.info("Adicione lançamentos para visualizar a projeção.")

