import streamlit as st
import pandas as pd
import plotly.express as px
import os  # Importar os

# --- Workaround para Permissão do Streamlit Cloud ---
# O Streamlit Cloud tem um sistema de ficheiros read-only, mas /tmp é gravável.
# O OpenBB SDK (e possivelmente as suas dependências) tentam escrever ficheiros
# (config, cache, locks) no arranque.
# Vamos criar diretórios graváveis e definir variáveis de ambiente para
# redirecionar todas as operações de escrita para /tmp.

# 1. Criar diretórios graváveis
base_dir = "/tmp/streamlit_workaround"
data_dir = os.path.join(base_dir, "openbb_data")
cache_dir = os.path.join(base_dir, "cache")
config_dir = os.path.join(base_dir, "config")
mpl_dir = os.path.join(base_dir, "mpl") # Para Matplotlib, uma dependência comum

for dir_path in [data_dir, cache_dir, config_dir, mpl_dir]:
    if not os.path.exists(dir_path):
        # exist_ok=True é seguro caso o diretório já exista
        os.makedirs(dir_path, exist_ok=True)

# 2. Definir as variáveis de ambiente ANTES de importar o openbb
os.environ["OPENBB_USER_DATA_DIRECTORY"] = data_dir
os.environ["XDG_CACHE_HOME"] = cache_dir     # Padrão XDG para cache
os.environ["XDG_CONFIG_HOME"] = config_dir  # Padrão XDG para config
os.environ["MPLCONFIGDIR"] = mpl_dir      # Específico do Matplotlib
os.environ["HOME"] = base_dir               # "Catch-all" para libs que usam ~/
# --- Fim do Workaround ---

# Adicionar um try/except para depurar melhor caso falhe novamente
try:
    from openbb import obb # <-- Importação ocorre DEPOIS da correção
except Exception as e:
    # Se a importação falhar, mostra uma página de erro detalhada
    st.set_page_config(layout="centered")
    st.title("Erro na Inicialização do OpenBB Fatal")
    st.error(f"""
        Ocorreu um erro crítico ao tentar importar a biblioteca OpenBB.
        Isto é provavelmente o erro de permissão do Streamlit Cloud.

        **Variáveis de Ambiente Definidas:**
        - `OPENBB_USER_DATA_DIRECTORY`: `{os.environ.get('OPENBB_USER_DATA_DIRECTORY')}`
        - `XDG_CACHE_HOME`: `{os.environ.get('XDG_CACHE_HOME')}`
        - `XDG_CONFIG_HOME`: `{os.environ.get('XDG_CONFIG_HOME')}`
        - `MPLCONFIGDIR`: `{os.environ.get('MPLCONFIGDIR')}`
        - `HOME`: `{os.environ.get('HOME')}`

        **Erro Detalhado:**
        ```
        {e}
        ```
    """)
    st.stop()  # Interrompe a execução se a importação falhar

from datetime import date, timedelta

# --- Configuração da Página ---
# Isto só será executado se a importação do openbb for bem-sucedida
st.set_page_config(
    page_title="Plataforma de Investimentos",
    page_icon="📈",
    layout="wide"
)

# --- Funções de Cache ---
@st.cache_data(ttl=3600)  # Cache de 1 hora
def get_stock_data(symbol, start_date, end_date):
    """Busca dados históricos de ações usando o OpenBB."""
    try:
        data = obb.equity.price.historical(
            symbol=symbol,
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d'),
            provider="yfinance"  # Usar o provedor yfinance
        ).to_df()
        return data
    except Exception as e:
        st.error(f"Erro ao buscar dados para {symbol}: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=86400)  # Cache de 24 horas
def get_company_info(symbol):
    """Busca informações/perfil da empresa."""
    try:
        info = obb.equity.profile.company(
            symbol=symbol,
            provider="yfinance"
        ).to_df()
        return info
    except Exception as e:
        st.error(f"Erro ao buscar informações da empresa {symbol}: {e}")
        return pd.DataFrame()

# --- Interface do Usuário (UI) ---
st.title("Plataforma de Análise de Investimentos 📈")
st.caption("Desenvolvido com Streamlit e OpenBB SDK")

# --- Barra Lateral (Sidebar) ---
with st.sidebar:
    st.header("Configurações")

    # Input do Ticker
    default_tickers = "NVDA, AAPL, MSFT, GOOG"
    ticker_input = st.text_input("Tickers (separados por vírgula)", default_tickers)
    symbols = [s.strip().upper() for s in ticker_input.split(',') if s.strip()]

    # Seleção de Data
    st.subheader("Intervalo de Datas")
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Data Inicial", date.today() - timedelta(days=365*1))
    with col2:
        end_date = st.date_input("Data Final", date.today())

    if start_date > end_date:
        st.error("A data inicial não pode ser posterior à data final.")
        st.stop()

# --- Painel Principal (Tabs) ---
if symbols:
    # Criar abas para cada ticker selecionado
    tabs = st.tabs(symbols)

    for i, symbol in enumerate(symbols):
        with tabs[i]:
            st.header(f"Análise de {symbol}", divider="rainbow")

            # Sub-abas para Preço e Informações
            sub_tab1, sub_tab2 = st.tabs(["📊 Gráfico de Preços", "ℹ️ Informações da Empresa"])

            # --- Aba 1: Gráfico de Preços ---
            with sub_tab1:
                data = get_stock_data(symbol, start_date, end_date)

                if not data.empty:
                    st.subheader(f"Histórico de Preços (Close) para {symbol}")

                    # Gráfico Plotly
                    fig = px.line(
                        data,
                        x=data.index,
                        y="close",
                        title=f"Preço de Fechamento de {symbol}",
                        labels={"close": "Preço de Fechamento (USD)", "date": "Data"}
                    )
                    fig.update_layout(
                        template="plotly_white",
                        xaxis_rangeslider_visible=True,
                        hovermode="x unified"
                    )
                    st.plotly_chart(fig, use_container_width=True)

                    # Mostrar dados brutos (opcional)
                    if st.checkbox(f"Mostrar dados brutos de {symbol}", key=f"data_{symbol}"):
                        st.dataframe(data.sort_index(ascending=False), use_container_width=True)
                else:
                    st.warning(f"Não foi possível carregar dados de preço para {symbol}.")

            # --- Aba 2: Informações da Empresa ---
            with sub_tab2:
                info_df = get_company_info(symbol)

                if not info_df.empty:
                    st.subheader(f"Perfil de {symbol}")

                    # O .to_df() do 'company' retorna um DataFrame onde o índice é o nome do campo.
                    # Vamos transpor (T) para facilitar a leitura no Streamlit
                    st.dataframe(info_df.T, use_container_width=True)

                    # Tentar extrair e mostrar o resumo (longBusinessSummary)
                    try:
                        # .loc acessa a linha 'longBusinessSummary', .iloc[0] pega o primeiro valor
                        summary = info_df.loc['longBusinessSummary'].iloc[0]
                        st.subheader("Resumo do Negócio")
                        st.markdown(summary)
                    except (KeyError, IndexError):
                        st.info("Resumo do negócio (longBusinessSummary) não disponível.")
                else:
                    st.warning(f"Não foi possível carregar informações da empresa {symbol}.")
else:
    st.info("Por favor, insira um ou mais tickers na barra lateral para começar.")
