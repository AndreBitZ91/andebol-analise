# teste.py — App de estatística de Andebol (Streamlit)
# Executar: python3 -m streamlit run teste.py

import os
import time
import copy
from io import BytesIO
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

import streamlit as st
import pandas as pd

# ===== Config =====
st.set_page_config(layout="wide")

try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=1000, key="tick_boot")
except Exception:
    pass

APP_VERSION = "1.1.0"

# ===== Utils =====
def now_ts() -> float:
    return time.time()

def fmt_hhmmss(seconds: float) -> str:
    s = max(0, int(seconds))
    return str(timedelta(seconds=s))

def format_mmss(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s//60:02d}:{s%60:02d}"

def deep_snapshot_from(keys: List[str], src: Dict[str, Any]) -> Dict[str, Any]:
    return {k: copy.deepcopy(src.get(k)) for k in keys}
# ===================== LEITURA DO EXCEL (PATCH ROBUSTO) =====================
from io import BytesIO

@st.cache_data(show_spinner=False)
def _parse_roster_excel(excel_bytes: bytes) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Recebe os bytes do Excel e devolve (atletas_df, oficiais_df, info_df) já normalizados.
    Só usa tipos serializáveis para funcionar bem com st.cache_data.
    """
    def _read_sheet(name: str) -> pd.DataFrame:
        bio = BytesIO(excel_bytes)
        return pd.read_excel(bio, sheet_name=name, engine="openpyxl")

    try:
        # Verificar folhas disponíveis de forma segura
        bio_names = BytesIO(excel_bytes)
        xls = pd.ExcelFile(bio_names, engine="openpyxl")
        required = {"Atletas", "Oficiais", "Info"}
        missing = required.difference(set(xls.sheet_names))
        if missing:
            raise ValueError(f"Falta(m) a(s) folha(s) obrigatória(s): {', '.join(sorted(missing))}")
    except ModuleNotFoundError:
        raise ModuleNotFoundError("Falta a dependência 'openpyxl'. Instala com: pip install openpyxl")

    # Ler folhas
    atletas = _read_sheet("Atletas")
    oficiais = _read_sheet("Oficiais")
    info = _read_sheet("Info")

    # Normalização de colunas (aceita acentos/variações)
    def _norm(df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        cols = [str(c).strip().lower() for c in out.columns]

        # mapear variantes comuns -> alvo sem acentos
        norm_map = {
            "número": "numero", "numero": "numero", "#": "numero", "no": "numero", "nº": "numero",
            "nome": "nome",
            "posição": "posicao", "posicao": "posicao", "pos": "posicao",
            "equipa a": "equipa a", "equipa": "equipa a",  # se só houver "Equipa" trata-se de A
            "equipa b": "equipa b",
            "data": "data",
            "local": "local",
        }
        # construir dict de renome
        rename = {}
        for old, low in zip(out.columns, cols):
            rename[old] = norm_map.get(low, low)

        out.rename(columns=rename, inplace=True)

        return out

    atletas = _norm(atletas)
    oficiais = _norm(oficiais)
    info = _norm(info)

    # Validar colunas obrigatórias
    for col in ("numero", "nome", "posicao"):
        if col not in atletas.columns:
            raise ValueError(f"Na folha 'Atletas' falta a coluna '{col}'")

    # Oficiais: número pode não existir no Excel; garantimos só Nome e Posição
    for col in ("nome", "posicao"):
        if col not in oficiais.columns:
            raise ValueError(f"Na folha 'Oficiais' falta a coluna '{col}'")

    # Info: Equipa A, Equipa B, Data, Local
    needed_info = ("equipa a", "equipa b", "data", "local")
    for col in needed_info:
        if col not in info.columns:
            raise ValueError(f"Na folha 'Info' falta a coluna '{col}'")

    # Uniformizar colunas finais para o resto do app
    atletas = atletas.rename(columns={"numero": "Numero", "nome": "Nome", "posicao": "Posicao"})[
        ["Numero", "Nome", "Posicao"]
    ]

    # Oficiais: se existir "Numero", mantemos; caso contrário, definimos 0
    if "numero" in oficiais.columns:
        oficiais = oficiais.rename(columns={"numero": "Numero", "nome": "Nome", "posicao": "Posicao"})
        if "Numero" not in oficiais.columns:
            oficiais["Numero"] = 0
        oficiais = oficiais[["Numero", "Nome", "Posicao"]]
    else:
        oficiais = oficiais.rename(columns={"nome": "Nome", "posicao": "Posicao"})
        oficiais["Numero"] = 0
        oficiais = oficiais[["Numero", "Nome", "Posicao"]]

    # Info final com maiúsculas iniciais nas chaves esperadas pelo app
    info = info.rename(columns={
        "equipa a": "Equipa a",
        "equipa b": "Equipa b",
        "data": "Data",
        "local": "Local",
    })[["Equipa a", "Equipa b", "Data", "Local"]]

    # Se info vazio, meter defaults
    if info.empty:
        info = pd.DataFrame([{
            "Equipa a": "Equipa A",
            "Equipa b": "Equipa B",
            "Data": pd.Timestamp.today().strftime("%Y-%m-%d"),
            "Local": "Local",
        }])

    return atletas, oficiais, info


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Obtém bytes do Excel (uploader ou Plantel.xlsx local), chama o parser cacheado
    e devolve DataFrames normalizados.
    """
    default_path = "Plantel.xlsx"

    # Uploader na sidebar (opcional)
    with st.sidebar:
        st.markdown("### 📂 Plantel")
        up = st.file_uploader(
            "Carregar Plantel.xlsx",
            type=["xlsx"],
            help="Deve conter as abas: Atletas, Oficiais e Info",
            key="file_uploader_roster",
        )
        if up is not None:
            st.session_state.excel_bytes = up.getvalue()  # guardamos BYTES (serializável)
            st.success("✔️ Plantel carregado para a sessão")

    # Prioridade: bytes da sessão > ficheiro local
    excel_bytes: Optional[bytes] = st.session_state.get("excel_bytes")
    if excel_bytes is None:
        if os.path.exists(default_path):
            with open(default_path, "rb") as f:
                excel_bytes = f.read()
        else:
            st.warning("⚠️ Carregue o ficheiro **Plantel.xlsx** na sidebar ou coloque-o na pasta da app.", icon="🗂️")
            st.stop()

    try:
        atletas_df, oficiais_df, info_df = _parse_roster_excel(excel_bytes)
    except ModuleNotFoundError:
        st.error("Falta a dependência **openpyxl**. Instala: `pip install openpyxl`")
        st.stop()
    except Exception as e:
        st.error(f"Erro ao abrir o Excel: {e}")
        st.stop()

    return atletas_df, oficiais_df, info_df
# =================== FIM DO PATCH DE LEITURA DO EXCEL ===================
# ===== Regras & Compatibilidade zonas =====
ZONE_COMPAT_MAP = {
    "Ponta": {1, 5},
    "Pivot": {2, 3, 4},
    "Penetração": {2, 3, 4},
    "6m": {2, 3, 4},
    "9m": {6, 7, 8},
    "Baliza Aberta": "NO_ZONE",
    "7m": "NO_ZONE",
    "1 Vaga": "ALL",
    "2 Vaga": "ALL",
    "3 Vaga": "ALL",
}
GOAL_CHOICES = ["9m","6m","Penetração","1 Vaga","2 Vaga","3 Vaga","Baliza Aberta","7m","Pivot","Ponta"]

def allowed_zones_for(typ: str) -> set:
    spec = ZONE_COMPAT_MAP.get(typ, "ALL")
    if spec == "ALL":
        return set(range(1,9))
    if spec == "NO_ZONE":
        return set()
    return set(spec)

def current_allowed_on_field(gs: Dict[str, Any]) -> int:
    # 7 - (sanções ativas de jogadores + equipa), nunca < 3
    per_player_active = sum(1 for pid,p in gs["players"].items() if (not p.get("is_official")) and p.get("two_active",0)>0)
    team_active = sum(1 for t in gs["team_penalties"] if t>0)
    return max(3, 7 - (per_player_active + team_active))

def play_unlocked(gs: Dict[str,Any]) -> bool:
    # 1ª parte: exatamente 7 selecionados (GR não é obrigatório). 2ª parte: livre
    return (gs["half"] == 2) or (len(gs["on_field_set"]) == 7)

# ===== Estado inicial =====
def init_state():
    if "game_state" in st.session_state:
        return

    atletas_df, oficiais_df, info_df = load_data()

    players: Dict[str, Dict[str, Any]] = {}
    gk_ids: List[str] = []
    field_ids: List[str] = []
    official_ids: List[str] = []

    # Atletas
    for idx, row in atletas_df.iterrows():
        num = row.get("Numero", 0)
        nome = str(row.get("Nome","")).strip()
        pos = str(row.get("Posicao","")).strip()
        if not nome:
            continue
        pid = f"player_{idx}_{nome}"
        try:
            num_norm = int(num) if pd.notna(num) and str(num).strip().isdigit() else str(num)
        except Exception:
            num_norm = str(num)
        players[pid] = {
            "id": pid,
            "num": num_norm,
            "nome": nome,
            "pos": pos,
            "in_field": False,
            "time_played": 0.0,
            "yellow": 0,
            "two_total": 0,
            "two_active": 0.0,
            "red": 0,
            "disq": False,
            "tech_faults": 0,
            "conquistas": [],
        }
        if str(pos).upper() == "GR":
            gk_ids.append(pid)
        else:
            field_ids.append(pid)

    # Oficiais
    for idx, row in oficiais_df.iterrows():
        nome = str(row.get("Nome","")).strip()
        pos = str(row.get("Posicao","")).strip()
        if not nome:
            continue
        oid = f"official_{idx}_{nome}"
        players[oid] = {
            "id": oid,
            "num": "0",
            "nome": nome,
            "pos": pos,           # A..E
            "is_official": True,
            "yellow": 0,
            "two_total": 0,       # vamos controlar limite COLETIVO de 2'
            "two_active": 0.0,    # não usado diretamente para oficiais
            "red": 0,
            "disq": False,
        }
        official_ids.append(oid)

    # Info
    info_row = info_df.iloc[0].to_dict() if not info_df.empty else {"Equipa a":"Equipa A","Equipa b":"Equipa B","Data":datetime.now().strftime("%Y-%m-%d"),"Local":"Local"}

    st.session_state.game_state = {
        "team_a": str(info_row.get("Equipa a","Equipa A")),
        "team_b": str(info_row.get("Equipa b","Equipa B")),
        "date": str(info_row.get("Data", datetime.now().strftime("%Y-%m-%d"))),
        "place": str(info_row.get("Local","Local")),

        "players": players,
        "gk_ids": gk_ids,
        "field_ids": field_ids,
        "official_ids": official_ids,

        "running": False,
        "start_time": None,
        "elapsed": 0.0,
        "half": 1,
        "half_len": 30*60,
        "last_minute_alert": False,

        "on_field_set": set(),
        "team_penalties": [],       # timers de 2' de equipa
        "passive": False,

        "team_yellow_total": 0,     # atletas (máx 3)
        "officials_yellow_total": 0, # oficiais (máx 1 global)
        "officials_two_total": 0,    # oficiais (máx 1 global)

        # bloqueio forçado (quando oficial leva 2' ou vermelho)
        "forced_bench_s": {},        # pid -> segundos restantes de bloqueio

        "score_for": {"1":0,"2":0},
        "score_against": {"1":0,"2":0},

        "goals": [],
        "shots": [],
        "events": [],

        "last_snapshot": None,
    }
# ===== Snapshots (Undo) =====
SNAP_KEYS = [
    "players","on_field_set","team_penalties","team_yellow_total",
    "officials_yellow_total","officials_two_total",
    "forced_bench_s",
    "score_for","score_against","goals","shots","events",
    "running","start_time","elapsed","half","last_minute_alert",
]

def push_snapshot(label: str):
    gs = st.session_state.game_state
    snap = deep_snapshot_from(SNAP_KEYS, gs)
    snap["_label"] = label
    gs["last_snapshot"] = snap

def undo_last():
    gs = st.session_state.game_state
    if not gs.get("last_snapshot"):
        st.warning("Não há ação para desfazer.", icon="⚠️"); return
    last = gs["last_snapshot"]
    for k in SNAP_KEYS:
        gs[k] = last[k]
    gs["last_snapshot"] = None
    st.toast(f"↩️ Desfeito: {last.get('_label','Ação')}", icon="↩️")

# ===== Tempo =====
def flush_time():
    gs = st.session_state.game_state
    if not gs["running"]:
        return
    if gs["start_time"] is None:
        gs["start_time"] = now_ts(); return

    now = now_ts()
    delta = max(0.0, now - gs["start_time"])
    if delta == 0: return

    gs["elapsed"] += delta
    gs["start_time"] = now

    # tempo de quem está em campo
    for pid in list(gs["on_field_set"]):
        p = gs["players"].get(pid)
        if p and (not p.get("is_official")):
            p["time_played"] = p.get("time_played",0.0) + delta

    # reduzir 2' ativos de jogadores
    finished_players = []
    for pid, p in gs["players"].items():
        if p.get("two_active",0.0) > 0:
            before = p["two_active"]
            p["two_active"] = max(0.0, before - delta)
            if before > 0 and p["two_active"] == 0:
                finished_players.append(pid)

    # reduzir 2' equipa
    finished_team = 0
    for i in range(len(gs["team_penalties"])):
        t = gs["team_penalties"][i]
        if t > 0:
            t2 = max(0.0, t - delta)
            gs["team_penalties"][i] = t2
            if t > 0 and t2 == 0:
                finished_team += 1

    # reduzir bloqueio forçado
    finished_forced = []
    for pid, secs in list(gs["forced_bench_s"].items()):
        newv = max(0.0, secs - delta)
        gs["forced_bench_s"][pid] = newv
        if secs > 0 and newv == 0:
            finished_forced.append(pid)

    for pid in finished_players:
        p = gs["players"][pid]
        if p.get("disq", False):
            st.toast(f"✅ Inferioridade associada a {p['num']} {p['nome']} terminou (permanece desqualificado).", icon="✅")
        else:
            st.toast(f"✅ {p['num']} {p['nome']} pode voltar a entrar (2’ terminou).", icon="✅")
    for _ in range(finished_team):
        st.toast("✅ Penalidade de equipa 2’ terminou.", icon="✅")
    for pid in finished_forced:
        p = gs["players"].get(pid, {"nome":pid})
        st.toast(f"✅ Bloqueio terminou — {p.get('nome','Jogador')} pode voltar a entrar.", icon="✅")

    # alerta último minuto
    rem = max(0, int(gs["half_len"] - gs["elapsed"]))
    if gs["running"] and rem <= 60 and not gs["last_minute_alert"]:
        st.toast(f"⏰ Último minuto! Faltam {rem}s", icon="⏰")
        gs["last_minute_alert"] = True

    # fim da parte
    if gs["elapsed"] >= gs["half_len"]:
        gs["elapsed"] = gs["half_len"]
        gs["running"] = False
        st.toast(f"⏱️ Fim da {gs['half']}ª parte (30:00)", icon="⏱️")
        if gs["half"] == 1:
            gs["half"] = 2
            gs["elapsed"] = 0.0
            gs["start_time"] = None
            gs["last_minute_alert"] = False
            st.toast("👉 Pronto para iniciar a 2ª parte", icon="➡️")
        else:
            st.toast("🏁 Fim do jogo", icon="🏁")

def start_play():
    gs = st.session_state.game_state
    if gs["half"] == 1 and len(gs["on_field_set"]) != 7:
        st.warning("Para iniciar a 1ª parte, seleciona **exatamente 7** jogadores em campo.", icon="⚠️")
        return
    gs["running"] = True
    gs["start_time"] = now_ts()

def pause_play():
    gs = st.session_state.game_state
    if gs["running"]:
        flush_time()
    gs["running"] = False
# ===== Sanções =====
def give_yellow(pid: str):
    gs = st.session_state.game_state
    p = gs["players"][pid]

    if p.get("disq", False):
        st.warning("Jogador/Oficial já desqualificado.", icon="⚠️"); return

    if p.get("is_official", False):
        # limite coletivo: 1 amarelo no total dos oficiais
        if gs["officials_yellow_total"] >= 1:
            st.warning("Limite de amarelos dos oficiais atingido (1/1).", icon="⚠️"); return
        if p.get("yellow",0) >= 1:
            st.warning("Este oficial já tem 1 amarelo.", icon="⚠️"); return
        push_snapshot(f"Amarelo Oficial {p['nome']}")
        p["yellow"] = 1
        gs["officials_yellow_total"] += 1
        st.toast(f"🟨 Oficial {p['nome']} — amarelo.", icon="🟨")
        return

    # atletas — limite equipa 3 amarelos e 1 por atleta
    if gs["team_yellow_total"] >= 3:
        st.warning("Limite de amarelos da equipa (3/3).", icon="⚠️"); return
    if p.get("yellow",0) >= 1:
        st.warning("Este atleta já tem 1 amarelo.", icon="⚠️"); return

    push_snapshot(f"Amarelo {p['nome']}")
    p["yellow"] = 1
    gs["team_yellow_total"] += 1
    st.toast(f"🟨 {p.get('num','')} {p['nome']} — amarelo (equipa {gs['team_yellow_total']}/3).", icon="🟨")

def _open_force_out_dialog(duration_s: int, reason: str):
    st.session_state._force_out_ctx = {"duration": duration_s, "reason": reason}
    st.session_state._open_force_out = True

def give_two_minutes(pid: str):
    gs = st.session_state.game_state
    p = gs["players"][pid]

    if p.get("disq", False):
        st.warning("Jogador/Oficial já desqualificado.", icon="⚠️"); return

    push_snapshot(f"2' {p['nome']}")

    # se estava em campo, sai
    if pid in gs["on_field_set"]:
        flush_time()
        gs["on_field_set"].discard(pid)
        p["in_field"] = False

    if p.get("is_official", False):
        # limite coletivo: 1× 2' no total dos oficiais
        if gs["officials_two_total"] >= 1:
            st.warning("Limite de 2’ dos oficiais atingido (1/1). A partir daqui, só vermelho.", icon="⚠️")
            return
        p["two_total"] = p.get("two_total",0) + 1
        gs["officials_two_total"] += 1
        gs["team_penalties"].append(120.0)
        st.toast(f"⏱️ Oficial {p['nome']} — 2’ (equipa cumpre 2’).", icon="⏱️")
        # escolher atleta a retirar e bloquear por 120s
        _open_force_out_dialog(120, "2’ do Oficial")
        return

    # atletas — acumula; 3×2’ => desqualificação + 2’ equipa
    p["two_total"] = p.get("two_total",0) + 1
    curr = p.get("two_active",0.0)
    if p["two_total"] >= 3:
        p["disq"] = True
        p["two_active"] = curr
        gs["team_penalties"].append(120.0)
        st.error(f"🟥 {p.get('num','')} {p['nome']} desqualificado (3×2’). Equipa cumpre +2’.", icon="🚫")
    else:
        p["two_active"] = curr + 120.0
        st.toast(f"🚫 {p.get('num','')} {p['nome']} — +2’ (ativo {int(p['two_active'])}s).", icon="⏱️")

def give_red(pid: str):
    gs = st.session_state.game_state
    p = gs["players"][pid]

    if p.get("disq", False):
        st.warning("Já está desqualificado.", icon="⚠️"); return

    push_snapshot(f"Vermelho {p['nome']}")

    if pid in gs["on_field_set"]:
        flush_time()
        gs["on_field_set"].discard(pid)
        p["in_field"] = False

    p["disq"] = True
    p["red"] = p.get("red",0) + 1
    gs["team_penalties"].append(120.0)

    if p.get("is_official", False):
        st.error(f"🟥 Oficial {p['nome']} — expulsão (equipa cumpre 2’).", icon="🚫")
        _open_force_out_dialog(120, "Vermelho ao Oficial")
    else:
        st.error(f"🟥 {p.get('num','')} {p['nome']} — expulsão (equipa cumpre 2’).", icon="🚫")
# ===== Ações de jogo =====
def register_goal(pid: str, typ: str, zona: Optional[int], sofrido: bool=False):
    gs = st.session_state.game_state
    p = gs["players"][pid]
    if p.get("disq", False):
        st.warning("Desqualificado — não pode marcar.", icon="⚠️"); return
    push_snapshot(f"Golo {p['nome']} ({typ})")
    e = {"player_id": pid, "tipo": typ, "zona": zona, "half": gs["half"], "sofrido": bool(sofrido), "t": int(gs["elapsed"])}
    gs["goals"].append(e)
    if sofrido:
        gs["score_against"][str(gs["half"])] += 1
        st.toast(f"⚠️ Golo sofrido — {typ}{(' · Zona '+str(zona)) if zona else ''}", icon="⚠️")
    else:
        gs["score_for"][str(gs["half"])] += 1
        st.toast(f"⚽ Golo — {p.get('num','')} {p['nome']} · {typ}{(' · Zona '+str(zona)) if zona else ''}", icon="⚽")
    gs["passive"] = False

def register_shot(pid: str, outcome: str, typ: str, zona: Optional[int], sofrido: bool=False):
    gs = st.session_state.game_state
    p = gs["players"][pid]
    if p.get("disq", False):
        st.warning("Desqualificado — não pode rematar.", icon="⚠️"); return
    push_snapshot(f"Remate {outcome} {p['nome']} ({typ})")
    e = {"player_id": pid, "tipo": typ, "resultado": outcome, "zona": zona, "half": gs["half"], "sofrido": bool(sofrido), "t": int(gs["elapsed"])}
    gs["shots"].append(e)
    icon = "🧤" if outcome=="defendido" else "❌"
    suf = " (sofrido)" if sofrido else ""
    st.toast(f"{icon} Remate {outcome}{suf} — {p['nome']} · {typ}{(' · Zona '+str(zona)) if zona else ''}", icon=icon)
    gs["passive"] = False

def compute_suffered_counters() -> Dict[str, Dict[str,int]]:
    gs = st.session_state.game_state
    out = {"golos_sofridos":{"1":0,"2":0,"T":0}, "defendidos":{"1":0,"2":0,"T":0}, "falhados":{"1":0,"2":0,"T":0}}
    for e in gs["goals"]:
        if e.get("sofrido"):
            h = str(e["half"]); out["golos_sofridos"][h]+=1; out["golos_sofridos"]["T"]+=1
    for e in gs["shots"]:
        if e.get("sofrido"):
            h = str(e["half"])
            if e.get("resultado")=="defendido":
                out["defendidos"][h]+=1; out["defendidos"]["T"]+=1
            elif e.get("resultado")=="falhado":
                out["falhados"][h]+=1; out["falhados"]["T"]+=1
    return out

# ===== Conquistas =====
def add_conquista(pid: str, label: str):
    gs = st.session_state.game_state
    p = gs["players"][pid]
    p.setdefault("conquistas", []).append({"t": int(gs["elapsed"]), "label": label})
    gs["events"].append({"t": int(gs["elapsed"]), "txt": f"{p['nome']} conquistou: {label}"})
    st.toast(f"🏆 Conquista: {label} — {p['nome']}", icon="🏆")
    gs["passive"] = False

def conquista_combo_two_plus_seven(pid: str):
    """Regista simultaneamente a conquista '2 min + 7m':
       - Um evento textual de conquista
       - E (opcionalmente) podes somar contadores se usares métricas separadas
    """
    add_conquista(pid, "2 min + 7m")
    # Se quiseres também materializar isto como eventos práticos:
    #  - isto normalmente dá 2' para adversário e 7m a nosso favor.
    # Aqui registamos apenas o evento, a sanção real no adversário e 7m
    # são normalmente registados noutros controlos (penalti/golo).
    # Mantemos simples porque a app controla a nossa equipa.
# ===== Abertura de modais =====
def open_sanction_modal(pid: str):
    st.session_state._sanction_pid = pid
    st.session_state._open_sanction = True

def open_shot_modal(pid: str, is_gk: bool):
    st.session_state._shot_ctx = (pid, is_gk)
    st.session_state._open_shot = True

def open_zone_modal(ctx: Dict[str,Any]):
    st.session_state._zone_ctx = ctx
    st.session_state._open_zone = True

def open_conquista_modal(pid: str, is_gk: bool):
    st.session_state._conquista_ctx = (pid, is_gk)
    st.session_state._open_conquista = True

@st.dialog("Aplicar sanção")
def sanction_dialog():
    pid = st.session_state.get("_sanction_pid")
    if not pid:
        st.write("Sem jogador selecionado.")
        if st.button("Fechar", use_container_width=True): st.session_state._open_sanction=False; st.rerun()
        return
    gs = st.session_state.game_state
    p = gs["players"][pid]
    is_off = p.get("is_official", False)

    st.subheader(f"{p.get('num','')} · {p['nome']}{' (Oficial)' if is_off else ''}")
    c1,c2,c3,c4 = st.columns(4)
    with c1: st.metric("Amarelo", f"{p.get('yellow',0)}/1" + (" (oficiais 1/1 máx)" if is_off else f" (equipa {gs['team_yellow_total']}/3)"))
    with c2: st.metric("2' total", f"{p.get('two_total',0)}" + (" (oficiais 1/1 máx)" if is_off else ""))
    with c3: st.metric("2' ativa (s)", f"{int(p.get('two_active',0))}")
    with c4: st.metric("Vermelhos", f"{p.get('red',0)}")

    st.divider()
    st.write("**Escolhe a sanção:**")
    can_y = not p.get("disq", False)
    can_2 = not p.get("disq", False)
    can_r = not p.get("disq", False)

    if is_off:
        if gs["officials_yellow_total"] >= 1 or p.get("yellow",0)>=1:
            can_y = False
        if gs["officials_two_total"] >= 1:
            can_2 = False
    else:
        if gs["team_yellow_total"] >= 3 or p.get("yellow",0)>=1:
            can_y = False

    b1,b2,b3 = st.columns(3)
    with b1:
        if st.button("🟨 Amarelo", use_container_width=True, disabled=not can_y):
            flush_time(); give_yellow(pid); st.session_state._open_sanction=False; st.rerun()
    with b2:
        if st.button("🚫 2 minutos", use_container_width=True, disabled=not can_2):
            flush_time(); give_two_minutes(pid); st.session_state._open_sanction=False; st.rerun()
    with b3:
        if st.button("🟥 Vermelho", use_container_width=True, disabled=not can_r):
            flush_time(); give_red(pid); st.session_state._open_sanction=False; st.rerun()

    st.divider()
    if st.button("Fechar", use_container_width=True):
        st.session_state._open_sanction = False; st.rerun()

@st.dialog("Remate / Golo")
def shot_dialog():
    tmp = st.session_state.get("_shot_ctx")
    if not tmp:
        st.write("Sem jogador."); 
        if st.button("Fechar", use_container_width=True): st.session_state._open_shot=False; st.rerun()
        return
    pid, is_gk = tmp
    gs = st.session_state.game_state
    p = gs["players"][pid]

    st.subheader(f"{p.get('num','')} · {p['nome']}{' (GR)' if is_gk else ''}")
    st.caption(f"Parte: {gs['half']}ª — Tempo: {fmt_hhmmss(gs['elapsed'])}")

    if is_gk:
        st.markdown("### 🧤 Remates Sofridos — **Golo Sofrido**")
        row1 = ["9m","6m","Penetração","1 Vaga","2 Vaga"]; row2 = ["3 Vaga","Baliza Aberta","7m","Pivot","Ponta"]
        for row, tag in [(row1,"a"),(row2,"b")]:
            cols = st.columns(len(row))
            for typ, col in zip(row, cols):
                with col:
                    if st.button(typ, key=f"gk_suf_goal_{pid}_{tag}_{typ}", use_container_width=True):
                        zones = allowed_zones_for(typ)
                        if not zones:
                            flush_time(); register_goal(pid, typ, None, sofrido=True); st.session_state._open_shot=False; st.rerun()
                        else:
                            open_zone_modal({"kind":"goal","pid":pid,"typ":typ,"sofrido":True}); st.session_state._open_shot=False; st.rerun()

        st.divider()
        st.markdown("### 🧤 Remates Sofridos — **Defendidos**")
        for row, tag in [(row1,"c"),(row2,"d")]:
            cols = st.columns(len(row))
            for typ, col in zip(row, cols):
                with col:
                    if st.button(typ, key=f"gk_suf_def_{pid}_{tag}_{typ}", use_container_width=True):
                        zones = allowed_zones_for(typ)
                        if not zones:
                            flush_time(); register_shot(pid,"defendido",typ,None,sofrido=True); st.session_state._open_shot=False; st.rerun()
                        else:
                            open_zone_modal({"kind":"defendido","pid":pid,"typ":typ,"sofrido":True}); st.session_state._open_shot=False; st.rerun()

        st.divider()
        st.markdown("### 🧤 Remates Sofridos — **Falhados**")
        for row, tag in [(row1,"e"),(row2,"f")]:
            cols = st.columns(len(row))
            for typ, col in zip(row, cols):
                with col:
                    if st.button(typ, key=f"gk_suf_miss_{pid}_{tag}_{typ}", use_container_width=True):
                        zones = allowed_zones_for(typ)
                        if not zones:
                            flush_time(); register_shot(pid,"falhado",typ,None,sofrido=True); st.session_state._open_shot=False; st.rerun()
                        else:
                            open_zone_modal({"kind":"falhado","pid":pid,"typ":typ,"sofrido":True}); st.session_state._open_shot=False; st.rerun()

        st.divider()
        st.markdown("### ⚽ Golo do GR")
        if st.button("Golo", key=f"gk_goal_{pid}", use_container_width=True):
            flush_time(); register_goal(pid, "Golo GR", None, sofrido=False); st.session_state._open_shot=False; st.rerun()

    else:
        st.markdown("### ⚽ Golo")
        rows = [["9m","6m","Penetração","1 Vaga","2 Vaga"],["3 Vaga","Baliza Aberta","7m","Pivot","Ponta"]]
        for row, tag in [(rows[0],"g"),(rows[1],"h")]:
            cols = st.columns(len(row))
            for typ, col in zip(row, cols):
                with col:
                    if st.button(typ, key=f"pl_goal_{pid}_{tag}_{typ}", use_container_width=True):
                        zones = allowed_zones_for(typ)
                        if not zones:
                            flush_time(); register_goal(pid, typ, None, sofrido=False); st.session_state._open_shot=False; st.rerun()
                        else:
                            open_zone_modal({"kind":"goal","pid":pid,"typ":typ,"sofrido":False}); st.session_state._open_shot=False; st.rerun()

        st.divider()
        st.markdown("### 🧤 Remates Defendidos")
        for row, tag in [(rows[0],"i"),(rows[1],"j")]:
            cols = st.columns(len(row))
            for typ, col in zip(row, cols):
                with col:
                    if st.button(typ, key=f"pl_def_{pid}_{tag}_{typ}", use_container_width=True):
                        zones = allowed_zones_for(typ)
                        if not zones:
                            flush_time(); register_shot(pid,"defendido",typ,None,sofrido=False); st.session_state._open_shot=False; st.rerun()
                        else:
                            open_zone_modal({"kind":"defendido","pid":pid,"typ":typ,"sofrido":False}); st.session_state._open_shot=False; st.rerun()

        st.divider()
        st.markdown("### ❌ Remates Falhados")
        for row, tag in [(rows[0],"k"),(rows[1],"l")]:
            cols = st.columns(len(row))
            for typ, col in zip(row, cols):
                with col:
                    if st.button(typ, key=f"pl_miss_{pid}_{tag}_{typ}", use_container_width=True):
                        zones = allowed_zones_for(typ)
                        if not zones:
                            flush_time(); register_shot(pid,"falhado",typ,None,sofrido=False); st.session_state._open_shot=False; st.rerun()
                        else:
                            open_zone_modal({"kind":"falhado","pid":pid,"typ":typ,"sofrido":False}); st.session_state._open_shot=False; st.rerun()

    st.divider()
    if st.button("Fechar", use_container_width=True):
        st.session_state._open_shot = False; st.rerun()

@st.dialog("Escolher zona de campo")
def zone_dialog():
    ctx = st.session_state.get("_zone_ctx")
    if not ctx:
        st.write("Sem contexto.")
        if st.button("Fechar", use_container_width=True): st.session_state._open_zone=False; st.rerun()
        return
    gs = st.session_state.game_state
    pid = ctx["pid"]; typ = ctx["typ"]; kind = ctx["kind"]; sofrido = ctx.get("sofrido", False)
    zones_allowed = allowed_zones_for(typ)

    p = gs["players"][pid]
    st.subheader(f"{p.get('num','')} · {p['nome']}")
    st.caption(f"Tipo: {typ} — {'Golo' if kind=='goal' else ('Defendido' if kind=='defendido' else 'Falhado')}")

    cols1 = st.columns(5)
    for i, col in enumerate(cols1, start=1):
        with col:
            if st.button(f"Zona {i}", key=f"zone_{pid}_{typ}_{kind}_{i}", use_container_width=True, disabled=(i not in zones_allowed)):
                flush_time()
                if kind == "goal": register_goal(pid, typ, i, sofrido)
                else: register_shot(pid, kind, typ, i, sofrido)
                st.session_state._open_zone=False; st.session_state._zone_ctx=None; st.rerun()

    cols2 = st.columns(3)
    for idx, z in enumerate([6,7,8]):
        with cols2[idx]:
            if st.button(f"Zona {z}", key=f"zone_{pid}_{typ}_{kind}_{z}", use_container_width=True, disabled=(z not in zones_allowed)):
                flush_time()
                if kind == "goal": register_goal(pid, typ, z, sofrido)
                else: register_shot(pid, kind, typ, z, sofrido)
                st.session_state._open_zone=False; st.session_state._zone_ctx=None; st.rerun()

    st.divider()
    if st.button("Cancelar", use_container_width=True):
        st.session_state._open_zone=False; st.session_state._zone_ctx=None; st.rerun()

@st.dialog("Conquista")
def conquista_dialog():
    tmp = st.session_state.get("_conquista_ctx")
    if not tmp:
        st.write("Sem jogador.")
        if st.button("Fechar", use_container_width=True): st.session_state._open_conquista=False; st.rerun()
        return
    pid, is_gk = tmp
    gs = st.session_state.game_state
    p = gs["players"][pid]
    st.subheader(f"{p.get('num','')} · {p['nome']}{' (GR)' if is_gk else ''}")

    if is_gk:
        st.write("**Conquistas (GR):**")
        if st.button("2 min (ao adversário)", use_container_width=True):
            add_conquista(pid, "2 min (GR)")
            st.session_state._open_conquista=False; st.rerun()
    else:
        st.write("**Conquistas (Jogador de Campo):**")
        row1 = ["Roubo de Bola","Interseção"]
        cols1 = st.columns(len(row1))
        for label, col in zip(row1, cols1):
            with col:
                if st.button(label, key=f"cq_{pid}_{label}", use_container_width=True):
                    add_conquista(pid, label); st.session_state._open_conquista=False; st.rerun()

        st.divider()
        row2 = ["2 min","7m","2 min + 7m"]
        cols2 = st.columns(len(row2))
        for label, col in zip(row2, cols2):
            with col:
                if st.button(label, key=f"cq2_{pid}_{label}", use_container_width=True):
                    if label == "2 min + 7m":
                        conquista_combo_two_plus_seven(pid)
                    else:
                        add_conquista(pid, label)
                    st.session_state._open_conquista=False; st.rerun()

    st.divider()
    if st.button("Fechar", use_container_width=True):
        st.session_state._open_conquista=False; st.rerun()

@st.dialog("Retirar atleta (sanção a Oficial)")
def force_out_dialog():
    ctx = st.session_state.get("_force_out_ctx")
    if not ctx:
        st.write("Sem contexto.")
        if st.button("Fechar", use_container_width=True): st.session_state._open_force_out=False; st.rerun()
        return
    gs = st.session_state.game_state
    duration = int(ctx["duration"]); reason = ctx["reason"]

    st.subheader(f"Escolhe 1 atleta para sair ({reason})")
    st.caption("O atleta ficará bloqueado por 120s e não poderá voltar a entrar até terminar.")

    # lista de quem está em campo e não é oficial
    in_field_players = [pid for pid in gs["on_field_set"] if not gs["players"][pid].get("is_official")]
    if not in_field_players:
        st.info("Não há atletas em campo para retirar neste momento.")
        if st.button("Fechar", use_container_width=True): st.session_state._open_force_out=False; st.rerun()
        return

    cols = st.columns(3)
    for i, pid in enumerate(in_field_players):
        p = gs["players"][pid]
        with cols[i % 3]:
            if st.button(f"{p.get('num','')} {p['nome']}", key=f"force_out_{pid}", use_container_width=True):
                push_snapshot(f"Retirar {p['nome']} ({reason})")
                # retira e bloqueia
                flush_time()
                if pid in gs["on_field_set"]:
                    gs["on_field_set"].discard(pid)
                p["in_field"] = False
                gs["forced_bench_s"][pid] = gs["forced_bench_s"].get(pid, 0.0) + duration
                st.toast(f"⛔ {p['nome']} bloqueado por {duration}s.", icon="⛔")
                st.session_state._open_force_out=False; st.session_state._force_out_ctx=None; st.rerun()

    st.divider()
    if st.button("Cancelar", use_container_width=True):
        st.session_state._open_force_out=False; st.session_state._force_out_ctx=None; st.rerun()
# ===== UI Helpers =====
def render_header_row():
    h_estado, h_tempo, h_num, h_nome, h_btns = st.columns([0.18,0.10,0.10,0.32,0.30])
    with h_estado: st.caption("Banco/Campo")
    with h_tempo:  st.caption("Tempo (min)")
    with h_num:    st.caption("Nº")
    with h_nome:   st.caption("Nome")
    with h_btns:   st.caption("Ações")

def render_player_row(pid: str, is_gk: bool=False, is_official: bool=False):
    gs = st.session_state.game_state
    p = gs["players"][pid]

    # badge estado
    if p.get("disq", False):
        badge = "<span class='pill pill-red'>🟥 Desqualificado</span>"
    elif p.get("two_active",0.0) > 0:
        badge = f"<span class='pill pill-orange'>⛔ 2’ ({int(p['two_active'])}s)</span>"
    else:
        if is_official:
            badge = "<span class='pill pill-blue'>👤 Oficial</span>"
        else:
            badge = "<span class='pill pill-green'>🟢 Em campo</span>" if p.get("in_field",False) else "<span class='pill pill-yellow'>🟡 Banco</span>"

    # tempo (min)
    mins = "" if is_official else int(min(60, p.get("time_played",0.0)//60))

    c_est, c_tmp, c_num, c_nom, c_btns = st.columns([0.18,0.10,0.10,0.32,0.30])
    with c_est: st.markdown(f"<div class='row-compact'>{badge}</div>", unsafe_allow_html=True)
    with c_tmp: st.markdown(f"<div class='row-compact mins'>{mins}</div>", unsafe_allow_html=True)
    with c_num: st.markdown(f"<div class='row-compact num'>{p.get('num','')}</div>", unsafe_allow_html=True)

    # botão nome para entrar/sair (jogadores)
    with c_nom:
        disabled = is_official or p.get("disq",False) or (p.get("two_active",0.0)>0) or (gs["forced_bench_s"].get(pid,0.0) > 0)
        label = f"{p['nome']}"
        clicked = st.button(label, key=f"btn_name_{pid}", use_container_width=True, disabled=disabled,
                            help="Clique para entrar/sair. Bloqueado se 2’ ou bloqueio ativo.")
        if clicked and not is_official:
            flush_time()
            # impedir reentrada se bloqueado
            if gs["forced_bench_s"].get(pid,0.0) > 0:
                st.warning("Este atleta está bloqueado e não pode entrar ainda.", icon="⚠️")
            else:
                if p.get("in_field",False):
                    p["in_field"]=False
                    gs["on_field_set"].discard(pid)
                else:
                    if len(gs["on_field_set"]) >= current_allowed_on_field(gs):
                        st.warning(f"Máximo de {current_allowed_on_field(gs)} em campo no momento.", icon="⚠️")
                    else:
                        p["in_field"]=True
                        gs["on_field_set"].add(pid)
            gs["start_time"] = now_ts()

    with c_btns:
        col1,col2,col3,col4 = st.columns(4)
        with col1:
            st.button("📋", key=f"btn_sanc_{pid}", use_container_width=True, help="Sanção",
                      on_click=open_sanction_modal, args=(pid,))
        with col2:
            if not is_official:
                st.button("🎯", key=f"btn_shot_{pid}", use_container_width=True,
                          help=("Remates Sofridos / Golo (GR)" if is_gk else "Remate/Golo"),
                          on_click=open_shot_modal, args=(pid,is_gk))
        with col3:
            if not is_official:
                st.button("🏆", key=f"btn_conquista_{pid}", use_container_width=True, help="Conquista",
                          on_click=open_conquista_modal, args=(pid,is_gk))
        with col4:
            if not is_official:
                if st.button("⚠️", key=f"btn_tech_{pid}", use_container_width=True, help="Falha Técnica"):
                    push_snapshot(f"Falha Técnica {p['nome']}"); p["tech_faults"]=p.get("tech_faults",0)+1; st.toast("⚠️ Falha técnica registada.", icon="⚠️")
# ===== UI Helpers =====
def render_header_row():
    h_estado, h_tempo, h_num, h_nome, h_btns = st.columns([0.18,0.10,0.10,0.32,0.30])
    with h_estado: st.caption("Banco/Campo")
    with h_tempo:  st.caption("Tempo (min)")
    with h_num:    st.caption("Nº")
    with h_nome:   st.caption("Nome")
    with h_btns:   st.caption("Ações")

def render_player_row(pid: str, is_gk: bool=False, is_official: bool=False):
    gs = st.session_state.game_state
    p = gs["players"][pid]

    # badge estado
    if p.get("disq", False):
        badge = "<span class='pill pill-red'>🟥 Desqualificado</span>"
    elif p.get("two_active",0.0) > 0:
        badge = f"<span class='pill pill-orange'>⛔ 2’ ({int(p['two_active'])}s)</span>"
    else:
        if is_official:
            badge = "<span class='pill pill-blue'>👤 Oficial</span>"
        else:
            badge = "<span class='pill pill-green'>🟢 Em campo</span>" if p.get("in_field",False) else "<span class='pill pill-yellow'>🟡 Banco</span>"

    # tempo (min)
    mins = "" if is_official else int(min(60, p.get("time_played",0.0)//60))

    c_est, c_tmp, c_num, c_nom, c_btns = st.columns([0.18,0.10,0.10,0.32,0.30])
    with c_est: st.markdown(f"<div class='row-compact'>{badge}</div>", unsafe_allow_html=True)
    with c_tmp: st.markdown(f"<div class='row-compact mins'>{mins}</div>", unsafe_allow_html=True)
    with c_num: st.markdown(f"<div class='row-compact num'>{p.get('num','')}</div>", unsafe_allow_html=True)

    # botão nome para entrar/sair (jogadores)
    with c_nom:
        disabled = is_official or p.get("disq",False) or (p.get("two_active",0.0)>0) or (gs["forced_bench_s"].get(pid,0.0) > 0)
        label = f"{p['nome']}"
        clicked = st.button(label, key=f"btn_name_{pid}", use_container_width=True, disabled=disabled,
                            help="Clique para entrar/sair. Bloqueado se 2’ ou bloqueio ativo.")
        if clicked and not is_official:
            flush_time()
            # impedir reentrada se bloqueado
            if gs["forced_bench_s"].get(pid,0.0) > 0:
                st.warning("Este atleta está bloqueado e não pode entrar ainda.", icon="⚠️")
            else:
                if p.get("in_field",False):
                    p["in_field"]=False
                    gs["on_field_set"].discard(pid)
                else:
                    if len(gs["on_field_set"]) >= current_allowed_on_field(gs):
                        st.warning(f"Máximo de {current_allowed_on_field(gs)} em campo no momento.", icon="⚠️")
                    else:
                        p["in_field"]=True
                        gs["on_field_set"].add(pid)
            gs["start_time"] = now_ts()

    with c_btns:
        col1,col2,col3,col4 = st.columns(4)
        with col1:
            st.button("📋", key=f"btn_sanc_{pid}", use_container_width=True, help="Sanção",
                      on_click=open_sanction_modal, args=(pid,))
        with col2:
            if not is_official:
                st.button("🎯", key=f"btn_shot_{pid}", use_container_width=True,
                          help=("Remates Sofridos / Golo (GR)" if is_gk else "Remate/Golo"),
                          on_click=open_shot_modal, args=(pid,is_gk))
        with col3:
            if not is_official:
                st.button("🏆", key=f"btn_conquista_{pid}", use_container_width=True, help="Conquista",
                          on_click=open_conquista_modal, args=(pid,is_gk))
        with col4:
            if not is_official:
                if st.button("⚠️", key=f"btn_tech_{pid}", use_container_width=True, help="Falha Técnica"):
                    push_snapshot(f"Falha Técnica {p['nome']}"); p["tech_faults"]=p.get("tech_faults",0)+1; st.toast("⚠️ Falha técnica registada.", icon="⚠️")
# ===== Inicialização =====
init_state()
gs = st.session_state.game_state

# ===== Cabeçalho do jogo =====
st.markdown(
    f"""
    <div style="text-align:center; margin-top:4px;">
      <div style="font-size:22px; font-weight:800;">{gs['team_a']} VS {gs['team_b']}</div>
      <div style="font-size:14px; color:#666;">{gs['date']} • {gs['place']}</div>
    </div>
    """,
    unsafe_allow_html=True
)

# ===== CSS utilitário =====
st.markdown(
    """
    <style>
      .row-compact { margin: 2px 0; padding: 4px 6px; border-bottom: 1px dashed #eee; }
      .pill { padding:4px 8px; border-radius:999px; font-size:13px; white-space:nowrap; }
      .pill-green { background:#2ecc71; color:#fff; }
      .pill-yellow{ background:#f1c40f; color:#000; }
      .pill-orange{ background:#e67e22; color:#000; }
      .pill-red   { background:#e74c3c; color:#fff; }
      .pill-blue  { background:#3498db; color:#fff; }
      .num { font-weight:700; text-align:center; }
      .mins { text-align:center; font-weight:600; }
      .section-title { font-weight:800; margin: 6px 0 0; }
      .center-row { display:flex; justify-content:center; align-items:center; gap:10px; }
    </style>
    """,
    unsafe_allow_html=True
)
# ===== Linha 1: Botões do cronómetro =====
flush_time()  # atualiza tempos antes de desenhar
allowed_now = current_allowed_on_field(gs)
pplay = play_unlocked(gs)

c1,c2,c3,c4 = st.columns([1,1,1,1])
with c1:
    st.button("▶️ Play / Retomar", use_container_width=True, on_click=start_play, disabled=not pplay,
              help=("Na 1ª parte precisa de 7 jogadores em campo" if gs["half"]==1 else ""))
with c2:
    st.button("⏸️ Pausa", use_container_width=True, on_click=pause_play)
with c3:
    st.button("↩️ Desfazer", use_container_width=True, on_click=undo_last)
with c4:
    st.empty()

# ===== Linha 2: Estado (Pausado / Em Jogo) =====
if gs["running"]:
    st.markdown("<div class='center-row' style='font-size:22px; font-weight:800; color:#0a0;'>🟢 EM JOGO</div>", unsafe_allow_html=True)
else:
    st.markdown("<div class='center-row' style='font-size:22px; font-weight:800; color:#c00;'>⏸️ PAUSADO</div>", unsafe_allow_html=True)

# ===== Linha 3: Cronómetro centrado =====
rem = max(0, int(gs["half_len"] - gs["elapsed"]))
st.markdown(
    f"""
    <div class='center-row' style='margin:6px 0;'>
      <div style='font-size:18px; font-weight:700;'>Tempo {gs['half']}ª</div>
      <div style='font-size:18px;'>{fmt_hhmmss(gs['elapsed'])} / 0:30:00</div>
      <div style='font-size:18px; color:#666;'>(faltam {fmt_hhmmss(rem)})</div>
    </div>
    """,
    unsafe_allow_html=True
)

# ===== Linha 4: Passivo + Igualdade/Inferioridade/7x6 =====
colP1,colP2 = st.columns([1.2, 2])
with colP1:
    gs["passive"] = st.toggle("🏳️ Passivo", value=gs["passive"], help="Desliga ao registar uma ação", key="toggle_passivo_main")
with colP2:
    # cálculo estado
    per_player_active = sum(1 for pid,p in gs["players"].items() if (not p.get("is_official")) and p.get("two_active",0)>0)
    team_active = sum(1 for t in gs["team_penalties"] if t>0)
    total_infer = per_player_active + team_active
    label_state = "Igualdade"
    if total_infer > 0:
        label_state = "Inferioridade"
    # 7x6: se há exatamente 7 em campo e nenhum GR entre eles
    seven = (len(gs["on_field_set"]) == 7)
    any_gk = any((gs["players"][pid].get("pos","").upper()=="GR") for pid in gs["on_field_set"])
    if seven and not any_gk:
        label_state = "7x6"
    st.markdown(f"<div class='center-row' style='font-size:16px; font-weight:700;'>Estado: {label_state}</div>", unsafe_allow_html=True)
# ===== Resultado (simples) =====
score_for_total = gs["score_for"]["1"] + gs["score_for"]["2"]
score_against_total = gs["score_against"]["1"] + gs["score_against"]["2"]
st.markdown(
    f"""
    <div class='center-row' style='margin:4px 0 10px 0;'>
      <div style='font-size:18px; font-weight:800;'>RESULTADO</div>
      <div style='font-size:16px; margin-left:8px;'>{score_for_total} x {score_against_total}</div>
    </div>
    """,
    unsafe_allow_html=True
)

st.divider()
# ===== Secção Principal =====
st.markdown("### Principal")

st.caption(f"Em campo: {len(gs['on_field_set'])}/{allowed_now} (máx dinâmico: 7 − sanções ativas; mínimo 3)")
render_header_row()

# Guarda-redes
if gs["gk_ids"]:
    st.markdown("<div class='section-title'>Guarda-redes</div>", unsafe_allow_html=True)
    for pid in gs["gk_ids"]:
        render_player_row(pid, is_gk=True, is_official=False)

# Jogadores de campo
if gs["field_ids"]:
    st.markdown("<div class='section-title'>Jogadores de campo</div>", unsafe_allow_html=True)
    for pid in gs["field_ids"]:
        render_player_row(pid, is_gk=False, is_official=False)

# Oficiais (só sanção)
if gs["official_ids"]:
    st.markdown("<div class='section-title'>Oficiais</div>", unsafe_allow_html=True)
    # Cabeçalho simples
    h1,h2,h3,h4 = st.columns([0.18,0.10,0.52,0.20])
    with h1: st.caption("Tipo")
    with h2: st.caption("Nº")
    with h3: st.caption("Nome / Posição")
    with h4: st.caption("Sanção")
    for pid in gs["official_ids"]:
        p = gs["players"][pid]
        if p.get("disq", False):
            badge = "<span class='pill pill-red'>🟥 Desqualificado</span>"
        elif p.get("two_active",0.0) > 0:
            badge = f"<span class='pill pill-orange'>⛔ 2’ ({int(p['two_active'])}s)</span>"
        else:
            badge = "<span class='pill pill-blue'>👤 Oficial</span>"
        c1,c2,c3,c4 = st.columns([0.18,0.10,0.52,0.20])
        with c1: st.markdown(f"<div class='row-compact'>{badge}</div>", unsafe_allow_html=True)
        with c2: st.markdown(f"<div class='row-compact num'>0</div>", unsafe_allow_html=True)
        with c3: st.markdown(f"<div class='row-compact'>{p['nome']} ({p.get('pos','')})</div>", unsafe_allow_html=True)
        with c4:
            st.button("📋", key=f"btn_sanc_off_{pid}", use_container_width=True, help="Sanção",
                      on_click=open_sanction_modal, args=(pid,))
# ===== Abas =====
tab_principal, tab_resumo = st.tabs(["Principal", "Resumo"])

with tab_principal:
    st.info("A listagem principal está acima (GR / Campo / Oficiais). Usa os botões de cada linha.", icon="ℹ️")

def build_export_frames():
    players = gs["players"]
    rows = []
    for pid, p in players.items():
        rows.append({
            "ID": pid,
            "Oficial": bool(p.get("is_official", False)),
            "Número": str(p.get("num","")),
            "Nome": p.get("nome",""),
            "Posição": p.get("pos",""),
            "Tempo (s)": float(p.get("time_played",0.0)) if not p.get("is_official") else 0.0,
            "Tempo (mm:ss)": format_mmss(float(p.get("time_played",0.0))) if not p.get("is_official") else "",
            "Em campo": bool(p.get("in_field", False)),
            "Amarelos": int(p.get("yellow",0)),
            "2' total": int(p.get("two_total",0)),
            "2' ativa (s)": int(p.get("two_active",0.0)),
            "Vermelhos": int(p.get("red",0)),
            "Desqualificado": bool(p.get("disq", False)),
            "Falhas Técnicas": int(p.get("tech_faults",0)),
            "Bloqueio (s)": int(gs["forced_bench_s"].get(pid,0.0)),
        })
    df_players = pd.DataFrame(rows)
    df_goals = pd.DataFrame(gs.get("goals", [])) if gs.get("goals") else pd.DataFrame(columns=["player_id","tipo","zona","half","sofrido","t"])
    df_shots = pd.DataFrame(gs.get("shots", [])) if gs.get("shots") else pd.DataFrame(columns=["player_id","tipo","resultado","zona","half","sofrido","t"])
    return df_players, df_goals, df_shots

def export_buttons():
    df_players, df_goals, df_shots = build_export_frames()
    st.subheader("Exportação de Dados")
    st.download_button("📥 Jogadores (CSV)", df_players.to_csv(index=False).encode("utf-8"), "jogadores.csv","text/csv")
    st.download_button("📥 Golos (CSV)", df_goals.to_csv(index=False).encode("utf-8"), "golos.csv","text/csv")
    st.download_button("📥 Remates (CSV)", df_shots.to_csv(index=False).encode("utf-8"), "remates.csv","text/csv")

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df_players.to_excel(w, index=False, sheet_name="Jogadores")
        df_goals.to_excel(w, index=False, sheet_name="Golos")
        df_shots.to_excel(w, index=False, sheet_name="Remates")
    st.download_button("📊 Exportar Tudo (Excel)", buf.getvalue(), "export_estatisticas_andebol.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

with tab_resumo:
    st.markdown("#### Resumos")
    df_players, df_goals, df_shots = build_export_frames()
    st.markdown("**Jogadores / Oficiais**")
    st.dataframe(df_players, hide_index=True, use_container_width=True)

    score_for = gs["score_for"]; score_against = gs["score_against"]
    df_score = pd.DataFrame({
        "Parte":["1ª","2ª","Total"],
        "Marcados":[score_for["1"], score_for["2"], score_for["1"]+score_for["2"]],
        "Sofridos":[score_against["1"], score_against["2"], score_against["1"]+score_against["2"]],
    })
    st.markdown("**Resultado — Marcados vs Sofridos**")
    st.dataframe(df_score, hide_index=True, use_container_width=True)

    suf = compute_suffered_counters()
    df_suf = pd.DataFrame({
        "Categoria":["Golos sofridos","Defendidos","Falhados"],
        "1ª Parte":[suf["golos_sofridos"]["1"], suf["defendidos"]["1"], suf["falhados"]["1"]],
        "2ª Parte":[suf["golos_sofridos"]["2"], suf["defendidos"]["2"], suf["falhados"]["2"]],
        "Total":[suf["golos_sofridos"]["T"], suf["defendidos"]["T"], suf["falhados"]["T"]],
    })
    st.markdown("**Remates Sofridos — Por parte e total**")
    st.dataframe(df_suf, hide_index=True, use_container_width=True)

    export_buttons()
# ===== Modais pendentes =====
if st.session_state.get("_open_sanction"): sanction_dialog()
if st.session_state.get("_open_shot"): shot_dialog()
if st.session_state.get("_open_zone"): zone_dialog()
if st.session_state.get("_open_conquista"): conquista_dialog()
if st.session_state.get("_open_force_out"): force_out_dialog()

# ===== Autorefresh (ciclo principal) =====
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=1000, key="tick_main")
except Exception:
    pass

# ===== Estilos finais =====
st.markdown(
    """
    <style>
      .stButton > button { padding: 0.45rem 0.7rem; }
      .small-caption { font-size: 12px; color: #777; text-align:center; margin-top:10px; }
    </style>
    """,
    unsafe_allow_html=True
)
# ===== Manter elapsed correto quando pausado =====
def _get_elapsed_now():
    if gs["running"] and gs["start_time"] is not None:
        return gs["elapsed"] + (now_ts() - gs["start_time"])
    return gs["elapsed"]

if not gs["running"]:
    gs["elapsed"] = _get_elapsed_now()

st.markdown("<div class='small-caption'>Estatísticas de Andebol • Streamlit</div>", unsafe_allow_html=True)