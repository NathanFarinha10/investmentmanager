import streamlit as st
import pandas as pd
import plotly.express as px
from openbb import obb
from datetime import date, timedelta

# --- Configuração da Página ---
# Usamos o layout "wide" para preencher a tela
st.set_page_config(
    page_title="Plataforma de Análise de Investimentos",
    page_icon="📈",
    layout="wide"
)

# --- Título Principal ---
st.title("Plataforma de Análise de Investimentos 📈")
st.markdown("Desenvolvido com Python, Streamlit e OpenBB SDK")

# --- Barra Lateral (Sidebar) para Entradas do Usuário ---
st.sidebar.header("Configurações de Análise")

# Input do Ticker
ticker = st.sidebar.text_input("Digite o Ticker da Ação (ex: AAPL, MSFT, NVDA)", "AAPL").upper()

# Inputs de Data
# Definimos datas padrão (último ano)
end_date_default = date.today()
start_date_default = end_date_default - timedelta(days=365)

start_date = st.sidebar.date_input("Data de Início", start_date_default)
end_date = st.sidebar.date_input("Data de Fim", end_date_default)

# --- Funções com Cache para Carregar Dados (Otimização do Streamlit) ---

# Cachear os dados evita recarregar da API a cada interação
@st.cache_data(ttl=3600) # Cache de 1 hora
def get_stock_data(symbol, start, end):
    """Busca dados históricos de preços."""
    try:
        # Usamos o yfinance como provedor padrão e gratuito
        data = obb.equity.price.historical(
            symbol=symbol,
            start_date=str(start),
            end_date=str(end),
            provider="yfinance"
        ).to_df()
        return data
    except Exception as e:
        st.error(f"Erro ao buscar dados de preço para {symbol}: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=86400) # Cache de 1 dia
def get_company_profile(symbol):
    """Busca informações de perfil da empresa."""
    try:
        # O provedor yfinance oferece um bom resumo
        profile = obb.equity.profile.info(symbol=symbol, provider="yfinance").to_df()
        # Transpomos o DataFrame para facilitar a leitura
        return profile.transpose()
    except Exception as e:
        st.error(f"Erro ao buscar perfil para {symbol}: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600) # Cache de 1 hora
def get_company_news(symbol):
    """Busca as últimas notícias da empresa."""
    try:
        # yfinance também agrega notícias
        news = obb.news.company(symbol=symbol, provider="yfinance", limit=20).to_df()
        return news
    except Exception as e:
        st.error(f"Erro ao buscar notícias para {symbol}: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=86400) # Cache de 1 dia
def get_income_statement(symbol):
    """Busca a demonstração de resultados (anual)."""
    try:
        income = obb.equity.fundamental.income(
            symbol=symbol,
            provider="yfinance",
            period="annual"
        ).to_df()
        return income
    except Exception as e:
        st.error(f"Erro ao buscar DRE para {symbol}: {e}")
        return pd.DataFrame()

# --- Área Principal da Aplicação ---

if ticker:
    st.header(f"Analisando: {ticker}")

    try:
        # Carrega todos os dados necessários
        price_data = get_stock_data(ticker, start_date, end_date)
        profile_data = get_company_profile(ticker)
        news_data = get_company_news(ticker)
        income_data = get_income_statement(ticker)

        # Define as abas para organizar a informação
        tab1, tab2, tab3, tab4 = st.tabs(["Resumo", "Gráfico de Preços", "Fundamentos", "Notícias"])

        # --- Aba 1: Resumo ---
        with tab1:
            st.subheader("Perfil da Empresa")
            if not profile_data.empty:
                # Exibe o resumo do negócio
                st.write(profile_data.loc['longBusinessSummary'].values[0] if 'longBusinessSummary' in profile_data.index else "Resumo não disponível.")

                st.subheader("Métricas Chave")
                # Exibe métricas em colunas
                col1, col2, col3 = st.columns(3)
                col1.metric("Setor", profile_data.loc['sector'].values[0] if 'sector' in profile_data.index else "N/A")
                col2.metric("Indústria", profile_data.loc['industry'].values[0] if 'industry' in profile_data.index else "N/A")
                col3.metric("País", profile_data.loc['country'].values[0] if 'country' in profile_data.index else "N/A")

                col4, col5, col6 = st.columns(3)
                col4.metric("Market Cap", f"${profile_data.loc['marketCap'].values[0]:,}" if 'marketCap' in profile_data.index else "N/A")
                col5.metric("P/E Ratio (Fwd)", f"{profile_data.loc['forwardPE'].values[0]:.2f}" if 'forwardPE' in profile_data.index else "N/A")
                col6.metric("Dividend Yield", f"{profile_data.loc['dividendYield'].values[0] * 100:.2f}%" if 'dividendYield' in profile_data.index and profile_data.loc['dividendYield'].values[0] else "N/A")

                # Exibe o DataFrame transposto com todos os dados do perfil
                st.dataframe(profile_data, use_container_width=True)
            else:
                st.warning("Não foi possível carregar o perfil da empresa.")

        # --- Aba 2: Gráfico de Preços ---
        with tab2:
            st.subheader("Histórico de Preço (Fechamento)")
            if not price_data.empty:
                # Cria um gráfico interativo com Plotly
                fig = px.line(price_data, x=price_data.index, y='close', title=f"Preço de Fechamento de {ticker}")
                fig.update_layout(xaxis_title="Data", yaxis_title="Preço (USD)")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("Não foi possível carregar os dados de preço.")

        # --- Aba 3: Fundamentos ---
        with tab3:
            st.subheader("Demonstração de Resultados (Anual)")
            if not income_data.empty:
                # Exibe os dados fundamentais
                st.dataframe(income_data, use_container_width=True)

                st.subheader("Receita e Lucro Líquido")
                # Gráfico de barras para Receita e Lucro
                if 'total_revenue' in income_data.columns and 'net_income' in income_data.columns:
                    chart_data = income_data[['total_revenue', 'net_income']].sort_index()
                    st.bar_chart(chart_data)
                else:
                    st.info("Colunas 'total_revenue' ou 'net_income' não encontradas.")
            else:
                st.warning("Não foi possível carregar os dados fundamentalistas.")

        # --- Aba 4: Notícias ---
        with tab4:
            st.subheader("Últimas Notícias")
            if not news_data.empty:
                # Itera sobre as notícias e as exibe
                for index, row in news_data.iterrows():
                    st.markdown(f"**[{row['title']}]({row['url']})**")
                    st.write(f"*{row['publisher_name']} - {pd.to_datetime(row['published_date']).strftime('%d/%m/%Y %H:%M')}*")
                    # 'text' pode não estar disponível em todos provedores, 'summary' é mais comum
                    if 'summary' in row and row['summary']:
                         st.write(row['summary'])
                    st.divider()
            else:
                st.warning("Não foi possível carregar as notícias.")

    except Exception as e:
        st.error(f"Ocorreu um erro geral ao processar o ticker {ticker}: {e}")
        st.info("Verifique se o ticker está correto ou tente novamente mais tarde.")

else:
    st.info("Por favor, insira um ticker na barra lateral para começar a análise.")
