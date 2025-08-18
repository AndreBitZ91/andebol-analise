# teste.py — Estatísticas de Andebol (Streamlit)
# Execução local:
#   python3 -m venv venv && source venv/bin/activate
#   pip install -r requirements.txt
#   python -m streamlit run teste.py

import os
import time
import copy
from io import BytesIO
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple, Set

import streamlit as st
import pandas as pd

APP_VERSION = "2.0.0"

st.set_page_config(layout="wide")

# Ticker 1s (se disponível)
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=1000, key="tick_1s_boot")
except Exception:
    pass

# ---------------- Utilidades ----------------
def now_ts() -> float:
    return time.time()

def fmt_hhmmss(seconds: float) -> str:
    s = max(0, int(seconds))
    return str(timedelta(seconds=s))

def mmss(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s//60:02d}:{s%60:02d}"

def deep_snapshot_from(keys: List[str], src: Dict[str, Any]) -> Dict[str, Any]:
    return {k: copy.deepcopy(src.get(k)) for k in keys}
# ---------------- Leitura robusta do Excel ----------------

REQUIRED_SHEETS = ["Atletas", "Oficiais", "Info"]

def _normalize_sheet_names(xl_dict: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    norm = {}
    for name, df in xl_dict.items():
        key = str(name).strip().lower()
        if key in ["atletas", "plantel", "jogadores"]:
            norm["Atletas"] = df
        elif key in ["oficiais", "oficial", "staff"]:
            norm["Oficiais"] = df
        elif key in ["info", "informacao", "informação", "jogo", "match", "game"]:
            norm["Info"] = df
    for req in REQUIRED_SHEETS:
        if req not in norm and req in xl_dict:
            norm[req] = xl_dict[req]
    return norm

def _norm_cols(df: pd.DataFrame, kind: str) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip().lower() for c in out.columns]

    colmap = {
        "número": "numero", "nº": "numero", "num": "numero", "nr": "numero",
        "posição": "posicao", "posiçao": "posicao", "posicao": "posicao", "pos": "posicao",
        "equipa a": "equipa a", "equipe a": "equipa a",
        "equipa b": "equipa b", "equipe b": "equipa b",
        "data": "data", "local": "local", "nome": "nome",
    }
    out.rename(columns={c: colmap.get(c, c) for c in out.columns}, inplace=True)

    if kind == "Atletas":
        if "numero" not in out.columns and out.shape[1] >= 1:
            out.rename(columns={out.columns[0]: "numero"}, inplace=True)
        if "nome" not in out.columns and out.shape[1] >= 2:
            out.rename(columns={out.columns[1]: "nome"}, inplace=True)
        if "posicao" not in out.columns and out.shape[1] >= 3:
            out.rename(columns={out.columns[2]: "posicao"}, inplace=True)

        missing = [c for c in ["numero", "nome", "posicao"] if c not in out.columns]
        if missing:
            raise ValueError(f"Na folha 'Atletas' faltam colunas: {', '.join(missing)}")

        out["numero"] = out["numero"].apply(lambda x: int(x) if pd.notna(x) and str(x).isdigit() else str(x).strip())
        out["nome"] = out["nome"].astype(str).str.strip()
        out["posicao"] = out["posicao"].astype(str).str.strip()
        out = out[["numero", "nome", "posicao"]]

    elif kind == "Oficiais":
        if "nome" not in out.columns and out.shape[1] >= 1:
            out.rename(columns={out.columns[0]: "nome"}, inplace=True)
        if "posicao" not in out.columns and out.shape[1] >= 2:
            out.rename(columns={out.columns[1]: "posicao"}, inplace=True)

        missing = [c for c in ["nome", "posicao"] if c not in out.columns]
        if missing:
            raise ValueError(f"Na folha 'Oficiais' faltam colunas: {', '.join(missing)}")

        out["nome"] = out["nome"].astype(str).str.strip()
        out["posicao"] = out["posicao"].astype(str).str.strip()
        out.insert(0, "numero", "0")
        out = out[["numero", "nome", "posicao"]]

    elif kind == "Info":
        if "equipa a" not in out.columns and out.shape[1] >= 1:
            out.rename(columns={out.columns[0]: "equipa a"}, inplace=True)
        if "equipa b" not in out.columns and out.shape[1] >= 2:
            out.rename(columns={out.columns[1]: "equipa b"}, inplace=True)
        if "data" not in out.columns and out.shape[1] >= 3:
            out.rename(columns={out.columns[2]: "data"}, inplace=True)
        if "local" not in out.columns and out.shape[1] >= 4:
            out.rename(columns={out.columns[3]: "local"}, inplace=True)

        if not all(c in out.columns for c in ["equipa a", "equipa b", "data", "local"]):
            out = pd.DataFrame([{
                "equipa a": "Equipa A",
                "equipa b": "Equipa B",
                "data": datetime.now().strftime("%Y-%m-%d"),
                "local": "Local"
            }])
        else:
            out = out[["equipa a", "equipa b", "data", "local"]]

    return out

@st.cache_data(show_spinner=False)
def _read_xlsx_from_path(path: str) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sheets = pd.read_excel(path, sheet_name=None, engine="openpyxl")
    sheets = _normalize_sheet_names(sheets)
    for req in REQUIRED_SHEETS:
        if req not in sheets:
            raise ValueError(f"Falta a folha obrigatória '{req}' no Excel.")
    atletas = _norm_cols(sheets["Atletas"], "Atletas")
    oficiais = _norm_cols(sheets["Oficiais"], "Oficiais")
    info = _norm_cols(sheets["Info"], "Info")
    return atletas, oficiais, info

@st.cache_data(show_spinner=False)
def _read_xlsx_from_bytes(b: bytes) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    bio = BytesIO(b)
    sheets = pd.read_excel(bio, sheet_name=None, engine="openpyxl")
    sheets = _normalize_sheet_names(sheets)
    for req in REQUIRED_SHEETS:
        if req not in sheets:
            raise ValueError(f"Falta a folha obrigatória '{req}' no Excel.")
    atletas = _norm_cols(sheets["Atletas"], "Atletas")
    oficiais = _norm_cols(sheets["Oficiais"], "Oficiais")
    info = _norm_cols(sheets["Info"], "Info")
    return atletas, oficiais, info

def load_data() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    default_path = "Plantel.xlsx"
    with st.sidebar:
        st.markdown("### 📂 Plantel")
        up = st.file_uploader(
            "Carregar Plantel.xlsx",
            type=["xlsx"],
            key="file_uploader_roster",
            help="Abas: Atletas, Oficiais e Info.",
        )
        if up is not None:
            try:
                return _read_xlsx_from_bytes(up.getvalue())
            except ModuleNotFoundError:
                st.error("Falta **openpyxl**. Instala: `pip install openpyxl`"); st.stop()
            except Exception as e:
                st.error(f"Erro ao abrir o Excel carregado: {e}"); st.stop()

    if os.path.exists(default_path):
        try:
            return _read_xlsx_from_path(default_path)
        except ModuleNotFoundError:
            st.error("Falta **openpyxl**. Instala: `pip install openpyxl`"); st.stop()
        except Exception as e:
            st.error(f"Erro ao abrir o Excel: {e}"); st.stop()
    else:
        st.warning("⚠️ Coloca **Plantel.xlsx** na pasta do app ou usa o uploader na sidebar.", icon="🗂️")
        st.stop()
# ---------------- Estado inicial do jogo ----------------

def ensure_roster_loaded():
    if "game_state" in st.session_state:
        return
    atletas_df, oficiais_df, info_df = load_data()

    players: Dict[str, Dict[str, Any]] = {}
    gk_ids: List[str] = []
    field_ids: List[str] = []
    official_ids: List[str] = []

    # Atletas
    for idx, row in atletas_df.iterrows():
        num = row["numero"]
        nome = row["nome"]
        pos = row["posicao"]
        if not str(nome).strip():
            continue
        pid = f"player_{idx}_{num}_{nome}"
        players[pid] = {
            "id": pid,
            "num": num,
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

    # Oficiais (máx 5)
    for idx, row in oficiais_df.head(5).iterrows():
        nome = row["nome"]
        pos = row["posicao"]
        if not str(nome).strip():
            continue
        oid = f"official_{idx}_{nome}"
        players[oid] = {
            "id": oid,
            "num": "0",
            "nome": nome,
            "pos": pos,
            "in_field": False,      # não usado
            "time_played": 0.0,     # não usado
            "yellow": 0,            # regra agregada tratada nas ações
            "two_total": 0,
            "two_active": 0.0,
            "red": 0,
            "disq": False,
            "is_official": True,
        }
        official_ids.append(oid)

    info = info_df.iloc[0].to_dict()
    team_a = str(info.get("equipa a", "Equipa A"))
    team_b = str(info.get("equipa b", "Equipa B"))
    game_date = str(info.get("data", datetime.now().strftime("%Y-%m-%d")))
    game_place = str(info.get("local", "Local"))

    st.session_state.game_state = {
        "team_a": team_a, "team_b": team_b, "date": game_date, "place": game_place,
        "players": players, "gk_ids": gk_ids, "field_ids": field_ids, "official_ids": official_ids,
        "running": False, "start_time": None, "elapsed": 0.0, "half": 1, "half_len": 30*60,
        "last_minute_alert": False,
        "on_field_set": set(),           # ids dos jogadores (campo+GR) em jogo
        "team_penalties": [],            # contadores de 2’ da equipa
        "passive": False,
        "team_yellow_total": 0,          # atletas: máx 3 no total da equipa
        "score_for": {"1": 0, "2": 0},
        "score_against": {"1": 0, "2": 0},
        "goals": [], "shots": [], "events": [],
        "last_snapshot": None,
        # força de saída quando oficial leva 2' ou vermelho
        "official_forced_out": {},       # pid_atleta -> ts_unblock
        # contabilização global dos oficiais:
        "officials_global": {"yellow": 0, "two": 0},  # máx 1 amarelo no total, máx 1 dois-min no total
    }

ensure_roster_loaded()
gs = st.session_state.game_state
# ---------------- Zonas/Remates ----------------
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
GOAL_CHOICES = ["9m", "6m", "Penetração", "1 Vaga", "2 Vaga", "3 Vaga", "Baliza Aberta", "7m", "Pivot", "Ponta"]

def allowed_zones_for(typ: str) -> Set[int]:
    spec = ZONE_COMPAT_MAP.get(typ, "ALL")
    if spec == "ALL":
        return set(range(1, 8+1))
    if spec == "NO_ZONE":
        return set()
    return set(spec)

def current_allowed_on_field(gs: Dict[str, Any]) -> int:
    per_player_active = sum(1 for p in gs["players"].values() if p.get("two_active", 0.0) > 0 and not p.get("is_official"))
    team_active = sum(1 for t in gs["team_penalties"] if t > 0)
    return max(3, 7 - (per_player_active + team_active))

def has_seven_selected(gs: Dict[str, Any]) -> bool:
    return len(gs["on_field_set"]) == 7  # 7 iniciais (GR não obrigatório)
# ---------------- Undo ----------------
SNAP_KEYS = [
    "players", "on_field_set", "team_penalties", "team_yellow_total",
    "score_for", "score_against", "goals", "shots", "events",
    "running", "start_time", "elapsed", "half", "last_minute_alert",
    "official_forced_out", "officials_global",
]

def push_snapshot(label: str):
    snap = deep_snapshot_from(SNAP_KEYS, gs)
    snap["_label"] = label
    gs["last_snapshot"] = snap

def undo_last():
    if not gs.get("last_snapshot"):
        st.warning("Não há ação para desfazer.", icon="⚠️")
        return
    last = gs["last_snapshot"]
    for k in SNAP_KEYS:
        gs[k] = last[k]
    gs["last_snapshot"] = None
    st.toast(f"↩️ Desfeito: {last.get('_label','Ação')}", icon="↩️")

# ---------------- Tempo ----------------
def flush_time():
    if not gs["running"]:
        return
    if gs["start_time"] is None:
        gs["start_time"] = now_ts()
        return
    now = now_ts()
    delta = max(0.0, now - gs["start_time"])
    if delta == 0:
        return

    gs["elapsed"] += delta
    gs["start_time"] = now

    # tempo jogado
    for pid in list(gs["on_field_set"]):
        p = gs["players"].get(pid)
        if p and not p.get("is_official"):
            p["time_played"] = p.get("time_played", 0.0) + delta

    # 2' por jogador
    finished_players = []
    for pid, p in gs["players"].items():
        if p.get("two_active", 0.0) > 0:
            before = p["two_active"]
            p["two_active"] = max(0.0, p["two_active"] - delta)
            if before > 0 and p["two_active"] == 0:
                finished_players.append(pid)

    # 2' de equipa (inclui oficiais e 3×2’)
    finished_team = 0
    for i in range(len(gs["team_penalties"])):
        t = gs["team_penalties"][i]
        if t > 0:
            t2 = max(0.0, t - delta)
            gs["team_penalties"][i] = t2
            if t > 0 and t2 == 0:
                finished_team += 1

    # desbloqueios por sanção de oficial
    expired: List[str] = []
    for pid, unblock_ts in list(gs["official_forced_out"].items()):
        if now >= unblock_ts:
            expired.append(pid)
    for pid in expired:
        gs["official_forced_out"].pop(pid, None)
        p = gs["players"].get(pid)
        if p:
            st.toast(f"✅ {p['num']} {p['nome']} pode voltar a entrar (sanção de oficial terminou).", icon="✅")

    # toasts
    for pid in finished_players:
        p = gs["players"][pid]
        if p.get("disq", False):
            st.toast(f"✅ Inferioridade associada a {p['num']} {p['nome']} terminou (continua desqualificado).", icon="✅")
        else:
            st.toast(f"✅ {p['num']} {p['nome']} pode voltar a entrar (2’ terminou).", icon="✅")
    for _ in range(finished_team):
        st.toast("✅ Penalidade de equipa 2’ terminou.", icon="✅")

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
# ---------------- Play/Pause ----------------
def start_play():
    # Na 1ª parte: precisa de 7 selecionados (GR não obrigatório)
    if gs["half"] == 1 and len(gs["on_field_set"]) != 7:
        st.warning("Para iniciar a 1ª parte, seleciona **7 jogadores** (GR não é obrigatório).", icon="⚠️")
        return
    gs["running"] = True
    gs["start_time"] = now_ts()

def pause_play():
    if gs["running"]:
        flush_time()
    gs["running"] = False
# ---------------- Sanções ----------------

def _force_out_dialog_select_player(duration_s: int):
    """Popup para escolher o atleta a retirar por sanção de oficial (2’/vermelho)."""
    on_field = [pid for pid in gs["on_field_set"] if not gs["players"][pid].get("is_official")]
    st.subheader("Seleciona o atleta a retirar (cumprirá inferioridade)")
    if not on_field:
        st.warning("Não há atletas em campo para retirar — ajusta manualmente.", icon="⚠️")
        if st.button("Fechar", use_container_width=True, key="force_close_no_players"):
            st.session_state._open_force_out = False
            st.rerun()
        return
    options = {f"{gs['players'][pid]['num']} {gs['players'][pid]['nome']}": pid for pid in on_field}
    choice = st.selectbox("Atleta em campo:", list(options.keys()), key="force_sel")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Confirmar", use_container_width=True, key="force_ok"):
            pid = options[choice]
            # retira agora e bloqueia reentrada por duration_s
            p = gs["players"][pid]
            if pid in gs["on_field_set"]:
                gs["on_field_set"].discard(pid)
                p["in_field"] = False
            gs["official_forced_out"][pid] = now_ts() + duration_s
            st.toast(f"⛔ {p['num']} {p['nome']} retirado por {duration_s//60}’ (sanção de oficial).", icon="⛔")
            st.session_state._open_force_out = False
            st.rerun()
    with c2:
        if st.button("Cancelar", use_container_width=True, key="force_cancel"):
            st.session_state._open_force_out = False
            st.rerun()

def _open_force_out_dialog(duration_s: int):
    st.session_state._open_force_out = True
    st.session_state._force_out_duration = duration_s

@st.dialog("Retirar atleta (sanção de oficial)")
def force_out_dialog():
    dur = st.session_state.get("_force_out_duration", 120)
    _force_out_dialog_select_player(dur)

def give_yellow(pid: str):
    p = gs["players"][pid]
    if p.get("disq", False):
        st.warning("Já está desqualificado.", icon="⚠️"); return

    if p.get("is_official", False):
        # Oficiais: no total 1 amarelo (global)
        if gs["officials_global"]["yellow"] >= 1:
            st.warning("Os oficiais já têm 1 amarelo no total — agora apenas 2’/🟥.", icon="⚠️")
            return
        if p["yellow"] >= 1:
            st.warning("Este oficial já tem amarelo.", icon="⚠️"); return
        push_snapshot(f"Amarelo oficial {p['nome']}")
        p["yellow"] = 1
        gs["officials_global"]["yellow"] += 1
        st.toast(f"🟨 Oficial {p['nome']}: amarelo (global: {gs['officials_global']['yellow']}/1).", icon="🟨")
        return

    # Atletas: equipa máx 3 amarelos; atleta máx 1
    if gs["team_yellow_total"] >= 3:
        st.warning("Limite de amarelos da equipa atingido (3/3).", icon="⚠️"); return
    if p["yellow"] >= 1:
        st.warning("Este atleta já tem 1 amarelo.", icon="⚠️"); return

    push_snapshot(f"Amarelo atleta {p['nome']}")
    p["yellow"] = 1
    gs["team_yellow_total"] += 1
    st.toast(f"🟨 {p['num']} {p['nome']}: amarelo (equipa {gs['team_yellow_total']}/3).", icon="🟨")

def give_two_minutes(pid: str):
    p = gs["players"][pid]
    if p.get("disq", False):
        st.warning("Desqualificado não pode receber 2’.", icon="⚠️"); return
    push_snapshot(f"2’ {p['nome']}")

    if p.get("is_official", False):
        # Oficiais: no total 1 dois minutos (global); depois só vermelho
        if gs["officials_global"]["two"] >= 1:
            st.warning("Os oficiais já têm 1 sanção de 2’ no total — a partir daqui só vermelho.", icon="⚠️")
            return
        if p["two_total"] >= 1:
            st.warning("Este oficial já tem 2’.", icon="⚠️"); return
        gs["officials_global"]["two"] += 1
        p["two_total"] += 1
        gs["team_penalties"].append(120.0)  # cumpre a equipa
        st.toast(f"⏱️ Oficial {p['nome']}: 2’ (equipa cumpre 2’).", icon="⏱️")
        _open_force_out_dialog(120)  # escolher atleta a retirar
        return

    # Jogadores (acumula, 3x => desqualificação + 2’ equipa)
    if pid in gs["on_field_set"]:
        flush_time()
        gs["on_field_set"].discard(pid)
        p["in_field"] = False

    p["two_total"] += 1
    if p["two_total"] >= 3:
        p["disq"] = True
        gs["team_penalties"].append(120.0)
        st.error(f"🟥 {p['num']} {p['nome']} desqualificado (3×2’). Equipa cumpre +2’.", icon="🚫")
    else:
        p["two_active"] = p.get("two_active", 0.0) + 120.0
        st.toast(f"🚫 {p['num']} {p['nome']}: +2’ (ativo: {int(p['two_active'])}s).", icon="⏱️")

def give_red(pid: str):
    p = gs["players"][pid]
    if p.get("disq", False):
        st.warning("Já está desqualificado.", icon="⚠️"); return
    push_snapshot(f"Vermelho {p['nome']}")

    if pid in gs["on_field_set"]:
        flush_time()
        gs["on_field_set"].discard(pid)
        p["in_field"] = False

    p["disq"] = True
    p["red"] = p.get("red", 0) + 1
    gs["team_penalties"].append(120.0)
    if p.get("is_official", False):
        st.error(f"🟥 Oficial {p['nome']}: expulsão. Equipa cumpre 2’.", icon="🚫")
        _open_force_out_dialog(120)  # escolher atleta a retirar
    else:
        st.error(f"🟥 {p['num']} {p['nome']}: expulsão. Equipa cumpre 2’.", icon="🚫")
# ---------------- Ações ----------------

def register_goal(pid: str, typ: str, zona: Optional[int], sofrido: bool = False):
    p = gs["players"][pid]
    if p.get("disq", False):
        st.warning("Desqualificado não pode marcar.", icon="⚠️"); return
    push_snapshot(f"Golo ({'sofrido' if sofrido else 'marcado'}) {p['nome']} {typ}")
    entry = {"player_id": pid, "tipo": typ, "zona": zona, "half": gs["half"], "sofrido": bool(sofrido), "t": int(gs["elapsed"])}
    gs["goals"].append(entry)
    if sofrido:
        gs["score_against"][str(gs["half"])] += 1
        st.toast(f"⚠️ Golo sofrido — {typ}{(' · Z'+str(zona)) if zona else ''}", icon="⚠️")
    else:
        gs["score_for"][str(gs["half"])] += 1
        st.toast(f"⚽ {p['num']} {p['nome']} — {typ}{(' · Z'+str(zona)) if zona else ''}", icon="⚽")
    gs["passive"] = False

def register_shot(pid: str, outcome: str, typ: str, zona: Optional[int], sofrido: bool = False):
    p = gs["players"][pid]
    if p.get("disq", False):
        st.warning("Desqualificado não pode rematar.", icon="⚠️"); return
    push_snapshot(f"Remate {outcome} {p['nome']} {typ}")
    entry = {"player_id": pid, "tipo": typ, "resultado": outcome, "zona": zona, "half": gs["half"], "sofrido": bool(sofrido), "t": int(gs["elapsed"])}
    gs["shots"].append(entry)
    icon = "🧤" if outcome == "defendido" else "❌"
    suf = " (sofrido)" if sofrido else ""
    st.toast(f"{icon} Remate {outcome}{suf} — {p['nome']} · {typ}{(' · Z'+str(zona)) if zona else ''}", icon=icon)
    gs["passive"] = False

def register_tech_fault(pid: str):
    p = gs["players"][pid]
    push_snapshot(f"Falha técnica {p['nome']}")
    p["tech_faults"] = p.get("tech_faults", 0) + 1
    st.toast(f"⚠️ Falha técnica — {p['nome']}", icon="⚠️")

def register_conquista(pid: str, label: str):
    p = gs["players"][pid]
    push_snapshot(f"Conquista {label} {p['nome']}")
    p["conquistas"].append({"t": int(gs["elapsed"]), "label": label})
    st.toast(f"🏆 Conquista: {label} — {p['nome']}", icon="🏆")
# ---------------- Modais ----------------

def open_sanction_modal(pid: str):
    st.session_state._tmp_player_for_sanction = pid
    st.session_state._open_sanction = True

def open_shot_modal(pid: str, is_gk: bool):
    st.session_state._tmp_player_for_shot = (pid, is_gk)
    st.session_state._open_shot = True

def open_zone_modal(ctx: Dict[str, Any]):
    st.session_state._zone_ctx = ctx
    st.session_state._open_zone = True

def open_conquista_modal(pid: str, is_gk: bool):
    st.session_state._tmp_player_for_conquista = (pid, is_gk)
    st.session_state._open_conquista = True

@st.dialog("Aplicar sanção")
def sanction_dialog():
    pid = st.session_state.get("_tmp_player_for_sanction")
    if not pid:
        st.write("Sem jogador selecionado.")
        if st.button("Fechar", use_container_width=True):
            st.session_state._open_sanction = False; st.rerun()
        return
    p = gs["players"][pid]
    is_off = p.get("is_official", False)

    st.subheader(f"{p.get('num','')} · {p['nome']}{' (Oficial)' if is_off else ''}")
    colA, colB, colC, colD = st.columns(4)
    with colA: st.metric("Amarelo", f"{p.get('yellow',0)}/1" if not is_off else f"{gs['officials_global']['yellow']}/1 (global)")
    with colB: st.metric("2' total", f"{p.get('two_total',0)}" if not is_off else f"{gs['officials_global']['two']}/1 (global)")
    with colC: st.metric("2' ativa (s)", f"{int(p.get('two_active',0))}")
    with colD: st.metric("Vermelhos", f"{p.get('red',0)}")

    st.divider()
    st.write("**Escolhe a sanção:**")

    can_yellow = not p.get("disq", False)
    can_two = not p.get("disq", False)
    can_red = not p.get("disq", False)

    if is_off:
        if gs["officials_global"]["yellow"] >= 1 or p.get("yellow", 0) >= 1:
            can_yellow = False
        if gs["officials_global"]["two"] >= 1 or p.get("two_total", 0) >= 1:
            can_two = False
    else:
        if gs["team_yellow_total"] >= 3 or p.get("yellow", 0) >= 1:
            can_yellow = False

    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("🟨 Amarelo", use_container_width=True, disabled=not can_yellow, key=f"s_y_{pid}"):
            flush_time(); give_yellow(pid)
            st.session_state._open_sanction = False; st.rerun()
    with b2:
        if st.button("🚫 2 minutos", use_container_width=True, disabled=not can_two, key=f"s_2_{pid}"):
            flush_time(); give_two_minutes(pid)
            st.session_state._open_sanction = False; st.rerun()
    with b3:
        if st.button("🟥 Vermelho", use_container_width=True, disabled=not can_red, key=f"s_r_{pid}"):
            flush_time(); give_red(pid)
            st.session_state._open_sanction = False; st.rerun()

    st.divider()
    if st.button("Fechar", use_container_width=True, key=f"s_close_{pid}"):
        st.session_state._open_sanction = False; st.rerun()

@st.dialog("Remate / Golo")
def shot_dialog():
    tmp = st.session_state.get("_tmp_player_for_shot")
    if not tmp:
        st.write("Sem jogador selecionado.")
        if st.button("Fechar", use_container_width=True): st.session_state._open_shot=False; st.rerun()
        return
    pid, is_gk = tmp
    p = gs["players"][pid]
    st.subheader(f"{p.get('num','')} · {p['nome']}{' (GR)' if is_gk else ''}")
    st.caption(f"Parte: {gs['half']}ª — Tempo: {fmt_hhmmss(gs['elapsed'])}")

    if is_gk:
        st.markdown("### 🧤 Remates Sofridos — **Golo Sofrido**")
        for row in [["9m","6m","Penetração","1 Vaga","2 Vaga"], ["3 Vaga","Baliza Aberta","7m","Pivot","Ponta"]]:
            cols = st.columns(len(row))
            for typ, col in zip(row, cols):
                with col:
                    if st.button(typ, key=f"gk_suf_goal_{pid}_{typ}", use_container_width=True):
                        zones = allowed_zones_for(typ)
                        if not zones:
                            flush_time(); register_goal(pid, typ, None, sofrido=True)
                            st.session_state._open_shot=False; st.rerun()
                        else:
                            open_zone_modal({"kind":"goal","pid":pid,"typ":typ,"sofrido":True})
                            st.session_state._open_shot=False; st.rerun()

        st.divider()
        st.markdown("### 🧤 Remates Sofridos — **Defendidos**")
        for row in [["9m","6m","Penetração","1 Vaga","2 Vaga"], ["3 Vaga","Baliza Aberta","7m","Pivot","Ponta"]]:
            cols = st.columns(len(row))
            for typ, col in zip(row, cols):
                with col:
                    if st.button(typ, key=f"gk_suf_def_{pid}_{typ}", use_container_width=True):
                        zones = allowed_zones_for(typ)
                        if not zones:
                            flush_time(); register_shot(pid, "defendido", typ, None, sofrido=True)
                            st.session_state._open_shot=False; st.rerun()
                        else:
                            open_zone_modal({"kind":"defendido","pid":pid,"typ":typ,"sofrido":True})
                            st.session_state._open_shot=False; st.rerun()

        st.divider()
        st.markdown("### 🧤 Remates Sofridos — **Falhados**")
        for row in [["9m","6m","Penetração","1 Vaga","2 Vaga"], ["3 Vaga","Baliza Aberta","7m","Pivot","Ponta"]]:
            cols = st.columns(len(row))
            for typ, col in zip(row, cols):
                with col:
                    if st.button(typ, key=f"gk_suf_miss_{pid}_{typ}", use_container_width=True):
                        zones = allowed_zones_for(typ)
                        if not zones:
                            flush_time(); register_shot(pid, "falhado", typ, None, sofrido=True)
                            st.session_state._open_shot=False; st.rerun()
                        else:
                            open_zone_modal({"kind":"falhado","pid":pid,"typ":typ,"sofrido":True})
                            st.session_state._open_shot=False; st.rerun()

        st.divider()
        st.markdown("### ⚽ Golo do GR")
        if st.button("Golo", key=f"gk_goal_{pid}", use_container_width=True):
            flush_time(); register_goal(pid, "Golo GR", None, sofrido=False)
            st.session_state._open_shot=False; st.rerun()

    else:
        st.markdown("### ⚽ Golo")
        for row in [["9m","6m","Penetração","1 Vaga","2 Vaga"], ["3 Vaga","Baliza Aberta","7m","Pivot","Ponta"]]:
            cols = st.columns(len(row))
            for typ, col in zip(row, cols):
                with col:
                    if st.button(typ, key=f"pl_goal_{pid}_{typ}", use_container_width=True):
                        zones = allowed_zones_for(typ)
                        if not zones:
                            flush_time(); register_goal(pid, typ, None, sofrido=False)
                            st.session_state._open_shot=False; st.rerun()
                        else:
                            open_zone_modal({"kind":"goal","pid":pid,"typ":typ,"sofrido":False})
                            st.session_state._open_shot=False; st.rerun()

        st.divider()
        st.markdown("### 🧤 Remates Defendidos")
        for row in [["9m","6m","Penetração","1 Vaga","2 Vaga"], ["3 Vaga","Baliza Aberta","7m","Pivot","Ponta"]]:
            cols = st.columns(len(row))
            for typ, col in zip(row, cols):
                with col:
                    if st.button(typ, key=f"pl_def_{pid}_{typ}", use_container_width=True):
                        zones = allowed_zones_for(typ)
                        if not zones:
                            flush_time(); register_shot(pid, "defendido", typ, None, sofrido=False)
                            st.session_state._open_shot=False; st.rerun()
                        else:
                            open_zone_modal({"kind":"defendido","pid":pid,"typ":typ,"sofrido":False})
                            st.session_state._open_shot=False; st.rerun()

        st.divider()
        st.markdown("### ❌ Remates Falhados")
        for row in [["9m","6m","Penetração","1 Vaga","2 Vaga"], ["3 Vaga","Baliza Aberta","7m","Pivot","Ponta"]]:
            cols = st.columns(len(row))
            for typ, col in zip(row, cols):
                with col:
                    if st.button(typ, key=f"pl_miss_{pid}_{typ}", use_container_width=True):
                        zones = allowed_zones_for(typ)
                        if not zones:
                            flush_time(); register_shot(pid, "falhado", typ, None, sofrido=False)
                            st.session_state._open_shot=False; st.rerun()
                        else:
                            open_zone_modal({"kind":"falhado","pid":pid,"typ":typ,"sofrido":False})
                            st.session_state._open_shot=False; st.rerun()

    st.divider()
    if st.button("Fechar", use_container_width=True):
        st.session_state._open_shot=False; st.rerun()

@st.dialog("Escolher zona de campo")
def zone_dialog():
    ctx = st.session_state.get("_zone_ctx")
    if not ctx:
        st.write("Sem contexto.")
        if st.button("Fechar", use_container_width=True): st.session_state._open_zone=False; st.rerun()
        return
    pid = ctx["pid"]; typ = ctx["typ"]; kind = ctx["kind"]; sofrido = ctx.get("sofrido", False)
    p = gs["players"][pid]

    zones_allowed = allowed_zones_for(typ)
    st.subheader(f"{p.get('num','')} · {p['nome']}")
    st.caption(f"Tipo: {typ} — {'Golo' if kind=='goal' else ('Defendido' if kind=='defendido' else 'Falhado')}")

    cols1 = st.columns(5)
    for i, col in enumerate(cols1, start=1):
        with col:
            if st.button(f"Zona {i}", key=f"z_{pid}_{typ}_{kind}_{i}", disabled=(i not in zones_allowed), use_container_width=True):
                flush_time()
                if kind == "goal": register_goal(pid, typ, i, sofrido=sofrido)
                else: register_shot(pid, kind, typ, i, sofrido=sofrido)
                st.session_state._open_zone=False; st.session_state._zone_ctx=None; st.rerun()

    cols2 = st.columns(3)
    for idx, z in enumerate([6,7,8]):
        with cols2[idx]:
            if st.button(f"Zona {z}", key=f"z_{pid}_{typ}_{kind}_{z}", disabled=(z not in zones_allowed), use_container_width=True):
                flush_time()
                if kind == "goal": register_goal(pid, typ, z, sofrido=sofrido)
                else: register_shot(pid, kind, typ, z, sofrido=sofrido)
                st.session_state._open_zone=False; st.session_state._zone_ctx=None; st.rerun()

    st.divider()
    if st.button("Cancelar", use_container_width=True):
        st.session_state._open_zone=False; st.session_state._zone_ctx=None; st.rerun()

@st.dialog("Conquista")
def conquista_dialog():
    tmp = st.session_state.get("_tmp_player_for_conquista")
    if not tmp:
        st.write("Sem jogador selecionado.")
        if st.button("Fechar", use_container_width=True): st.session_state._open_conquista=False; st.rerun()
        return
    pid, is_gk = tmp
    p = gs["players"][pid]
    st.subheader(f"{p.get('num','')} · {p['nome']}{' (GR)' if is_gk else ''}")

    if is_gk:
        if st.button("Conquista 2’ (provoca 2’ adversário)", use_container_width=True, key=f"cq_gr_{pid}"):
            register_conquista(pid, "Conquista 2’ (GR)")
            st.session_state._open_conquista=False; st.rerun()
    else:
        row1 = ["Roubo de Bola", "Interseção"]
        cols1 = st.columns(len(row1))
        for lab, col in zip(row1, cols1):
            with col:
                if st.button(lab, use_container_width=True, key=f"cq_{pid}_{lab}"):
                    register_conquista(pid, lab); st.session_state._open_conquista=False; st.rerun()
        st.divider()
        # Botão 2 min + 7m (um clique regista ambos)
        row2 = ["2 min", "7m", "2 min + 7m"]
        cols2 = st.columns(len(row2))
        for lab, col in zip(row2, cols2):
            with col:
                if st.button(lab, use_container_width=True, key=f"cq2_{pid}_{lab}"):
                    if lab == "2 min + 7m":
                        register_conquista(pid, "2 min"); register_conquista(pid, "7m")
                    else:
                        register_conquista(pid, lab)
                    st.session_state._open_conquista=False; st.rerun()

    st.divider()
    if st.button("Fechar", use_container_width=True, key=f"cq_close_{pid}"):
        st.session_state._open_conquista=False; st.rerun()
# ---------------- UI: Cabeçalho e Linhas ----------------

def render_header_row():
    h_estado, h_tempo, h_num, h_nome, h_btns = st.columns([0.18, 0.10, 0.10, 0.32, 0.30])
    with h_estado: st.caption("Banco/Campo")
    with h_tempo:  st.caption("Tempo (min)")
    with h_num:    st.caption("Nº")
    with h_nome:   st.caption("Nome")
    with h_btns:   st.caption("Ações")

def _can_enter(pid: str) -> bool:
    """Bloqueia entrada se atleta estiver forçado por sanção de oficial."""
    unblock = gs["official_forced_out"].get(pid)
    if unblock and now_ts() < unblock:
        return False
    return True

def render_player_row(pid: str, is_gk: bool=False, is_official: bool=False):
    p = gs["players"][pid]

    # Badge estado
    if p.get("disq", False):
        badge = "<span class='pill pill-red'>🟥 Desqualificado</span>"
    elif p.get("two_active", 0.0) > 0:
        badge = f"<span class='pill pill-orange'>⛔ 2’ ({int(p['two_active'])}s)</span>"
    else:
        if is_official:
            badge = "<span class='pill pill-blue'>👤 Oficial</span>"
        else:
            badge = "<span class='pill pill-green'>🟢 Em campo</span>" if p.get("in_field", False) else "<span class='pill pill-yellow'>🟡 Banco</span>"

    mins = "" if is_official else int(min(60, p.get("time_played", 0.0) // 60))

    c_est, c_tmp, c_num, c_nom, c_btns = st.columns([0.18, 0.10, 0.10, 0.32, 0.30])

    with c_est:  st.markdown(f"<div class='row-compact'>{badge}</div>", unsafe_allow_html=True)
    with c_tmp:  st.markdown(f"<div class='row-compact mins'>{mins}</div>", unsafe_allow_html=True)
    with c_num:  st.markdown(f"<div class='row-compact num'>{p.get('num','')}</div>", unsafe_allow_html=True)

    with c_nom:
        disabled_name = is_official or p.get("disq", False) or (p.get("two_active", 0.0) > 0) or (not _can_enter(pid))
        label = f"{p['nome']}"
        clicked = st.button(label, key=f"btn_name_{pid}", use_container_width=True, disabled=disabled_name,
                            help="Clique para entrar/sair (oficiais não entram em campo).")
        if clicked and not is_official:
            flush_time()
            if p.get("in_field", False):
                p["in_field"] = False
                gs["on_field_set"].discard(pid)
            else:
                if len(gs["on_field_set"]) >= current_allowed_on_field(gs):
                    st.warning(f"Máximo de {current_allowed_on_field(gs)} em campo neste momento.", icon="⚠️")
                else:
                    p["in_field"] = True
                    gs["on_field_set"].add(pid)
            gs["start_time"] = now_ts()

    with c_btns:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.button("📋", key=f"btn_sanc_{pid}", use_container_width=True, help="Sanção",
                      on_click=open_sanction_modal, args=(pid,))
        with col2:
            if not is_official:
                st.button("🎯", key=f"btn_shot_{pid}", use_container_width=True,
                          help=("Remates/GR" if is_gk else "Golos/Remates"),
                          on_click=open_shot_modal, args=(pid, is_gk))
        with col3:
            if not is_official:
                st.button("🏆", key=f"btn_conquista_{pid}", use_container_width=True,
                          help="Conquista", on_click=open_conquista_modal, args=(pid, is_gk))
        with col4:
            if not is_official:
                if st.button("⚠️", key=f"btn_tech_{pid}", use_container_width=True, help="Falha Técnica"):
                    register_tech_fault(pid)
# ---------------- Layout topo ----------------

# Branding/sidebar
with st.sidebar:
    st.markdown(
        f"""
        <div style="text-align:center; font-weight:800; letter-spacing:1px; margin-bottom:10px;">
            BY ANDRÉ TOJAL
        </div>
        """,
        unsafe_allow_html=True
    )
    st.caption(f"Versão: {APP_VERSION}")
    st.divider()

# Info do jogo
st.markdown(
    f"""
    <div style="text-align:center; margin-top:2px;">
      <div style="font-size:22px; font-weight:800;">{gs['team_a']} VS {gs['team_b']}</div>
      <div style="font-size:14px; color:#666;">{gs['date']} • {gs['place']}</div>
    </div>
    """,
    unsafe_allow_html=True
)

# Linha 1 — Botões do cronómetro
c1, c2, c3, c4 = st.columns([1,1,1,1])
with c1: st.button("▶️ Play", on_click=start_play, use_container_width=True, key="btn_play_top")
with c2: st.button("⏸️ Pausa", on_click=pause_play, use_container_width=True, key="btn_pause_top")
with c3: st.button("↩️ Desfazer", on_click=undo_last, use_container_width=True, key="btn_undo_top")
with c4:
    st.write("")  # reservado

# Linha 2 — Banner estado
if gs["running"]:
    banner = "<div style='text-align:center; font-size:20px; font-weight:800; color:#0a0;'>🟢 EM JOGO</div>"
else:
    banner = "<div style='text-align:center; font-size:20px; font-weight:800; color:#c00;'>⏸️ PAUSADO</div>"
st.markdown(banner, unsafe_allow_html=True)

# Atualizar tempo
flush_time()

# Linha 3 — Mostrador cronómetro
rem = max(0, int(gs["half_len"] - gs["elapsed"]))
cA, cB, cC = st.columns([1,1,1])
with cB:
    st.metric(f"Tempo {gs['half']}ª", f"{fmt_hhmmss(gs['elapsed'])} / 0:30:00", delta=f"Faltam {fmt_hhmmss(rem)}")

# Linha 4 — Passivo + Estado (Igualdade / Inferioridade / 7x6)
cP1, cP2 = st.columns([1,1])
with cP1:
    gs["passive"] = st.toggle("🏳️ Passivo", value=gs["passive"], help="Ativa/Desativa jogo passivo (desliga ao registar ação)")
with cP2:
    infer = (sum(1 for t in gs["team_penalties"] if t > 0) > 0) or \
            (sum(1 for p in gs["players"].values() if p.get("two_active",0)>0 and not p.get("is_official"))>0)
    seven_no_gk = (len(gs["on_field_set"]) == 7 and all(gs["players"][pid].get("pos","").upper() != "GR" for pid in gs["on_field_set"]))
    if seven_no_gk:
        st.markdown("<div style='text-align:center; font-weight:700;'>7x6</div>", unsafe_allow_html=True)
    elif infer:
        st.markdown("<div style='text-align:center; font-weight:700;'>Inferioridade</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div style='text-align:center; font-weight:700;'>Igualdade</div>", unsafe_allow_html=True)

# CSS utilitário
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
    </style>
    """,
    unsafe_allow_html=True
)
# ---------------- Resultado (Topo compacto) ----------------
score_for_total = gs["score_for"]["1"] + gs["score_for"]["2"]
score_against_total = gs["score_against"]["1"] + gs["score_against"]["2"]

cR1, cR2, cR3 = st.columns([1,1.2,1])
with cR2:
    st.markdown(
        f"""
        <div style="text-align:center; margin:4px 0 8px 0;">
          <div style="font-size:18px; font-weight:800;">RESULTADO</div>
          <div style="font-size:16px; margin-top:4px;">({score_for_total}) Totais ({score_against_total})</div>
          <div style="font-size:14px; margin-top:2px;">({gs['score_for']['1']}) 1ª Parte ({gs['score_against']['1']})</div>
          <div style="font-size:14px; margin-top:2px;">({gs['score_for']['2']}) 2ª Parte ({gs['score_against']['2']})</div>
        </div>
        """,
        unsafe_allow_html=True
    )

# ---------------- Abas ----------------
tab_principal, tab_resumo = st.tabs(["Principal", "Resumo"])

with tab_principal:
    allowed_now = current_allowed_on_field(gs)
    st.caption(f"Em campo: {len(gs['on_field_set'])}/{allowed_now} (máx dinâmico: 7 − sanções ativas; mínimo 3)")
    render_header_row()

    # GR
    if gs["gk_ids"]:
        st.markdown("<div class='section-title'>Guarda-redes</div>", unsafe_allow_html=True)
        for pid in gs["gk_ids"]:
            render_player_row(pid, is_gk=True, is_official=False)

    # Jogadores de campo
    if gs["field_ids"]:
        st.markdown("<div class='section-title'>Jogadores de campo</div>", unsafe_allow_html=True)
        for pid in gs["field_ids"]:
            render_player_row(pid, is_gk=False, is_official=False)

    # Oficiais
    if gs["official_ids"]:
        st.markdown("<div class='section-title'>Oficiais</div>", unsafe_allow_html=True)
        h_est2, h_num2, h_nome2, h_btn2 = st.columns([0.18, 0.10, 0.52, 0.20])
        with h_est2: st.caption("Tipo")
        with h_num2: st.caption("Nº")
        with h_nome2: st.caption("Nome")
        with h_btn2: st.caption("Sanção")

        for pid in gs["official_ids"]:
            p = gs["players"][pid]
            if p.get("disq", False):
                badge = "<span class='pill pill-red'>🟥 Desqualificado</span>"
            elif p.get("two_active", 0.0) > 0:
                badge = f"<span class='pill pill-orange'>⛔ 2’ ({int(p['two_active'])}s)</span>"
            else:
                badge = "<span class='pill pill-blue'>👤 Oficial</span>"

            c1, c2, c3, c4 = st.columns([0.18, 0.10, 0.52, 0.20])
            with c1: st.markdown(f"<div class='row-compact'>{badge}</div>", unsafe_allow_html=True)
            with c2: st.markdown(f"<div class='row-compact num'>0</div>", unsafe_allow_html=True)
            with c3: st.markdown(f"<div class='row-compact'>{p['nome']} ({p.get('pos','')})</div>", unsafe_allow_html=True)
            with c4:
                st.button("📋", key=f"btn_sanc_off_{pid}", use_container_width=True, help="Sanção ao oficial",
                          on_click=open_sanction_modal, args=(pid,))
with tab_resumo:
    def build_dataframes_for_export():
        players = gs["players"]
        rows = []
        for pid, p in players.items():
            rows.append({
                "ID": str(pid),
                "Oficial": bool(p.get("is_official", False)),
                "Número": str(p.get("num", "")),
                "Nome": str(p.get("nome", "")),
                "Posição": str(p.get("pos", "")),
                "Tempo (s)": float(p.get("time_played", 0.0)),
                "Tempo (mm:ss)": mmss(float(p.get("time_played", 0.0))),
                "Em campo": bool(p.get("in_field", False)),
                "Amarelos": int(p.get("yellow", 0)),
                "2' total": int(p.get("two_total", 0)),
                "2' ativa (s)": int(p.get("two_active", 0.0)),
                "Vermelhos": int(p.get("red", 0)),
                "Desqualificado": bool(p.get("disq", False)),
                "Falhas Técnicas": int(p.get("tech_faults", 0)),
            })
        df_players = pd.DataFrame(rows)

        df_goals = pd.DataFrame(gs.get("goals", [])) if gs.get("goals") else pd.DataFrame(columns=["player_id","tipo","zona","half","sofrido","t"])
        df_shots = pd.DataFrame(gs.get("shots", [])) if gs.get("shots") else pd.DataFrame(columns=["player_id","tipo","resultado","zona","half","sofrido","t"])

        # Normalizar tipos para Arrow
        for col in ["player_id","tipo","resultado"]:
            if col in df_shots.columns:
                df_shots[col] = df_shots[col].astype(str)
        for col in ["player_id","tipo"]:
            if col in df_goals.columns:
                df_goals[col] = df_goals[col].astype(str)
        if "zona" in df_goals.columns:
            df_goals["zona"] = df_goals["zona"].astype("Int64")
        if "zona" in df_shots.columns:
            df_shots["zona"] = df_shots["zona"].astype("Int64")

        return df_players, df_goals, df_shots

    df_players, df_goals, df_shots = build_dataframes_for_export()

    st.markdown("#### Jogadores / Oficiais")
    st.dataframe(df_players, hide_index=True, use_container_width=True)

    df_score = pd.DataFrame({
        "Parte": ["1ª", "2ª", "Total"],
        "Marcados": [gs["score_for"]["1"], gs["score_for"]["2"], gs["score_for"]["1"] + gs["score_for"]["2"]],
        "Sofridos": [gs["score_against"]["1"], gs["score_against"]["2"], gs["score_against"]["1"] + gs["score_against"]["2"]],
    })
    st.markdown("#### Resultado — Marcados vs Sofridos")
    st.dataframe(df_score, hide_index=True, use_container_width=True)

    st.markdown("#### Exportação")
    st.download_button(
        "📥 Jogadores (CSV)",
        data=df_players.to_csv(index=False).encode("utf-8"),
        file_name="jogadores.csv",
        mime="text/csv",
        key="dl_players_csv"
    )
    st.download_button(
        "📥 Golos (CSV)",
        data=df_goals.to_csv(index=False).encode("utf-8"),
        file_name="golos.csv",
        mime="text/csv",
        key="dl_goals_csv"
    )
    st.download_button(
        "📥 Remates (CSV)",
        data=df_shots.to_csv(index=False).encode("utf-8"),
        file_name="remates.csv",
        mime="text/csv",
        key="dl_shots_csv"
    )

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_players.to_excel(writer, index=False, sheet_name="Jogadores")
        df_goals.to_excel(writer, index=False, sheet_name="Golos")
        df_shots.to_excel(writer, index=False, sheet_name="Remates")
    st.download_button(
        "📊 Exportar Tudo (Excel)",
        data=output.getvalue(),
        file_name="export_estatisticas_andebol.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dl_all_xlsx"
    )
# ---------------- Modais pendentes ----------------
if st.session_state.get("_open_sanction"):
    sanction_dialog()
if st.session_state.get("_open_shot"):
    shot_dialog()
if st.session_state.get("_open_zone"):
    zone_dialog()
if st.session_state.get("_open_conquista"):
    conquista_dialog()
if st.session_state.get("_open_force_out"):
    force_out_dialog()

# ---------------- Estilos finais ----------------
st.markdown(
    """
    <style>
      .stButton > button { padding: 0.45rem 0.7rem; }
      .small-caption { font-size: 12px; color: #777; }
      hr { border: none; height: 1px; background: #eee; }
    </style>
    """,
    unsafe_allow_html=True
)

# Tick principal
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=1000, key="tick_1s_main")
except Exception:
    pass
# ---------------- Sincronização em pausa + rodapé ----------------

def _get_elapsed():
    if gs["running"] and gs["start_time"] is not None:
        return now_ts() - gs["start_time"]
    return gs["elapsed"]

if not gs["running"]:
    gs["elapsed"] = _get_elapsed()

st.markdown(
    "<div class='small-caption' style='text-align:center; margin-top:10px;'>Estatísticas de Andebol • Streamlit</div>",
    unsafe_allow_html=True
)