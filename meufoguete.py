import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json # Para salvar/carregar dados de calibração

# --- Constantes Globais ---
RHO = 1000  # Densidade da água (kg/m³)
G = 9.81    # Aceleração da gravidade (m/s²)
P0 = 101325 # Pressão atmosférica padrão (Pa)
M_REF = 0.4 # Massa de referência para cálculo de eficiência (kg)
A_REF = 100 # Área de aletas de referência para cálculo de eficiência (cm²)
ALPHA_M = 0.3 # Fator de penalidade para massa
ALPHA_A = 0.2 # Fator de penalidade para área das aletas
F_STAB = 1.0 # Fator de estabilidade (simplificado)
CD_ALETA_UNIT = 1.0 # Coeficiente de arrasto assumido por aleta (simplificado)
CD_CORPO = 0.5 # Coeficiente de arrasto do corpo (simplificado)

# --- Funções de Cálculo ---
def calcular_fator_eficiencia(m_total, area_aletas, acabamento="liso", alinhamento="bom", E0=40.0):
    """Calcula o fator de eficiência geral (E) baseado nos parâmetros e em E0."""
    penalidade_m = ALPHA_M * max(0, m_total - M_REF)
    # Convertendo área de aletas para m² para consistência interna, se necessário,
    # mas como a referência é em cm², mantemos a comparação em cm².
    penalidade_a = ALPHA_A * max(0, area_aletas - A_REF)

    fator_vis = 1.0
    if acabamento == "rugoso":
        fator_vis *= 0.9
    if alinhamento == "torto":
        fator_vis *= 0.9

    # Garante que os fatores de penalidade não resultem em eficiência negativa ou > 1
    fator_penalidades_vis = max(0, (1 - penalidade_m)) * max(0, (1 - penalidade_a)) * fator_vis
    
    E = E0 * fator_penalidades_vis
    return E, fator_penalidades_vis # Retorna E total e o fator de penalidades/visual

def calcular_distancia(P_psi, m_total, Vw_L, N_aletas, E_total):
    """Calcula a distância estimada do lançamento."""
    if m_total <= 0: # Evita divisão por zero
        return 0.0

    P_pascal = P_psi * 6894.76 # Converte psi para Pascal
    deltaP = P_pascal - P0     # Pressão manométrica em Pascal
    Vw_m3 = Vw_L / 1000        # Converte Volume de água de L para m³

    if deltaP <= 0 or Vw_m3 <= 0: # Condições não físicas para lançamento
        return 0.0

    # Impulso inicial simplificado (Termo K de Tsiolkovsky adaptado?)
    K = 2 * deltaP / (RHO * G) # Componente relacionado à pressão

    m_prop = RHO * Vw_m3 # Massa do propelente (água)
    
    # Verificação para evitar log de zero ou negativo ou divisão por zero
    massa_final = m_total - m_prop
    if massa_final <= 0 or m_prop <= 0:
         st.warning(f"Massa total ({m_total:.2f} kg) deve ser maior que a massa de água ({m_prop:.2f} kg).")
         return 0.0 # Massa final não pode ser zero ou negativa

    # Coeficiente de arrasto total simplificado
    # Pode ser melhorado para depender da velocidade, etc.
    Cd_total = CD_CORPO + N_aletas * CD_ALETA_UNIT

    if Cd_total <= 0: # Evita divisão por zero
        return 0.0

    # Fórmula simplificada para distância - REVISAR A FÍSICA DESTA FÓRMULA
    # Esta fórmula parece muito simplificada e pode não representar a física real.
    # D = K * (m_prop / m_total)**2 * (1 / Cd_total) * f_stab * E ???
    # A fórmula original do código base era:
    # D_model = K * (m_prop / m_total) ** 2 * (1 / Cd_total) * f_stab
    # return E * D_model
    # Vamos manter a estrutura original por enquanto.
    
    # Cálculo base da distância (sem o fator E)
    distancia_base_modelo = K * (m_prop / m_total) ** 2 * (1 / Cd_total) * F_STAB

    # Distância final multiplicada pelo fator de eficiência total
    distancia_final = E_total * distancia_base_modelo
    
    return distancia_final

