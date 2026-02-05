# source venv/bin/activate
# streamlit run app.py 
import streamlit as st
import ccxt
import pandas as pd
import time
import datetime

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Crypto Scanner Pro", layout="wide", page_icon="💎")

# --- CUSTOM CSS FOR PREMIUM LOOK ---
st.markdown("""
<style>
    /* Global Background & Font */
    .stApp {
        background-color: #0E1117;
        color: #FAFAFA;
        font-family: 'Inter', sans-serif;
    }
    
    /* Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #161B22;
        border-right: 1px solid #30363D;
    }
    
    /* Custom Title */
    h1 {
        font-weight: 700;
        background: -webkit-linear-gradient(45deg, #00C9FF, #92FE9D);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0px;
    }
    
    /* Metrics Styling */
    div[data-testid="stMetricValue"] {
        font-size: 28px;
        color: #00C9FF;
    }
    
    /* Table Styling */
    div[data-testid="stDataFrame"] {
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid #30363D;
    }
    
    .stButton>button {
        background: linear-gradient(90deg, #00C9FF 0%, #0072FF 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0, 201, 255, 0.3);
    }
    
    /* Hide Streamlit running man if possible (optional) */
    .stStatusWidget {
        visibility: hidden;
    }
</style>
""", unsafe_allow_html=True)

# --- SIDEBAR PER INPUT (MUST BE OUTSIDE LOOP) ---
with st.sidebar:
    st.title("⚙️ Config")
    
    # Lista Curata Crypto
    crypto_options = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE', 'AVAX', 'DOT', 'TRX', 'MATIC', 'LTC', 'LINK', 'ATOM']
    coin_input = st.selectbox("Select Asset", crypto_options, index=0)
    
    st.divider()
    
    # Live control
    auto_refresh = st.checkbox("🔴 Live Updates", value=True)
    if st.button("🔄 Manual Re-Run"):
        st.rerun()
    
    st.divider()
    st.info("Scanner looks for USDT/USD pairs automatically.")

# Lista Exchange da monitorare
exchanges_list = ['binance', 'kraken', 'coinbase', 'kucoin', 'bybit', 'okx', 'gateio', 'bitget', 'htx']

# --- FUNZIONI FETCH ---

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_historical_6_months(coin):
    """
    Fetch cached historical data for the last 6 months (approx 180 days).
    Runs once per session/hour for a given coin.
    """
    timeframe = '1d'
    limit = 180 
    
    best_avg_price = float('inf')
    best_exchange = None
    all_results = []
    
    # Iterate exchanges to find history
    for ex_name in exchanges_list:
        try:
            exchange_class = getattr(ccxt, ex_name)
            ex = exchange_class()
            if not ex.has['fetchOHLCV']:
                continue
            
            # Try USDT then USD
            ohlcv = None
            try:
                ohlcv = ex.fetch_ohlcv(f"{coin}/USDT", timeframe=timeframe, limit=limit)
            except:
                try:
                    ohlcv = ex.fetch_ohlcv(f"{coin}/USD", timeframe=timeframe, limit=limit)
                except:
                    pass
            
            if ohlcv:
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                
                avg_price = df['close'].mean()
                all_results.append({
                    "Exchange": ex_name.title(),
                    "Avg Price ($)": avg_price,
                    "History": df
                })
                
                if avg_price < best_avg_price:
                    best_avg_price = avg_price
                    best_exchange = {
                        "Exchange": ex_name.title(),
                        "Avg Price ($)": avg_price,
                        "History": df
                    }
        except:
            continue
            
    return all_results, best_exchange

def fetch_live_price(exchange_id, coin):
    """
    Fetches real-time price. Not cached.
    """
    try:
        exchange_class = getattr(ccxt, exchange_id)
        exchange = exchange_class({'enableRateLimit': True})
        
        symbols = [f"{coin}/USDT", f"{coin}/USD", f"{coin}/USDC"]
        errors_list = []
        for symbol in symbols:
            try:
                ticker = exchange.fetch_ticker(symbol)
                price = ticker['ask'] if ticker['ask'] else ticker['last']
                if price:
                    return {"Exchange": exchange_id.title(), "Price ($)": price}
            except Exception as e:
                errors_list.append(f"{symbol}: {str(e)}")
                continue
        
        if errors_list:
             return {"Exchange": exchange_id.title(), "Error": " | ".join(errors_list)}
             
    except Exception as e:
        return {"Exchange": exchange_id.title(), "Error": str(e)}
    return None

# --- LAYOUT SETUP ---

# --- LAYOUT CONTAINERS ---
header_container = st.container()
live_stats_container = st.container()
loading_bar_container = st.empty() # Temp container for loading
historical_container = st.container()

# 1. Header
with header_container:
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("Global Crypto Scanner")
        st.caption("Real-time arbitrage opportunities across major exchanges.")
    st.divider()

