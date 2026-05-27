import streamlit as st
import pandas as pd
import os
import re
import time
import json
import copy
import io
import uuid
import base64
from PIL import Image
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import hashlib
import unicodedata
import warnings

# ============================================================
# DASHBOARD ARQTEC – COMPLETO COM CORREÇÃO PARA STREAMLIT CLOUD
# ============================================================

# ============================================================
# 0. CONFIGURAÇÕES GLOBAIS
# ============================================================
PASTA_RAIZ_WINDOWS = r"C:\Users\Maikon\Nextcloud\09 - ENGENHARIA\08 - DASHBOARD"
if os.path.exists(PASTA_RAIZ_WINDOWS):
    PASTA_RAIZ = PASTA_RAIZ_WINDOWS
else:
    PASTA_RAIZ = os.getcwd()

ARQ_USUARIOS      = os.path.join(PASTA_RAIZ, "usuarios.json")
ARQ_CONFIG        = os.path.join(PASTA_RAIZ, "dashboard_config.json")
COR_ARQTEC        = "#E30613"
COR_META_PADRAO   = "#2ECC71"
TEMPO_ATUALIZACAO = 5   # minutos (padrão)
SENHA_PLANILHA    = "aamm"

PASTA_PROGRAMA    = os.path.basename(os.path.dirname(os.path.abspath(__file__)))

PALETA_DIVERSA = ["#E30613", "#3498DB", "#2ECC71", "#F1C40F", "#9B59B6", "#E67E22", "#1ABC9C", "#34495E", "#E74C3C", "#7F8C8D"]

warnings.filterwarnings("ignore", message="Could not infer format")

# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================
def remover_acentos(texto):
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')

def inicializar_tema():
    if "tema_detectado" not in st.session_state:
        st.session_state.tema_detectado = "light"
    js_code = """
    <script>
        function getStreamlitTheme() {
            const body = document.body;
            const isDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
            const hasDarkClass = body.classList.contains('dark') || body.classList.contains('dark-mode');
            let tema = 'light';
            if (hasDarkClass || isDark) {
                tema = 'dark';
            }
            sessionStorage.setItem('streamlit_theme', tema);
            const url = new URL(window.location.href);
            url.searchParams.set('theme_detected', tema);
            window.history.replaceState({}, '', url);
        }
        getStreamlitTheme();
    </script>
    """
    st.markdown(js_code, unsafe_allow_html=True)
    tema_url = st.query_params.get("theme_detected")
    if tema_url in ["dark", "light"]:
        st.session_state.tema_detectado = tema_url
    else:
        try:
            tema = st.get_option("theme.base")
            if tema in ["dark", "light"]:
                st.session_state.tema_detectado = tema
        except:
            pass

def obter_cor_texto():
    return "white" if st.session_state.tema_detectado == "dark" else "black"

def hash_senha(senha):
    return hashlib.sha256(senha.encode()).hexdigest()

def verificar_senha(senha, hash_armazenado):
    return hash_senha(senha) == hash_armazenado

def formatar_abreviado(n):
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000:     return f"{n/1_000:.1f}k"
    if n == 0:         return "0"
    try:               return f"{float(n):g}"
    except:            return str(n)

def salvar_filtro_data_url(cid, data_inicio, data_fim):
    params = st.query_params.to_dict()
    params[f"data_inicio_{cid}"] = data_inicio.isoformat() if data_inicio else ""
    params[f"data_fim_{cid}"] = data_fim.isoformat() if data_fim else ""
    st.query_params.update(params)

def carregar_filtro_data_url(cid, data_min_padrao, data_max_padrao):
    params = st.query_params
    inicio = params.get(f"data_inicio_{cid}")
    fim = params.get(f"data_fim_{cid}")
    try:
        data_inicio = datetime.fromisoformat(inicio).date() if inicio else data_min_padrao
        data_fim = datetime.fromisoformat(fim).date() if fim else data_max_padrao
    except:
        data_inicio, data_fim = data_min_padrao, data_max_padrao
    return data_inicio, data_fim

@st.cache_data
def carregar_logo_seguro():
    caminhos = [os.path.join(PASTA_RAIZ, "image_75fd31.png"), "image_75fd31.png"]
    for p in caminhos:
        if os.path.exists(p):
            try: return Image.open(p).copy()
            except: continue
    return None

img_logo = carregar_logo_seguro()
st.set_page_config(page_title="Arq Indicadores", page_icon=img_logo if img_logo else "📊", layout="wide")
inicializar_tema()

# ============================================================
# CSS + META TAG PARA DESABILITAR TRADUÇÃO
# ============================================================
st.markdown("""
<style>
    .block-container { padding-top: 4rem !important; padding-bottom: 1rem !important; padding-left: 2rem !important; padding-right: 2rem !important; }
    footer { visibility: hidden; }
    .stDeployButton { visibility: hidden; }
    .st-emotion-cache-1jicfl2 { padding: 0.8rem; border-radius: 10px; background-color: rgba(128,128,128,0.05); }
    .stProgress > div { background-color: #E30613 !important; }
    [data-testid="stVerticalBlock"] > div, [data-testid="stHorizontalBlock"] > div,
    [data-testid="stElementContainer"], .element-container, .stPlotlyChart {
        opacity: 1 !important; transition: none !important; filter: blur(0px) !important;
    }
</style>
<meta name="google" content="notranslate">
""", unsafe_allow_html=True)

# ============================================================
# 1. MOTOR DE DADOS E CONFIGURAÇÕES
# ============================================================
def obter_lista_setores():
    pastas = ["Selecione..."]
    if os.path.exists(PASTA_RAIZ):
        pastas += [d for d in os.listdir(PASTA_RAIZ) 
                   if os.path.isdir(os.path.join(PASTA_RAIZ, d)) and d != PASTA_PROGRAMA]
    return pastas

def carregar_usuarios():
    padrao = {"maikon": {"senha": hash_senha("admin123"), "status": "aprovado", "role": "admin", "setor": "Todos"}}
    if os.path.exists(ARQ_USUARIOS):
        try:
            with open(ARQ_USUARIOS, "r", encoding="utf-8") as f: 
                data = json.load(f)
            for k, v in data.items():
                if isinstance(v, str):
                    data[k] = {"senha": hash_senha(v), "status": "aprovado", "role": "admin" if k == "maikon" else "user", "setor": "Todos"}
                elif isinstance(v, dict):
                    if len(v.get("senha", "")) != 64:
                        data[k]["senha"] = hash_senha(v["senha"])
                    if "setor" not in data[k]:
                        data[k]["setor"] = "Todos" if data[k].get("role") == "admin" else "Geral"
            if "maikon" not in data: data["maikon"] = padrao["maikon"]
            return data
        except: pass
    return padrao

def salvar_usuarios(users):
    with open(ARQ_USUARIOS, "w", encoding="utf-8") as f: 
        json.dump(users, f, indent=4, ensure_ascii=False)