def calcular_distancia_base(P_psi, m_total, Vw_L, N_aletas):
    """Calcula a distância base do modelo (sem fator de eficiência E)."""
    if m_total <= 0: return 0.0
    P_pascal = P_psi * 6894.76
    deltaP = P_pascal - P0
    Vw_m3 = Vw_L / 1000
    if deltaP <= 0 or Vw_m3 <= 0: return 0.0

    K = 2 * deltaP / (RHO * G)
    m_prop = RHO * Vw_m3
    massa_final = m_total - m_prop
    if massa_final <= 0 or m_prop <= 0: return 0.0

    Cd_total = CD_CORPO + N_aletas * CD_ALETA_UNIT
    if Cd_total <= 0: return 0.0

    distancia_base_modelo = K * (m_prop / m_total) ** 2 * (1 / Cd_total) * F_STAB
    return distancia_base_modelo

# --- Função Auxiliar para Simulação ---
def rodar_simulacao(param_variavel_nome, param_range, inputs_fixos, E0_usado, valor_atual):
    """
    Roda uma simulação variando um parâmetro e retorna DataFrame estilizado e figura.
    """
    simulacoes = []
    # Extrai valores fixos do dicionário
    massa_f = inputs_fixos['massa_total']
    area_f = inputs_fixos['area_aletas']
    acab_f = inputs_fixos['acabamento']
    alin_f = inputs_fixos['alinhamento']
    pressao_f = inputs_fixos['pressao_psi']
    volume_f = inputs_fixos['volume_agua']
    num_aletas_f = inputs_fixos['num_aletas']

    param_title = "" # Inicializa para evitar UnboundLocalError

    for val in param_range:
        # Cria cópias para não modificar os valores fixos originais no loop
        m, a, p, v, n_a, acab, alin = massa_f, area_f, pressao_f, volume_f, num_aletas_f, acab_f, alin_f

        # Atualiza o valor do parâmetro que está variando
        if param_variavel_nome == 'pressao_psi':
            p = val
            param_title = "Pressão (psi)"
        elif param_variavel_nome == 'massa_total':
            m = val
            param_title = "Massa Total (kg)"
        elif param_variavel_nome == 'volume_agua':
            v = val
            param_title = "Volume Água (L)"
        elif param_variavel_nome == 'area_aletas':
            a = val
            param_title = "Área Aletas (cm²)"
        elif param_variavel_nome == 'num_aletas':
            n_a = int(val) # Número de aletas deve ser inteiro
            param_title = "Número Aletas"
        else:
             # Caso base se o nome do parâmetro não for reconhecido (evita erros)
             param_title = param_variavel_nome.replace('_', ' ').title()


        # Calcula E e Distância com os valores atuais (fixos + o variado)
        E_sim, _ = calcular_fator_eficiencia(m, a, acab, alin, E0=E0_usado)
        d_sim = calcular_distancia(p, m, v, n_a, E_sim)

        simulacoes.append({
            param_title: round(val, 2), # Coluna com o nome do parâmetro variado
            "Fator E Calc.": round(E_sim, 2),
            "Distância Estimada (m)": round(d_sim, 1)
        })

    if not simulacoes: # Se nenhuma simulação foi gerada
         st.warning(f"Nenhuma simulação pôde ser gerada para {param_title}.")
         return pd.DataFrame().style, plt.figure() # Retorna vazio

    df_sim = pd.DataFrame(simulacoes)

    # Verifica se a coluna do parâmetro variado existe antes de definir como índice
    if param_title not in df_sim.columns:
        st.error(f"Erro interno: Coluna '{param_title}' não encontrada no DataFrame da simulação.")
        return df_sim.style, plt.figure()

    try:
        df_sim = df_sim.set_index(param_title) # Define o parâmetro variado como índice
    except KeyError:
         st.error(f"Erro ao definir o índice '{param_title}'. Verifique os dados da simulação.")
         return df_sim.style, plt.figure()


    # Cria o gráfico
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(df_sim.index, df_sim["Distância Estimada (m)"], marker='o', linestyle='-')
     # Adiciona uma linha vertical no valor atual do input principal
    ax.axvline(x=valor_atual, color='red', linestyle='--', label=f'Valor Atual ({valor_atual:.2f})')
    ax.set_xlabel(f"{param_title}")
    ax.set_ylabel("Distância Estimada (m)")
    ax.set_title(f"Simulação: Distância Estimada vs {param_title}")
    ax.legend()
    ax.grid(True)
    plt.tight_layout()

    # Estiliza DataFrame para destacar a linha mais próxima do valor atual
    try:
        # Tenta encontrar valor exato primeiro (mais robusto com get_loc)
        exact_pos = df_sim.index.get_loc(valor_atual)
        # Se get_loc retornar um slice ou array, não é um valor único, não destacar
        if isinstance(exact_pos, (slice, np.ndarray)):
             df_styled = df_sim.style
        else:
             df_styled = df_sim.style.apply(lambda x: ['background-color: yellow' if x.name == valor_atual else '' for i in x], axis=1)

    except KeyError:
        # Se não achar valor exato, busca o mais próximo
        try: # Adiciona um try/except interno para o caso de índice não numérico
             # 1. Encontra a POSIÇÃO (inteiro) do índice mais próximo
             closest_idx_pos = np.abs(df_sim.index.to_numpy() - valor_atual).argmin()
             # 2. Obtém o VALOR do índice naquela posição
             closest_val = df_sim.index[closest_idx_pos]
             # Aplica o estilo comparando com o valor mais próximo encontrado
             df_styled = df_sim.style.apply(lambda x: ['background-color: yellow' if np.isclose(x.name, closest_val) else '' for i in x], axis=1)
        except TypeError:
             # Caso o índice não seja numérico ou a subtração falhe, não aplica estilo
             st.warning(f"Não foi possível destacar o valor mais próximo para '{param_title}'. O índice pode não ser numérico ou o tipo de dado é incompatível.")
             df_styled = df_sim.style # Retorna o estilo padrão
    except Exception as e: # Captura outras exceções inesperadas
        st.error(f"Erro inesperado ao estilizar tabela para '{param_title}': {e}")
        df_styled = df_sim.style # Retorna o estilo padrão


    # Formata as colunas numéricas do DataFrame estilizado
    try:
        df_styled = df_styled.format({
            "Fator E Calc.": "{:.2f}",
            "Distância Estimada (m)": "{:.1f}"
        })
    except Exception as e:
        st.error(f"Erro ao formatar tabela para '{param_title}': {e}")
        # Se a formatação falhar, retorna o estilo sem formatação (melhor que quebrar)

    return df_styled, fig