# 2. Live Section Placeholder
with live_stats_container:
    st.subheader("⚡️ Live Market Overview")
    live_placeholder = st.empty()

# Initial Loading Bar Logic
# Trigger if first load OR if coin changed
current_coin = coin_input
needs_loading = False

if 'last_coin' not in st.session_state:
    st.session_state['last_coin'] = current_coin
    needs_loading = True
elif st.session_state['last_coin'] != current_coin:
    st.session_state['last_coin'] = current_coin
    needs_loading = True

preloaded_data = None

if needs_loading:
    with loading_bar_container.container():
        # Create elements inside the temp container
        l_status = st.empty()
        l_bar = st.progress(0)
        
        preloaded_data = []
        total_ex = len(exchanges_list)
        
        l_status.text(f"Initializing scan for {current_coin}...")
        
        for i, ex_id in enumerate(exchanges_list):
            l_status.text(f"Scanning {ex_id.title()} for {current_coin}...")
            res = fetch_live_price(ex_id, current_coin)
            if res:
                preloaded_data.append(res)
            l_bar.progress((i + 1) / total_ex)
            time.sleep(0.05)
            
    # Clear the container after loading is done
    loading_bar_container.empty()

# 3. Historical Section (Static, Cached)
with historical_container:
    st.divider()
    st.subheader("📚 Historical Analysis (Last 6 Months)")
    st.caption("Comparing average prices over the last 180 days. Cached for performance.")

    # Fetch History ONCE
    with st.spinner(f"Loading 6-month history for {coin_input}..."):
        hist_results, best_hist = fetch_historical_6_months(coin_input)

    if hist_results and best_hist:
        h_col1, h_col2 = st.columns([1, 2])
        
        with h_col1:
            st.success(f"🏆 Best 6-Month Average: **{best_hist['Exchange']}**")
            st.metric("Lowest Avg Price", f"${best_hist['Avg Price ($)']:,.2f}")
        
        with h_col2:
            # Sort results
            hist_df = pd.DataFrame(hist_results)
            hist_df = hist_df.sort_values(by="Avg Price ($)", ascending=True).reset_index(drop=True)
            
            st.dataframe(
                hist_df[['Exchange', 'Avg Price ($)']].style.format({"Avg Price ($)": "${:,.2f}"})
                .background_gradient(subset=["Avg Price ($)"], cmap="Greens_r"),
                width="stretch",
                hide_index=True
            )
            
        st.line_chart(best_hist['History'], x='timestamp', y='close', color='#00C9FF')
        
    else:
        st.warning("Could not fetch historical data for this asset. Try checking your internet connection or API limits.")

# --- LIVE UPDATE LOOP ---
# This runs infinitely updating ONLY 'live_placeholder'
# The rest of the page (Sidebar, History) remains static and does not flicker.


while True:
    # Fetch Live Data
    live_data = []
    
    if preloaded_data is not None:
        # Use simple caching from the loading bar for the first frame
        live_data = preloaded_data
        preloaded_data = None
    else:
        # Normal Loop Fetch
        for ex in exchanges_list:
            res = fetch_live_price(ex, coin_input)
            if res:
                live_data.append(res)
            
            # Update the container
    with live_placeholder.container():
        # Separate valid data from errors
        valid_data = [d for d in live_data if "Error" not in d]
        errors = [d for d in live_data if "Error" in d]

        # Display errors first if any (useful for debugging)
        if errors:
            with st.expander("⚠️ Connection Issues / Debug Log", expanded=True):
                for err in errors:
                    st.error(f"**{err['Exchange']}**: {err['Error']}")

        if valid_data:
            df = pd.DataFrame(valid_data)
            df_sorted = df.sort_values(by="Price ($)", ascending=True).reset_index(drop=True)
            
            best_price = df_sorted.iloc[0]['Price ($)']
            worst_price = df_sorted.iloc[-1]['Price ($)']
            spread = worst_price - best_price
            spread_pct = (spread / best_price) * 100
            
            # Metrics
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Best Price", f"${best_price:,.2f}", df_sorted.iloc[0]['Exchange'])
            m2.metric("Worst Price", f"${worst_price:,.2f}", df_sorted.iloc[-1]['Exchange'])
            m3.metric("Spread ($)", f"${spread:,.2f}")
            m4.metric("Spread (%)", f"{spread_pct:.2f}%")
            
            # Table
            st.dataframe(
                df_sorted.style.format({"Price ($)": "${:,.4f}"})
                .background_gradient(subset=["Price ($)"], cmap="RdYlGn_r"),
                width="stretch",
                hide_index=True
            )
        else:
            st.warning("Connecting to exchanges...")
            
    if not auto_refresh:
        # If user stops live updates, we break the loop and script ends.
        # User can click "Manual Re-Run" to restart.
        break
        
    time.sleep(1) # Fast refresh
