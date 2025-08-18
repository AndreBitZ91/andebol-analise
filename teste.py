# teste.py — App de estatística de andebol
# Requisitos: streamlit, pandas, openpyxl, pyarrow, (opcional) streamlit-autorefresh
# Executar: python3 -m streamlit run teste.py

import os
import time
import copy
from io import BytesIO
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

import streamlit as st
import pandas as pd

st.set_page_config(layout="wide", page_title="Estatísticas Andebol", page_icon="🏐")

try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=1000, key="tick_boot")
except Exception:
    pass

def fmt_hhmmss(seconds: float) -> str:
    s = max(0, int(seconds))
    return str(timedelta(seconds=s))

def format_time(seconds: float) -> str:
    s = max(0, int(seconds))
    mm = s // 60
    ss = s % 60
    return f"{mm:02d}:{ss:02d}"

def now_ts() -> float:
    return time.time()

def deep_snapshot_from(keys: List[str], src: Dict[str, Any]) -> Dict[str, Any]:
    return {k: copy.deepcopy(src.get(k)) for k in keys}
# ======================= Excel Helpers =======================

def _norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
    ren = {}
    for c in list(out.columns):
        c_low = c.lower()
        if c_low in ("numero", "número", "nr", "nº", "num", "n."):
            ren[c] = "Numero"
        elif c_low in ("nome", "jogador", "atleta"):
            ren[c] = "Nome"
        elif c_low in ("posicao", "posição", "pos", "posição."):
            ren[c] = "Posicao"
        elif c_low in ("equipa a", "equipa_a", "equipa-a"):
            ren[c] = "Equipa a"
        elif c_low in ("equipa b", "equipa_b", "equipa-b"):
            ren[c] = "Equipa b"
        elif c_low in ("data",):
            ren[c] = "Data"
        elif c_low in ("local",):
            ren[c] = "Local"
    if ren:
        out = out.rename(columns=ren)
    return out

def load_data_excel(uploaded_file) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    try:
        xl = pd.ExcelFile(uploaded_file)
    except ModuleNotFoundError:
        st.error("Falta a dependência **openpyxl**. Instala: `pip install openpyxl`")
        st.stop()
    except Exception as e:
        st.error(f"Erro ao abrir o Excel: {e}")
        st.stop()

    required = ["Atletas", "Oficiais", "Info"]
    for sh in required:
        if sh not in xl.sheet_names:
            st.error(f"❌ Faltou a folha obrigatória '{sh}' no Excel.")
            st.stop()

    atletas_df = _norm_cols(xl.parse("Atletas"))
    oficiais_df = _norm_cols(xl.parse("Oficiais"))
    info_df     = _norm_cols(xl.parse("Info"))

    for col in ["Numero","Nome","Posicao"]:
        if col not in atletas_df.columns:
            st.error(f"Na folha 'Atletas' falta a coluna '{col}'.")
            st.stop()
    for col in ["Nome","Posicao"]:
        if col not in oficiais_df.columns:
            st.error(f"Na folha 'Oficiais' falta a coluna '{col}'.")
            st.stop()
    for col in ["Equipa a","Equipa b","Data","Local"]:
        if col not in info_df.columns:
            st.error(f"Na folha 'Info' falta a coluna '{col}'.")
            st.stop()

    if info_df.empty:
        info_df = pd.DataFrame([{
            "Equipa a": "Equipa A",
            "Equipa b": "Equipa B",
            "Data": datetime.now().strftime("%Y-%m-%d"),
            "Local": "Local"
        }])

    # garantir numeros coerentes como texto/int
    atletas_df["Numero"] = atletas_df["Numero"].apply(
        lambda x: int(x) if pd.notna(x) and str(x).strip().isdigit() else str(x).strip()
    )
    return atletas_df, oficiais_df, info_df
# =============== Carregamento obrigatório (bloqueante se não houver) ===============

def ensure_roster_loaded_blocking() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    uploaded = st.file_uploader(
        "📂 Carrega o ficheiro **Plantel.xlsx** (Atletas, Oficiais, Info)",
                type=["xlsx"],
                accept_multiple_files=False,
                key="roster_uploader_blocking",
    )
    if not uploaded:
        st.info("⚠️ Necessário carregar o **Plantel.xlsx** para continuar.", icon="🗂️")
        st.stop()

    atletas_df, oficiais_df, info_df = load_data_excel(uploaded)
    st.session_state["atletas_df"] = atletas_df
    st.session_state["oficiais_df"] = oficiais_df
    st.session_state["info_df"] = info_df
    st.session_state["excel_loaded_once"] = True
    return atletas_df, oficiais_df, info_df

# Usa dados da sessão se existirem; caso não, pede upload e bloqueia
if "atletas_df" in st.session_state and "oficiais_df" in st.session_state and "info_df" in st.session_state:
    atletas_df = st.session_state["atletas_df"]
    oficiais_df = st.session_state["oficiais_df"]
    info_df = st.session_state["info_df"]
else:
    atletas_df, oficiais_df, info_df = ensure_roster_loaded_blocking()
