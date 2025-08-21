import streamlit as st
import pandas as pd
import time
import datetime
import json
from pathlib import Path

# --- Configuração da Página ---
st.set_page_config(
    page_title="AndiBol - Análise de Andebol",
    page_icon=" handball ",
    layout="wide"
)

# --- Funções de Persistência de Estado ---

def save_state():
    """Guarda o st.session_state num ficheiro JSON."""
    state_file = Path("andibol_state.json")
    state_to_save = {}
    # Filtra objetos não serializáveis, se houver
    for k, v in st.session_state.items():
        if isinstance(v, (int, float, str, bool, list, dict, type(None))):
             state_to_save[k] = v
        elif isinstance(v, pd.DataFrame):
             state_to_save[k] = v.to_dict('records') # Converte DataFrame para um formato serializável

    with state_file.open("w", encoding="utf-8") as f:
        json.dump(state_to_save, f)

def load_state():
    """Carrega o estado a partir de um ficheiro JSON, se existir."""
    state_file = Path("andibol_state.json")
    if state_file.exists():
        with state_file.open("r", encoding="utf-8") as f:
            try:
                loaded_state = json.load(f)
                for k, v in loaded_state.items():
                    # Reconverte DataFrames se necessário
                    if k in ['atletas_df', 'oficiais_df'] and isinstance(v, list):
                        st.session_state[k] = pd.DataFrame(v)
                    elif k not in st.session_state:
                         st.session_state[k] = v
            except json.JSONDecodeError:
                # O ficheiro pode estar vazio ou corrompido, ignora
                pass

# --- Inicialização do Estado da Sessão ---
def initialize_state():
    """Inicializa todas as variáveis necessárias no st.session_state."""
    # Carrega o estado anterior antes de inicializar
    load_state()

    # Variáveis do cronómetro
    if 'start_time' not in st.session_state:
        st.session_state.start_time = 0
    if 'elapsed_time' not in st.session_state:
        st.session_state.elapsed_time = 0
    if 'running' not in st.session_state:
        st.session_state.running = False
    if 'game_started' not in st.session_state:
        st.session_state.game_started = False

    # Variáveis da equipa e do jogo
    if 'excel_loaded' not in st.session_state:
        st.session_state.excel_loaded = False
    if 'atletas_df' not in st.session_state:
        st.session_state.atletas_df = pd.DataFrame()
    if 'oficiais_df' not in st.session_state:
        st.session_state.oficiais_df = pd.DataFrame()

    # Timers de sanções
    if 'sanction_timers' not in st.session_state:
        st.session_state.sanction_timers = {} # {numero_atleta: end_time}
    if 'adversary_sanction_timer' not in st.session_state:
        st.session_state.adversary_sanction_timer = 0 # end_time

# --- Funções Auxiliares ---

def format_time(seconds):
    """Formata segundos para o formato MM:SS."""
    return str(datetime.timedelta(seconds=int(seconds))).zfill(8)[3:]

def get_player_status_color(atleta):
    """Devolve a cor e o ícone com base no estado do atleta."""
    numero = atleta['Numero']
    # Verifica se o jogador está com sanção ativa
    if numero in st.session_state.sanction_timers and time.time() < st.session_state.sanction_timers[numero]:
        return '🟧', 'orange' # Sanção de 2 minutos ativa
    if atleta['Estado'] == 'Desqualificado':
        return '🟥', 'red' # Desqualificado
    if atleta['Estado'] == 'Sanção Oficial':
        return '🔵', 'blue' # Sanção por causa de um oficial
    if atleta['Em Campo']:
        return '🟩', 'green' # Em campo
    return '🟨', 'yellow' # No banco

def count_players_on_court():
    """Conta quantos jogadores estão em campo."""
    if not st.session_state.excel_loaded:
        return 0
    return st.session_state.atletas_df['Em Campo'].sum()