# --- Interface Streamlit ---
st.set_page_config(layout="wide") # Usa layout largo para melhor visualização
st.title("🚀 Simulador de Foguetes de Água - Estimativa de Alcance")

# Inicializa session state se não existir
if 'dados_calibracao' not in st.session_state:
    st.session_state.dados_calibracao = []
if 'E0_calibrado' not in st.session_state:
    st.session_state.E0_calibrado = None
if 'usar_calibrado' not in st.session_state:
    st.session_state.usar_calibrado = False # Por padrão, não usa o calibrado

# --- Abas para Organização ---
tab_entrada, tab_calibracao, tab_resultados, tab_simulacoes = st.tabs([
    "🔩 Entrada Principal",
    "📊 Calibração",
    "🎯 Resultados",
    "📈 Simulações"
])

# --- Tab 1: Entrada Principal ---
with tab_entrada:
    st.header("🔧 Parâmetros de Entrada do Foguete e Lançamento")
    col1, col2 = st.columns(2)
    with col1:
        massa_total = st.number_input("Massa total do foguete (kg)", value=0.4, min_value=0.05, step=0.01, format="%.3f", key="massa_total")
        area_aletas = st.number_input("Área total das aletas (cm²)", value=100.0, min_value=1.0, step=1.0, format="%.1f", key="area_aletas")
        num_aletas = st.number_input("Número de aletas", value=3, min_value=0, max_value=8, step=1, key="num_aletas")
    with col2:
        pressao_psi = st.number_input("Pressão de lançamento (psi)", value=70, min_value=10, max_value=150, step=1, key="pressao_psi")
        volume_agua = st.number_input("Volume de água (L)", value=0.5, min_value=0.05, max_value=2.0, step=0.05, format="%.2f", key="volume_agua")
        acabamento = st.selectbox("Acabamento da superfície", ["liso", "rugoso"], key="acabamento")
        alinhamento = st.selectbox("Alinhamento das aletas", ["bom", "torto"], key="alinhamento")

    st.caption(f"Constantes do Modelo: Densidade H₂O={RHO} kg/m³, g={G} m/s², P₀={P0/1000:.1f} kPa, M_ref={M_REF} kg, A_ref={A_REF} cm², α_m={ALPHA_M}, α_a={ALPHA_A}, Cd_corpo={CD_CORPO}, Cd_aleta={CD_ALETA_UNIT}")