# =============== Estado inicial ===============
def init_state():
    if "game_state" in st.session_state:
        return

    players: Dict[str, Dict[str, Any]] = {}
    gk_ids: List[str] = []
    field_ids: List[str] = []

    for idx, row in atletas_df.iterrows():
        num = row.get("Numero", 0)
        nome = str(row.get("Nome", "")).strip()
        pos = str(row.get("Posicao", "")).strip()
        if not nome:
            continue
        pid = f"player_{idx}_{num}_{nome}"
        players[pid] = {
            "id": pid,
            "num": int(num) if isinstance(num, int) else str(num),
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

    official_ids: List[str] = []
    for idx, row in oficiais_df.head(5).iterrows():
        nome = str(row.get("Nome", "")).strip()
        pos = str(row.get("Posicao", "")).strip()
        if not nome:
            continue
        oid = f"official_{idx}_{nome}"
        players[oid] = {
            "id": oid,
            "num": "0",
            "nome": nome,
            "pos": pos,            # A..E
            "in_field": False,
            "time_played": 0.0,
            "yellow": 0,
            "two_total": 0,
            "two_active": 0.0,
            "red": 0,
            "disq": False,
            "is_official": True,
        }
        official_ids.append(oid)

    info_row = info_df.iloc[0].to_dict()
    team_a = str(info_row.get("Equipa a", "Equipa A"))
    team_b = str(info_row.get("Equipa b", "Equipa B"))
    game_date = str(info_row.get("Data", datetime.now().strftime("%Y-%m-%d")))
    game_place = str(info_row.get("Local", "Local"))

    st.session_state.game_state = {
        "team_a": team_a, "team_b": team_b, "date": game_date, "place": game_place,
        "players": players, "gk_ids": gk_ids, "field_ids": field_ids, "official_ids": official_ids,
        "running": False, "start_time": None, "elapsed": 0.0, "half": 1,
        "half_len": 30*60, "last_minute_alert": False,
        "on_field_set": set(), "team_penalties": [], "passive": False,
        "team_yellow_total": 0, "officials_yellow_total": 0,
        "score_for": {"1": 0, "2": 0}, "score_against": {"1": 0, "2": 0},
        "goals": [], "shots": [], "events": [],
        "last_snapshot": None,
        "blocked_until": {},  # pid -> timestamp
    }

init_state()
gs = st.session_state.game_state
# ======================= Regras Aux =======================
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

def allowed_zones_for(typ: str) -> set:
    spec = ZONE_COMPAT_MAP.get(typ, "ALL")
    if spec == "ALL": return set(range(1,9))
    if spec == "NO_ZONE": return set()
    return set(spec)

def current_allowed_on_field(gs: Dict[str, Any]) -> int:
    per_player_active = sum(1 for p in gs["players"].values() if p.get("two_active", 0.0) > 0 and not p.get("is_official"))
    team_active = sum(1 for t in gs["team_penalties"] if t > 0)
    return max(3, 7 - (per_player_active + team_active))

def has_seven_selected(gs: Dict[str, Any]) -> bool:
    return len(gs["on_field_set"]) == 7
# ======================= Snapshots / Undo =======================
SNAP_KEYS = [
    "players","on_field_set","team_penalties","team_yellow_total","officials_yellow_total",
    "score_for","score_against","goals","shots","events",
    "running","start_time","elapsed","half","last_minute_alert","blocked_until"
]

def push_snapshot(label: str):
    snap = deep_snapshot_from(SNAP_KEYS, gs)
    snap["_label"] = label
    gs["last_snapshot"] = snap

def undo_last():
    if not gs.get("last_snapshot"):
        st.warning("Não há ação para desfazer.", icon="⚠️"); return
    last = gs["last_snapshot"]
    for k in SNAP_KEYS: gs[k] = last[k]
    gs["last_snapshot"] = None
    st.toast(f"↩️ Desfeito: {last.get('_label','Ação')}", icon="↩️")
# ======================= Tempo / Cronómetro =======================
def flush_time():
    if not gs["running"]:
        return
    if gs["start_time"] is None:
        gs["start_time"] = now_ts(); return
    now = now_ts()
    delta = max(0.0, now - gs["start_time"])
    if delta == 0: return

    gs["elapsed"] += delta
    gs["start_time"] = now

    for pid in list(gs["on_field_set"]):
        p = gs["players"].get(pid)
        if p and not p.get("is_official"):
            p["time_played"] = p.get("time_played", 0.0) + delta

    finished_players = []
    for pid, p in gs["players"].items():
        if p.get("two_active", 0.0) > 0:
            before = p["two_active"]
            p["two_active"] = max(0.0, p["two_active"] - delta)
            if before > 0 and p["two_active"] == 0:
                finished_players.append(pid)

    finished_team = 0
    for i in range(len(gs["team_penalties"])):
        t = gs["team_penalties"][i]
        if t > 0:
            t2 = max(0.0, t - delta)
            gs["team_penalties"][i] = t2
            if t > 0 and t2 == 0:
                finished_team += 1
    # desbloqueios por sanção de oficial
    now2 = now_ts()
    to_unblock = [pid for pid, until_ts in gs["blocked_until"].items() if now2 >= until_ts]
    for pid in to_unblock:
        gs["blocked_until"].pop(pid, None)
        p = gs["players"].get(pid)
        if p:
            st.toast(f"✅ {p.get('num','')} {p.get('nome','')} pode voltar a entrar (bloqueio terminou).", icon="✅")

    for pid in finished_players:
        p = gs["players"][pid]
        if p.get("disq", False):
            st.toast(f"✅ Inferioridade associada a {p['num']} {p['nome']} terminou (jogador permanece desqualificado).", icon="✅")
        else:
            st.toast(f"✅ {p['num']} {p['nome']} pode voltar a entrar (2’ terminou).", icon="✅")

    for _ in range(finished_team):
        st.toast("✅ Penalidade de equipa 2’ terminou.", icon="✅")

    rem = max(0, int(gs["half_len"] - gs["elapsed"]))
    if gs["running"] and rem <= 60 and not gs["last_minute_alert"]:
        st.toast(f"⏰ Último minuto! Faltam {rem}s", icon="⏰")
        gs["last_minute_alert"] = True

    if gs["elapsed"] >= gs["half_len"]:
        gs["elapsed"] = gs["half_len"]
        gs["running"] = False
        st.toast(f"⏱️ Fim da {gs['half']}ª parte (30:00)", icon="⏱️")
        if gs["half"] == 1:
            gs["half"] = 2; gs["elapsed"] = 0.0; gs["start_time"] = None; gs["last_minute_alert"] = False
            st.toast("👉 Pronto para iniciar a 2ª parte", icon="➡️")
        else:
            st.toast("🏁 Fim do jogo", icon="🏁")

def start_play():
    if not has_seven_selected(gs):
        st.warning("Para iniciar, seleciona exatamente **7 jogadores** (GR não obrigatório).", icon="⚠️"); return
    gs["running"] = True
    gs["start_time"] = now_ts()

def pause_play():
    if gs["running"]:
        flush_time()
    gs["running"] = False
# ======================= Sanções =======================
def give_yellow(pid: str):
    p = gs["players"][pid]
    if p.get("disq", False):
        st.warning(f"{p.get('num','')} {p['nome']} está desqualificado (não pode receber amarelo).", icon="⚠️"); return

    if p.get("is_official", False):
        if gs["officials_yellow_total"] >= 1:
            st.warning("Os oficiais já receberam 1 amarelo no total — a partir daqui só 2’/🟥.", icon="⚠️"); return
        if p.get("yellow", 0) >= 1:
            st.warning(f"O oficial {p['nome']} já tem 1 amarelo — agora só 2’/🟥.", icon="⚠️"); return
        push_snapshot(f"Amarelo Oficial {p['nome']}")
        p["yellow"] = 1
        gs["officials_yellow_total"] += 1
        st.toast(f"🟨 Oficial {p['nome']}: amarelo (oficiais {gs['officials_yellow_total']}/1).", icon="🟨")
        return

    if gs["team_yellow_total"] >= 3:
        st.warning("Limite de amarelos da equipa atingido (3/3). A partir daqui só 2’.", icon="⚠️"); return
    if p.get("yellow", 0) >= 1:
        st.warning(f"{p.get('num','')} {p['nome']} já tem 1 amarelo — agora só 2’/🟥.", icon="⚠️"); return

    push_snapshot(f"Amarelo {p['nome']}")
    p["yellow"] = 1
    gs["team_yellow_total"] += 1
    st.toast(f"🟨 {p.get('num','')} {p['nome']}: cartão amarelo (equipa {gs['team_yellow_total']}/3).", icon="🟨")

def _apply_official_team_penalty_and_choose_player(minutes: int):
    st.session_state._official_penalty_minutes = minutes
    st.session_state._open_official_pick = True

@st.dialog("Seleciona o atleta a retirar (sanção de oficial)")
def official_pick_dialog():
    minutes = int(st.session_state.get("_official_penalty_minutes", 2))
    secs = minutes * 60
    st.write(f"Escolhe o atleta **em campo** a retirar por **{minutes} minutos**:")

    in_field_players = [pid for pid in gs["on_field_set"] if not gs["players"][pid].get("is_official")]
    if not in_field_players:
        st.error("Não há atletas em campo para retirar. Retira manualmente um atleta.", icon="⚠️")
        if st.button("Fechar", use_container_width=True):
            st.session_state._open_official_pick = False; st.rerun()
        return

    cols = st.columns(3)
    for i, pid in enumerate(in_field_players):
        p = gs["players"][pid]
        with cols[i % 3]:
            if st.button(f"{p.get('num','')} · {p['nome']}", key=f"pick_{pid}", use_container_width=True):
                flush_time()
                if pid in gs["on_field_set"]:
                    gs["on_field_set"].discard(pid)
                    gs["players"][pid]["in_field"] = False
                gs["blocked_until"][pid] = now_ts() + secs
                st.toast(f"⛔ {p.get('num','')} {p['nome']} retirado até {minutes}’ passarem.", icon="⏱️")
                st.session_state._open_official_pick = False
                st.rerun()
    st.divider()
    if st.button("Cancelar", use_container_width=True):
        st.session_state._open_official_pick = False; st.rerun()
def give_two_minutes(pid: str):
    p = gs["players"][pid]
    if p.get("disq", False):
        st.warning(f"{p.get('num','')} {p['nome']} está desqualificado (não pode receber 2’).", icon="⚠️"); return

    push_snapshot(f"2 minutos {p['nome']}")

    if p.get("is_official", False):
        if p.get("two_total", 0) >= 1:
            st.warning("Oficiais só podem receber 1x 2’ — após isso apenas vermelho.", icon="⚠️"); return
        p["two_total"] = 1
        gs["team_penalties"].append(120.0)
        st.toast(f"⏱️ Oficial {p['nome']}: 2’ (equipa cumpre 2’).", icon="⏱️")
        _apply_official_team_penalty_and_choose_player(minutes=2)
        return

    if pid in gs["on_field_set"]:
        flush_time()
        gs["on_field_set"].discard(pid)
        p["in_field"] = False

    p["two_total"] += 1
    curr_active = p.get("two_active", 0.0)
    if p["two_total"] >= 3:
        p["disq"] = True
        p["two_active"] = curr_active
        gs["team_penalties"].append(120.0)
        st.error(f"🟥 {p.get('num','')} {p['nome']} desqualificado (3×2’). Equipa cumpre +2’.", icon="🚫")
    else:
        p["two_active"] = curr_active + 120.0
        st.toast(f"🚫 {p.get('num','')} {p['nome']}: +2’ (ativo: {int(p['two_active'])}s).", icon="⏱️")

def give_red(pid: str):
    p = gs["players"][pid]
    if p.get("disq", False):
        st.warning(f"{p.get('num','')} {p['nome']} já está desqualificado.", icon="⚠️"); return

    push_snapshot(f"Vermelho {p['nome']}")

    if pid in gs["on_field_set"]:
        flush_time()
        gs["on_field_set"].discard(pid)
        p["in_field"] = False

    p["disq"] = True
    p["red"] = p.get("red", 0) + 1
    gs["team_penalties"].append(120.0)
    label = "Oficial" if p.get("is_official", False) else f"{p.get('num','')} {p['nome']}"
    st.error(f"🟥 {label}: expulsão. Equipa cumpre 2’.", icon="🚫")

    if p.get("is_official", False):
        _apply_official_team_penalty_and_choose_player(minutes=2)
# ======================= Ações =======================
def register_goal(pid: str, typ: str, zona: Optional[int], sofrido: bool = False):
    p = gs["players"][pid]
    if p.get("disq", False):
        st.warning(f"{p.get('num','')} {p['nome']} está desqualificado (não pode marcar).", icon="⚠️"); return
    push_snapshot(f"Golo {p['nome']} ({typ})")

    entry = {"player_id": pid, "tipo": typ, "zona": zona, "half": gs["half"], "sofrido": bool(sofrido), "t": int(gs["elapsed"])}
    gs["goals"].append(entry)
    if sofrido:
        gs["score_against"][str(gs["half"])] += 1
        st.toast(f"⚠️ Golo sofrido — {typ}{(' · Zona '+str(zona)) if zona else ''}", icon="⚠️")
    else:
        gs["score_for"][str(gs["half"])] += 1
        st.toast(f"⚽ Golo — {p.get('num','')} {p['nome']} · {typ}{(' · Zona '+str(zona)) if zona else ''}", icon="⚽")
    gs["passive"] = False

def register_shot(pid: str, outcome: str, typ: str, zona: Optional[int], sofrido: bool = False):
    p = gs["players"][pid]
    if p.get("disq", False):
        st.warning(f"{p.get('num','')} {p['nome']} está desqualificado (não pode rematar).", icon="⚠️"); return
    push_snapshot(f"Remate {outcome} {p['nome']} ({typ})")
    entry = {"player_id": pid, "tipo": typ, "resultado": outcome, "zona": zona, "half": gs["half"], "sofrido": bool(sofrido), "t": int(gs["elapsed"])}
    gs["shots"].append(entry)
    icon = "🧤" if outcome == "defendido" else "❌"
    tag = "Remate defendido" if outcome == "defendido" else "Remate falhado"
    suf = " (sofrido)" if sofrido else ""
    st.toast(f"{icon} {tag}{suf} — {p['nome']} · {typ}{(' · Zona '+str(zona)) if zona else ''}", icon=icon)
    gs["passive"] = False

def compute_suffered_counters():
    suf = {"golos_sofridos": {"1":0,"2":0,"T":0}, "defendidos": {"1":0,"2":0,"T":0}, "falhados": {"1":0,"2":0,"T":0}}
    for e in gs["goals"]:
        if e.get("sofrido"):
            h = str(e.get("half")); suf["golos_sofridos"][h]+=1; suf["golos_sofridos"]["T"]+=1
    for e in gs["shots"]:
        if e.get("sofrido"):
            h = str(e.get("half"))
            if e.get("resultado")=="defendido":
                suf["defendidos"][h]+=1; suf["defendidos"]["T"]+=1
            elif e.get("resultado")=="falhado":
                suf["falhados"][h]+=1; suf["falhados"]["T"]+=1
    return suf
# ======================= Modais =======================
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

    p = gs["players"][pid]; is_off = p.get("is_official", False)
    st.subheader(f"{p.get('num','')} · {p['nome']}{' (Oficial)' if is_off else ''}")

    colA, colB, colC, colD = st.columns(4)
    with colA: st.metric("Amarelo", f"{p.get('yellow',0)}/1" + (" (oficiais {}/1)".format(gs['officials_yellow_total']) if is_off else f" (equipa {gs['team_yellow_total']}/3)"))
    with colB: st.metric("2' total", f"{p.get('two_total',0)}")
    with colC: st.metric("2' ativa (s)", f"{int(p.get('two_active',0))}")
    with colD: st.metric("Vermelhos", f"{p.get('red',0)}")

    st.divider()
    st.write("**Escolhe a sanção:**")

    can_yellow = (not p.get("disq", False))
    can_two = (not p.get("disq", False))
    can_red = (not p.get("disq", False))

    if not is_off:
        if gs["team_yellow_total"] >= 3 or p.get("yellow", 0) >= 1: can_yellow = False
    else:
        if gs["officials_yellow_total"] >= 1 or p.get("yellow", 0) >= 1: can_yellow = False
        if p.get("two_total", 0) >= 1: can_two = False

    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("🟨 Amarelo", use_container_width=True, disabled=not can_yellow):
            flush_time(); give_yellow(pid); st.session_state._open_sanction=False; st.rerun()
    with b2:
        if st.button("🚫 2 minutos", use_container_width=True, disabled=not can_two):
            flush_time(); give_two_minutes(pid); st.session_state._open_sanction=False; st.rerun()
    with b3:
        if st.button("🟥 Vermelho", use_container_width=True, disabled=not can_red):
            flush_time(); give_red(pid); st.session_state._open_sanction=False; st.rerun()

    st.divider()
    if st.button("Fechar", use_container_width=True):
        st.session_state._open_sanction = False; st.rerun()
@st.dialog("Remate / Golo")
def shot_dialog():
    tmp = st.session_state.get("_tmp_player_for_shot")
    if not tmp:
        st.write("Sem jogador selecionado.")
        if st.button("Fechar", use_container_width=True):
            st.session_state._open_shot = False; st.rerun()
        return
    pid, is_gk = tmp
    p = gs["players"][pid]

    st.subheader(f"{p.get('num','')} · {p['nome']}{' (GR)' if is_gk else ''}")
    st.caption(f"Parte: {gs['half']}ª — Tempo: {fmt_hhmmss(gs['elapsed'])}")

    if is_gk:
        st.markdown("### 🧤 Remates Sofridos — **Golo Sofrido**")
        row = ["9m","6m","Penetração","1 Vaga","2 Vaga"]
        cols = st.columns(len(row))
        for typ, col in zip(row, cols):
            with col:
                if st.button(typ, key=f"gk_suf_goal_{pid}_{typ}", use_container_width=True):
                    zones = allowed_zones_for(typ)
                    if len(zones)==0:
                        flush_time(); register_goal(pid, typ, None, sofrido=True); st.session_state._open_shot=False; st.rerun()
                    else:
                        open_zone_modal({"kind":"goal","pid":pid,"typ":typ,"sofrido":True}); st.session_state._open_shot=False; st.rerun()
        row2 = ["3 Vaga","Baliza Aberta","7m","Pivot","Ponta"]
        cols2 = st.columns(len(row2))
        for typ, col in zip(row2, cols2):
            with col:
                if st.button(typ, key=f"gk_suf_goal2_{pid}_{typ}", use_container_width=True):
                    zones = allowed_zones_for(typ)
                    if len(zones)==0:
                        flush_time(); register_goal(pid, typ, None, sofrido=True); st.session_state._open_shot=False; st.rerun()
                    else:
                        open_zone_modal({"kind":"goal","pid":pid,"typ":typ,"sofrido":True}); st.session_state._open_shot=False; st.rerun()

        st.divider()
        st.markdown("### 🧤 Remates Sofridos — **Defendidos**")
        for row in [["9m","6m","Penetração","1 Vaga","2 Vaga"], ["3 Vaga","Baliza Aberta","7m","Pivot","Ponta"]]:
            cols = st.columns(len(row))
            for typ, col in zip(row, cols):
                with col:
                    if st.button(typ, key=f"gk_suf_def_{pid}_{typ}", use_container_width=True):
                        zones = allowed_zones_for(typ)
                        if len(zones)==0:
                            flush_time(); register_shot(pid, "defendido", typ, None, sofrido=True); st.session_state._open_shot=False; st.rerun()
                        else:
                            open_zone_modal({"kind":"defendido","pid":pid,"typ":typ,"sofrido":True}); st.session_state._open_shot=False; st.rerun()

        st.divider()
        st.markdown("### 🧤 Remates Sofridos — **Falhados**")
        for row in [["9m","6m","Penetração","1 Vaga","2 Vaga"], ["3 Vaga","Baliza Aberta","7m","Pivot","Ponta"]]:
            cols = st.columns(len(row))
            for typ, col in zip(row, cols):
                with col:
                    if st.button(typ, key=f"gk_suf_miss_{pid}_{typ}", use_container_width=True):
                        zones = allowed_zones_for(typ)
                        if len(zones)==0:
                            flush_time(); register_shot(pid, "falhado", typ, None, sofrido=True); st.session_state._open_shot=False; st.rerun()
                        else:
                            open_zone_modal({"kind":"falhado","pid":pid,"typ":typ,"sofrido":True}); st.session_state._open_shot=False; st.rerun()

        st.divider()
        st.markdown("### ⚽ Golo do GR (remate direto)")
        if st.button("Golo", key=f"gk_goal_{pid}", use_container_width=True):
            flush_time(); register_goal(pid, "Golo GR", None, sofrido=False); st.session_state._open_shot=False; st.rerun()

    else:
        st.markdown("### ⚽ Golo")
        for row in [["9m","6m","Penetração","1 Vaga","2 Vaga"], ["3 Vaga","Baliza Aberta","7m","Pivot","Ponta"]]:
            cols = st.columns(len(row))
            for typ, col in zip(row, cols):
                with col:
                    if st.button(typ, key=f"pl_goal_{pid}_{typ}", use_container_width=True):
                        zones = allowed_zones_for(typ)
                        if len(zones)==0:
                            flush_time(); register_goal(pid, typ, None, sofrido=False); st.session_state._open_shot=False; st.rerun()
                        else:
                            open_zone_modal({"kind":"goal","pid":pid,"typ":typ,"sofrido":False}); st.session_state._open_shot=False; st.rerun()

        st.divider()
        st.markdown("### 🧤 Remates Defendidos")
        for row in [["9m","6m","Penetração","1 Vaga","2 Vaga"], ["3 Vaga","Baliza Aberta","7m","Pivot","Ponta"]]:
            cols = st.columns(len(row))
            for typ, col in zip(row, cols):
                with col:
                    if st.button(typ, key=f"pl_def_{pid}_{typ}", use_container_width=True):
                        zones = allowed_zones_for(typ)
                        if len(zones)==0:
                            flush_time(); register_shot(pid, "defendido", typ, None, sofrido=False); st.session_state._open_shot=False; st.rerun()
                        else:
                            open_zone_modal({"kind":"defendido","pid":pid,"typ":typ,"sofrido":False}); st.session_state._open_shot=False; st.rerun()

        st.divider()
        st.markdown("### ❌ Remates Falhados")
        for row in [["9m","6m","Penetração","1 Vaga","2 Vaga"], ["3 Vaga","Baliza Aberta","7m","Pivot","Ponta"]]:
            cols = st.columns(len(row))
            for typ, col in zip(row, cols):
                with col:
                    if st.button(typ, key=f"pl_miss_{pid}_{typ}", use_container_width=True):
                        zones = allowed_zones_for(typ)
                        if len(zones)==0:
                            flush_time(); register_shot(pid, "falhado", typ, None, sofrido=False); st.session_state._open_shot=False; st.rerun()
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
        if st.button("Fechar", use_container_width=True):
            st.session_state._open_zone = False; st.rerun()
        return
    pid = ctx["pid"]; typ = ctx["typ"]; kind = ctx["kind"]; sofrido = ctx.get("sofrido", False)
    p = gs["players"][pid]
    zones_allowed = allowed_zones_for(typ)

    st.subheader(f"{p.get('num','')} · {p['nome']}")
    st.caption(f"Tipo: {typ} — Categoria: {'Golo' if kind=='goal' else ('Defendido' if kind=='defendido' else 'Falhado')}")

    cols1 = st.columns(5)
    for i, col in enumerate(cols1, start=1):
        with col:
            if st.button(f"Zona {i}", key=f"z_{pid}_{typ}_{kind}_{i}", use_container_width=True, disabled=(i not in zones_allowed)):
                flush_time()
                if kind == "goal": register_goal(pid, typ, i, sofrido=sofrido)
                else: register_shot(pid, kind, typ, i, sofrido=sofrido)
                st.session_state._open_zone = False; st.session_state._zone_ctx = None; st.rerun()

    cols2 = st.columns(3)
    for idx, z in enumerate([6,7,8]):
        with cols2[idx]:
            if st.button(f"Zona {z}", key=f"z_{pid}_{typ}_{kind}_{z}", use_container_width=True, disabled=(z not in zones_allowed)):
                flush_time()
                if kind == "goal": register_goal(pid, typ, z, sofrido=sofrido)
                else: register_shot(pid, kind, typ, z, sofrido=sofrido)
                st.session_state._open_zone = False; st.session_state._zone_ctx = None; st.rerun()

    st.divider()
    if st.button("Cancelar", use_container_width=True):
        st.session_state._open_zone = False; st.session_state._zone_ctx = None; st.rerun()

# ======================= UI Helpers =======================
def render_header_row():
    h_estado, h_tempo, h_num, h_nome, h_btns = st.columns([0.18, 0.10, 0.10, 0.32, 0.30])
    with h_estado: st.caption("Banco/Campo")
    with h_tempo:  st.caption("Tempo (min)")
    with h_num:    st.caption("Nº")
    with h_nome:   st.caption("Nome")
    with h_btns:   st.caption("Ações")
def render_player_row(pid: str, is_gk: bool=False, is_official: bool=False):
    p = gs["players"][pid]

    # Badges de estado
    if p.get("disq", False):
        badge = "<span class='pill pill-red'>🟥 Desqualificado</span>"
    elif p.get("two_active", 0.0) > 0:
        badge = f"<span class='pill pill-orange'>⛔ 2’ ({int(p['two_active'])}s)</span>"
    else:
        if is_official:
            badge = "<span class='pill pill-blue'>👤 Oficial</span>"
        else:
            badge = "<span class='pill pill-green'>🟢 Em campo</span>" if p.get("in_field", False) else "<span class='pill pill-yellow'>🟡 Banco</span>"

    mins = int(min(60, p.get("time_played", 0.0) // 60)) if not is_official else ""
    c_est, c_tmp, c_num, c_nom, c_btns = st.columns([0.18, 0.10, 0.10, 0.32, 0.30])

    with c_est: st.markdown(f"<div class='row-compact'>{badge}</div>", unsafe_allow_html=True)
    with c_tmp: st.markdown(f"<div class='row-compact mins'>{mins}</div>", unsafe_allow_html=True)
    with c_num: st.markdown(f"<div class='row-compact num'>{p.get('num','')}</div>", unsafe_allow_html=True)

    # Botão do nome com prefixo de cor de estado (em vez de pintar o botão)
    with c_nom:
        blocked = False
        if pid in gs["blocked_until"]:
            blocked = now_ts() < gs["blocked_until"][pid]
        disq_or_3x2 = p.get("disq", False) or p.get("two_total", 0) >= 3
        prefix = "🟢 " if p.get("in_field", False) else ("🟠 " if blocked else ("🟥 " if disq_or_3x2 else ""))
        disabled_name = is_official or p.get("disq", False) or (p.get("two_active", 0.0) > 0) or blocked
        hint = "Clique para entrar/sair (jogadores). Oficiais não entram em campo."
        if blocked: hint = "Bloqueado por sanção de oficial (aguarda terminar 2’)."

        if st.button(prefix + p["nome"], key=f"btn_name_{pid}", use_container_width=True, disabled=disabled_name, help=hint):
            flush_time()
            if p.get("in_field", False):
                p["in_field"] = False; gs["on_field_set"].discard(pid)
            else:
                if len(gs["on_field_set"]) >= current_allowed_on_field(gs):
                    st.warning(f"Máximo de {current_allowed_on_field(gs)} em campo neste momento.", icon="⚠️")
                else:
                    p["in_field"] = True; gs["on_field_set"].add(pid)
            gs["start_time"] = now_ts()

    with c_btns:
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.button("📋", key=f"btn_sanc_{pid}", use_container_width=True, help="Sanção",
                      on_click=open_sanction_modal, args=(pid,))
        with col2:
            if not is_official:
                st.button("🎯", key=f"btn_shot_{pid}", use_container_width=True,
                          help=("Remate" if not is_gk else "Remates Sofridos / Golo"),
                          on_click=open_shot_modal, args=(pid, is_gk))
        with col3:
            if not is_official:
                st.button("🏆", key=f"btn_conquista_{pid}", use_container_width=True,
                          help="Conquista", on_click=open_conquista_modal, args=(pid, is_gk))
        with col4:
            if not is_official:
                if st.button("⚠️", key=f"btn_tech_{pid}", use_container_width=True, help="Falha Técnica"):
                    push_snapshot(f"Falha Técnica {p['nome']}")
                    p["tech_faults"] = p.get("tech_faults", 0) + 1
                    st.toast(f"⚠️ Falha técnica registada — {p['nome']}", icon="⚠️")
        with col5:
            if is_gk and not is_official:
                if st.button("⚽", key=f"btn_gk_goal_{pid}", use_container_width=True, help="Golo direto do GR"):
                    flush_time(); register_goal(pid, "Golo GR", None, sofrido=False)

# ======================= CSS =======================
st.markdown("""
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
""", unsafe_allow_html=True)

# ======================= Topo (Info + Controlo) =======================
st.markdown(
    f"""
    <div style="text-align:center; margin-top:4px;">
      <div style="font-size:22px; font-weight:800;">{gs['team_a']} VS {gs['team_b']}</div>
      <div style="font-size:14px; color:#666;">{gs['date']} • {gs['place']}</div>
    </div>
    """, unsafe_allow_html=True
)

score_for_total = gs["score_for"]["1"] + gs["score_for"]["2"]
score_against_total = gs["score_against"]["1"] + gs["score_against"]["2"]
cR1, cR2, cR3 = st.columns([1, 1.2, 1])
with cR2:
    st.markdown(
        f"""
        <div style="text-align:center; margin:4px 0 8px 0;">
          <div style="font-size:18px; font-weight:800;">RESULTADO</div>
          <div style="font-size:16px; margin-top:4px;">({score_for_total}) Totais ({score_against_total})</div>
          <div style="font-size:14px; margin-top:2px;">({gs['score_for']['1']}) 1ª Parte ({gs['score_against']['1']})</div>
          <div style="font-size:14px; margin-top:2px;">({gs['score_for']['2']}) 2ª Parte ({gs['score_against']['2']})</div>
        </div>
        """, unsafe_allow_html=True
    )

# Botões cronómetro
c1, c2, c3, c4 = st.columns([1,1,1,1])
with c1: st.button("▶️ Play", on_click=start_play, use_container_width=True)
with c2: st.button("⏸️ Pausa", on_click=pause_play, use_container_width=True)
with c3: st.button("↩️ Desfazer", on_click=undo_last, use_container_width=True)
with c4: st.write("")

flush_time()
banner = "🟢 EM JOGO" if gs["running"] else "⏸️ PAUSADO"
st.markdown(f"<div style='text-align:center; font-size:22px; font-weight:800; color:{'#0a0' if gs['running'] else '#c00'}; margin:6px 0;'>{banner}</div>", unsafe_allow_html=True)

rem = max(0, int(gs["half_len"] - gs["elapsed"]))
cT1, cT2, cT3 = st.columns([1,1,1])
with cT2:
    st.metric(f"Tempo {gs['half']}ª", f"{fmt_hhmmss(gs['elapsed'])} / 0:30:00", delta=f"Faltam {fmt_hhmmss(rem)}")

state_msg = "Igualdade"
if any(p.get("two_active",0)>0 for p in gs["players"].values()) or any(t>0 for t in gs["team_penalties"]):
    state_msg = "Inferioridade"
elif len(gs["on_field_set"]) == 7:
    has_gk = any((pid in gs["on_field_set"]) and (str(gs["players"][pid].get("pos","")).upper()=="GR") for pid in gs["players"])
    if not has_gk:
        state_msg = "7x6"

cP1, cP2, cP3 = st.columns([1,1,1])
with cP2:
    gs["passive"] = st.toggle("🏳️ Passivo", value=gs["passive"], help="Ativa/Desativa jogo passivo (desliga ao registar ação)")
    st.caption(f"Estado: **{state_msg}**")

# ======================= Abas (Principal / Resumo) =======================
tab_principal, tab_resumo = st.tabs(["Principal", "Resumo"])

with tab_principal:
    st.markdown("### Principal")
    allowed_now = current_allowed_on_field(gs)
    st.caption(f"Em campo: {len(gs['on_field_set'])}/{allowed_now} (máx dinâmico: 7 − sanções ativas; mínimo 3)")
    render_header_row()

    if gs["gk_ids"]:
        st.markdown("<div class='section-title'>Guarda-redes</div>", unsafe_allow_html=True)
        for pid in gs["gk_ids"]:
            render_player_row(pid, is_gk=True, is_official=False)

    if gs["field_ids"]:
        st.markdown("<div class='section-title'>Jogadores de campo</div>", unsafe_allow_html=True)
        for pid in gs["field_ids"]:
            render_player_row(pid, is_gk=False, is_official=False)

    if gs["official_ids"]:
        st.markdown("<div class='section-title'>Oficiais</div>", unsafe_allow_html=True)
        h_est2, h_num2, h_nome2, h_btn2 = st.columns([0.18, 0.10, 0.52, 0.20])
        with h_est2: st.caption("Tipo")
        with h_num2: st.caption("Nº")
        with h_nome2: st.caption("Nome")
        with h_btn2: st.caption("Sanção")
        for oid in gs["official_ids"]:
            p = gs["players"][oid]
            if p.get("disq", False):
                badge = "<span class='pill pill-red'>🟥 Desqualificado</span>"
            elif p.get("two_active", 0.0) > 0:
                badge = f"<span class='pill pill-orange'>⛔ 2’ ({int(p['two_active'])}s)</span>"
            else:
                badge = "<span class='pill pill-blue'>👤 Oficial</span>"
            c1o, c2o, c3o, c4o = st.columns([0.18, 0.10, 0.52, 0.20])
            with c1o: st.markdown(f"<div class='row-compact'>{badge}</div>", unsafe_allow_html=True)
            with c2o: st.markdown(f"<div class='row-compact num'>0</div>", unsafe_allow_html=True)
            with c3o: st.markdown(f"<div class='row-compact'>{p['nome']} ( {p.get('pos','')} )</div>", unsafe_allow_html=True)
            with c4o:
                st.button("📋", key=f"btn_sanc_off_{oid}", use_container_width=True, help="Sanção ao oficial",
                          on_click=open_sanction_modal, args=(oid,))

with tab_resumo:
    st.markdown("#### Tabelas de Resumo")
    def build_dataframes_for_export():
        rows = []
        for pid, p in gs["players"].items():
            is_official = p.get("is_official", False)
            num_col = str(p.get("num",""))
            rows.append({
                "ID": pid, "Oficial": is_official, "Número": num_col, "Nome": p.get("nome",""),
                "Posição": p.get("pos",""), "Tempo (s)": float(p.get("time_played",0.0)),
                "Tempo (mm:ss)": format_time(float(p.get("time_played",0.0))),
                "Em campo": p.get("in_field", False), "Amarelos": p.get("yellow",0),
                "2' total": p.get("two_total",0), "2' ativa (s)": int(p.get("two_active",0.0)),
                "Vermelhos": p.get("red",0), "Desqualificado": p.get("disq",False),
                "Falhas Técnicas": p.get("tech_faults",0),
            })
        df_players = pd.DataFrame(rows)
        df_goals = pd.DataFrame(gs.get("goals", [])) if gs.get("goals") else pd.DataFrame(columns=["player_id","tipo","zona","half","sofrido","t"])
        df_shots = pd.DataFrame(gs.get("shots", [])) if gs.get("shots") else pd.DataFrame(columns=["player_id","tipo","resultado","zona","half","sofrido","t"])
        return df_players, df_goals, df_shots

    df_players, df_goals, df_shots = build_dataframes_for_export()
    st.markdown("**Jogadores / Oficiais**"); st.dataframe(df_players, hide_index=True, use_container_width=True)

    score_for = gs["score_for"]; score_against = gs["score_against"]
    df_score = pd.DataFrame({
        "Parte": ["1ª", "2ª", "Total"],
        "Marcados": [score_for["1"], score_for["2"], score_for["1"] + score_for["2"]],
        "Sofridos": [score_against["1"], score_against["2"], score_against["1"] + score_against["2"]],
    })
    st.markdown("**Resultado — Marcados vs Sofridos**"); st.dataframe(df_score, hide_index=True, use_container_width=True)

    suf = compute_suffered_counters()
    df_suf = pd.DataFrame({
        "Categoria": ["Golos sofridos","Defendidos","Falhados"],
        "1ª Parte": [suf["golos_sofridos"]["1"],suf["defendidos"]["1"],suf["falhados"]["1"]],
        "2ª Parte": [suf["golos_sofridos"]["2"],suf["defendidos"]["2"],suf["falhados"]["2"]],
        "Total":    [suf["golos_sofridos"]["T"],suf["defendidos"]["T"],suf["falhados"]["T"]],
    })
    st.markdown("**Remates Sofridos — Por parte e total**"); st.dataframe(df_suf, hide_index=True, use_container_width=True)

# ======================= Modais pendentes =======================
if st.session_state.get("_open_sanction"): sanction_dialog()
if st.session_state.get("_open_shot"): shot_dialog()
if st.session_state.get("_open_zone"): zone_dialog()
if st.session_state.get("_open_official_pick"): official_pick_dialog()
if st.session_state.get("_open_conquista"): st.session_state._open_conquista = False  # placeholder

# ======================= Secção FINAL: Ficheiro (recarregar) =======================
st.divider()
st.markdown("### 📂 Ficheiro (recarregar)")
uploaded2 = st.file_uploader("Trocar o Plantel.xlsx (opcional)", type=["xlsx"], key="roster_uploader_footer")
if uploaded2 is not None:
    atletas_df_new, oficiais_df_new, info_df_new = load_data_excel(uploaded2)
    st.session_state["atletas_df"] = atletas_df_new
    st.session_state["oficiais_df"] = oficiais_df_new
    st.session_state["info_df"] = info_df_new
    st.success("✔️ Plantel atualizado. A página vai recarregar…")
    st.experimental_rerun()

# Estilos finos
st.markdown("""
<style>
  .stButton > button { padding: 0.45rem 0.7rem; }
  .small-caption { font-size: 12px; color: #777; }
</style>
""", unsafe_allow_html=True)

try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=1000, key="tick_main")
except Exception:
    pass