def has_goalkeeper_on_court():
    """Verifica se existe um guarda-redes em campo."""
    if not st.session_state.excel_loaded:
        return False
    return st.session_state.atletas_df[
        (st.session_state.atletas_df['Posicao'] == 'GR') &
        (st.session_state.atletas_df['Em Campo'])
    ].shape[0] > 0

def get_team_situation():
    """Determina a situação atual da equipa (Igualdade, Inferioridade, etc.)."""
    n_jogadores_campo = count_players_on_court()
    n_sancoes_ativas_proprias = len([t for t in st.session_state.sanction_timers.values() if time.time() < t])

    # Situação 7x6
    if n_jogadores_campo == 7 and not has_goalkeeper_on_court():
        return "7x6"

    # Superioridade
    if time.time() < st.session_state.adversary_sanction_timer:
        return "Superioridade"

    # Inferioridade
    if n_jogadores_campo < 7 or n_sancoes_ativas_proprias > 0:
         return "Inferioridade"

    # Igualdade
    return "Igualdade"


# --- Interface Principal ---

def main_app():
    """Função que desenha a aplicação principal."""

    # --- Sidebar ---
    with st.sidebar:
        st.header("Configuração do Jogo")
        uploaded_file = st.file_uploader(
            "Carregar Ficheiro do Plantel (Plantel.xlsx)",
            type=["xlsx"],
            help="O ficheiro deve conter duas folhas: 'Atletas' e 'Oficiais'. Máximo de 16 atletas e 5 oficiais."
        )

        if uploaded_file is not None and not st.session_state.excel_loaded:
            try:
                atletas = pd.read_excel(uploaded_file, sheet_name='Atletas')
                oficiais = pd.read_excel(uploaded_file, sheet_name='Oficiais')

                # Validação de colunas obrigatórias (ajustado para o seu ficheiro)
                required_atleta_cols = ['Numero', 'Nome', 'Posicao']
                required_oficial_cols = ['Posicao', 'Nome']

                missing_atleta_cols = [col for col in required_atleta_cols if col not in atletas.columns]
                if missing_atleta_cols:
                    st.error(f"Erro na folha 'Atletas': Faltam as colunas obrigatórias: {', '.join(missing_atleta_cols)}. Verifique o seu ficheiro Excel.")
                    st.stop()

                missing_oficial_cols = [col for col in required_oficial_cols if col not in oficiais.columns]
                if missing_oficial_cols:
                    st.error(f"Erro na folha 'Oficiais': Faltam as colunas obrigatórias: {', '.join(missing_oficial_cols)}. Verifique o seu ficheiro Excel.")
                    st.stop()

                # Validações de número de registos
                if len(atletas) > 16:
                    st.error("Erro: O número de atletas não pode exceder 16.")
                elif len(oficiais) > 5:
                    st.error("Erro: O número de oficiais não pode exceder 5.")
                else:
                    # Inicialização das colunas extra
                    atletas['Em Campo'] = False
                    atletas['Tempo Jogo (s)'] = 0
                    atletas['Estado'] = 'Banco' # Banco, Em Campo, 2min, Desqualificado, Sanção Oficial
                    atletas['Contador 2min'] = 0
                    atletas['Sanções'] = ''
                    atletas['Remates Sofridos'] = 0
                    atletas['Falhas Técnicas'] = 0
                    atletas['Conquistas'] = 0
                    atletas['Golos'] = 0

                    oficiais['Sanções'] = ''

                    st.session_state.atletas_df = atletas
                    st.session_state.oficiais_df = oficiais
                    st.session_state.excel_loaded = True
                    st.success("Plantel carregado com sucesso!")
                    # Força o rerender para desbloquear a app
                    st.rerun()

            except Exception as e:
                st.error(f"Erro ao ler o ficheiro Excel: {e}")
                st.info("Verifique se o ficheiro 'Plantel.xlsx' tem as folhas 'Atletas' e 'Oficiais' com o formato correto.")

        st.markdown("---")
        st.info("Autor: AndiBol AI")
        st.info("Versão: 1.0.3")

    # Bloqueia a app se o Excel não estiver carregado
    if not st.session_state.excel_loaded:
        st.title("Bem-vindo ao AndiBol")
        st.warning(" Por favor, carregue o ficheiro 'Plantel.xlsx' na barra lateral para começar.")
        st.stop()

    # --- Abas da Aplicação ---
    tab_principal, tab_resumo = st.tabs([" Principal", " Resumo"])

    with tab_principal:
        # --- Cronómetro e Banner de Estado ---
        crono_col1, crono_col2 = st.columns([3, 1])

        with crono_col1:
            # Atualiza o tempo decorrido se o cronómetro estiver a correr
            if st.session_state.running:
                st.session_state.elapsed_time = time.time() - st.session_state.start_time

            # Banner de estado
            game_status_text = "EM JOGO" if st.session_state.running else "PAUSADO"
            team_situation_text = get_team_situation()
            st.markdown(
                f"""
                <div style="background-color: #222; padding: 10px; border-radius: 5px; text-align: center; margin-bottom: 10px;">
                    <h3 style="color: white; margin: 0;">
                        {game_status_text} | {team_situation_text}
                    </h3>
                </div>
                """,
                unsafe_allow_html=True
            )

        with crono_col2:
            st.markdown(
                f"""
                <div style="background-color: #333; padding: 10px; border-radius: 5px; text-align: center;">
                    <h1 style="color: white; margin: 0; font-size: 2.5em;">
                        {format_time(st.session_state.elapsed_time)}
                    </h1>
                </div>
                """,
                unsafe_allow_html=True
            )

        # Botões do Cronómetro
        crono_botoes = st.columns(4)
        n_jogadores_em_campo = count_players_on_court()

        # Lógica de bloqueio do botão Play
        play_disabled = st.session_state.running or (not st.session_state.game_started and n_jogadores_em_campo != 7)
        play_help_text = "O jogo só pode começar com exatamente 7 jogadores em campo." if (not st.session_state.game_started and n_jogadores_em_campo != 7) else ""

        if crono_botoes[0].button("▶️ Play", disabled=play_disabled, help=play_help_text, use_container_width=True):
            if not st.session_state.running:
                st.session_state.start_time = time.time() - st.session_state.elapsed_time
                st.session_state.running = True
                if not st.session_state.game_started:
                    st.session_state.game_started = True
                st.rerun()

        if crono_botoes[1].button("⏸️ Pause", disabled=not st.session_state.running, use_container_width=True):
            if st.session_state.running:
                st.session_state.elapsed_time = time.time() - st.session_state.start_time
                st.session_state.running = False
                st.rerun()

        if crono_botoes[2].button("🔄 Reset", use_container_width=True):
            # Reinicia tudo
            st.session_state.start_time = 0
            st.session_state.elapsed_time = 0
            st.session_state.running = False
            st.session_state.game_started = False
            st.session_state.sanction_timers = {}
            st.session_state.adversary_sanction_timer = 0
            # Recarrega o estado inicial dos jogadores a partir do dataframe original
            initialize_state()
            st.rerun()

        # Edição de tempo (só quando pausado)
        with crono_botoes[3].popover("✏️ Editar Tempo", disabled=st.session_state.running, use_container_width=True):
            st.write("Corrigir tempo de jogo (MM:SS):")
            new_time_str = st.text_input("Novo tempo", value=format_time(st.session_state.elapsed_time), label_visibility="collapsed")
            if st.button("Aplicar"):
                try:
                    m, s = map(int, new_time_str.split(':'))
                    new_total_seconds = m * 60 + s
                    st.session_state.elapsed_time = new_total_seconds
                    st.rerun()
                except ValueError:
                    st.error("Formato inválido. Use MM:SS.")

        st.markdown("---")

        # --- Gestão de Atletas ---
        st.subheader("Gestão de Atletas em Jogo")

        # Separação por Posição
        df_gr = st.session_state.atletas_df[st.session_state.atletas_df['Posicao'] == 'GR']
        df_jogadores = st.session_state.atletas_df[st.session_state.atletas_df['Posicao'] != 'GR']

        # --- Guarda-Redes ---
        st.markdown("##### Guarda-Redes")
        gr_cols = st.columns([2, 1, 1, 1, 1, 1, 1, 1])
        headers = ["Atleta", "Tempo", "Rem. Sofrido", "Falha Téc.", "Conquista", "Golo", "Negativo", "Sanção"]
        for col, header in zip(gr_cols, headers):
            col.markdown(f"**{header}**")

        for index, atleta in df_gr.iterrows():
            badge, color = get_player_status_color(atleta)
            nome_atleta = atleta['Nome']
            numero_atleta = atleta['Numero']

            # Coluna do nome com botão de substituição
            with gr_cols[0]:
                # Timer de sanção
                timer_display = ""
                if numero_atleta in st.session_state.sanction_timers:
                    remaining_time = st.session_state.sanction_timers[numero_atleta] - time.time()
                    if remaining_time > 0:
                        timer_display = f" ({format_time(remaining_time)})"

                # Botão de substituição
                is_disabled = (atleta['Estado'] in ['Desqualificado', 'Sanção Oficial'] or
                               (numero_atleta in st.session_state.sanction_timers and time.time() < st.session_state.sanction_timers[numero_atleta]))

                if st.button(f"{badge} {nome_atleta} | Nº{numero_atleta}{timer_display}", key=f"sub_gr_{numero_atleta}", disabled=is_disabled, use_container_width=True):
                    if atleta['Em Campo']:
                        st.session_state.atletas_df.loc[index, 'Em Campo'] = False
                    else:
                        # Regra: não pode entrar se a equipa já tiver 7 em campo
                        if count_players_on_court() < 7:
                            st.session_state.atletas_df.loc[index, 'Em Campo'] = True
                        else:
                            st.toast("A equipa já tem 7 jogadores em campo!", icon="⚠️")
                    st.rerun()

            # Outras colunas de eventos
            gr_cols[1].metric("Min", f"{atleta['Tempo Jogo (s)'] // 60}")
            if gr_cols[2].button("🥅", key=f"rem_sfr_gr_{numero_atleta}", use_container_width=True):
                st.session_state.atletas_df.loc[index, 'Remates Sofridos'] += 1
                st.rerun()
            if gr_cols[3].button("✋", key=f"falha_tec_gr_{numero_atleta}", use_container_width=True):
                st.session_state.atletas_df.loc[index, 'Falhas Técnicas'] += 1
                st.rerun()
            if gr_cols[4].button("🏆", key=f"conq_gr_{numero_atleta}", use_container_width=True):
                st.session_state.atletas_df.loc[index, 'Conquistas'] += 1
                st.rerun()
            if gr_cols[5].button("⚽", key=f"golo_gr_{numero_atleta}", use_container_width=True):
                st.session_state.atletas_df.loc[index, 'Golos'] += 1
                st.rerun()

            # Pop-up para eventos negativos
            with gr_cols[6].popover("➖", use_container_width=True):
                 if st.button("Passos", key=f"passos_gr_{numero_atleta}"):
                     st.session_state.atletas_df.loc[index, 'Falhas Técnicas'] += 1
                     st.rerun()
                 if st.button("Perda de Bola", key=f"perda_bola_gr_{numero_atleta}"):
                     st.session_state.atletas_df.loc[index, 'Falhas Técnicas'] += 1
                     st.rerun()
                 if st.button("7m", key=f"7m_gr_{numero_atleta}"):
                     st.session_state.atletas_df.loc[index, 'Falhas Técnicas'] += 1
                     st.rerun()

            # Pop-up para sanções
            with gr_cols[7].popover("징", use_container_width=True):
                st.write(f"Sancionar {nome_atleta}")
                if st.button("Amarelo", key=f"amarelo_gr_{numero_atleta}"):
                    st.session_state.atletas_df.loc[index, 'Sanções'] += 'A '
                    st.rerun()
                if st.button("2 Minutos", key=f"2min_gr_{numero_atleta}"):
                    st.session_state.atletas_df.loc[index, 'Contador 2min'] += 1
                    st.session_state.atletas_df.loc[index, 'Sanções'] += '2\' '
                    st.session_state.sanction_timers[numero_atleta] = time.time() + 120
                    # Se for a 3ª sanção de 2min, desqualifica
                    if st.session_state.atletas_df.loc[index, 'Contador 2min'] >= 3:
                        st.session_state.atletas_df.loc[index, 'Estado'] = 'Desqualificado'
                    st.rerun()
                if st.button("Vermelho", key=f"verm_gr_{numero_atleta}"):
                    st.session_state.atletas_df.loc[index, 'Estado'] = 'Desqualificado'
                    st.session_state.atletas_df.loc[index, 'Sanções'] += 'V '
                    st.rerun()
                if st.button("2m + 7m", key=f"2m7m_gr_{numero_atleta}"):
                    st.session_state.atletas_df.loc[index, 'Falhas Técnicas'] += 1
                    st.session_state.atletas_df.loc[index, 'Contador 2min'] += 1
                    st.session_state.atletas_df.loc[index, 'Sanções'] += '2\' '
                    st.session_state.sanction_timers[numero_atleta] = time.time() + 120
                    if st.session_state.atletas_df.loc[index, 'Contador 2min'] >= 3:
                        st.session_state.atletas_df.loc[index, 'Estado'] = 'Desqualificado'
                    st.rerun()


        st.markdown("---")
        # --- Jogadores de Campo ---
        st.markdown("##### Jogadores de Campo")
        jc_cols = st.columns([2, 1, 1, 1, 1, 1, 1])
        headers_jc = ["Atleta", "Tempo", "Remate Exec.", "Falha Téc.", "Conquista", "Negativo", "Sanção"]
        for col, header in zip(jc_cols, headers_jc):
            col.markdown(f"**{header}**")

        for index, atleta in df_jogadores.iterrows():
            badge, color = get_player_status_color(atleta)
            nome_atleta = atleta['Nome']
            numero_atleta = atleta['Numero']

            with jc_cols[0]:
                timer_display = ""
                if numero_atleta in st.session_state.sanction_timers:
                    remaining_time = st.session_state.sanction_timers[numero_atleta] - time.time()
                    if remaining_time > 0:
                        timer_display = f" ({format_time(remaining_time)})"

                is_disabled = (atleta['Estado'] in ['Desqualificado', 'Sanção Oficial'] or
                               (numero_atleta in st.session_state.sanction_timers and time.time() < st.session_state.sanction_timers[numero_atleta]))

                if st.button(f"{badge} {nome_atleta} | Nº{numero_atleta}{timer_display}", key=f"sub_jc_{numero_atleta}", disabled=is_disabled, use_container_width=True):
                    if atleta['Em Campo']:
                        st.session_state.atletas_df.loc[index, 'Em Campo'] = False
                    else:
                        if count_players_on_court() < 7:
                            st.session_state.atletas_df.loc[index, 'Em Campo'] = True
                        else:
                            st.toast("A equipa já tem 7 jogadores em campo!", icon="⚠️")
                    st.rerun()

            jc_cols[1].metric("Min", f"{atleta['Tempo Jogo (s)'] // 60}")
            if jc_cols[2].button("🎯", key=f"rem_exe_jc_{numero_atleta}", use_container_width=True):
                st.session_state.atletas_df.loc[index, 'Golos'] += 1 # Assumindo que remate executado é golo para simplificar
                st.rerun()
            if jc_cols[3].button("✋", key=f"falha_tec_jc_{numero_atleta}", use_container_width=True):
                st.session_state.atletas_df.loc[index, 'Falhas Técnicas'] += 1
                st.rerun()
            if jc_cols[4].button("🏆", key=f"conq_jc_{numero_atleta}", use_container_width=True):
                st.session_state.atletas_df.loc[index, 'Conquistas'] += 1
                st.rerun()

            with jc_cols[5].popover("➖", use_container_width=True):
                 if st.button("Passos", key=f"passos_jc_{numero_atleta}"):
                     st.session_state.atletas_df.loc[index, 'Falhas Técnicas'] += 1
                     st.rerun()
                 if st.button("Perda de Bola", key=f"perda_bola_jc_{numero_atleta}"):
                     st.session_state.atletas_df.loc[index, 'Falhas Técnicas'] += 1
                     st.rerun()
                 if st.button("7m", key=f"7m_jc_{numero_atleta}"):
                     st.session_state.atletas_df.loc[index, 'Falhas Técnicas'] += 1
                     st.rerun()

            with jc_cols[6].popover("징", use_container_width=True):
                st.write(f"Sancionar {nome_atleta}")
                if st.button("Amarelo", key=f"amarelo_jc_{numero_atleta}"):
                    st.session_state.atletas_df.loc[index, 'Sanções'] += 'A '
                    st.rerun()
                if st.button("2 Minutos", key=f"2min_jc_{numero_atleta}"):
                    st.session_state.atletas_df.loc[index, 'Contador 2min'] += 1
                    st.session_state.atletas_df.loc[index, 'Sanções'] += '2\' '
                    st.session_state.sanction_timers[numero_atleta] = time.time() + 120
                    if st.session_state.atletas_df.loc[index, 'Contador 2min'] >= 3:
                        st.session_state.atletas_df.loc[index, 'Estado'] = 'Desqualificado'
                    st.rerun()
                if st.button("Vermelho", key=f"verm_jc_{numero_atleta}"):
                    st.session_state.atletas_df.loc[index, 'Estado'] = 'Desqualificado'
                    st.session_state.atletas_df.loc[index, 'Sanções'] += 'V '
                    st.rerun()
                if st.button("2m + 7m", key=f"2m7m_jc_{numero_atleta}"):
                    st.session_state.atletas_df.loc[index, 'Falhas Técnicas'] += 1
                    st.session_state.atletas_df.loc[index, 'Contador 2min'] += 1
                    st.session_state.atletas_df.loc[index, 'Sanções'] += '2\' '
                    st.session_state.sanction_timers[numero_atleta] = time.time() + 120
                    if st.session_state.atletas_df.loc[index, 'Contador 2min'] >= 3:
                        st.session_state.atletas_df.loc[index, 'Estado'] = 'Desqualificado'
                    st.rerun()


        st.markdown("---")
        # --- Oficiais e Sanções Adversárias ---
        col_oficiais, col_adv = st.columns(2)

        with col_oficiais:
            st.markdown("##### Oficiais")
            for index, oficial in st.session_state.oficiais_df.iterrows():
                oficial_cols = st.columns([2, 1])
                oficial_cols[0].markdown(f"**{oficial['Posicao']}**: {oficial['Nome']}")
                # CORREÇÃO: Removido o argumento 'key' do popover
                with oficial_cols[1].popover("징 Sanção", use_container_width=True):
                    if st.button("Amarelo", key=f"amarelo_oficial_{index}"):
                        st.session_state.oficiais_df.loc[index, 'Sanções'] += 'A '
                        st.rerun()
                    if st.button("2 Minutos", key=f"2min_oficial_{index}"):
                        st.session_state.oficiais_df.loc[index, 'Sanções'] += '2\' '
                        # Lógica para bloquear um jogador
                        # Pega no primeiro jogador em campo que não seja GR e não tenha sanção
                        jogadores_campo = st.session_state.atletas_df[
                            (st.session_state.atletas_df['Em Campo']) &
                            (st.session_state.atletas_df['Posicao'] != 'GR') &
                            (st.session_state.atletas_df['Estado'] != 'Desqualificado')
                        ]
                        if not jogadores_campo.empty:
                            idx_jogador_a_sancionar = jogadores_campo.index[0]
                            num_jogador = st.session_state.atletas_df.loc[idx_jogador_a_sancionar, 'Numero']
                            st.session_state.atletas_df.loc[idx_jogador_a_sancionar, 'Estado'] = 'Sanção Oficial'
                            st.session_state.sanction_timers[num_jogador] = time.time() + 120
                            st.toast(f"Sanção de oficial. {st.session_state.atletas_df.loc[idx_jogador_a_sancionar, 'Nome']} fica de fora por 2 min.", icon="🔵")
                        st.rerun()
                    if st.button("Vermelho", key=f"verm_oficial_{index}"):
                         st.session_state.oficiais_df.loc[index, 'Sanções'] += 'V '
                         st.rerun()

        with col_adv:
            st.markdown("##### Ações Adversário")
            timer_adv_display = ""
            if time.time() < st.session_state.adversary_sanction_timer:
                rem_time = st.session_state.adversary_sanction_timer - time.time()
                timer_adv_display = f"Superioridade ({format_time(rem_time)})"

            with st.popover(f"➕ Sanção Adversário {timer_adv_display}", use_container_width=True):
                st.write("Registar sanção na equipa adversária:")
                if st.button("2 Minutos Adversário", key="adv_2min"):
                    st.session_state.adversary_sanction_timer = time.time() + 120
                    st.rerun()
                if st.button("Vermelho Adversário", key="adv_verm"):
                    st.session_state.adversary_sanction_timer = time.time() + 120 # Vermelho direto também implica 2 min de inferioridade
                    st.rerun()

    with tab_resumo:
        st.header("Resumo e Estatísticas do Jogo")
        st.write("Esta área está reservada para os relatórios finais.")

        st.subheader("Estatísticas dos Atletas")
        st.dataframe(st.session_state.atletas_df[[
            'Numero', 'Nome', 'Posicao', 'Golos', 'Conquistas', 'Falhas Técnicas', 'Remates Sofridos', 'Sanções'
        ]], use_container_width=True)

        st.subheader("Estatísticas dos Oficiais")
        st.dataframe(st.session_state.oficiais_df, use_container_width=True)


# --- Loop Principal e Atualização de Estado ---
if __name__ == "__main__":
    initialize_state()
    main_app()

    # Lógica para manter a app a atualizar a cada segundo quando o cronómetro está a correr
    if st.session_state.get('running', False):
        # Atualiza o tempo de jogo dos atletas em campo
        for index, atleta in st.session_state.atletas_df.iterrows():
            if atleta['Em Campo']:
                st.session_state.atletas_df.loc[index, 'Tempo Jogo (s)'] += 1

        # Limpa sanções expiradas
        now = time.time()
        for numero, end_time in list(st.session_state.sanction_timers.items()):
            if now >= end_time:
                del st.session_state.sanction_timers[numero]
                # Reverte o estado de 'Sanção Oficial' se aplicável
                idx = st.session_state.atletas_df[st.session_state.atletas_df['Numero'] == numero].index
                if not idx.empty and st.session_state.atletas_df.loc[idx[0], 'Estado'] == 'Sanção Oficial':
                     st.session_state.atletas_df.loc[idx[0], 'Estado'] = 'Banco'

        # Guarda o estado atual
        save_state()
        time.sleep(1)
        st.rerun()
    else:
        # Guarda o estado mesmo quando pausado para persistir outras alterações
        save_state()