# --- Tab 2: Calibração ---
with tab_calibracao:
    st.header("📋 Calibração do Modelo com Dados Reais")

    col_calib_1, col_calib_2 = st.columns(2)

    with col_calib_1:
        st.subheader("Entrada de Dados Reais")
        modo_calibracao = st.radio("Adicionar dados de lançamentos reais?", ["Não", "Sim"], index=0, key="modo_calib")

        if modo_calibracao == "Sim":
            num_lancamentos_novos = st.number_input("Quantos *novos* lançamentos deseja adicionar?", min_value=1, max_value=10, value=1, step=1, key="num_lanc_add")

            with st.form("form_lancamentos"):
                novos_dados = []
                for i in range(num_lancamentos_novos):
                    st.markdown(f"--- Lançamento Novo {i+1} ---")
                    # Usar colunas dentro do form para organizar
                    col_form_1, col_form_2 = st.columns(2)
                    with col_form_1:
                        massa_l = st.number_input(f"Massa (kg) {i+1}", min_value=0.1, step=0.01, format="%.3f", key=f"m_{i}")
                        pressao_l = st.number_input(f"Pressão (psi) {i+1}", min_value=10, step=1, key=f"p_{i}")
                        # Adicionar área de aletas por lançamento se for muito variável? Por ora, usa o global.
                        # area_l = st.number_input(f"Área Aletas (cm²) {i+1}", min_value=1.0, step=1.0, format="%.1f", key=f"a_{i}")
                        acabamento_l = st.selectbox(f"Acabamento {i+1}", ["liso", "rugoso"], key=f"acab_{i}")

                    with col_form_2:
                        volume_l = st.number_input(f"Volume H₂O (L) {i+1}", min_value=0.1, step=0.05, format="%.2f", key=f"v_{i}")
                        num_aletas_l = st.number_input(f"Nº Aletas {i+1}", min_value=0, max_value=8, step=1, key=f"n_{i}")
                        alinhamento_l = st.selectbox(f"Alinhamento {i+1}", ["bom", "torto"], key=f"alin_{i}")
                        distancia_real_l = st.number_input(f"Distância Real (m) {i+1}", min_value=0.1, step=0.1, format="%.1f", key=f"d_{i}")

                    novos_dados.append({
                        'massa': massa_l, 'pressao': pressao_l, 'volume': volume_l,
                        'num_aletas': num_aletas_l, 'acabamento': acabamento_l,
                        'alinhamento': alinhamento_l, 'distancia_real': distancia_real_l,
                        # 'area_aletas': area_l # Descomentar se adicionar input de área por lançamento
                    })

                submitted = st.form_submit_button("Adicionar Lançamentos à Lista")
                if submitted:
                    st.session_state.dados_calibracao.extend(novos_dados)
                    st.success(f"{len(novos_dados)} lançamento(s) adicionado(s) à lista de calibração.")
                    # Limpar o form? Pode ser complexo com st.form. Recarregar a página pode ser mais fácil.

    with col_calib_2:
        st.subheader("Dados para Calibração")
        if st.session_state.dados_calibracao:
            df_cal = pd.DataFrame(st.session_state.dados_calibracao)
            st.dataframe(df_cal, height=200)

            if st.button("Limpar Lista de Dados"):
                st.session_state.dados_calibracao = []
                st.rerun() # Recarrega a página para refletir a limpeza

            # --- Botão de Salvar Dados ---
            if st.session_state.dados_calibracao:
                 json_data = json.dumps(st.session_state.dados_calibracao, indent=4)
                 st.download_button(
                     label="Salvar Dados de Calibração (JSON)",
                     data=json_data,
                     file_name='dados_calibracao_foguete.json',
                     mime='application/json',
                 )
        else:
            st.info("Nenhum dado de calibração na lista. Adicione dados à esquerda ou carregue um arquivo.")

        # --- Botão de Carregar Dados ---
        uploaded_file = st.file_uploader("Carregar Dados de Calibração (JSON)", type="json")
        if uploaded_file is not None:
            try:
                loaded_data = json.load(uploaded_file)
                # Validação básica se é uma lista de dicionários
                if isinstance(loaded_data, list) and all(isinstance(item, dict) for item in loaded_data):
                    st.session_state.dados_calibracao = loaded_data
                    st.success(f"Dados carregados com sucesso de '{uploaded_file.name}'.")
                    st.rerun() # Recarrega para exibir os dados carregados
                else:
                    st.error("Arquivo JSON inválido. Deve ser uma lista de lançamentos (dicionários).")
            except Exception as e:
                st.error(f"Erro ao ler o arquivo JSON: {e}")


    st.divider()
    st.subheader("Executar Calibração e Resultados")

    # Só mostra o botão se houver dados
    if st.session_state.dados_calibracao:
        # Usa a área de aletas global definida na aba de entrada para a calibração
        area_aletas_global = st.session_state.get('area_aletas', A_REF)
        st.caption(f"Nota: A calibração usará a Área de Aletas definida na Entrada Principal ({area_aletas_global} cm²) para calcular penalidades, a menos que você modifique o código para incluir área por lançamento.")

        if st.button("🚀 Calcular Novo Fator de Eficiência Base (E₀)"):
            E0s_implicitos = []
            dados_plot_calibracao = []

            with st.spinner("Calculando E₀ calibrado..."):
                for i, dado in enumerate(st.session_state.dados_calibracao):
                    # Pega a área de aletas - da entrada principal ou do dado individual se existir
                    area_l = dado.get('area_aletas', area_aletas_global)

                    # Calcula fator de penalidades/visual para este lançamento
                    _, fator_pen_vis = calcular_fator_eficiencia(
                        dado['massa'], area_l, dado['acabamento'], dado['alinhamento'], E0=1.0 # E0=1 para pegar só o fator
                    )

                    # Calcula a distância base (sem nenhum fator de eficiência)
                    distancia_base = calcular_distancia_base(
                        dado['pressao'], dado['massa'], dado['volume'], dado['num_aletas']
                    )

                    if distancia_base > 1e-6 and fator_pen_vis > 1e-6: # Evita divisão por zero ou valores muito pequenos
                        E0_implicito = dado['distancia_real'] / (distancia_base * fator_pen_vis)
                        E0s_implicitos.append(E0_implicito)

                        # Calcula predições para plot (com E0=40 e com E0 implícito individual)
                        E_original, _ = calcular_fator_eficiencia(dado['massa'], area_l, dado['acabamento'], dado['alinhamento'], E0=40.0)
                        dist_pred_original = calcular_distancia(dado['pressao'], dado['massa'], dado['volume'], dado['num_aletas'], E_original)

                        dados_plot_calibracao.append({
                            'lancamento': i + 1,
                            'distancia_real': dado['distancia_real'],
                            'E0_implicito': E0_implicito,
                            'distancia_predita_E0_40': dist_pred_original,
                            # 'distancia_predita_E0_implicito': dist_pred_E0_imp # Pode ser calculado depois com a média
                        })
                    else:
                        st.warning(f"Lançamento {i+1} ignorado na calibração (distância base ou fator de penalidade muito baixo/zero). Verifique os dados: {dado}")

            if E0s_implicitos:
                E0_calibrado_calc = np.mean(E0s_implicitos)
                E0_std_dev = np.std(E0s_implicitos)
                st.session_state.E0_calibrado = E0_calibrado_calc # Salva no estado da sessão
                st.success(f"✅ Novo Fator de Eficiência Base (E₀) Calibrado: **{E0_calibrado_calc:.2f}** (Desvio Padrão: {E0_std_dev:.2f})")
                st.info(f"Baseado em {len(E0s_implicitos)} lançamentos válidos.")

                # --- Gráficos de Calibração ---
                df_plot = pd.DataFrame(dados_plot_calibracao)

                # 1. Comparação E0 Original vs. Calibrado
                fig1, ax1 = plt.subplots(figsize=(6, 4))
                E0_original_const = 40.0 # Valor hardcoded na função original
                ax1.bar(['Original (E₀=40)', 'Calibrado (Média)'], [E0_original_const, E0_calibrado_calc], color=['lightblue', 'lightgreen'])
                # Adicionar pontos individuais de E0 implícito
                ax1.scatter(['Calibrado (Média)']*len(df_plot['E0_implicito']), df_plot['E0_implicito'], color='blue', zorder=3, label='E₀ Implícito (por Lanç.)')
                ax1.set_title("Comparação: Fator de Eficiência Base (E₀)")
                ax1.set_ylabel("Valor de E₀")
                ax1.legend()
                st.pyplot(fig1)

                # 2. Plot Previsto vs. Real
                # Calcula predição com E0 calibrado para todos os pontos
                df_plot['distancia_predita_calibrada'] = df_plot.apply(
                    lambda row: calcular_distancia(
                        st.session_state.dados_calibracao[int(row['lancamento'])-1]['pressao'],  # Força a conversão para inteiro
                        st.session_state.dados_calibracao[int(row['lancamento'])-1]['massa'],    # Força a conversão para inteiro
                        st.session_state.dados_calibracao[int(row['lancamento'])-1]['volume'],   # Força a conversão para inteiro
                        st.session_state.dados_calibracao[int(row['lancamento'])-1]['num_aletas'],  # Força a conversão para inteiro
                        calcular_fator_eficiencia(
                            st.session_state.dados_calibracao[int(row['lancamento'])-1]['massa'],
                            st.session_state.dados_calibracao[int(row['lancamento'])-1].get('area_aletas', area_aletas_global),
                            st.session_state.dados_calibracao[int(row['lancamento'])-1]['acabamento'],
                            st.session_state.dados_calibracao[int(row['lancamento'])-1]['alinhamento'],
                            E0=E0_calibrado_calc # Usa o E0 médio calibrado
                        )[0]  # Pega só o E total
                    ), axis=1
                )

                fig2, ax2 = plt.subplots(figsize=(7, 5))
                ax2.scatter(df_plot['distancia_real'], df_plot['distancia_predita_E0_40'], label=f'Predito (E₀=40)', color='red', marker='x', alpha=0.7)
                ax2.scatter(df_plot['distancia_real'], df_plot['distancia_predita_calibrada'], label=f'Predito (E₀={E0_calibrado_calc:.1f})', color='green', marker='o', alpha=0.7)
                lim_max = max(df_plot['distancia_real'].max(), df_plot['distancia_predita_calibrada'].max(), df_plot['distancia_predita_E0_40'].max()) * 1.1
                ax2.plot([0, lim_max], [0, lim_max], color='grey', linestyle='--', label='Ideal (Real = Predito)')
                ax2.set_xlabel("Distância Real Medida (m)")
                ax2.set_ylabel("Distância Predita pelo Modelo (m)")
                ax2.set_title("Comparação: Distância Real vs. Predita")
                ax2.legend()
                ax2.grid(True)
                ax2.set_xlim(0, lim_max)
                ax2.set_ylim(0, lim_max)
                st.pyplot(fig2)

                # 3. Mostrar E0s implícitos por lançamento
                st.write("Detalhes da Calibração por Lançamento:")
                st.dataframe(df_plot[['lancamento', 'distancia_real', 'distancia_predita_E0_40', 'distancia_predita_calibrada', 'E0_implicito']].style.format({
                    'distancia_real': '{:.1f}',
                    'distancia_predita_E0_40': '{:.1f}',
                    'distancia_predita_calibrada': '{:.1f}',
                    'E0_implicito': '{:.2f}'
                }))

            else:
                st.error("Não foi possível calcular o E₀ calibrado. Verifique os dados de entrada e se são válidos.")
    else:
        st.warning("Adicione ou carregue dados de lançamentos reais para poder calibrar o modelo.")

    st.divider()
    # Opção para USAR o E0 calibrado (só aparece se um E0 foi calibrado)
    if st.session_state.E0_calibrado is not None:
        st.session_state.usar_calibrado = st.toggle(
            f"Usar E₀ Calibrado ({st.session_state.E0_calibrado:.2f}) nos cálculos?",
            value=st.session_state.get('usar_calibrado', True), # Padrão é usar se disponível
            key="toggle_usar_calibrado"
        )
        if st.session_state.usar_calibrado:
             st.success(f"O valor E₀ = {st.session_state.E0_calibrado:.2f} (calibrado) será usado nos Resultados e Simulações.")
        else:
             st.info(f"O valor E₀ = 40.0 (padrão) será usado nos Resultados e Simulações.")
    else:
        st.info("Nenhum E₀ calibrado disponível. O valor padrão E₀ = 40.0 será usado.")
        st.session_state.usar_calibrado = False # Garante que não tente usar se não houver