def carregar_config_dashboard():
    padrao = {
        "ids": ["G1"], 
        "charts": {
            "G1": {
                "nome": "Indicador Arqtec", "tipo_fonte": "Local", "url": "", "setor": "Selecione...",
                "arquivo": "...", "aba": "...", "x": "...", "y": "...", "meta": "...", "subgrupo": "...",
                "modo": "Somar", "ordem": "Mês", "tipo": "Barras", "cor": COR_ARQTEC, "cor_meta": COR_META_PADRAO,
                "cores_cats": {}, "filtros_multiplos": [], "filtros_selecionados": {},
                "filtro_data_col": "...", "mostrar_total_legenda": True,
                "palavras_chave": "", "agrupamento_data": "Dia", "formato_rotulo": "Valor",
                "data_inicio": None, "data_fim": None,
                "legendas_personalizadas": {},
                "modo_visualizacao": "Gráfico"
            }
        }, 
        "presets": {},
        "layouts_por_setor": {}
    }
    if os.path.exists(ARQ_CONFIG):
        try:
            with open(ARQ_CONFIG, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "ids" in data and "charts" in data:
                    if "presets" not in data: data["presets"] = {}
                    if "layouts_por_setor" not in data: data["layouts_por_setor"] = {}
                    for chart_id, chart_data in data["charts"].items():
                        if "arq" in chart_data and "arquivo" not in chart_data:
                            chart_data["arquivo"] = chart_data["arq"]
                        if "ordem" in chart_data and chart_data["ordem"] == "Mes":
                            chart_data["ordem"] = "Mês"
                        if "agrupamento_data" not in chart_data:
                            chart_data["agrupamento_data"] = "Dia"
                        if "setor" not in chart_data:
                            chart_data["setor"] = "Selecione..."
                        if "filtros_multiplos" not in chart_data:
                            chart_data["filtros_multiplos"] = []
                            if chart_data.get("filtro_col", "...") != "...":
                                chart_data["filtros_multiplos"].append(chart_data["filtro_col"])
                        if "filtro_col" in chart_data:
                            del chart_data["filtro_col"]
                        if "filtros_selecionados" not in chart_data:
                            chart_data["filtros_selecionados"] = {}
                        if "data_inicio" not in chart_data:
                            chart_data["data_inicio"] = None
                        if "data_fim" not in chart_data:
                            chart_data["data_fim"] = None
                        if "legendas_personalizadas" not in chart_data:
                            chart_data["legendas_personalizadas"] = {}
                        if "modo_visualizacao" not in chart_data:
                            chart_data["modo_visualizacao"] = "Gráfico"
                    return data
        except: pass
    return padrao

def salvar_config_dashboard(ids, charts, presets, layouts=None):
    try:
        for cid, conf in charts.items():
            if "data_inicio" in conf and conf["data_inicio"] is not None:
                if isinstance(conf["data_inicio"], (datetime,)):
                    conf["data_inicio"] = conf["data_inicio"].isoformat()
                elif hasattr(conf["data_inicio"], 'isoformat'):
                    conf["data_inicio"] = conf["data_inicio"].isoformat()
            if "data_fim" in conf and conf["data_fim"] is not None:
                if isinstance(conf["data_fim"], (datetime,)):
                    conf["data_fim"] = conf["data_fim"].isoformat()
                elif hasattr(conf["data_fim"], 'isoformat'):
                    conf["data_fim"] = conf["data_fim"].isoformat()
        obj = {"ids": ids, "charts": charts, "presets": presets}
        if layouts is not None:
            obj["layouts_por_setor"] = layouts
        with open(ARQ_CONFIG, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=4, ensure_ascii=False)
    except Exception as e:
        st.error(f"❌ Erro ao salvar configuração: {str(e)}")

def limpar_numero(serie):
    def converter(val):
        if pd.isna(val) or str(val).strip() == "": return 0.0
        if isinstance(val, (int, float)): return float(val)
        val = str(val).upper().replace("R$", "").strip()
        val = re.sub(r"[^\d\.,\-]", "", val)
        lc, ld = val.rfind(","), val.rfind(".")
        if lc > ld: val = val.replace(".", "").replace(",", ".")
        elif ld > lc and lc != -1: val = val.replace(",", "")
        else:
            if val.count(",") > 1: val = val.replace(",", "")
            elif val.count(",") == 1: val = val.replace(",", ".")
            if val.count(".") > 1:
                p = val.rsplit(".", 1)
                val = p[0].replace(".", "") + "." + p[1]
        try: return round(float(val), 2)
        except: return 0.0
    return serie.apply(converter)

def processar_dados_arquivo(dados_brutos):
    try:
        df = pd.DataFrame(dados_brutos)
        linha_header = 0
        for i in range(min(20, len(df))):
            vals = [str(v).upper() for v in df.iloc[i].values if pd.notna(v)]
            if any(k in " ".join(vals) for k in ["STATUS","CLIENTE","SEGMENTO","VALOR","MES","META","REALIZADA"]):
                linha_header = i
                break
        df_f = df.iloc[linha_header:].copy()
        df_f.columns = [str(c).strip().upper() for c in df_f.iloc[0].values]
        df_f = df_f.iloc[1:].reset_index(drop=True).loc[:, ~df_f.columns.str.contains("^UNNAMED")]
        
        cols = df_f.columns.tolist()
        new_cols = []
        counts = {}
        for col in cols:
            if col in counts:
                counts[col] += 1
                new_cols.append(f"{col}_{counts[col]}")
            else:
                counts[col] = 0
                new_cols.append(col)
        df_f.columns = new_cols
        indice_corte = None
        contador_vazias = 0
        for idx, row in df_f.iterrows():
            if row.dropna().astype(str).str.strip().eq("").all() or row.isna().all():
                contador_vazias += 1
            else:
                contador_vazias = 0
            if contador_vazias >= 2:
                indice_corte = idx - 1
                break
        if indice_corte is not None and indice_corte > 0:
            df_f = df_f.iloc[:indice_corte].copy()
        return df_f
    except:
        return pd.DataFrame()

def normalizar_url_google_sheets(url: str) -> str:
    if "docs.google.com/spreadsheets" not in url: return url
    id_match  = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    gid_match = re.search(r"gid=(\d+)", url)
    doc_id = id_match.group(1) if id_match else ""
    gid    = gid_match.group(1) if gid_match else "0"
    return f"https://docs.google.com/spreadsheets/d/{doc_id}/export?format=csv&gid={gid}"

# -----------------------------------------------------------
# LEITURA INTELIGENTE (com hash de bytes)
# -----------------------------------------------------------
if "cache_arquivos" not in st.session_state:
    st.session_state.cache_arquivos = {}
if "hash_agregado" not in st.session_state:
    st.session_state.hash_agregado = {}  
if "setores_atualizados" not in st.session_state:
    st.session_state.setores_atualizados = {}  

def carregar_planilha_sem_cache(origem, aba=None, tipo="Local"):
    try:
        if tipo == "URL" or ("docs.google.com/spreadsheets" in str(origem)):
            url_final = normalizar_url_google_sheets(origem)
            try:
                response = st.session_state.get(f"url_bytes_{url_final}")
                if not response:
                    import requests
                    response = requests.get(url_final)
                    st.session_state[f"url_bytes_{url_final}"] = response
                df = pd.read_csv(io.BytesIO(response.content), header=None)
            except:
                df = pd.read_excel(url_final, sheet_name=0, header=None, engine="openpyxl")
            return processar_dados_arquivo(df)
        else:
            caminho = origem
            if not os.path.exists(caminho):
                return pd.DataFrame()
            mtime_atual = os.path.getmtime(caminho)
            
            chave_cache = f"{caminho}_{aba}"
            cache = st.session_state.cache_arquivos.get(chave_cache)
            if cache and cache[0] == mtime_atual:
                return cache[1].copy()
                
            nome_arquivo = os.path.basename(caminho)
            with open(caminho, "rb") as f:
                file_bytes = f.read()
                bytes_io = io.BytesIO(file_bytes)
            if aba is None or aba == "...":
                sheet = 0
            else:
                sheet = aba
            if "PEDIDO" in nome_arquivo.upper() or "PEDIDOS" in nome_arquivo.upper():
                try:
                    df = pd.read_excel(bytes_io, sheet_name=sheet, header=None, engine="openpyxl", password=SENHA_PLANILHA)
                except:
                    bytes_io.seek(0)
                    df = pd.read_excel(bytes_io, sheet_name=sheet, header=None, engine="openpyxl")
            else:
                df = pd.read_excel(bytes_io, sheet_name=sheet, header=None, engine="openpyxl")
            df_processado = processar_dados_arquivo(df)
            
            st.session_state.cache_arquivos[chave_cache] = (mtime_atual, df_processado.copy())
            return df_processado
    except Exception as e:
        st.warning(f"Erro ao carregar {origem}: {str(e)[:100]}")
        return pd.DataFrame()

@st.cache_data(ttl=60, show_spinner=False)
def carregar_planilha_com_cache_url(url):
    url_final = normalizar_url_google_sheets(url)
    try: df = pd.read_csv(url_final, header=None)
    except: df = pd.read_excel(url_final, sheet_name=0, header=None, engine="openpyxl")
    return processar_dados_arquivo(df)

def converter_coluna_data_robusto(serie):
    if pd.api.types.is_datetime64_any_dtype(serie):
        result = serie.copy()
        if hasattr(result.dtype, 'tz') and result.dtype.tz is not None:
            result = result.dt.tz_localize(None)
        return result
    def converter_valor(val):
        if pd.isna(val) or str(val).strip() in ("", "NAT", "NAN", "NONE"):
            return pd.NaT
        if hasattr(val, 'year'):
            try: return pd.Timestamp(val)
            except: return pd.NaT
        val_str = str(val).strip()
        try:
            num = float(val_str.replace(",", "."))
            if num >= 35000:
                dt = datetime(1899, 12, 30) + timedelta(days=num)
                if 1900 <= dt.year <= 2100:
                    return pd.Timestamp(dt)
        except:
            pass
        return None
    resultado_parcial = serie.apply(converter_valor)
    mascara_pendente = resultado_parcial.isna() & serie.notna() & (serie.astype(str).str.strip() != "")
    if mascara_pendente.any():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tentativa_br = pd.to_datetime(serie[mascara_pendente], errors='coerce', dayfirst=True)
        resultado_parcial[mascara_pendente] = tentativa_br
    mascara_ainda_nat = resultado_parcial.isna() & serie.notna() & (serie.astype(str).str.strip() != "")
    if mascara_ainda_nat.any():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tentativa_iso = pd.to_datetime(serie[mascara_ainda_nat], errors='coerce', dayfirst=False)
        resultado_parcial[mascara_ainda_nat] = tentativa_iso
    result = pd.to_datetime(resultado_parcial, errors='coerce')
    if hasattr(result.dtype, 'tz') and result.dtype.tz is not None:
        result = result.dt.tz_localize(None)
    result = result.mask((result.dt.year < 1900) | (result.dt.year > 2100))
    return result

def aplicar_agrupamento_data(df, coluna_data, tipo_agrupamento):
    if coluna_data not in df.columns: return df
    if df[coluna_data].isna().all(): return df
    df_temp = df.copy()
    try:
        series_datetime = converter_coluna_data_robusto(df_temp[coluna_data])
        if series_datetime.isna().all(): return df
        df_temp[coluna_data] = series_datetime
        df_temp = df_temp.dropna(subset=[coluna_data])
        if df_temp.empty: return df
        if tipo_agrupamento == "Dia":
            df_temp[coluna_data] = df_temp[coluna_data].dt.strftime("%d/%m/%Y")
        elif tipo_agrupamento == "Mês":
            df_temp[coluna_data] = df_temp[coluna_data].dt.strftime("%B/%Y")
        elif tipo_agrupamento == "Ano":
            df_temp[coluna_data] = df_temp[coluna_data].dt.strftime("%Y")
        return df_temp
    except Exception:
        return df

# ============================================================
# 2. LOGIN E INICIALIZAÇÃO DE SESSÃO
# ============================================================
usuarios_db = carregar_usuarios()

if "filtros_data" not in st.session_state:
    st.session_state.filtros_data = {}
if "auth" not in st.session_state:
    st.session_state.auth = False
if "logged_user" not in st.session_state:
    st.session_state.logged_user = ""
if "personalizar_layout" not in st.session_state:
    st.session_state.personalizar_layout = False

if not st.session_state.auth:
    token_url = st.query_params.get("t")
    if token_url:
        for u, data_u in usuarios_db.items():
            if data_u.get("token") == token_url and data_u.get("status") == "aprovado":
                st.session_state.auth = True
                st.session_state.logged_user = u
                break

if not st.session_state.auth:
    tela_login = st.empty()
    with tela_login.container():
        _, col, _ = st.columns([3, 2, 3])
        with col:
            st.markdown("<br><br>", unsafe_allow_html=True)
            if img_logo: st.image(img_logo, use_container_width=True)
            tab_login, tab_cad = st.tabs(["🔐 Login", "📝 Solicitar Acesso"])
            with tab_login:
                with st.form("form_login"):
                    u = st.text_input("Usuário").lower().strip()
                    s = st.text_input("Senha", type="password")
                    if st.form_submit_button("Acessar Sistema", use_container_width=True):
                        if u in usuarios_db and verificar_senha(s, usuarios_db[u]["senha"]):
                            if usuarios_db[u]["status"] == "aprovado":
                                st.session_state.auth = True
                                st.session_state.logged_user = u
                                novo_token = str(uuid.uuid4())
                                usuarios_db[u]["token"] = novo_token
                                salvar_usuarios(usuarios_db)
                                st.query_params["t"] = novo_token
                                tela_login.empty()
                                st.rerun()
                            else: st.warning("⏳ Cadastro em análise.")
                        else: st.error("❌ Usuário ou senha incorretos.")
            with tab_cad:
                with st.form("form_cadastro"):
                    novo_u = st.text_input("Nome de usuário").lower().strip()
                    novo_s = st.text_input("Senha", type="password")
                    # Lista de setores sem a pasta do programa
                    setores_cadastro = ["Todos os Setores (Diretoria)"] + [
                        d for d in os.listdir(PASTA_RAIZ) 
                        if os.path.isdir(os.path.join(PASTA_RAIZ, d)) and d != PASTA_PROGRAMA
                    ]
                    setor_escolhido = st.selectbox("Setor de acesso", setores_cadastro)
                    if st.form_submit_button("Solicitar Acesso", use_container_width=True):
                        if not novo_u or not novo_s: st.error("Preencha todos os campos!")
                        elif novo_u in usuarios_db: st.error("Usuário já existe ou já solicitado!")
                        else:
                            role = "admin" if setor_escolhido.startswith("Todos") else "user"
                            usuarios_db[novo_u] = {
                                "senha": hash_senha(novo_s),
                                "status": "pendente",
                                "role": role,
                                "setor": setor_escolhido.replace("Todos os Setores (Diretoria)", "Todos")
                            }
                            salvar_usuarios(usuarios_db)
                            st.success("✅ Solicitação enviada! Aguarde aprovação.")
    st.stop()

user_data = usuarios_db.get(st.session_state.logged_user, {})
is_admin = (user_data.get("role") == "admin" or st.session_state.logged_user == "maikon")
user_setor = user_data.get("setor", "Todos")
allowed_setores = ["Todos"] if user_setor == "Todos" else [user_setor]

if not is_admin:
    config_salva = carregar_config_dashboard()
    st.session_state.chart_ids = config_salva["ids"]
    st.session_state.charts = config_salva["charts"]
    st.session_state.presets = config_salva.get("presets", {})
    st.session_state.layouts_setores = config_salva.get("layouts_por_setor", {})
elif "chart_ids" not in st.session_state:
    config_salva = carregar_config_dashboard()
    st.session_state.chart_ids = config_salva["ids"]
    st.session_state.charts = config_salva["charts"]
    st.session_state.presets = config_salva.get("presets", {})
    st.session_state.layouts_setores = config_salva.get("layouts_por_setor", {})
elif "layouts_setores" not in st.session_state:
    st.session_state.layouts_setores = carregar_config_dashboard().get("layouts_por_setor", {})

# Filtrar gráficos visíveis conforme permissão do usuário
if user_setor != "Todos":
    st.session_state.chart_ids_visiveis = [
        cid for cid in st.session_state.chart_ids
        if st.session_state.charts[cid].get("setor", "Geral") in allowed_setores
    ]
else:
    st.session_state.chart_ids_visiveis = st.session_state.chart_ids[:]

bloquear_refresh_por_edicao = False

# ============================================================
# 3. SIDEBAR
# ============================================================
with st.sidebar:
    if img_logo: st.image(img_logo, width=150)
    st.markdown(f"**👤 Usuário:** {st.session_state.logged_user.capitalize()}")
    st.markdown(f"**📂 Setor:** {user_setor}")
    
    cor_atual = obter_cor_texto()
    tema_detectado = st.session_state.tema_detectado
    st.info(f"🎨 Cor do texto: **{cor_atual}** (tema detectado: **{tema_detectado}**)")
    
    tema_manual = st.selectbox("🔧 Forçar tema (se a detecção falhar):", ["Automático", "Claro", "Escuro"], index=0)
    if tema_manual == "Claro":
        st.session_state.tema_detectado = "light"
        st.session_state.tema_forcado = True
    elif tema_manual == "Escuro":
        st.session_state.tema_detectado = "dark"
        st.session_state.tema_forcado = True
    elif tema_manual == "Automático":
        if st.session_state.get("tema_forcado", False):
            inicializar_tema()
            st.session_state.tema_forcado = False
            st.rerun()
    
    if is_admin:
        st.divider()
        with st.expander("👥 Gestão de Usuários", expanded=False):
            pendentes = {k:v for k,v in usuarios_db.items() if v.get("status")=="pendente"}
            aprovados = {k:v for k,v in usuarios_db.items() if v.get("status")=="aprovado" and k!=st.session_state.logged_user}
            if pendentes:
                st.markdown("**⏳ Pendentes:**")
                for p_user in pendentes:
                    c1,c2,c3 = st.columns([5,2,2])
                    c1.write(p_user)
                    if c2.button("✔️", key=f"apr_{p_user}"):
                        usuarios_db[p_user]["status"]="aprovado"
                        salvar_usuarios(usuarios_db)
                        st.rerun()
                    if c3.button("❌", key=f"rej_{p_user}"):
                        del usuarios_db[p_user]
                        salvar_usuarios(usuarios_db)
                        st.rerun()
            else: st.caption("Nenhuma solicitação pendente.")
            if aprovados:
                st.markdown("---"); st.markdown("**✅ Ativos:**")
                for a_user in aprovados:
                    c1,c2,c3 = st.columns([4,3,3])
                    c1.write(a_user)
                    atual_setor = usuarios_db[a_user].get("setor", "Geral")
                    # Lista de setores sem a pasta do programa
                    lista_setores_user = ["Todos"] + [
                        d for d in os.listdir(PASTA_RAIZ) 
                        if os.path.isdir(os.path.join(PASTA_RAIZ, d)) and d != PASTA_PROGRAMA
                    ]
                    # Garantir que o setor atual apareça, mesmo que seja a pasta do programa (se já existir)
                    if atual_setor not in lista_setores_user:
                        lista_setores_user.append(atual_setor)
                    novo_setor = c2.selectbox("Setor", lista_setores_user, 
                                             index=lista_setores_user.index(atual_setor) if atual_setor in lista_setores_user else 0, 
                                             key=f"setor_{a_user}")
                    if novo_setor != atual_setor:
                        usuarios_db[a_user]["setor"] = novo_setor
                        salvar_usuarios(usuarios_db)
                        st.rerun()
                    if c3.button("Excluir", key=f"del_{a_user}"):
                        del usuarios_db[a_user]
                        salvar_usuarios(usuarios_db)
                        st.rerun()
    
    st.divider()
    st.header("⚙️ Visualização")
    auto_refresh = st.toggle("⏱️ Auto-Update", value=True)
    
    if auto_refresh:
        intervalo_atualizacao_min = st.slider(
            "Intervalo de atualização (minutos)", 
            min_value=1, max_value=30, value=TEMPO_ATUALIZACAO, step=1,
            help="Tempo entre recargas dos gráficos. O arquivo só é lido se modificado."
        )
        intervalo_atualizacao = intervalo_atualizacao_min * 60
    else:
        intervalo_atualizacao = TEMPO_ATUALIZACAO * 60
    
    rotacao_automatica = st.toggle("🔄 Rotação Automática por Setor", value=False)
    if rotacao_automatica: 
        tempo_rotacao = st.slider("Segundos por tela", 5, 120, 15)
    else: 
        tempo_rotacao = intervalo_atualizacao
    
    st.markdown("---")
    if st.button("🔄 Atualizar agora", use_container_width=True, help="Força a leitura dos dados e recria todos os gráficos."):
        st.session_state.cache_arquivos = {}
        st.session_state.hash_agregado = {}
        st.session_state.setores_atualizados = {}
        st.rerun()
    
    st.markdown("📐 **Tamanho dos gráficos**")
    opcoes_tamanho = [
        "Setores (6 por linha)",
        "Pequenos (3 por linha)",
        "Médios (2 por linha)",
        "Médios (4 por linha)",
        "Grandes (1 por linha)"
    ]
    tamanho_grid = st.radio("Layout:", opcoes_tamanho, index=2, label_visibility="collapsed")
    if "Setores" in tamanho_grid: 
        num_cols = 6
        altura_grafico = 280
    elif "Pequenos" in tamanho_grid: 
        num_cols = 3
        altura_grafico = 280
    elif "Médios (2" in tamanho_grid: 
        num_cols = 2
        altura_grafico = 380
    elif "Médios (4" in tamanho_grid:
        num_cols = 4
        altura_grafico = 330
    else: 
        num_cols = 1
        altura_grafico = 500

    st.markdown("---")
    personalizar_layout = st.toggle(
        "🎯 Personalizar layout por Setor", 
        value=st.session_state.personalizar_layout,
        help="Permite definir número de colunas e altura diferentes para cada setor."
    )
    st.session_state.personalizar_layout = personalizar_layout

    if personalizar_layout:
        setores_com_graficos = sorted(list(set(
            st.session_state.charts[cid].get("setor", "Geral") 
            for cid in st.session_state.chart_ids_visiveis 
            if st.session_state.charts[cid].get("setor", "Selecione...") != "Selecione..."
        )))
        if not setores_com_graficos:
            st.info("Nenhum gráfico configurado ainda.")
        else:
            with st.expander("⚙️ Configurar layout por setor", expanded=True):
                for setor in setores_com_graficos:
                    st.markdown(f"**{setor}**")
                    saved = st.session_state.layouts_setores.get(setor, {})
                    cols_personalizado = saved.get("cols", num_cols)
                    altura_personalizada = saved.get("height", altura_grafico)
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        n_cols = st.slider(f"Colunas - {setor}", 1, 6, cols_personalizado, key=f"cols_{setor}")
                    with c2:
                        n_altura = st.slider(f"Altura - {setor}", 200, 600, altura_personalizada, key=f"altura_{setor}")
                    
                    st.session_state.layouts_setores[setor] = {"cols": n_cols, "height": n_altura}
                salvar_config_dashboard(st.session_state.chart_ids, st.session_state.charts, 
                                        st.session_state.presets, st.session_state.layouts_setores)

    if is_admin:
        st.markdown("---")
        st.header("🛠️ Administração")
        if st.button("➕ Novo Gráfico", use_container_width=True):
            nid = f"G{int(time.time())}"
            st.session_state.chart_ids.append(nid)
            num_graficos = len(st.session_state.chart_ids)
            st.session_state.charts[nid] = {
                "nome": f"Novo Gráfico {num_graficos}", "tipo_fonte": "Local", "url": "", "setor": "Selecione...",
                "arquivo": "...", "aba": "...", "x": "...", "y": "...", "meta": "...", "subgrupo": "...",
                "modo": "Somar", "ordem": "Mês", "tipo": "Barras", "cor": COR_ARQTEC, "cor_meta": COR_META_PADRAO,
                "cores_cats": {}, "filtros_multiplos": [], "filtros_selecionados": {},
                "filtro_data_col": "...", "mostrar_total_legenda": True,
                "palavras_chave": "", "agrupamento_data": "Dia", "formato_rotulo": "Valor",
                "data_inicio": None, "data_fim": None,
                "legendas_personalizadas": {},
                "modo_visualizacao": "Gráfico"
            }
            salvar_config_dashboard(st.session_state.chart_ids, st.session_state.charts, 
                                    st.session_state.presets, st.session_state.layouts_setores)
            st.rerun()
        st.divider()
        if st.session_state.chart_ids:
            opcoes_estrutura = ["⚙️ Visualizar Painel"] + st.session_state.chart_ids
            def formatar_lista(x):
                if x == "⚙️ Visualizar Painel": return x
                return f"✏️ Editar: {st.session_state.charts[x]['nome']}"
            selecao_edicao = st.selectbox("Modo", opcoes_estrutura, format_func=formatar_lista)
            if selecao_edicao != "⚙️ Visualizar Painel":
                bloquear_refresh_por_edicao = True
                eid = selecao_edicao
                conf = st.session_state.charts[eid]
                st.info("🎯 Modo Configuração - Auto-Update pausado.")
                
                col1, col2 = st.columns([3,1])
                with col1:
                    st.subheader(f"Editando: {conf.get('nome', eid)}")
                with col2:
                    if st.button("🗑️ Excluir", key=f"del_top_{eid}", help="Excluir este gráfico"):
                        st.session_state.chart_ids.remove(eid)
                        del st.session_state.charts[eid]
                        salvar_config_dashboard(st.session_state.chart_ids, st.session_state.charts, 
                                                st.session_state.presets, st.session_state.layouts_setores)
                        st.rerun()
                
                with st.expander("💾 Salvar / Carregar Predefinições", expanded=False):
                    chaves_ordenadas = sorted(st.session_state.presets.keys(), key=lambda k: (st.session_state.presets[k].get("setor","Geral"), k))
                    if chaves_ordenadas:
                        st.markdown("**Predefinições existentes:**")
                        for preset_nome in chaves_ordenadas:
                            c1, c2 = st.columns([8,2])
                            with c1:
                                st.write(f"• {preset_nome}")
                            with c2:
                                if st.button("🗑️", key=f"del_preset_{preset_nome}", help=f"Excluir {preset_nome}"):
                                    del st.session_state.presets[preset_nome]
                                    salvar_config_dashboard(st.session_state.chart_ids, st.session_state.charts, 
                                                            st.session_state.presets, st.session_state.layouts_setores)
                                    st.rerun()
                    st.markdown("---")
                    c_load1, c_load2 = st.columns([7,3])
                    lista_presets = ["Selecione..."] + chaves_ordenadas
                    def formatar_preset(k):
                        if k == "Selecione...": return k
                        return f"[{st.session_state.presets[k].get('setor','Sem Setor')}] - {k}"
                    preset_selecionado = c_load1.selectbox("Predefinições", lista_presets, format_func=formatar_preset, label_visibility="collapsed", key=f"sel_pre_{eid}")
                    if c_load2.button("Carregar", use_container_width=True, key=f"btn_ld_{eid}") and preset_selecionado != "Selecione...":
                        preset_data = copy.deepcopy(st.session_state.presets[preset_selecionado])
                        nome_atual = conf["nome"]
                        st.session_state.charts[eid] = preset_data
                        st.session_state.charts[eid]["nome"] = nome_atual
                        salvar_config_dashboard(st.session_state.chart_ids, st.session_state.charts, 
                                                st.session_state.presets, st.session_state.layouts_setores)
                        st.rerun()
                    c_save1, c_save2 = st.columns([7,3])
                    nome_novo_preset = c_save1.text_input("Salvar como:", placeholder="Ex: Padrão Pizza", label_visibility="collapsed", key=f"txt_pre_{eid}")
                    if c_save2.button("Salvar", use_container_width=True, key=f"btn_sv_{eid}"):
                        if nome_novo_preset.strip():
                            st.session_state.presets[nome_novo_preset.strip()] = copy.deepcopy(conf)
                            salvar_config_dashboard(st.session_state.chart_ids, st.session_state.charts, 
                                                    st.session_state.presets, st.session_state.layouts_setores)
                            st.success("✅ Predefinição salva!"); time.sleep(1); st.rerun()

                conf["nome"] = st.text_input("Título", conf["nome"])
                conf["tipo_fonte"] = st.radio("Origem", ["Local","URL"], index=0 if conf["tipo_fonte"]=="Local" else 1)
                
                lista_setores = obter_lista_setores()
                idx_setor = lista_setores.index(conf["setor"]) if conf["setor"] in lista_setores else 0
                conf["setor"] = st.selectbox("Setor (agrupamento de abas)", lista_setores, index=idx_setor)
                
                df_preview = pd.DataFrame()
                abas_disponiveis = []
                cols = ["..."]
                
                if conf["tipo_fonte"] == "URL":
                    conf["url"] = st.text_input("Link URL", conf["url"])
                    if conf["url"]:
                        with st.spinner("Carregando dados..."):
                            df_preview = carregar_planilha_com_cache_url(conf["url"])
                else:
                    if conf["setor"] != "Selecione...":
                        ps = os.path.join(PASTA_RAIZ, conf["setor"])
                        if os.path.exists(ps):
                            arquivos = ["..."] + [f for f in os.listdir(ps) if f.endswith(".xlsx")]
                            valor_atual_arquivo = conf.get("arquivo", conf.get("arq","..."))
                            conf["arquivo"] = st.selectbox("Planilha Excel", arquivos, index=arquivos.index(valor_atual_arquivo) if valor_atual_arquivo in arquivos else 0)
                            if conf["arquivo"] != "...":
                                caminho_arquivo = os.path.join(ps, conf["arquivo"])
                                try:
                                    with st.spinner("Lendo abas..."):
                                        with open(caminho_arquivo, "rb") as f:
                                            aba_bytes = io.BytesIO(f.read())
                                        xls = pd.ExcelFile(aba_bytes, engine="openpyxl")
                                        abas_disponiveis = xls.sheet_names
                                except:
                                    abas_disponiveis = []
                                
                                if abas_disponiveis:
                                    if conf.get("aba", "...") not in abas_disponiveis:
                                        conf["aba"] = abas_disponiveis[0]
                                    conf["aba"] = st.selectbox("Aba", abas_disponiveis, index=abas_disponiveis.index(conf["aba"]))
                                else:
                                    conf["aba"] = st.text_input("Aba", conf["aba"])
                                
                                try:
                                    with st.spinner("Carregando dados..."):
                                        df_preview = carregar_planilha_sem_cache(caminho_arquivo, conf["aba"])
                                except: st.warning("Erro ao carregar arquivo local.")
                    else:
                        st.warning(f"Pasta '{conf['setor']}' não encontrada.")
                
                if not df_preview.empty:
                    cols = ["..."] + list(df_preview.columns)
                    conf["x"] = st.selectbox("Eixo X", cols, index=cols.index(conf["x"]) if conf["x"] in cols else 0)
                    conf["y"] = st.selectbox("Realizado", cols, index=cols.index(conf["y"]) if conf["y"] in cols else 0)
                    conf["meta"] = st.selectbox("Meta", cols, index=cols.index(conf["meta"]) if conf["meta"] in cols else 0)
                    conf["subgrupo"] = st.selectbox("Subgrupo", cols, index=cols.index(conf.get("subgrupo","...")) if conf.get("subgrupo","...") in cols else 0)
                    st.markdown("---")
                    conf["palavras_chave"] = st.text_input("Palavras-chave (vírgula)", conf.get("palavras_chave",""))
                    st.markdown("---")
                    conf["agrupamento_data"] = st.radio("Agrupar datas por:", ["Dia","Mês","Ano"], index=["Dia","Mês","Ano"].index(conf.get("agrupamento_data","Dia")), horizontal=True)
                    st.markdown("---")
                    conf["mostrar_total_legenda"] = st.checkbox("Mostrar Totais", value=conf.get("mostrar_total_legenda",True), key=f"tog_leg_{eid}")
                    conf["formato_rotulo"] = st.radio("Formato valores:", ["Valor","Porcentagem"], index=0 if conf.get("formato_rotulo","Valor")=="Valor" else 1, horizontal=True)
                    st.markdown("---")
                    
                    st.markdown("**🔍 Filtros Dropdown (Múltiplos)**")
                    if "filtros_multiplos" not in conf:
                        conf["filtros_multiplos"] = []
                    if "filtros_selecionados" not in conf:
                        conf["filtros_selecionados"] = {}
                    
                    filtros_atuais = conf["filtros_multiplos"]
                    para_remover = None
                    
                    for idx, f_col in enumerate(filtros_atuais):
                        c1, c2 = st.columns([8, 2])
                        with c1:
                            idx_sel = cols.index(f_col) if f_col in cols else 0
                            novo_f = st.selectbox(f"Filtro {idx+1}", cols, index=idx_sel, key=f"sel_f_{eid}_{idx}", label_visibility="collapsed")
                            filtros_atuais[idx] = novo_f
                        with c2:
                            if st.button("🗑️", key=f"del_f_{eid}_{idx}", help="Remover este filtro"):
                                para_remover = idx
                    
                    if para_remover is not None:
                        filtros_atuais.pop(para_remover)
                        conf["filtros_selecionados"] = {k:v for k,v in conf["filtros_selecionados"].items() if int(k) != para_remover}
                        salvar_config_dashboard(st.session_state.chart_ids, st.session_state.charts, 
                                                st.session_state.presets, st.session_state.layouts_setores)
                        st.rerun()

                    if st.button("➕ Adicionar Filtro", key=f"add_f_{eid}"):
                        filtros_atuais.append("...")
                        salvar_config_dashboard(st.session_state.chart_ids, st.session_state.charts, 
                                                st.session_state.presets, st.session_state.layouts_setores)
                        st.rerun()
                    
                    conf["filtro_data_col"] = st.selectbox("Filtro período para coluna data:", cols, index=cols.index(conf.get("filtro_data_col","...")) if conf.get("filtro_data_col","...") in cols else 0)
                    st.markdown("---")

                conf["tipo"] = st.selectbox("Tipo", ["Barras","Pizza","Linhas"], index=["Barras","Pizza","Linhas"].index(conf["tipo"]))
                conf["modo"] = st.selectbox("Cálculo", ["Somar","Contar"], index=0 if conf["modo"]=="Somar" else 1)
                conf["ordem"] = st.selectbox("Ordenação", ["Mês","Valor","A-Z"], index=["Mês","Valor","A-Z"].index(conf.get("ordem","Mês")))
                
                # ---------- MODO DE VISUALIZAÇÃO ----------
                conf["modo_visualizacao"] = st.radio(
                    "📊 Modo de Visualização",
                    options=["Gráfico", "Tabela", "Ambos"],
                    index=["Gráfico", "Tabela", "Ambos"].index(conf.get("modo_visualizacao", "Gráfico")),
                    horizontal=True
                )
                # -----------------------------------------

                st.markdown("**🎨 Cores**")
                c_cor1, c_cor2 = st.columns(2)
                with c_cor1: conf["cor"] = st.color_picker("Principal", conf.get("cor", COR_ARQTEC))
                with c_cor2: conf["cor_meta"] = st.color_picker("Cor da Barra de Falta", conf.get("cor_meta", COR_META_PADRAO))
                cat_para_cores = conf.get("subgrupo","...") if conf.get("subgrupo","...") != "..." else conf.get("x","...")
                if not df_preview.empty and cat_para_cores != "..." and cat_para_cores in df_preview.columns:
                    df_preview[cat_para_cores] = df_preview[cat_para_cores].astype(str).str.strip().str.upper()
                    with st.expander(f"🖌️ Cores por {cat_para_cores}"):
                        if "cores_cats" not in conf: conf["cores_cats"] = {}
                        categorias = [str(x) for x in df_preview[cat_para_cores].dropna().unique() if str(x).strip()!=""][:30]
                        for i in range(0,len(categorias),2):
                            c_a,c_b = st.columns(2)
                            cat_a = categorias[i]
                            cor_padrao_a = PALETA_DIVERSA[i%len(PALETA_DIVERSA)]
                            cor_a = conf["cores_cats"].get(cat_a, cor_padrao_a)
                            with c_a: conf["cores_cats"][cat_a] = st.color_picker(cat_a[:15], cor_a, key=f"cor_{eid}_{cat_a}")
                            if i+1 < len(categorias):
                                cat_b = categorias[i+1]
                                cor_padrao_b = PALETA_DIVERSA[(i+1)%len(PALETA_DIVERSA)]
                                cor_b = conf["cores_cats"].get(cat_b, cor_padrao_b)
                                with c_b: conf["cores_cats"][cat_b] = st.color_picker(cat_b[:15], cor_b, key=f"cor_{eid}_{cat_b}")
                
                # ---------- LEGENDAS PERSONALIZADAS ----------
                with st.expander("🏷️ Legendas Personalizadas", expanded=False):
                    st.markdown("Formato: `chave = texto` (uma por linha)")
                    st.markdown("Exemplo:\n```\n1 = Pipeline 90%\nRealizado = Vendas 2024\nFalta = Ainda falta\nMeta Acumulada = Meta Anual\nEixo Y - Realizado = Valor Realizado\nEixo Y - Falta = Valor Restante\n```")
                    legenda_raw = st.text_area(
                        "Legendas",
                        value="\n".join([f"{k} = {v}" for k, v in conf.get("legendas_personalizadas", {}).items()]),
                        height=200,
                        key=f"leg_{eid}"
                    )
                    novas_legendas = {}
                    for linha in legenda_raw.split("\n"):
                        linha = linha.strip()
                        if "=" in linha:
                            chave, texto = linha.split("=", 1)
                            chave = chave.strip()
                            texto = texto.strip()
                            if chave and texto:
                                novas_legendas[chave] = texto
                    conf["legendas_personalizadas"] = novas_legendas
                # ----------------------------------------------------

                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("💾 Salvar Alterações", use_container_width=True):
                    for k in ["data_inicio", "data_fim"]:
                        if conf.get(k) and hasattr(conf[k], 'isoformat'):
                            conf[k] = conf[k].isoformat()
                    salvar_config_dashboard(st.session_state.chart_ids, st.session_state.charts, 
                                            st.session_state.presets, st.session_state.layouts_setores)
                    st.success("Alterações salvas!")
        for cid, conf in st.session_state.charts.items():
            for k in ["data_inicio", "data_fim"]:
                if conf.get(k) and hasattr(conf[k], 'isoformat'):
                    conf[k] = conf[k].isoformat()
        salvar_config_dashboard(st.session_state.chart_ids, st.session_state.charts, 
                                st.session_state.presets, st.session_state.layouts_setores)
    st.divider()
    st.markdown("💡 **Dica:** O sistema agora está liberando os arquivos do Excel imediatamente após a leitura. Pode salvar suas edições tranquilamente.")
    if st.button("🚪 Sair", use_container_width=True):
        if st.session_state.logged_user in usuarios_db:
            usuarios_db[st.session_state.logged_user]["token"] = ""
            salvar_usuarios(usuarios_db)
        st.session_state.auth = False
        st.session_state.logged_user = ""
        if "t" in st.query_params: del st.query_params["t"]
        st.rerun()

# ============================================================
# 4. CORPO PRINCIPAL (COM NOTIFICAÇÕES EM TEMPO REAL)
# ============================================================
cor_texto_atual = obter_cor_texto()

def desenhar_graficos():
    is_tv_mode = rotacao_automatica and not bloquear_refresh_por_edicao
    setores_ativos = sorted(list(set(
        st.session_state.charts[cid].get("setor","Geral") 
        for cid in st.session_state.chart_ids_visiveis 
        if st.session_state.charts[cid].get("setor","Selecione...") != "Selecione..."
    )))
    
    # -----------------------------------------------------------
    # PRIMEIRA PASSADA: carrega dados e atualiza notificações
    # -----------------------------------------------------------
    for setor in setores_ativos:
        graficos_do_setor = [cid for cid in st.session_state.chart_ids_visiveis if st.session_state.charts[cid].get("setor","Geral") == setor]
        for cid in graficos_do_setor:
            conf = st.session_state.charts[cid]
            if conf["x"] == "..." or (conf["y"] == "..." and conf["modo"] != "Contar"):
                continue
            try:
                if conf["tipo_fonte"] == "URL":
                    df_c = carregar_planilha_com_cache_url(conf["url"])
                    if not df_c.empty:
                        hash_atual = hashlib.md5(df_c.head(1000).to_csv(index=False).encode()).hexdigest()
                    else:
                        hash_atual = ""
                else:
                    nome_arquivo = conf.get("arquivo", conf.get("arq","..."))
                    caminho = os.path.join(PASTA_RAIZ, conf["setor"], nome_arquivo)
                    if os.path.exists(caminho):
                        try:
                            with open(caminho, "rb") as f:
                                bytes_arquivo = f.read()
                            hash_atual = hashlib.md5(bytes_arquivo).hexdigest()
                        except:
                            hash_atual = ""
                    else:
                        hash_atual = ""
                hash_anterior = st.session_state.hash_agregado.get(cid, "")
                if hash_atual != hash_anterior:
                    st.session_state.setores_atualizados[setor] = time.time()
                    st.session_state.hash_agregado[cid] = hash_atual
            except:
                pass
    # -----------------------------------------------------------
    # SEGUNDA PASSADA: renderiza abas e gráficos (agora com notificações atualizadas)
    # -----------------------------------------------------------
    if is_tv_mode:
        if "rotacao_idx" not in st.session_state: st.session_state.rotacao_idx = 0
        if setores_ativos:
            setor_da_vez = setores_ativos[st.session_state.rotacao_idx % len(setores_ativos)]
            html_abas = "<div style='display: flex; gap: 24px; margin-bottom: 20px; border-bottom: 1px solid rgba(128,128,128,0.2);'>"
            for s in setores_ativos:
                ts = st.session_state.setores_atualizados.get(s, 0)
                bolinha = "🟢" if (time.time() - ts) < 10 else ""
                html_abas += f"<div style='padding-bottom:8px; font-size:1rem;'>{bolinha} {s}</div>"
            html_abas += "</div>"
            st.markdown(html_abas, unsafe_allow_html=True)
            lista_iteracao = [(setor_da_vez, st.container())]
        else: lista_iteracao = []
    else:
        if setores_ativos:
            abas_labels = []
            for s in setores_ativos:
                ts = st.session_state.setores_atualizados.get(s, 0)
                bolinha = "🟢 " if (time.time() - ts) < 10 else ""
                abas_labels.append(f"{bolinha}{s}")
            abas = st.tabs(abas_labels)
            lista_iteracao = list(zip(setores_ativos, abas))
        else:
            lista_iteracao = []

    for setor, container_setor in lista_iteracao:
        if st.session_state.personalizar_layout and setor in st.session_state.layouts_setores:
            cfg = st.session_state.layouts_setores[setor]
            n_cols = cfg["cols"]
            n_altura = cfg["height"]
        else:
            n_cols = num_cols
            n_altura = altura_grafico

        with container_setor:
            graficos_do_setor = [cid for cid in st.session_state.chart_ids_visiveis if st.session_state.charts[cid].get("setor","Geral") == setor]
            if not graficos_do_setor: continue
            colunas_grid = st.columns(n_cols)
            for index, cid in enumerate(graficos_do_setor):
                conf = st.session_state.charts[cid]
                is_pct = (conf.get("formato_rotulo") == "Porcentagem")
                legendas_pers = conf.get("legendas_personalizadas", {})
                modo_vis = conf.get("modo_visualizacao", "Gráfico")
                with colunas_grid[index % n_cols]:
                    container_grafico = st.container(border=True)
                    with container_grafico:
                        tit_container = st.empty()
                        grafico_placeholder = st.empty()
                        if conf["x"] != "..." and (conf["y"] != "..." or conf["modo"] == "Contar"):
                            try:
                                with st.spinner(f"📊 {conf['nome']}..."):
                                    if conf["tipo_fonte"] == "URL":
                                        df_c = carregar_planilha_com_cache_url(conf["url"])
                                    else:
                                        nome_arquivo = conf.get("arquivo", conf.get("arq","..."))
                                        caminho = os.path.join(PASTA_RAIZ, conf["setor"], nome_arquivo)
                                        df_c = carregar_planilha_sem_cache(caminho, conf["aba"])
                                
                                if not df_c.empty:
                                    cx, cy, cm = conf["x"], conf["y"], conf["meta"]
                                    cg = conf.get("subgrupo","...")
                                    if conf.get("agrupamento_data") and cx in df_c.columns:
                                        amostra = df_c[cx].dropna()
                                        if len(amostra) > 0:
                                            test_date = pd.to_datetime(amostra.iloc[0], errors='coerce')
                                            if pd.notna(test_date):
                                                df_c = aplicar_agrupamento_data(df_c, cx, conf.get("agrupamento_data","Dia"))
                                    if cx in df_c.columns:
                                        df_c[cx] = df_c[cx].astype(str).str.strip().str.upper()
                                    if cg != "..." and cg in df_c.columns:
                                        serie_str = df_c[cg].astype(str).str.strip()
                                        if serie_str.str.contains(r"\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2}").any():
                                            try:
                                                datas = pd.to_datetime(serie_str, errors='coerce', dayfirst=True)
                                                df_c[cg] = datas.dt.strftime("%Y").fillna(serie_str).astype(str).str.upper()
                                            except: df_c[cg] = serie_str.str.upper()
                                        else: df_c[cg] = serie_str.str.upper()
                                    
                                    # -------------------------------------------------------
                                    # FILTRO DE DATA (APLICADO SEMPRE, CONTROLE SÓ ADMIN)
                                    # -------------------------------------------------------
                                    f_data_col = conf.get("filtro_data_col", "...")
                                    if f_data_col != "..." and f_data_col in df_c.columns:
                                        try:
                                            df_c[f_data_col] = converter_coluna_data_robusto(df_c[f_data_col])
                                            df_valido = df_c[df_c[f_data_col].notna() & (df_c[f_data_col].dt.year >= 1900) & (df_c[f_data_col].dt.year <= 2100)]
                                            if not df_valido.empty:
                                                min_date = df_valido[f_data_col].min().date()
                                                max_date = df_valido[f_data_col].max().date()
                                                if min_date.year < 1900: min_date = datetime(2000,1,1).date()
                                                if max_date.year > 2100: max_date = datetime.today().date()
                                                
                                                data_inicio, data_fim = carregar_filtro_data_url(cid, min_date, max_date)
                                                if data_inicio == min_date and data_fim == max_date:
                                                    saved_inicio = conf.get("data_inicio")
                                                    saved_fim = conf.get("data_fim")
                                                    if saved_inicio and saved_fim:
                                                        try:
                                                            data_inicio = datetime.fromisoformat(saved_inicio).date()
                                                            data_fim = datetime.fromisoformat(saved_fim).date()
                                                        except:
                                                            pass
                                                if data_inicio < min_date or data_inicio > max_date:
                                                    data_inicio = min_date
                                                if data_fim < min_date or data_fim > max_date:
                                                    data_fim = max_date
                                                if data_inicio > data_fim:
                                                    data_inicio, data_fim = data_fim, data_inicio

                                                if is_admin:
                                                    if conf.get("tipo") == "Linhas":
                                                        datas_unicas = sorted(df_c[cx].dropna().unique())
                                                        if len(datas_unicas) >= 2:
                                                            datas_labels = list(datas_unicas)
                                                            inicio_idx = max(0, min(len(datas_labels)-1, datas_labels.index(data_inicio.strftime("%d/%m/%Y")))) if data_inicio.strftime("%d/%m/%Y") in datas_labels else 0
                                                            fim_idx = max(0, min(len(datas_labels)-1, datas_labels.index(data_fim.strftime("%d/%m/%Y")))) if data_fim.strftime("%d/%m/%Y") in datas_labels else len(datas_labels)-1
                                                            slider_range = st.select_slider(
                                                                f"📅 Período ({f_data_col})",
                                                                options=datas_labels,
                                                                value=(datas_labels[inicio_idx], datas_labels[fim_idx]),
                                                                key=f"slider_{cid}"
                                                            )
                                                            if slider_range:
                                                                data_inicio = datetime.strptime(slider_range[0], "%d/%m/%Y").date()
                                                                data_fim = datetime.strptime(slider_range[1], "%d/%m/%Y").date()
                                                                salvar_filtro_data_url(cid, data_inicio, data_fim)
                                                                conf["data_inicio"] = data_inicio.isoformat()
                                                                conf["data_fim"] = data_fim.isoformat()
                                                    else:
                                                        datas_selecionadas = st.date_input(
                                                            f"📅 Período ({f_data_col})",
                                                            value=(data_inicio, data_fim),
                                                            min_value=min_date, max_value=max_date,
                                                            format="DD/MM/YYYY", key=f"cal_{cid}"
                                                        )
                                                        st.session_state.filtros_data[cid] = datas_selecionadas
                                                        if isinstance(datas_selecionadas, tuple) and len(datas_selecionadas)==2:
                                                            salvar_filtro_data_url(cid, datas_selecionadas[0], datas_selecionadas[1])
                                                            conf["data_inicio"] = datas_selecionadas[0].isoformat()
                                                            conf["data_fim"] = datas_selecionadas[1].isoformat()
                                                            data_inicio, data_fim = datas_selecionadas[0], datas_selecionadas[1]
                                                        elif len(datas_selecionadas) == 1:
                                                            data_inicio = datas_selecionadas[0]
                                                            conf["data_inicio"] = data_inicio.isoformat()
                                                            conf["data_fim"] = data_inicio.isoformat()
                                                            data_fim = data_inicio
                                                    salvar_config_dashboard(st.session_state.chart_ids, st.session_state.charts, 
                                                                            st.session_state.presets, st.session_state.layouts_setores)
                                                
                                                df_c = df_c[df_c[f_data_col].isna() | ((df_c[f_data_col].dt.date >= data_inicio) & (df_c[f_data_col].dt.date <= data_fim))]
                                        except Exception as e:
                                            st.warning(f"Erro no filtro de data: {e}")
                                    # -------------------------------------------------------

                                    if cx in df_c.columns:
                                        df_c = df_c[df_c[cx].astype(str).str.strip() != ""]
                                        padrao_filtro = "|".join(["TOTAL","TOTAIS","ORÇADO","MÉDIA","SUBTOTAL","SUM","AVERAGE"])
                                        df_c = df_c[~df_c[cx].astype(str).str.upper().str.contains(padrao_filtro, na=False)]
                                    lista_chaves = [kw.strip().upper() for kw in conf.get("palavras_chave","").split(",") if kw.strip()]
                                    if lista_chaves:
                                        def extrair_chave(texto):
                                            for chave in lista_chaves:
                                                if chave in str(texto): return chave
                                            return None
                                        df_c["CHAVE_FILTRADA"] = df_c[cx].apply(extrair_chave)
                                        df_c = df_c[df_c["CHAVE_FILTRADA"].notna()]
                                        df_c[cx] = df_c["CHAVE_FILTRADA"]
                                    
                                    # -------------------------------------------------------
                                    # FILTROS DROPDOWN (APLICADOS SEMPRE, CONTROLES SÓ ADMIN)
                                    # -------------------------------------------------------
                                    filtros_para_aplicar = [f for f in conf.get("filtros_multiplos", []) if f != "..." and f in df_c.columns]
                                    if filtros_para_aplicar:
                                        if is_admin:
                                            cols_filtros = st.columns(len(filtros_para_aplicar))
                                        for idx, f_col in enumerate(filtros_para_aplicar):
                                            df_c[f_col] = df_c[f_col].astype(str).str.strip().str.upper()
                                            txt_todos = f"--- Todos ({f_col}) ---"
                                            v_unicos = [txt_todos] + sorted({str(v).strip() for v in df_c[f_col].dropna() if str(v).strip()!=""})
                                            key_filtro = f"dyn_filt_{cid}_{idx}"
                                            val_salvo = conf.get("filtros_selecionados", {}).get(str(idx), txt_todos)
                                            val_anterior = st.session_state.get(key_filtro, val_salvo)
                                            if val_anterior not in v_unicos:
                                                val_anterior = txt_todos
                                            
                                            f_val = val_anterior
                                            if is_admin:
                                                with cols_filtros[idx]:
                                                    f_val = st.selectbox(
                                                        f"Filtro: {f_col}",
                                                        v_unicos,
                                                        index=v_unicos.index(val_anterior),
                                                        key=key_filtro,
                                                        label_visibility="collapsed"
                                                    )
                                                    conf["filtros_selecionados"][str(idx)] = f_val
                                                    salvar_config_dashboard(st.session_state.chart_ids, st.session_state.charts, 
                                                                            st.session_state.presets, st.session_state.layouts_setores)
                                            
                                            if f_val != txt_todos:
                                                df_c = df_c[df_c[f_col].astype(str).str.strip() == f_val]
                                    # -------------------------------------------------------

                                    if df_c.empty:
                                        tit_container.markdown(f"<div style='font-size:1.2rem;font-weight:bold'>{conf['nome']} <span style='float:right;font-size:0.8rem;color:gray'>Total: 0</span></div>", unsafe_allow_html=True)
                                        grafico_placeholder.info("Sem dados no período/filtro.")
                                        continue
                                    
                                    tem_subgrupo = (cg != "..." and cg in df_c.columns and conf["tipo"] != "Pizza")
                                    agrupamento = [cx, cg] if tem_subgrupo else [cx]
                                    if conf["modo"] == "Somar":
                                        df_c[cy] = limpar_numero(df_c[cy])
                                        agg = {cy:"sum"}
                                        if cm != "...": df_c[cm] = limpar_numero(df_c[cm]); agg[cm]="sum"
                                        res = df_c.groupby(agrupamento).agg(agg).reset_index()
                                        yf = cy
                                        hover_fmt = "%{y:,.2f}"
                                    else:
                                        res = df_c.groupby(agrupamento).size().reset_index(name="VAL")
                                        yf = "VAL"
                                        if cm != "...":
                                            df_c[cm] = limpar_numero(df_c[cm])
                                            m_map = df_c.groupby(agrupamento)[cm].sum().reset_index()
                                            res = pd.merge(res, m_map, on=agrupamento)
                                        hover_fmt = "%{y:d}"
                                    res = res[res[cx].astype(str).str.strip() != ""]
                                    if tem_subgrupo: res = res[res[cg].astype(str).str.strip() != ""]
                                    total_grafico = res[yf].sum()
                                    str_total = formatar_abreviado(total_grafico) if conf["modo"]=="Somar" else f"{int(total_grafico):,}".replace(",",".")
                                    
                                    tit_container.markdown(f"""
                                    <div style='font-size:1.2rem;font-weight:bold;margin-bottom:0;'>
                                        {conf['nome']} 
                                        <span style='float:right;font-size:0.8rem;color:gray;background:rgba(128,128,128,0.1);padding:2px 8px;border-radius:5px;'>Total: {str_total}</span>
                                    </div>
                                    """, unsafe_allow_html=True)
                                    
                                    # --- LEGENDAS NO EIXO X E SUBGRUPOS ---
                                    totais_cx = res.groupby(cx)[yf].sum()
                                    mapa_cx = {}
                                    for cx_key, cx_val in totais_cx.items():
                                        nome_amigavel_x = legendas_pers.get(str(cx_key), str(cx_key))
                                        if conf.get("mostrar_total_legenda", True):
                                            v_form = formatar_abreviado(cx_val) if conf["modo"]=="Somar" else f"{int(cx_val):,}".replace(",",".")
                                            mapa_cx[str(cx_key)] = f"{nome_amigavel_x} ({v_form})"
                                        else: 
                                            mapa_cx[str(cx_key)] = nome_amigavel_x
                                            
                                    res['cx_display'] = res[cx].astype(str).map(mapa_cx)
                                    
                                    mapa_subgrupos = {}
                                    if tem_subgrupo:
                                        totais_sg = res.groupby(cg)[yf].sum()
                                        for sg_key, sg_val in totais_sg.items():
                                            nome_amigavel_sg = legendas_pers.get(str(sg_key), str(sg_key))
                                            if conf.get("mostrar_total_legenda", True):
                                                v_form = formatar_abreviado(sg_val) if conf["modo"]=="Somar" else f"{int(sg_val):,}".replace(",",".")
                                                mapa_subgrupos[str(sg_key)] = f"{nome_amigavel_sg} ({v_form})"
                                            else: 
                                                mapa_subgrupos[str(sg_key)] = nome_amigavel_sg

                                    ordem_tipo = conf.get("ordem", "Mês")
                                    meses_map = {
                                        "janeiro":0, "fevereiro":1, "marco":2, "abril":3, "maio":4, "junho":5,
                                        "julho":6, "agosto":7, "setembro":8, "outubro":9, "novembro":10, "dezembro":11
                                    }
                                    if ordem_tipo == "Mês":
                                        res["_mes_normalizado"] = res[cx].astype(str).str.lower().apply(remover_acentos)
                                        res["_o"] = res["_mes_normalizado"].map(meses_map).fillna(99)
                                        sort_cols = ["_o", cg] if tem_subgrupo else ["_o"]
                                        res = res.sort_values(sort_cols).drop(["_o", "_mes_normalizado"], axis=1)
                                    elif ordem_tipo == "Valor": res = res.sort_values(yf, ascending=False)
                                    else: res = res.sort_values([cx, cg] if tem_subgrupo else [cx])
                                    
                                    # ============================================================
                                    # EXIBIÇÃO CONDICIONAL: TABELA, GRÁFICO OU AMBOS
                                    # ============================================================
                                    
                                    # Preparar DataFrame para tabela (com legendas)
                                    if modo_vis in ("Tabela", "Ambos"):
                                        df_tabela = res[['cx_display', yf]].copy()
                                        df_tabela.columns = [cx, 'Valor']
                                        if tem_subgrupo:
                                            df_tabela[cg] = res[cg].map(lambda x: legendas_pers.get(str(x), str(x)))
                                            df_tabela = df_tabela[[cx, cg, 'Valor']]
                                        if cm != "...":
                                            df_tabela['Meta'] = res[cm] if cm in res.columns else 0
                                    
                                    # Exibir tabela (se for o modo)
                                    if modo_vis == "Tabela":
                                        st.dataframe(df_tabela, use_container_width=True)
                                    elif modo_vis == "Ambos":
                                        st.dataframe(df_tabela, use_container_width=True)
                                        st.markdown("---")
                                    
                                    # Exibir gráfico (se for o modo)
                                    if modo_vis in ("Gráfico", "Ambos"):
                                        fig = go.Figure()
                                        cor_principal = conf.get("cor", COR_ARQTEC)
                                        cor_meta_barra = conf.get("cor_meta", COR_META_PADRAO)
                                        LINHA_META_VERDE = COR_META_PADRAO
                                        texto_config = {'textposition': 'auto', 'textfont': dict(size=10, color=cor_texto_atual)}
                                        
                                        nome_y_realizado = legendas_pers.get("Eixo Y - Realizado", "Realizado")
                                        nome_y_falta = legendas_pers.get("Eixo Y - Falta", "Falta")
                                        
                                        if tem_subgrupo:
                                            subgrupos_unicos = res[cg].unique()
                                            for i, sg in enumerate(subgrupos_unicos):
                                                df_sg = res[res[cg]==sg]
                                                cor_sg = conf.get("cores_cats",{}).get(str(sg), PALETA_DIVERSA[i%len(PALETA_DIVERSA)])
                                                textos_abrev = [f"{(v/total_grafico)*100:.1f}%".replace('.',',') if is_pct and total_grafico>0 else formatar_abreviado(v) for v in df_sg[yf]]
                                                nome_legenda = mapa_subgrupos.get(str(sg), str(sg))
                                                
                                                if conf["tipo"]=="Barras":
                                                    fig.add_trace(go.Bar(
                                                        name=nome_legenda, x=df_sg['cx_display'], y=df_sg[yf],
                                                        text=textos_abrev, textposition=texto_config['textposition'],
                                                        textfont=texto_config['textfont'], marker_color=cor_sg,
                                                        hovertemplate=f"<b>%{{x}} - {sg}</b><br>{nome_y_realizado}: {hover_fmt}<extra></extra>"
                                                    ))
                                                elif conf["tipo"]=="Linhas":
                                                    fig.add_trace(go.Scatter(
                                                        name=nome_legenda, x=df_sg['cx_display'], y=df_sg[yf],
                                                        mode='lines+markers+text', text=textos_abrev, textposition='top center',
                                                        textfont=dict(size=10, color=cor_texto_atual),
                                                        line=dict(color=cor_sg, width=3),
                                                        hovertemplate=f"<b>%{{x}} - {sg}</b><br>{nome_y_realizado}: {hover_fmt}<extra></extra>"
                                                    ))
                                            fig.update_layout(barmode='group', showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5))
                                            
                                            if cm != "...":
                                                df_meta = df_c.groupby(cx)[cm].sum().reset_index()
                                                df_meta['cx_display'] = df_meta[cx].astype(str).map(mapa_cx)
                                                if ordem_tipo == "Mês":
                                                    df_meta["_mes_normalizado"] = df_meta[cx].astype(str).str.lower().apply(remover_acentos)
                                                    df_meta["_o"] = df_meta["_mes_normalizado"].map(meses_map).fillna(99)
                                                    df_meta = df_meta.sort_values("_o").drop(["_o", "_mes_normalizado"], axis=1)
                                                df_meta['META_ACUMULADA'] = df_meta[cm].cumsum()
                                                nome_meta = legendas_pers.get("Meta Acumulada", "Meta Acumulada")
                                                fig.add_trace(go.Scatter(
                                                    name=nome_meta,
                                                    x=df_meta['cx_display'], y=df_meta['META_ACUMULADA'],
                                                    mode='lines',
                                                    yaxis='y2',
                                                    line=dict(color=LINHA_META_VERDE, width=3, dash='dot'),
                                                    hovertemplate=f"<b>%{{x}}</b><br>Meta Acumulada: %{{y:,.2f}}<extra></extra>"
                                                ))
                                        else:
                                            if conf["tipo"]=="Barras":
                                                if cm=="...":
                                                    cores = [conf.get("cores_cats",{}).get(str(x), PALETA_DIVERSA[i%len(PALETA_DIVERSA)]) for i,x in enumerate(res[cx])]
                                                    textos_abrev = [f"{(v/total_grafico)*100:.1f}%".replace('.',',') if is_pct and total_grafico>0 else formatar_abreviado(v) for v in res[yf]]
                                                    fig.add_trace(go.Bar(
                                                        x=res['cx_display'], y=res[yf], text=textos_abrev,
                                                        textposition=texto_config['textposition'], textfont=texto_config['textfont'],
                                                        marker_color=cores,
                                                        hovertemplate=f"<b>%{{x}}</b><br>{nome_y_realizado}: {hover_fmt}<extra></extra>"
                                                    ))
                                                else:
                                                    res['Falta'] = res.apply(lambda row: max(row[cm]-row[yf],0), axis=1)
                                                    total_meta_geral = res[cm].sum()
                                                    txt_realizado = [f"{(v/total_grafico)*100:.1f}%".replace('.',',') if is_pct and total_grafico>0 else formatar_abreviado(v) for v in res[yf]]
                                                    txt_falta = [f"{(v/total_meta_geral)*100:.1f}%".replace('.',',') if is_pct and total_meta_geral>0 and v>0 else (formatar_abreviado(v) if v>0 else "") for v in res['Falta']]
                                                    nome_realizado = legendas_pers.get("Realizado", nome_y_realizado)
                                                    nome_falta = legendas_pers.get("Falta", nome_y_falta)
                                                    
                                                    fig.add_trace(go.Bar(
                                                        name=nome_realizado, x=res['cx_display'], y=res[yf],
                                                        text=txt_realizado, textposition=texto_config['textposition'],
                                                        textfont=texto_config['textfont'], marker_color=cor_principal,
                                                        hovertemplate=f"<b>%{{x}}</b><br>{nome_y_realizado}: {hover_fmt}<extra></extra>"
                                                    ))
                                                    fig.add_trace(go.Bar(
                                                        name=nome_falta, x=res['cx_display'], y=res['Falta'],
                                                        text=txt_falta, textposition=texto_config['textposition'],
                                                        textfont=texto_config['textfont'], marker_color=cor_meta_barra,
                                                        hovertemplate=f"<b>%{{x}}</b><br>{nome_y_falta}: {hover_fmt}<extra></extra>"
                                                    ))
                                                    fig.update_layout(barmode='stack', showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5))
                                                    df_meta = df_c.groupby(cx)[cm].sum().reset_index()
                                                    df_meta['cx_display'] = df_meta[cx].astype(str).map(mapa_cx)
                                                    if ordem_tipo == "Mês":
                                                        df_meta["_mes_normalizado"] = df_meta[cx].astype(str).str.lower().apply(remover_acentos)
                                                        df_meta["_o"] = df_meta["_mes_normalizado"].map(meses_map).fillna(99)
                                                        df_meta = df_meta.sort_values("_o").drop(["_o", "_mes_normalizado"], axis=1)
                                                    df_meta['META_ACUMULADA'] = df_meta[cm].cumsum()
                                                    nome_meta = legendas_pers.get("Meta Acumulada", "Meta Acumulada")
                                                    fig.add_trace(go.Scatter(
                                                        name=nome_meta,
                                                        x=df_meta['cx_display'], y=df_meta['META_ACUMULADA'],
                                                        mode='lines',
                                                        yaxis='y2',
                                                        line=dict(color=LINHA_META_VERDE, width=3, dash='dot'),
                                                        hovertemplate=f"<b>%{{x}}</b><br>Meta Acumulada: %{{y:,.2f}}<extra></extra>"
                                                    ))
                                            elif conf["tipo"]=="Pizza":
                                                cores = [conf.get("cores_cats",{}).get(str(x), PALETA_DIVERSA[i%len(PALETA_DIVERSA)]) for i,x in enumerate(res[cx])]
                                                textos_abrev = [formatar_abreviado(v) for v in res[yf]]
                                                fig.add_trace(go.Pie(
                                                    labels=res['cx_display'], values=res[yf], text=textos_abrev,
                                                    textinfo='label+percent' if is_pct else 'label+text',
                                                    textfont=dict(size=11, color=cor_texto_atual),
                                                    hovertemplate=f"<b>%{{label}}</b><br>Valor: %{{value:,.2f}}<extra></extra>" if conf["modo"]=="Somar" else f"<b>%{{label}}</b><br>Contagem: %{{value:d}}<extra></extra>",
                                                    marker=dict(colors=cores), hole=0.4
                                                ))
                                            elif conf["tipo"]=="Linhas":
                                                textos_abrev = [f"{(v/total_grafico)*100:.1f}%".replace('.',',') if is_pct and total_grafico>0 else formatar_abreviado(v) for v in res[yf]]
                                                nome_realizado = legendas_pers.get("Realizado", nome_y_realizado)
                                                fig.add_trace(go.Scatter(
                                                    name=nome_realizado, x=res['cx_display'], y=res[yf],
                                                    mode='lines+markers+text', text=textos_abrev, textposition='top center',
                                                    textfont=dict(size=10, color=cor_texto_atual),
                                                    line=dict(color=cor_principal, width=3),
                                                    hovertemplate=f"<b>%{{x}}</b><br>{nome_y_realizado}: {hover_fmt}<extra></extra>"
                                                ))
                                                if cm != "...":
                                                    df_meta = df_c.groupby(cx)[cm].sum().reset_index()
                                                    df_meta['cx_display'] = df_meta[cx].astype(str).map(mapa_cx)
                                                    if ordem_tipo == "Mês":
                                                        df_meta["_mes_normalizado"] = df_meta[cx].astype(str).str.lower().apply(remover_acentos)
                                                        df_meta["_o"] = df_meta["_mes_normalizado"].map(meses_map).fillna(99)
                                                        df_meta = df_meta.sort_values("_o").drop(["_o", "_mes_normalizado"], axis=1)
                                                    df_meta['META_ACUMULADA'] = df_meta[cm].cumsum()
                                                    nome_meta = legendas_pers.get("Meta Acumulada", "Meta Acumulada")
                                                    fig.add_trace(go.Scatter(
                                                        name=nome_meta,
                                                        x=df_meta['cx_display'], y=df_meta['META_ACUMULADA'],
                                                        mode='lines',
                                                        yaxis='y2',
                                                        line=dict(color=LINHA_META_VERDE, width=3, dash='dot'),
                                                        hovertemplate=f"<b>%{{x}}</b><br>Meta Acumulada: %{{y:,.2f}}<extra></extra>"
                                                    ))
                                                    fig.update_layout(showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5))
                                        
                                        tem_meta = (cm != "...")
                                        layout_updates = dict(
                                            height=n_altura,
                                            margin=dict(l=5, r=5, t=30, b=5) if n_cols >= 3 else dict(l=10, r=10, t=30, b=10),
                                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                            separators=".,", transition_duration=0,
                                            font=dict(size=10, color=cor_texto_atual)
                                        )
                                        if conf["tipo"] != "Pizza":
                                            layout_updates.update(dict(
                                                yaxis=dict(
                                                    title=nome_y_realizado if conf["tipo"] in ("Barras", "Linhas") and cm != "..." else None,
                                                    tickformat=".3s" if conf["modo"]=="Somar" else "d",
                                                    gridcolor="rgba(128,128,128,0.2)"
                                                ),
                                                xaxis=dict(tickangle=-45, categoryorder='array', categoryarray=res['cx_display'].unique())
                                            ))
                                        if tem_meta and conf["tipo"] in ("Barras", "Linhas"):
                                            layout_updates.update(dict(
                                                yaxis2=dict(
                                                    title="Meta Acumulada",
                                                    overlaying='y',
                                                    side='right',
                                                    showgrid=False,
                                                    tickformat=".3s" if conf["modo"]=="Somar" else "d"
                                                )
                                            ))
                                        fig.update_layout(**layout_updates)
                                        
                                        grafico_placeholder.plotly_chart(fig, use_container_width=True, key=f"plt_{cid}")
                                    # ============================================================
                                    
                                    # ---------- TABELA DE DADOS BRUTOS + EXPORTAÇÃO ----------
                                    with st.expander("📋 Ver dados brutos", expanded=False):
                                        st.dataframe(df_c.head(500), use_container_width=True)
                                        csv = df_c.to_csv(index=False).encode('utf-8')
                                        st.download_button(
                                            label="⬇️ Baixar CSV",
                                            data=csv,
                                            file_name=f"{conf.get('nome', 'dados')}.csv",
                                            mime="text/csv",
                                            key=f"dl_{cid}"
                                        )
                                    # ----------------------------------------------------------
                                else:
                                    tit_container.markdown(f"#### {conf['nome']}")
                                    grafico_placeholder.warning("Aguardando dados...")
                            except Exception as e:
                                tit_container.markdown(f"#### {conf['nome']}")
                                grafico_placeholder.error(f"Erro: {str(e)[:100]}")
                        else:
                            tit_container.markdown(f"#### {conf['nome']}")
                            grafico_placeholder.info("Configure Eixo X e Realizado.")

# ============================================================
# 5. RENDERIZAÇÃO CONDICIONAL (COM FRAGMENTO)
# ============================================================
if st.session_state.auth:
    if not bloquear_refresh_por_edicao and auto_refresh and not rotacao_automatica:
        @st.fragment(run_every=intervalo_atualizacao)
        def fragmento_graficos():
            desenhar_graficos()
        fragmento_graficos()
    elif not bloquear_refresh_por_edicao and auto_refresh and rotacao_automatica:
        @st.fragment(run_every=tempo_rotacao)
        def fragmento_tv():
            if "rotacao_idx" not in st.session_state: st.session_state.rotacao_idx = 0
            st.session_state.rotacao_idx += 1
            desenhar_graficos()
        fragmento_tv()
    else:
        desenhar_graficos()