# --- Tab 3: Resultados Principais ---
with tab_resultados:
    st.header("🎯 Resultados da Simulação Principal")

    # Determina qual E0 usar baseado no toggle da aba de calibração
    if st.session_state.get('usar_calibrado', False) and st.session_state.E0_calibrado is not None:
        E0_para_calculo = st.session_state.E0_calibrado
        st.info(f"Calculando com E₀ Calibrado = {E0_para_calculo:.2f}")
    else:
        E0_para_calculo = 40.0 # Valor Padrão
        st.info(f"Calculando com E₀ Padrão = {E0_para_calculo:.2f}")

    # Recupera os valores dos inputs principais (podem ter sido alterados na Aba 1)
    massa_atual = st.session_state.get('massa_total', 0.4)
    area_atual = st.session_state.get('area_aletas', 100.0)
    acab_atual = st.session_state.get('acabamento', 'liso')
    alin_atual = st.session_state.get('alinhamento', 'bom')
    pressao_atual = st.session_state.get('pressao_psi', 70)
    volume_atual = st.session_state.get('volume_agua', 0.5)
    num_aletas_atual = st.session_state.get('num_aletas', 3)

    # Cálculo com valores principais e E0 selecionado
    E_calc, _ = calcular_fator_eficiencia(massa_atual, area_atual, acab_atual, alin_atual, E0=E0_para_calculo)
    distancia_calc = calcular_distancia(pressao_atual, massa_atual, volume_atual, num_aletas_atual, E_calc)

    col_res1, col_res2 = st.columns(2)
    with col_res1:
        st.metric(label="Fator de Eficiência Total (E)", value=f"{E_calc:.2f}")
        with st.expander("ℹ️ Como o Fator de Eficiência (E) é calculado?"):
             st.latex(r"E = E_0 \times (1 - \alpha_m \times \max(0, m_{total} - m_{ref})) \times (1 - \alpha_a \times \max(0, A_{aletas} - A_{ref})) \times f_{visual}")
             # --- LINHA CORRIGIDA ABAIXO ---
             st.markdown(f"""
             Onde:
             - $E_0$: Fator de Eficiência Base (Padrão=40 ou Calibrado={f"{st.session_state.E0_calibrado:.2f}" if st.session_state.E0_calibrado is not None else 'N/A'})
             - $\\alpha_m = {ALPHA_M}$: Penalidade por massa acima de $m_{{ref}}={M_REF}$ kg.
             - $\\alpha_a = {ALPHA_A}$: Penalidade por área de aletas acima de $A_{{ref}}={A_REF}$ cm².
             - $f_{{visual}}$: Fator por acabamento e alinhamento (0.9 para rugoso, 0.9 para torto).
             """)
             # --- FIM DA CORREÇÃO ---
    with col_res2:
        st.metric(label="Distância Estimada", value=f"{distancia_calc:.1f} metros")

    st.warning("Lembrete: A fórmula de distância usada é uma simplificação e pode não refletir com precisão a trajetória real.")

# --- Tab 4: Simulações ---
with tab_simulacoes:
    st.header("📈 Simulações Variando Parâmetros")
    st.markdown("Veja como a distância estimada varia ao mudar um parâmetro de cada vez, mantendo os outros fixos nos valores da 'Entrada Principal'.")

    # Determina E0 a ser usado nas simulações
    if st.session_state.get('usar_calibrado', False) and st.session_state.E0_calibrado is not None:
        E0_simulacao = st.session_state.E0_calibrado
        st.info(f"Simulações usando E₀ Calibrado = {E0_simulacao:.2f}")
    else:
        E0_simulacao = 40.0
        st.info(f"Simulações usando E₀ Padrão = {E0_simulacao:.2f}")

    # Dicionário com os inputs atuais (fixos para cada simulação)
    inputs_atuais_sim = {
        'massa_total': st.session_state.get('massa_total', 0.4),
        'area_aletas': st.session_state.get('area_aletas', 100.0),
        'acabamento': st.session_state.get('acabamento', 'liso'),
        'alinhamento': st.session_state.get('alinhamento', 'bom'),
        'pressao_psi': st.session_state.get('pressao_psi', 70),
        'volume_agua': st.session_state.get('volume_agua', 0.5),
        'num_aletas': st.session_state.get('num_aletas', 3)
    }

    num_pontos_sim = st.slider("Número de pontos por simulação:", 5, 25, 10)

    # --- Simulação Variando Pressão ---
    st.subheader("🧪 Variação: Pressão")
    pressao_min_sim = max(10, inputs_atuais_sim['pressao_psi'] - 40)
    pressao_max_sim = inputs_atuais_sim['pressao_psi'] + 50
    pressao_range = np.linspace(pressao_min_sim, pressao_max_sim, num_pontos_sim)
    df_pressao_styled, fig_pressao = rodar_simulacao('pressao_psi', pressao_range, inputs_atuais_sim, E0_simulacao, inputs_atuais_sim['pressao_psi'])
    st.dataframe(df_pressao_styled, use_container_width=True)
    st.pyplot(fig_pressao)
    st.divider()

    # --- Simulação Variando Massa ---
    st.subheader("⚖️ Variação: Massa Total")
    massa_min_sim = max(0.1, inputs_atuais_sim['massa_total'] * 0.5)
    massa_max_sim = inputs_atuais_sim['massa_total'] * 2.0
    massa_range = np.linspace(massa_min_sim, massa_max_sim, num_pontos_sim)
    df_massa_styled, fig_massa = rodar_simulacao('massa_total', massa_range, inputs_atuais_sim, E0_simulacao, inputs_atuais_sim['massa_total'])
    st.dataframe(df_massa_styled, use_container_width=True)
    st.pyplot(fig_massa)
    st.divider()

    # --- Simulação Variando Volume de Água ---
    st.subheader("💧 Variação: Volume de Água")
    volume_min_sim = max(0.05, inputs_atuais_sim['volume_agua'] * 0.2)
    volume_max_sim = inputs_atuais_sim['volume_agua'] * 2.5
    volume_range = np.linspace(volume_min_sim, volume_max_sim, num_pontos_sim)
    df_volume_styled, fig_volume = rodar_simulacao('volume_agua', volume_range, inputs_atuais_sim, E0_simulacao, inputs_atuais_sim['volume_agua'])
    st.dataframe(df_volume_styled, use_container_width=True)
    st.pyplot(fig_volume)
    st.divider()

    # --- Simulação Variando Área das Aletas ---
    st.subheader("📐 Variação: Área das Aletas")
    area_min_sim = max(10, inputs_atuais_sim['area_aletas'] * 0.3)
    area_max_sim = inputs_atuais_sim['area_aletas'] * 2.5
    area_range = np.linspace(area_min_sim, area_max_sim, num_pontos_sim)
    df_area_styled, fig_area = rodar_simulacao('area_aletas', area_range, inputs_atuais_sim, E0_simulacao, inputs_atuais_sim['area_aletas'])
    st.dataframe(df_area_styled, use_container_width=True)
    st.pyplot(fig_area)
    st.divider()

    # --- Simulação Variando Número de Aletas ---
    st.subheader("🔢 Variação: Número de Aletas")
    num_aletas_min_sim = 0
    num_aletas_max_sim = 8
    # Garante que o valor atual esteja no range e que os pontos sejam inteiros
    num_aletas_range = np.unique(np.linspace(num_aletas_min_sim, num_aletas_max_sim, num_pontos_sim, dtype=int))
    if inputs_atuais_sim['num_aletas'] not in num_aletas_range:
         num_aletas_range = np.sort(np.append(num_aletas_range, inputs_atuais_sim['num_aletas']))

    df_num_aletas_styled, fig_num_aletas = rodar_simulacao('num_aletas', num_aletas_range, inputs_atuais_sim, E0_simulacao, inputs_atuais_sim['num_aletas'])
    st.dataframe(df_num_aletas_styled, use_container_width=True)
    st.pyplot(fig_num_aletas)
