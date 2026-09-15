"""
Módulo interface.py
Dashboard Web em Streamlit para o DarkAI (Pipeline de Automação de Vídeos para Canal Dark - Fases 1 & 2).
Com suporte a persistência de estado (sobrevive a F5/recarregamento), execução em background thread,
geração de imagens cinematográficas com IA (Pollinations Flux / Gemini) e publicação via YouTube Data API v3.
"""

import os
import json
import time
from datetime import datetime
from PIL import Image
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

import gerenciador_estado as estado
import pipeline_worker as worker
import banco_dados
from gerador_audio import clonar_voz_elevenlabs, usar_audio_proprio, DEFAULT_VOICE_ID
from gerador_roteiro import sanitizar_nome_arquivo, gerar_perguntas_aprofundamento
from editor_video import detectar_aceleracao_gpu
from gerador_imagens import ESTILOS_VISUAIS, extrair_biblia_visual, gerar_imagem_cena_individual
from radar_youtube import obter_nichos_dark, pesquisar_pautas_virais

# Configuração da página Streamlit
st.set_page_config(
    page_title="DarkAI Studio - Canal Dark YouTube",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilização CSS personalizada (Estética Dark Channel moderna)
st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(90deg, #ff4b4b, #ff8f00);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1rem;
        color: #9aa0a6;
        margin-bottom: 1.2rem;
    }
    .phase-badge {
        background-color: #1e293b;
        color: #38bdf8;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.85rem;
        font-weight: 600;
        border: 1px solid #0284c7;
        display: inline-block;
        margin-bottom: 0.8rem;
    }
    .running-banner {
        background: linear-gradient(90deg, #1e1b4b, #311042);
        border: 1px solid #6366f1;
        border-radius: 8px;
        padding: 12px 16px;
        color: #e0e7ff;
        font-weight: 500;
        margin-bottom: 1rem;
    }
    .scene-card {
        background-color: #0f172a;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 12px;
    }
</style>
""", unsafe_allow_html=True)


# =====================================================================
# CARREGAMENTO E SINCRONIZAÇÃO DE ESTADO PERSISTIDO (SOBREVIVE AO F5)
# =====================================================================
dados_estado = estado.obter_estado()

st.session_state.tema = dados_estado.get("tema", "Os 5 Lugares Mais Misteriosos Onde Pessoas Simplesmente Desapareceram")
st.session_state.duracao_minima = float(dados_estado.get("duracao_minima", 3.0))
st.session_state.voz_tipo = dados_estado.get("voz_tipo", "neural_ptbr")
st.session_state.voice_id = dados_estado.get("voice_id") or "pt-BR-AntonioNeural"
st.session_state.audio_proprio_path = dados_estado.get("audio_proprio_path")
st.session_state.respostas_usuario = dados_estado.get("respostas_usuario", {})
st.session_state.roteiro = dados_estado.get("roteiro")
st.session_state.audio_path = dados_estado.get("audio_path")
st.session_state.sync_dados = dados_estado.get("sync_dados")
st.session_state.imagens_cenas = dados_estado.get("imagens_cenas", {}) or {}
st.session_state.estilo_visual = dados_estado.get("estilo_visual", "dark_cinematic")
st.session_state.provedor_imagem = dados_estado.get("provedor_imagem", "gemini")
st.session_state.aspect_ratio_imagem = dados_estado.get("aspect_ratio_imagem", "16:9")
st.session_state.biblia_visual = dados_estado.get("biblia_visual")
st.session_state.flow_motion_ativo = bool(dados_estado.get("flow_motion_ativo", True))
st.session_state.video_path = dados_estado.get("video_path")
st.session_state.youtube_dados = dados_estado.get("youtube_dados")
st.session_state.shorts_gerados = dados_estado.get("shorts_gerados", []) or []
st.session_state.logs = dados_estado.get("logs", [])
st.session_state.progresso_valor = dados_estado.get("progresso_valor", 0.0)
st.session_state.progresso_texto = dados_estado.get("progresso_texto", "Aguardando início...")
st.session_state.status = dados_estado.get("status", "idle")
st.session_state.etapa_atual = dados_estado.get("etapa_atual", "")
st.session_state.erro = dados_estado.get("erro")

if "perfil_canal" not in st.session_state:
    st.session_state.perfil_canal = banco_dados.obter_perfil_canal()
if "pautas_radar" not in st.session_state:
    st.session_state.pautas_radar = []

esta_rodando = (st.session_state.status == "running")


# =====================================================================
# MODAL DE PERGUNTAS DE APROFUNDAMENTO (@st.dialog)
# =====================================================================
@st.dialog("🧠 Aprofundar Conteúdo com IA")
def modal_aprofundar_conteudo(tema_atual: str, duracao_atual: float):
    st.markdown(f"##### 🎯 Direcionamento Narrativo: *{tema_atual}*")
    meta_palavras = max(120, int(duracao_atual * 140))
    st.caption(f"Meta de minutagem: **{duracao_atual:.1f} min** (~{meta_palavras} palavras). O Gemini formulou perguntas estratégicas para calibrar o tom, revelações e mistério.")

    if "perguntas_cache" not in st.session_state or st.session_state.get("tema_cache_perguntas") != tema_atual:
        with st.spinner("Gerando perguntas estratégicas com Gemini..."):
            st.session_state.perguntas_cache = gerar_perguntas_aprofundamento(tema_atual, duracao_atual)
            st.session_state.tema_cache_perguntas = tema_atual

    perguntas = st.session_state.get("perguntas_cache", [])
    respostas_escolhidas = {}

    for idx, p in enumerate(perguntas):
        pid = p.get("id", f"p_{idx}")
        enunciado = p.get("pergunta", "")
        opcoes = p.get("opcoes", [])
        st.markdown(f"**{idx + 1}. {enunciado}**")
        escolha = st.radio(
            f"Opção {idx+1}",
            options=opcoes,
            key=f"modal_rad_{pid}",
            label_visibility="collapsed"
        )
        respostas_escolhidas[enunciado] = escolha

    st.markdown("---")
    obs_extra = st.text_input(
        "💡 Detalhe extra ou teoria que você deseja incluir (Opcional):",
        placeholder="Ex: Enfatizar o diário secreto da expedição de 1959..."
    )
    if obs_extra.strip():
        respostas_escolhidas["Observação Adicional"] = obs_extra.strip()

    col_btn_m1, col_btn_m2 = st.columns(2)
    with col_btn_m1:
        if st.button("🚀 Gerar Roteiro Aprofundado", type="primary", use_container_width=True):
            st.session_state.respostas_usuario = respostas_escolhidas
            estado.definir_dados(duracao_minima=duracao_atual)
            worker.disparar_etapa_roteiro(
                tema=tema_atual,
                duracao_minima_minutos=duracao_atual,
                respostas_usuario=respostas_escolhidas,
                perfil_canal=st.session_state.perfil_canal
            )
            st.rerun()
    with col_btn_m2:
        if st.button("Fechar", use_container_width=True):
            st.rerun()


# =====================================================================
# SIDEBAR: CONFIGURAÇÕES E CREDENCIAIS
# =====================================================================
with st.sidebar:
    st.markdown("### ⚙️ Painel de Controle")
    st.markdown("<div class='phase-badge'>FASES 1 & 2 ATIVAS</div>", unsafe_allow_html=True)

    # Status das Chaves
    gemini_key_env = os.getenv("GEMINI_API_KEY", "").strip()
    eleven_key_env = os.getenv("ELEVENLABS_API_KEY", "").strip()
    tem_youtube_secrets = os.path.exists("client_secrets.json")

    st.markdown("#### Status das Integrações")
    gpu_status = detectar_aceleracao_gpu()
    tem_gpu = gpu_status.get("disponivel", False)
    if tem_gpu:
        st.markdown(f"🟢 **GPU Acelerada:** `{gpu_status['gpu_nome']}`")
        st.caption(f"⚡ Encoder **{gpu_status['encoder']}** ativo (Renderização ultrarrápida)")
    else:
        st.markdown("🟡 **Aceleração GPU:** Modo CPU (`libx264`)")

    if gemini_key_env and "sua_chave" not in gemini_key_env.lower():
        st.markdown("🟢 **Gemini API:** Ativa (Roteiro & Nano Banana)")
    else:
        st.markdown("🟡 **Gemini API:** Mock/Contingência")

    if eleven_key_env and "sua_chave" not in eleven_key_env.lower():
        st.markdown("🟢 **ElevenLabs:** Configurada")
    else:
        st.markdown("🟡 **ElevenLabs:** Voz Local/SAPI")

    if tem_youtube_secrets:
        st.markdown("🟢 **YouTube OAuth:** `client_secrets.json` detectado")
    else:
        st.markdown("🟡 **YouTube OAuth:** Modo Validação/Simulado")

    st.divider()

    # Configurações de IA e Imagens
    st.markdown("#### Parâmetros da Produção")
    provedor_img = st.selectbox(
        "Gerador de Imagens com IA",
        options=["pollinations", "gemini"],
        format_func=lambda x: "⚡ Pollinations AI (Flux - Gratuito & 8K)" if x == "pollinations" else "🍌 Google Gemini (Nano Banana)",
        index=0 if st.session_state.get("provedor_imagem", "pollinations") == "pollinations" else 1,
        disabled=esta_rodando
    )
    if provedor_img != st.session_state.get("provedor_imagem"):
        st.session_state.provedor_imagem = provedor_img
        estado.definir_dados(provedor_imagem=provedor_img)

    estilos_keys = list(ESTILOS_VISUAIS.keys())
    idx_estilo = estilos_keys.index(st.session_state.get("estilo_visual", "dark_cinematic")) if st.session_state.get("estilo_visual") in estilos_keys else 0
    estilo_selecionado = st.selectbox(
        "Estilo Visual das Imagens",
        options=estilos_keys,
        format_func=lambda k: f"{ESTILOS_VISUAIS[k]['emoji']} {ESTILOS_VISUAIS[k]['nome']}",
        index=idx_estilo,
        disabled=esta_rodando
    )
    if estilo_selecionado != st.session_state.get("estilo_visual"):
        st.session_state.estilo_visual = estilo_selecionado
        estado.definir_dados(estilo_visual=estilo_selecionado)

    formato_video = st.selectbox(
        "Formato do Vídeo",
        options=["16:9", "9:16"],
        index=0,
        disabled=esta_rodando,
        help="16:9 (Horizontal / Padrão YouTube) ou 9:16 (Vertical / Shorts & Reels)."
    )

    whisper_model = st.selectbox(
        "Modelo Whisper",
        options=["base", "tiny", "small"],
        index=0,
        disabled=esta_rodando,
        help="'base' oferece alta acurácia para narrações em português."
    )

    modo_sync_rapido = st.checkbox(
        "Sincronização Rápida (Fallback proporcional)",
        value=False,
        disabled=esta_rodando,
        help="Calcula marcações instantaneamente sem rodar o Whisper local."
    )

    st.divider()

    # Aceleração por Hardware (NVENC / GPU)
    st.markdown("#### ⚡ Aceleração por Hardware")
    if tem_gpu:
        modo_encoder = st.selectbox(
            "Motor de Renderização",
            options=["nvenc", "cpu"],
            format_func=lambda x: f"⚡ NVIDIA NVENC ({gpu_status.get('gpu_nome', 'GPU')}) [ATIVADO]" if x == "nvenc" else "🐌 CPU (libx264 - Lento)",
            index=0 if st.session_state.get("modo_encoder", "nvenc") == "nvenc" else 1,
            disabled=esta_rodando,
            help="NVIDIA NVENC utiliza os chips dedicados da sua RTX 3070 Ti para renderizar vídeos 1080p em ~15 a 30 segundos em vez de 25 minutos!"
        )
        st.session_state.modo_encoder = modo_encoder
        forcar_cpu_modo = (modo_encoder == "cpu")
        if not forcar_cpu_modo:
            st.success(f"🟢 **NVENC ATIVADO** | Hardware: `{gpu_status.get('gpu_nome', 'NVIDIA GPU')}`")
        else:
            st.warning("⚠️ Modo CPU selecionado (Renderização por software lenta)")
    else:
        st.selectbox(
            "Motor de Renderização",
            options=["cpu"],
            format_func=lambda x: "🐌 CPU (libx264 - GPU indisponível)",
            index=0,
            disabled=True
        )
        st.session_state.modo_encoder = "cpu"
        forcar_cpu_modo = True
        st.info("ℹ️ Renderização será processada via CPU.")

    # Efeito Flow Motion (Animação estilo Google Flow / Ken Burns)
    flow_motion_ativo = st.toggle(
        "🎬 Flow Motion (Animação de Câmera)",
        value=st.session_state.get("flow_motion_ativo", True),
        disabled=esta_rodando,
        help="Aplica zoom e pan cinematográficos dinâmicos nas imagens estilo Google Flow/Vids. Evita fotos estáticas e turbina a retenção no YouTube e TikTok!"
    )
    if flow_motion_ativo != st.session_state.get("flow_motion_ativo"):
        st.session_state.flow_motion_ativo = flow_motion_ativo
        estado.definir_dados(flow_motion_ativo=flow_motion_ativo)

    # Transições Suaves entre Cenas (Crossfade/Xfade)
    transicao_ativa = st.toggle(
        "✨ Transições Suaves entre Cenas",
        value=st.session_state.get("transicao_ativa", True),
        disabled=esta_rodando,
        help="Aplica transições dissolve/fade entre cenas em vez de cortes secos. Eleva a qualidade cinematográfica do vídeo!"
    )
    st.session_state.transicao_ativa = transicao_ativa
    if transicao_ativa:
        col_tr1, col_tr2 = st.columns([1, 1])
        with col_tr1:
            transicao_duracao = st.slider(
                "Duração (s):",
                min_value=0.3, max_value=1.5, value=0.5, step=0.1,
                disabled=esta_rodando,
                label_visibility="collapsed"
            )
        with col_tr2:
            transicao_tipo = st.selectbox(
                "Tipo:",
                options=["fade", "dissolve", "wipeleft", "slideright", "smoothleft", "circlecrop"],
                index=0,
                disabled=esta_rodando,
                label_visibility="collapsed"
            )
        st.session_state.transicao_duracao = transicao_duracao
        st.session_state.transicao_tipo = transicao_tipo
    else:
        st.session_state.transicao_duracao = 0.0
        st.session_state.transicao_tipo = "fade"

    # Trilha Sonora de Fundo (BGM)
    bgm_ativo = st.toggle(
        "🎵 Trilha Sonora de Fundo (BGM)",
        value=st.session_state.get("bgm_ativo", False),
        disabled=esta_rodando,
        help="Adiciona música de fundo em volume baixo (-18dB) sob a narração. Escolha automática por IA ou manual."
    )
    st.session_state.bgm_ativo = bgm_ativo
    if bgm_ativo:
        bgm_modo = st.selectbox(
            "Trilha BGM:",
            options=["auto", "suspense", "epico", "misterioso", "tecnologico", "calmo", "dramatico", "nenhuma"],
            format_func=lambda x: {
                "auto": "🤖 Automático (IA escolhe)",
                "suspense": "🎭 Suspense Cinematográfico",
                "epico": "⚔️ Épico / Grandioso",
                "misterioso": "🌙 Misterioso / Dark Ambient",
                "tecnologico": "💻 Tecnológico / Futurista",
                "calmo": "🌊 Calmo / Contemplativo",
                "dramatico": "🎬 Dramático / Emotivo",
                "nenhuma": "🔇 Sem trilha"
            }.get(x, x),
            index=0,
            disabled=esta_rodando
        )
        st.session_state.bgm_modo = bgm_modo

    # Thumbnail Automática
    thumbnail_ativa = st.toggle(
        "🖼️ Gerar Thumbnail Automática",
        value=st.session_state.get("thumbnail_ativa", True),
        disabled=esta_rodando,
        help="Gera thumbnail de alta conversão (1280x720) com texto impactante sobre a melhor imagem do roteiro."
    )
    st.session_state.thumbnail_ativa = thumbnail_ativa

    st.divider()

    # Credenciais e Secrets
    with st.expander("🔑 Chaves e Arquivo de Autenticação", expanded=False):
        novo_gemini = st.text_input("Gemini API Key", value=gemini_key_env, type="password")
        novo_eleven = st.text_input("ElevenLabs Secret Key (sk_...)", value=eleven_key_env, type="password")
        
        uploaded_secrets = st.file_uploader("Upload client_secrets.json (YouTube)", type=["json"])
        if uploaded_secrets:
            with open("client_secrets.json", "wb") as f:
                f.write(uploaded_secrets.getvalue())
            st.success("client_secrets.json salvo na raiz!")
            st.rerun()

        if st.button("Salvar Chaves na Sessão"):
            os.environ["GEMINI_API_KEY"] = novo_gemini
            os.environ["ELEVENLABS_API_KEY"] = novo_eleven
            st.success("Chaves salvas!")
            st.rerun()

    st.divider()

    # Reset
    if st.button("🗑️ Novo Vídeo / Limpar Tudo", use_container_width=True):
        estado.resetar_estado()
        st.rerun()


# =====================================================================
# ÁREA PRINCIPAL
# =====================================================================
st.markdown("<div class='main-title'>DarkAI Studio</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-title'>Automação Completa de Canal Dark & Faceless: Roteiro, Voz com IA, Sincronização Precisa, Flow Motion e YouTube</div>", unsafe_allow_html=True)

# Banner de Execução Ativa
if esta_rodando:
    st.markdown(
        """
        <div class='running-banner'>
            ⚡ <b>Execução em segundo plano ativa.</b> O processamento continua mesmo se você recarregar (F5) ou fechar a página.
        </div>
        """,
        unsafe_allow_html=True
    )
elif st.session_state.status == "completed":
    st.success("🎉 **Processo concluído com sucesso!** Veja os resultados nas abas abaixo.")
elif st.session_state.status == "error":
    st.error(f"❌ **Ocorreu um erro:** {st.session_state.erro}")

# Barra de Progresso
prog_col1, prog_col2 = st.columns([4, 1])
with prog_col1:
    st.progress(
        min(max(st.session_state.progresso_valor, 0.0), 1.0),
        text=f"Progresso ({int(st.session_state.progresso_valor * 100)}%): {st.session_state.progresso_texto}"
    )
with prog_col2:
    st.metric(label="Status", value=st.session_state.status.upper())

# =====================================================================
# IDENTIDADE DO CANAL DARK & RADAR DE PAUTAS DO YOUTUBE
# =====================================================================
col_canal, col_radar = st.columns([1, 1])

with col_canal:
    with st.expander("📺 Perfil do Meu Canal Dark (Linha Editorial)", expanded=False):
        st.caption("Defina o perfil do seu canal. Os roteiros e pautas serão personalizados para manter a coerência de tom, vocabulário e identidade de marca.")
        p_canal = st.session_state.perfil_canal
        p_nome = st.text_input("Nome do Canal:", value=p_canal.get("nome_canal", "Meu Canal Dark"), disabled=esta_rodando)
        
        nichos_disponiveis = obter_nichos_dark()
        nomes_nichos = [n["nome"] for n in nichos_disponiveis]
        nicho_idx = 0
        for i, n in enumerate(nichos_disponiveis):
            if n["nome"] == p_canal.get("nicho_principal") or n["id"] == p_canal.get("nicho_principal"):
                nicho_idx = i
                break

        p_nicho = st.selectbox("Nicho Principal:", options=nomes_nichos, index=nicho_idx, disabled=esta_rodando)
        p_tom = st.text_input("Tom Narrativo:", value=p_canal.get("tom_narrativo", "Sombrio, investigativo, sério e imersivo"), disabled=esta_rodando)
        p_persona = st.text_input("Persona do Narrador:", value=p_canal.get("persona_narrador", "Investigador documental de arquivos antigos"), disabled=esta_rodando)

        if st.button("💾 Salvar Perfil do Canal", disabled=esta_rodando, use_container_width=True):
            novo_perfil = {
                "nome_canal": p_nome.strip(),
                "nicho_principal": p_nicho,
                "tom_narrativo": p_tom.strip(),
                "persona_narrador": p_persona.strip()
            }
            banco_dados.salvar_perfil_canal(novo_perfil)
            st.session_state.perfil_canal = novo_perfil
            st.success("✅ Perfil do canal atualizado com sucesso!")
            st.rerun()

with col_radar:
    with st.expander("📡 Radar de Pautas Virais do YouTube", expanded=True):
        st.caption("A IA garimpa temas virais com alto CTR e retenção no YouTube ajustados ao seu canal Sem Rosto (Faceless).")
        col_rad_sel, col_rad_btn = st.columns([2, 1])
        with col_rad_sel:
            opcoes_nicho = ["todos"] + [n["id"] for n in obter_nichos_dark()]
            nomes_map = {"todos": "🌐 Todos os Nichos (Alta Retenção)"}
            for n in obter_nichos_dark():
                nomes_map[n["id"]] = f"{n['emoji']} {n['nome']}"
            nicho_garimpar = st.selectbox(
                "Filtrar Nicho:",
                options=opcoes_nicho,
                format_func=lambda x: nomes_map.get(x, x),
                label_visibility="collapsed",
                disabled=esta_rodando
            )
        with col_rad_btn:
            if st.button("🔥 Buscar Pautas", disabled=esta_rodando, use_container_width=True):
                with st.spinner("Garimpando pautas virais com Gemini..."):
                    st.session_state.pautas_radar = pesquisar_pautas_virais(
                        nicho_id=nicho_garimpar,
                        perfil_canal=st.session_state.perfil_canal
                    )
                st.rerun()

        if st.session_state.pautas_radar:
            st.markdown("---")
            for idx_p, p in enumerate(st.session_state.pautas_radar):
                c_p1, c_p2 = st.columns([4, 1])
                with c_p1:
                    st.markdown(f"**{p.get('tema')}** `🔥 {p.get('ctr_estimado', 'Alto CTR')}`")
                    st.caption(f"🎣 **Hook (5s):** *{p.get('hook_inicial')}*")
                    st.caption(f"🔑 **Clímax:** *{p.get('revelacao_chave')}*")
                with c_p2:
                    st.write("")
                    if st.button("⚡ Usar Pauta", key=f"btn_pauta_{idx_p}", disabled=esta_rodando, use_container_width=True):
                        st.session_state.tema = p.get("tema")
                        estado.definir_dados(tema=p.get("tema"))
                        banco_dados.salvar_pauta_historico(p)
                        st.success("Pauta aplicada ao tema do vídeo!")
                        st.rerun()
                st.divider()
        else:
            st.info("👆 Selecione o nicho e clique em **'🔥 Buscar Pautas'** para obter sugestões do YouTube.")

st.divider()

# Input do Tema e Ação Rápida
st.markdown("### 🎯 Tema do Vídeo & Minutagem Alvo")
col_tema, col_dur, col_act = st.columns([3, 1, 1])

with col_tema:
    novo_tema = st.text_input(
        "Digite o tema ou mistério central:",
        value=st.session_state.tema,
        disabled=esta_rodando,
        placeholder="Ex: Os Segredos Subterrâneos Mais Obscuros da Guerra Fria"
    )
    if novo_tema != st.session_state.tema:
        st.session_state.tema = novo_tema
        estado.definir_dados(tema=novo_tema)

with col_dur:
    nova_duracao = st.slider(
        "Duração Mínima (min):",
        min_value=1.0,
        max_value=15.0,
        value=float(st.session_state.duracao_minima),
        step=0.5,
        disabled=esta_rodando,
        help="Cadência de fala (~140 palavras/minuto). Calibra quantidade de cenas e densidade de texto gerado pelo Gemini."
    )
    if nova_duracao != st.session_state.duracao_minima:
        st.session_state.duracao_minima = nova_duracao
        estado.definir_dados(duracao_minima=nova_duracao)

with col_act:
    st.write("")
    st.write("")
    if esta_rodando:
        st.button("⏳ Processando...", disabled=True, use_container_width=True)
    else:
        if st.button("⚡ Executar Pipeline Completa", type="primary", use_container_width=True):
            if not novo_tema.strip():
                st.error("Informe um tema antes de iniciar.")
            else:
                voz_id_usar = None
                if st.session_state.voz_tipo == "clonada":
                    voz_id_usar = st.session_state.voice_id
                elif st.session_state.voz_tipo == "neural_ptbr":
                    voz_id_usar = st.session_state.get("voice_id", "pt-BR-AntonioNeural")

                audio_prop_usar = st.session_state.audio_path if st.session_state.voz_tipo == "propria" else None
                worker.disparar_pipeline_completa(
                    tema=novo_tema,
                    aspect_ratio=formato_video,
                    whisper_model=whisper_model,
                    modo_rapido=modo_sync_rapido,
                    provedor_imagens=provedor_img,
                    estilo_id=st.session_state.estilo_visual,
                    biblia_visual=st.session_state.biblia_visual,
                    duracao_minima_minutos=nova_duracao,
                    perfil_canal=st.session_state.perfil_canal,
                    voice_id=voz_id_usar,
                    caminho_audio_proprio=audio_prop_usar,
                    forcar_cpu=forcar_cpu_modo,
                    ativar_flow_motion=flow_motion_ativo,
                    transicao_duracao=st.session_state.get("transicao_duracao", 0.5),
                    transicao_tipo=st.session_state.get("transicao_tipo", "fade"),
                    bgm_modo=st.session_state.get("bgm_modo", None) if st.session_state.get("bgm_ativo", False) else None,
                    gerar_thumbnail_auto=st.session_state.get("thumbnail_ativa", True)
                )
                st.rerun()

st.divider()

# =====================================================================
# ABAS SEQUENCIAIS DAS FASES 1 & 2 + HISTÓRICO & MÉTRICAS
# =====================================================================
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "1. 📝 Roteiro",
    "2. 🎙️ Áudio & Clonagem",
    "3. ⏱️ Sincronização",
    "4. 🎨 Imagens com IA",
    "5. 🎬 Vídeo Final",
    "6. 📱 Cortes & Shorts (9:16)",
    "7. 🚀 Publicar YouTube",
    "8. 📊 Histórico & Métricas"
])

# ---------------------------------------------------------------------
# ETAPA 1: ROTEIRO
# ---------------------------------------------------------------------
with tab1:
    st.markdown("#### Etapa 1: Geração e Aprovação do Roteiro")
    st.caption(f"Configuração ativa: Duração mínima de **{st.session_state.duracao_minima:.1f} minutos** (~{int(st.session_state.duracao_minima * 140)} palavras).")
    
    col_btn_rot1, col_btn_rot2 = st.columns([1, 1])
    with col_btn_rot1:
        btn_rot_label = "⏳ Gerando..." if (esta_rodando and st.session_state.etapa_atual == "roteiro") else "🚀 1. Gerar Roteiro Direto (Gemini)"
        if st.button(btn_rot_label, disabled=esta_rodando, use_container_width=True):
            if not st.session_state.tema.strip():
                st.error("Digite um tema primeiro.")
            else:
                worker.disparar_etapa_roteiro(
                    tema=st.session_state.tema,
                    duracao_minima_minutos=st.session_state.duracao_minima,
                    perfil_canal=st.session_state.perfil_canal
                )
                st.rerun()

    with col_btn_rot2:
        if st.button("🧠 Perguntas de Aprofundamento (IA)", disabled=esta_rodando, use_container_width=True):
            if not st.session_state.tema.strip():
                st.error("Digite um tema primeiro.")
            else:
                modal_aprofundar_conteudo(st.session_state.tema, st.session_state.duracao_minima)

    if st.session_state.roteiro:
        roteiro = st.session_state.roteiro
        st.markdown("##### ✏️ Revisão e Edição Manual")
        edit_titulo = st.text_input("Título do Vídeo:", value=roteiro.get("titulo", ""), disabled=esta_rodando)
        edit_descricao = st.text_area("Descrição do Vídeo:", value=roteiro.get("descricao", ""), height=70, disabled=esta_rodando)
        tags_str = ", ".join(roteiro.get("tags", []))
        edit_tags = st.text_input("Tags:", value=tags_str, disabled=esta_rodando)

        st.markdown("##### Cenas Estruturadas")
        cenas = roteiro.get("cenas", [])
        cenas_editadas = []

        for idx, cena in enumerate(cenas):
            with st.expander(f"🎬 Cena {cena.get('cena_id', idx+1)}: {cena.get('narracao', '')[:35]}...", expanded=(idx < 2)):
                col_c1, col_c2 = st.columns([1, 1])
                with col_c1:
                    novo_prompt = st.text_area(
                        f"Prompt Visual (IA) - Cena {idx+1}:",
                        value=cena.get("visual_prompt", ""),
                        height=90,
                        key=f"prompt_{idx}",
                        disabled=esta_rodando
                    )
                with col_c2:
                    nova_narracao = st.text_area(
                        f"Narração - Cena {idx+1}:",
                        value=cena.get("narracao", ""),
                        height=90,
                        key=f"narracao_{idx}",
                        disabled=esta_rodando
                    )
                cenas_editadas.append({
                    "cena_id": cena.get("cena_id", idx + 1),
                    "visual_prompt": novo_prompt,
                    "narracao": nova_narracao
                })

        if not esta_rodando and st.button("💾 Salvar Alterações no Roteiro"):
            roteiro_atualizado = {
                "titulo": edit_titulo,
                "descricao": edit_descricao,
                "tags": [t.strip() for t in edit_tags.split(",") if t.strip()],
                "cenas": cenas_editadas
            }
            estado.definir_dados(roteiro=roteiro_atualizado)
            slug = sanitizar_nome_arquivo(st.session_state.tema)
            with open(f"output/roteiros/{slug}_roteiro.json", "w", encoding="utf-8") as f:
                json.dump(roteiro_atualizado, f, ensure_ascii=False, indent=2)
            st.success("Roteiro salvo com sucesso!")
            st.rerun()
    else:
        st.info("👆 Clique em **'1. Gerar Roteiro (Gemini)'** para iniciar.")


# ---------------------------------------------------------------------
# ETAPA 2: ÁUDIO
# ---------------------------------------------------------------------
with tab2:
    st.markdown("#### Etapa 2: Narração em Áudio (.mp3) & Clonagem de Voz")
    st.warning("⚠️ **Atenção Algorítmica:** O YouTube está desmonetizando e penalizando canais com vozes genéricas de IA. Recomendamos fortemente usar **sua própria voz clonada** ou enviar sua **locução gravada**.")

    if not st.session_state.roteiro:
        st.warning("⚠️ Roteiro pendente. Gere e aprove o roteiro na Etapa 1 primeiro.")
    else:
        modos_disponiveis = ["neural_ptbr", "clonada", "propria", "padrao"]
        idx_modo = 0
        if st.session_state.get("voz_tipo") == "clonada":
            idx_modo = 1
        elif st.session_state.get("voz_tipo") == "propria":
            idx_modo = 2
        elif st.session_state.get("voz_tipo") == "padrao":
            idx_modo = 3

        modo_voz = st.radio(
            "Selecione o método de locução:",
            options=modos_disponiveis,
            index=idx_modo,
            format_func=lambda x: {
                "neural_ptbr": "🇧🇷 1. Voz Neural Brasileira (Antônio - Documentário Dark) [RECOMENDADO]",
                "clonada": "🧬 2. Clonar Minha Voz (ElevenLabs Instant Voice Cloning)",
                "propria": "🗣️ 3. Enviar Minha Locução Gravada (100% Humana - Bypassa TTS)",
                "padrao": "🤖 4. Voz ElevenLabs / Fallback SAPI (Adam)"
            }[x],
            disabled=esta_rodando
        )

        # -------------------------------------------------------------
        # MODO 0: VOZ NEURAL BRASILEIRA (EDGE-TTS PT-BR)
        # -------------------------------------------------------------
        if modo_voz == "neural_ptbr":
            st.markdown("##### 🇧🇷 Voz Neural Brasileira de Estúdio (100% PT-BR)")
            st.caption("Locução ultra-realista em Português do Brasil com entonação sombria, pausada e dramática, perfeita para documentários Dark sem risco de penalização algorítmica por idioma incorreto.")
            
            col_vpt1, col_vpt2 = st.columns([2, 1])
            with col_vpt1:
                vozes_ptbr_opcoes = {
                    "pt-BR-AntonioNeural": "🎙️ Antônio (Voz Masculina Grave - Mistério & Arquivos Secretos)",
                    "pt-BR-FranciscaNeural": "🎙️ Francisca (Voz Feminina Suspense & Investigativa)",
                    "pt-BR-FabioNeural": "🎙️ Fábio (Voz Masculina Firme & Narrativa Documental)",
                    "pt-BR-NicolauNeural": "🎙️ Nicolau (Voz Masculina Clássica)"
                }
                voz_ptbr_sel = st.selectbox(
                    "Voz Narrativa em Português:",
                    options=list(vozes_ptbr_opcoes.keys()),
                    format_func=lambda k: vozes_ptbr_opcoes[k],
                    disabled=esta_rodando
                )
            with col_vpt2:
                st.write("")
                st.write("")
                btn_aud_ptbr = "⏳ Sintetizando..." if (esta_rodando and st.session_state.etapa_atual == "audio") else "🎙️ Gerar Áudio PT-BR Neural"
                if st.button(btn_aud_ptbr, disabled=esta_rodando, type="primary", use_container_width=True):
                    st.session_state.voz_tipo = "neural_ptbr"
                    st.session_state.voice_id = voz_ptbr_sel
                    estado.definir_dados(voz_tipo="neural_ptbr", voice_id=voz_ptbr_sel)
                    worker.disparar_etapa_audio(st.session_state.roteiro, voice_id=voz_ptbr_sel)
                    st.rerun()

        # -------------------------------------------------------------
        # MODO 1: CLONAGEM DE VOZ COM AMOSTRA
        # -------------------------------------------------------------
        elif modo_voz == "clonada":
            st.markdown("##### 🧬 Clonagem Instantânea de Voz com IA")
            st.caption("Envie uma amostra de áudio (1 a 3 minutos) de você falando com tom calmo, pausado e misterioso.")

            col_amostra1, col_amostra2 = st.columns([2, 1])
            with col_amostra1:
                amostra_arquivo = st.file_uploader(
                    "Selecione a amostra da sua voz (.mp3 ou .wav):",
                    type=["mp3", "wav"],
                    key="uploader_amostra_voz"
                )
                nome_voz_input = st.text_input("Nome da sua voz clonada:", value="Minha Voz Canal Dark", key="nome_voz_clonada")

            with col_amostra2:
                st.write("")
                st.write("")
                if st.button("🧬 Clonar Minha Voz (ElevenLabs)", disabled=(amostra_arquivo is None or esta_rodando), use_container_width=True):
                    try:
                        os.makedirs("temp", exist_ok=True)
                        caminho_amostra_temp = os.path.join("temp", amostra_arquivo.name)
                        with open(caminho_amostra_temp, "wb") as f:
                            f.write(amostra_arquivo.getvalue())

                        with st.spinner("Enviando amostra e clonando voz na ElevenLabs..."):
                            novo_voice_id = clonar_voz_elevenlabs(caminho_amostra_temp, nome_voz=nome_voz_input)
                            st.session_state.voice_id = novo_voice_id
                            st.session_state.voz_tipo = "clonada"
                            estado.definir_dados(voice_id=novo_voice_id, voz_tipo="clonada")
                            st.success(f"🎉 Voz clonada com sucesso! ID: `{novo_voice_id}`")
                    except Exception as err:
                        st.error(f"Erro na clonagem: {err}")

            voice_id_atual = st.session_state.get("voice_id") or os.getenv("ELEVENLABS_VOICE_ID", "")
            if voice_id_atual:
                st.success(f"✅ **Voz Clonada Pronta para Uso:** `{voice_id_atual}`")
                btn_aud_label = "⏳ Sintetizando..." if (esta_rodando and st.session_state.etapa_atual == "audio") else "🎙️ Gerar Áudio com Minha Voz Clonada"
                if st.button(btn_aud_label, disabled=esta_rodando, type="primary"):
                    st.session_state.voz_tipo = "clonada"
                    estado.definir_dados(voz_tipo="clonada", voice_id=voice_id_atual)
                    worker.disparar_etapa_audio(st.session_state.roteiro, voice_id=voice_id_atual)
                    st.rerun()
            else:
                st.info("Suba sua amostra de áudio acima para gerar o ID da sua voz clonada.")

        # -------------------------------------------------------------
        # MODO 2: LOCUÇÃO HUMANA COMPLETA
        # -------------------------------------------------------------
        elif modo_voz == "propria":
            st.markdown("##### 🗣️ Locução Própria Completa (100% Humana)")
            st.caption("Grave a leitura completa do roteiro da Etapa 1 no seu microfone e envie o arquivo aqui.")

            up_narracao_propria = st.file_uploader(
                "Upload da narração gravada (.mp3 ou .wav):",
                type=["mp3", "wav"],
                key="uploader_audio_proprio"
            )

            if up_narracao_propria:
                slug = sanitizar_nome_arquivo(st.session_state.tema)
                ext = os.path.splitext(up_narracao_propria.name)[1].lower()
                caminho_narracao_salva = os.path.join("output", "audios", f"{slug}_proprio{ext}")
                os.makedirs("output/audios", exist_ok=True)
                with open(caminho_narracao_salva, "wb") as f:
                    f.write(up_narracao_propria.getvalue())

                st.session_state.audio_path = caminho_narracao_salva
                st.session_state.voz_tipo = "propria"
                estado.definir_dados(audio_path=caminho_narracao_salva, voz_tipo="propria")
                st.success(f"✅ Gravação própria salva: `{caminho_narracao_salva}`! Avance diretamente para a **Etapa 3: Sincronização**.")

        # -------------------------------------------------------------
        # MODO 3: VOZ PADRÃO
        # -------------------------------------------------------------
        else:
            st.markdown("##### 🤖 Voz Padrão IA Dark (Adam / SAPI)")
            st.caption("Utiliza a voz padrão misteriosa configurada na ElevenLabs ou o sintetizador nativo de contingência.")
            btn_aud_label = "⏳ Sintetizando..." if (esta_rodando and st.session_state.etapa_atual == "audio") else "🎙️ Gerar Áudio com Voz Padrão"
            if st.button(btn_aud_label, disabled=esta_rodando, type="primary"):
                st.session_state.voz_tipo = "padrao"
                estado.definir_dados(voz_tipo="padrao")
                worker.disparar_etapa_audio(st.session_state.roteiro)
                st.rerun()

        # Player se áudio existir
        if st.session_state.audio_path and os.path.exists(st.session_state.audio_path):
            st.markdown("---")
            st.markdown("##### 🎧 Player do Áudio Gerado")
            st.audio(st.session_state.audio_path)
            st.caption(f"Arquivo: `{st.session_state.audio_path}` | Modalidade: `{st.session_state.get('voz_tipo', 'padrao').upper()}`")


# ---------------------------------------------------------------------
# ETAPA 3: SINCRONIZAÇÃO
# ---------------------------------------------------------------------
with tab3:
    st.markdown("#### Etapa 3: Sincronização e Timestamps (Whisper)")
    if not st.session_state.audio_path or not os.path.exists(st.session_state.audio_path):
        st.warning("⚠️ Áudio pendente.")
    else:
        col_btn_sync, col_info_sync = st.columns([1, 2])
        with col_btn_sync:
            btn_sync_label = "⏳ Sincronizando..." if (esta_rodando and st.session_state.etapa_atual == "sync") else "⏱️ 3. Sincronizar com Whisper"
            if st.button(btn_sync_label, disabled=esta_rodando, use_container_width=True):
                worker.disparar_etapa_sync(
                    audio_path=st.session_state.audio_path,
                    roteiro=st.session_state.roteiro,
                    whisper_model=whisper_model,
                    modo_rapido=modo_sync_rapido
                )
                st.rerun()

        if st.session_state.sync_dados:
            sync = st.session_state.sync_dados
            st.markdown(f"**Duração:** `{sync.get('duracao_total', 0.0):.2f}s` | **Método:** `{sync.get('_metodo', 'Whisper')}`")
            legendas = sync.get("legendas_timestamps", [])
            st.dataframe(
                [{"Início (s)": l["start"], "Fim (s)": l["end"], "Texto": l["text"]} for l in legendas],
                use_container_width=True,
                height=220
            )


# ---------------------------------------------------------------------
# ETAPA 4: IMAGENS COM IA (FASE 2)
# ---------------------------------------------------------------------
with tab4:
    st.markdown("#### Etapa 4: Geração de Imagens com IA, Estilos Visuais & Storytelling")
    
    if not st.session_state.roteiro:
        st.warning("⚠️ Roteiro pendente. Gere ou aprove o roteiro na Aba 1 antes de gerar imagens.")
    else:
        # Controles Visuais Principais
        col_estilo, col_prov, col_ratio = st.columns([2, 2, 1])
        with col_estilo:
            chaves_estilos = list(ESTILOS_VISUAIS.keys())
            idx_estilo_tab = chaves_estilos.index(st.session_state.estilo_visual) if st.session_state.estilo_visual in chaves_estilos else 0
            estilo_ativo = st.selectbox(
                "🎨 Estilo Visual das Cenas:",
                options=chaves_estilos,
                format_func=lambda k: f"{ESTILOS_VISUAIS[k]['emoji']} {ESTILOS_VISUAIS[k]['nome']}",
                index=idx_estilo_tab,
                disabled=esta_rodando,
                key="tab4_select_estilo"
            )
            if estilo_ativo != st.session_state.estilo_visual:
                st.session_state.estilo_visual = estilo_ativo
                estado.definir_dados(estilo_visual=estilo_ativo)

        with col_prov:
            prov_ativo = st.selectbox(
                "⚡ Provedor de Imagem:",
                options=["pollinations", "gemini"],
                format_func=lambda x: "⚡ Pollinations AI (Flux - Gratuito & 8K)" if x == "pollinations" else "🍌 Google Gemini (Nano Banana)",
                index=0 if st.session_state.provedor_imagem == "pollinations" else 1,
                disabled=esta_rodando,
                key="tab4_select_prov"
            )
            if prov_ativo != st.session_state.provedor_imagem:
                st.session_state.provedor_imagem = prov_ativo
                estado.definir_dados(provedor_imagem=prov_ativo)

        with col_ratio:
            ratio_ativo = st.selectbox(
                "📐 Proporção:",
                options=["16:9", "9:16"],
                index=0 if st.session_state.get("aspect_ratio_imagem", "16:9") == "16:9" else 1,
                disabled=esta_rodando,
                key="tab4_select_ratio"
            )
            if ratio_ativo != st.session_state.get("aspect_ratio_imagem"):
                st.session_state.aspect_ratio_imagem = ratio_ativo
                estado.definir_dados(aspect_ratio_imagem=ratio_ativo)

        # Descrição do Estilo Selecionado
        desc_estilo = ESTILOS_VISUAIS[estilo_ativo]["descricao"]
        st.info(f"💡 **Estilo Ativo ({ESTILOS_VISUAIS[estilo_ativo]['nome']}):** {desc_estilo}")

        # Seção de Storytelling & Bíblia Visual
        with st.expander("👤 Bíblia Visual do Roteiro (Personagens & Cenários para Storytelling)", expanded=True):
            st.caption("A IA mantém a aparência exata dos personagens e dos cenários idêntica entre as diferentes cenas.")
            
            c_bib_btn, c_bib_status = st.columns([1, 2])
            with c_bib_btn:
                if st.button("🔍 Extrair / Atualizar Bíblia com IA", disabled=esta_rodando, use_container_width=True):
                    with st.spinner("Analisando roteiro e personagens com Gemini..."):
                        nova_biblia = extrair_biblia_visual(st.session_state.roteiro)
                        st.session_state.biblia_visual = nova_biblia
                        estado.definir_dados(biblia_visual=nova_biblia)
                        st.success("Bíblia Visual atualizada!")
                        st.rerun()

            biblia = st.session_state.biblia_visual
            if biblia:
                col_p, col_e = st.columns(2)
                with col_p:
                    st.markdown("**👤 Personagens Identificados:**")
                    for idx_p, p in enumerate(biblia.get("personagens", [])):
                        cenas_p_str = ", ".join(map(str, p.get("cenas_recorrentes", [])))
                        st.markdown(f"- **{p.get('nome')}** (Cenas: `{cenas_p_str or 'Todas'}`)")
                        st.caption(f"_{p.get('descricao_visual_fixa')}_")

                with col_e:
                    st.markdown("**🏛️ Cenários / Entorno Identificados:**")
                    for idx_e, e in enumerate(biblia.get("entornos", [])):
                        cenas_e_str = ", ".join(map(str, e.get("cenas_recorrentes", [])))
                        st.markdown(f"- **{e.get('nome')}** (Cenas: `{cenas_e_str or 'Todas'}`)")
                        st.caption(f"_{e.get('descricao_visual_fixa')}_")
            else:
                st.caption("Nenhuma bíblia extraída ainda. Clique em 'Extrair / Atualizar Bíblia' ou gere as imagens diretamente (a IA extrairá automaticamente).")

        # Botão de Geração em Massa
        st.markdown("---")
        col_btn_img, col_info_img = st.columns([1, 2])
        with col_btn_img:
            btn_img_label = "⏳ Gerando Imagens..." if (esta_rodando and st.session_state.etapa_atual == "imagens") else "🎨 4. Gerar Todas as Imagens com IA"
            if st.button(btn_img_label, disabled=esta_rodando, type="primary", use_container_width=True):
                worker.disparar_etapa_imagens(
                    roteiro=st.session_state.roteiro,
                    aspect_ratio=ratio_ativo,
                    provedor=prov_ativo,
                    estilo_id=estilo_ativo,
                    biblia_visual=st.session_state.biblia_visual
                )
                st.rerun()

        with col_info_img:
            qtd_cenas_tot = len(st.session_state.roteiro.get("cenas", []))
            st.caption(f"Gera {qtd_cenas_tot} imagens em alta resolução combinando o estilo **{ESTILOS_VISUAIS[estilo_ativo]['nome']}** com as fichas da Bíblia Visual.")

        imagens_cenas = st.session_state.imagens_cenas or {}
        cenas = st.session_state.roteiro.get("cenas", [])

        if imagens_cenas:
            st.markdown("##### 🖼️ Galeria de Imagens Geradas por Cena")
            grid_cols = st.columns(2)

            for idx, cena in enumerate(cenas):
                cena_id = cena.get("cena_id", idx + 1)
                img_path = imagens_cenas.get(cena_id) or imagens_cenas.get(str(cena_id))
                col_atual = grid_cols[idx % 2]

                with col_atual:
                    with st.container():
                        st.markdown(f"**Cena {cena_id}:** {cena.get('narracao', '')[:60]}...")
                        if img_path and os.path.exists(img_path):
                            st.image(img_path, use_container_width=True)
                        else:
                            st.info(f"Nenhuma imagem gerada ainda para a Cena {cena_id}.")

                        # Regeneração individual ou upload customizado
                        with st.expander(f"⚙️ Ajustar Imagem da Cena {cena_id}"):
                            custom_prompt = st.text_area(f"Prompt Visual:", value=cena.get("visual_prompt", ""), height=70, key=f"custom_p_{cena_id}")
                            
                            c_sub1, c_sub2 = st.columns(2)
                            with c_sub1:
                                if st.button(f"🔄 Regenerar Cena {cena_id}", key=f"regen_{cena_id}", disabled=esta_rodando):
                                    slug = sanitizar_nome_arquivo(st.session_state.tema)
                                    novo_caminho = gerar_imagem_cena_individual(
                                        prompt=custom_prompt,
                                        cena_id=cena_id,
                                        slug=slug,
                                        aspect_ratio=ratio_ativo,
                                        estilo_id=estilo_ativo,
                                        biblia_visual=st.session_state.biblia_visual,
                                        narracao=cena.get("narracao", ""),
                                        provedor_preferido=prov_ativo
                                    )
                                    imagens_cenas[cena_id] = novo_caminho
                                    estado.definir_dados(imagens_cenas=imagens_cenas)
                                    st.success("Imagem regenerada!")
                                    st.rerun()

                            with c_sub2:
                                upload_sub = st.file_uploader(f"Subir foto manual:", type=["jpg", "png", "webp"], key=f"up_{cena_id}")
                                if upload_sub:
                                    slug = sanitizar_nome_arquivo(st.session_state.tema)
                                    caminho_custom = f"output/imagens/{slug}_cena_{cena_id}.jpg"
                                    with open(caminho_custom, "wb") as f:
                                        f.write(upload_sub.getvalue())
                                    imagens_cenas[cena_id] = caminho_custom
                                    estado.definir_dados(imagens_cenas=imagens_cenas)
                                    st.success("Foto atualizada!")
                                    st.rerun()


# ---------------------------------------------------------------------
# ETAPA 5: VÍDEO FINAL
# ---------------------------------------------------------------------
with tab5:
    st.markdown("#### Etapa 5: Renderização do Vídeo Final com Imagens e Legendas")
    
    if not st.session_state.sync_dados or not st.session_state.audio_path:
        st.warning("⚠️ Áudio e sincronização pendentes.")
    else:
        col_btn_vid, col_info_vid = st.columns([1, 2])
        with col_btn_vid:
            btn_vid_label = "⏳ Renderizando Vídeo..." if (esta_rodando and st.session_state.etapa_atual == "video") else "🎬 5. Renderizar Vídeo Final MP4"
            if st.button(btn_vid_label, disabled=esta_rodando, type="primary", use_container_width=True):
                worker.disparar_etapa_video(
                    audio_path=st.session_state.audio_path,
                    sync_dados=st.session_state.sync_dados,
                    roteiro=st.session_state.roteiro,
                    aspect_ratio=formato_video,
                    imagens_cenas=st.session_state.imagens_cenas,
                    forcar_cpu=forcar_cpu_modo,
                    ativar_flow_motion=flow_motion_ativo,
                    transicao_duracao=st.session_state.get("transicao_duracao", 0.5),
                    transicao_tipo=st.session_state.get("transicao_tipo", "fade")
                )
                st.rerun()

        with col_info_vid:
            if not forcar_cpu_modo and tem_gpu:
                st.success(f"🟢 **NVENC ATIVADO** | Hardware: `{gpu_status.get('gpu_nome', 'NVIDIA RTX')}` (Renderização ultrarrápida: ~15 a 30 segundos)")
            else:
                st.info("🐌 **Modo CPU (libx264)** | Renderização por software (~10 a 25 minutos)")

            if flow_motion_ativo:
                st.info("🎬 **Flow Motion ATIVADO:** Animações dinâmicas de câmera (Zoom In/Out, Pan L/R, Tilt U/D estilo Google Flow) serão aplicadas em cada cena.")
            else:
                st.caption("📷 **Flow Motion Desativado:** Cenas renderizadas com imagens estáticas.")

        if st.session_state.video_path and os.path.exists(st.session_state.video_path):
            st.markdown("##### 📺 Prévia do Vídeo Final Renderizado")
            st.video(st.session_state.video_path)

            tam_mb = os.path.getsize(st.session_state.video_path) / (1024 * 1024)
            st.markdown(f"**Arquivo:** `{st.session_state.video_path}` ({tam_mb:.2f} MB)")

            with open(st.session_state.video_path, "rb") as vf:
                st.download_button(
                    label="⬇️ Baixar Vídeo MP4",
                    data=vf,
                    file_name=os.path.basename(st.session_state.video_path),
                    mime="video/mp4",
                    use_container_width=True
                )

            # Thumbnail Automática
            caminho_thumb = st.session_state.get("caminho_thumbnail", "")
            if caminho_thumb and os.path.exists(caminho_thumb):
                st.markdown("##### 🖼️ Thumbnail Gerada Automaticamente")
                st.image(caminho_thumb, caption="Thumbnail para YouTube (1280x720)", use_container_width=True)
                with open(caminho_thumb, "rb") as tf:
                    st.download_button(
                        label="⬇️ Baixar Thumbnail JPG",
                        data=tf,
                        file_name=os.path.basename(caminho_thumb),
                        mime="image/jpeg"
                    )

# ---------------------------------------------------------------------
# ETAPA 6: CORTES & SHORTS VERTICAIS (9:16)
# ---------------------------------------------------------------------
with tab6:
    st.markdown("#### Etapa 6: Geração Inteligente de Cortes Verticais (9:16) para Shorts, TikTok e Reels")
    st.caption("Aproveite o vídeo longo já produzido para gerar de 1 a 3 vídeos curtos de alta retenção com reenquadramento vertical Ambient Blur.")

    if not st.session_state.video_path or not os.path.exists(st.session_state.video_path):
        st.warning("⚠️ Vídeo longo pendente. Conclua a Etapa 5 primeiro para desbloquear a análise de Shorts.")
    else:
        col_sh1, col_sh2 = st.columns([2, 1])
        with col_sh1:
            qtd_cortes_sel = st.slider(
                "Quantidade de Shorts verticais a extrair:",
                min_value=1,
                max_value=3,
                value=2,
                disabled=esta_rodando,
                help="O Gemini analisa as cenas mais magnéticas com duração ideal entre 30 e 58 segundos."
            )
        with col_sh2:
            st.write("")
            st.write("")
            btn_sh_label = "⏳ Analisando & Gerando Shorts..." if (esta_rodando and st.session_state.etapa_atual == "shorts") else "⚡ Gerar Cortes Verticais com IA"
            if st.button(btn_sh_label, disabled=esta_rodando, type="primary", use_container_width=True):
                worker.disparar_etapa_shorts(
                    audio_path=st.session_state.audio_path,
                    sync_dados=st.session_state.sync_dados,
                    roteiro=st.session_state.roteiro,
                    imagens_cenas=st.session_state.imagens_cenas,
                    max_cortes=qtd_cortes_sel,
                    forcar_cpu=forcar_cpu_modo
                )
                st.rerun()

        # Exibição dos Shorts gerados
        shorts = st.session_state.shorts_gerados or []
        if shorts:
            st.markdown("---")
            st.markdown(f"##### 📱 Galeria de Shorts Verticais Gerados ({len(shorts)} vídeos)")
            grid_shorts = st.columns(len(shorts))

            for idx, item in enumerate(shorts):
                col_short = grid_shorts[idx]
                with col_short:
                    st.markdown(f"**Corte #{item.get('corte_id', idx+1)}: {item.get('titulo_short')}**")
                    st.caption(f"⏱️ Duração: **{item.get('duracao', 0.0):.1f}s** | [{item.get('tempo_inicio', 0.0):.1f}s - {item.get('tempo_fim', 0.0):.1f}s]")

                    vpath = item.get("caminho_video")
                    if vpath and os.path.exists(vpath):
                        st.video(vpath)
                        with open(vpath, "rb") as sf:
                            st.download_button(
                                label=f"⬇️ Baixar Short #{idx+1} (MP4)",
                                data=sf,
                                file_name=os.path.basename(vpath),
                                mime="video/mp4",
                                key=f"dl_short_{idx}",
                                use_container_width=True
                            )
                    else:
                        st.info("Arquivo de vídeo do Short não localizado.")

                    st.info(f"💡 **Gancho Estratégico:** {item.get('gancho_explicacao', 'Momento de alta retenção')}")
        else:
            st.info("👆 Clique em **'⚡ Gerar Cortes Verticais com IA'** para que a IA analise o roteiro e recorte os melhores momentos em 9:16.")


# ---------------------------------------------------------------------
# ETAPA 7: PUBLICAR NO YOUTUBE (FASE 2)
# ---------------------------------------------------------------------
with tab7:
    st.markdown("#### Etapa 7: Publicação Automatizada no YouTube (YouTube Data API v3)")

    if not st.session_state.video_path or not os.path.exists(st.session_state.video_path):
        st.warning("⚠️ Vídeo pendente. Renderize o vídeo na Etapa 5 antes de publicar.")
    else:
        st.markdown("##### ⚙️ Parâmetros de Envio")
        col_yt1, col_yt2 = st.columns([2, 1])

        with col_yt1:
            privacidade_sel = st.selectbox(
                "Status de Privacidade",
                options=["unlisted", "private", "public"],
                format_func=lambda x: "Não-listado (Recomendado para conferência)" if x == "unlisted" else ("Privado" if x == "private" else "Público (Visível para todos)"),
                index=0,
                disabled=esta_rodando
            )
            usar_simulacao = st.checkbox(
                "Modo Simulação / Validação (Sem OAuth)",
                value=(not os.path.exists("client_secrets.json")),
                help="Se marcado, valida os metadados do YouTube sem disparar a requisição de upload real."
            )

        with col_yt2:
            st.write("")
            st.write("")
            btn_yt_label = "⏳ Publicando..." if (esta_rodando and st.session_state.etapa_atual == "youtube") else "🚀 Publicar no YouTube"
            if st.button(btn_yt_label, disabled=esta_rodando, type="primary", use_container_width=True):
                # Thumbnail: usa imagem da cena 1 se disponível
                thumb_path = None
                if st.session_state.imagens_cenas:
                    thumb_path = st.session_state.imagens_cenas.get(1) or st.session_state.imagens_cenas.get("1")

                worker.disparar_etapa_youtube(
                    video_path=st.session_state.video_path,
                    roteiro=st.session_state.roteiro,
                    privacidade=privacidade_sel,
                    caminho_thumbnail=thumb_path,
                    forcar_simulacao=usar_simulacao
                )
                st.rerun()

        # Exibição do Resultado do Upload
        if st.session_state.youtube_dados:
            yt_res = st.session_state.youtube_dados
            st.markdown("---")
            if yt_res.get("sucesso"):
                st.success(f"🎉 **Vídeo publicado com sucesso!**")
                st.markdown(f"🔗 **Link:** [{yt_res.get('video_url')}]({yt_res.get('video_url')})")
                st.markdown(f"**Privacidade:** `{yt_res.get('privacidade')}` | **Modo:** `{yt_res.get('modo')}`")

                if "aviso" in yt_res:
                    st.info(yt_res["aviso"])
            else:
                st.error(f"Falha na publicação: {yt_res.get('erro_detalhado')}")


# ---------------------------------------------------------------------
# ETAPA 8: HISTÓRICO & MÉTRICAS (SQLITE)
# ---------------------------------------------------------------------
with tab8:
    st.markdown("#### 📊 Histórico de Produção & Métricas do Canal")
    metricas = banco_dados.obter_metricas_gerais()

    # Cards de Métricas
    col_m1, col_m2, col_m3, col_m4, col_m5, col_m6 = st.columns(6)
    col_m1.metric("Vídeos Criados", f"{metricas['total_videos']}")
    col_m2.metric("Minutos Totais", f"{metricas['total_minutos']} min")
    col_m3.metric("Horas de Conteúdo", f"{metricas['total_horas']} h")
    col_m4.metric("Espaço em Disco", f"{metricas['total_tamanho_mb']} MB")
    col_m5.metric("No YouTube", f"{metricas['total_youtube']}")
    col_m6.metric("Shorts (9:16)", f"{metricas['total_shorts']}")

    st.divider()

    # Busca no Histórico
    col_busca, col_refresh = st.columns([4, 1])
    with col_busca:
        busca_termo = st.text_input("🔍 Buscar no histórico:", placeholder="Filtrar por tema, título ou tags...")
    with col_refresh:
        st.write("")
        st.write("")
        if st.button("🔄 Atualizar Lista", use_container_width=True):
            st.rerun()

    historico = banco_dados.listar_historico(limite=100, busca=busca_termo)

    if not historico:
        st.info("Nenhum vídeo registrado no banco SQLite ainda. Conclua uma renderização para salvar o primeiro histórico.")
    else:
        # Tabela formatada
        tabela_dados = []
        for reg in historico:
            tabela_dados.append({
                "ID": reg["id"],
                "Título": reg["titulo"],
                "Duração": f"{reg['duracao_segundos']:.1f}s",
                "Formato": reg["aspect_ratio"],
                "Voz": reg["voz_tipo"],
                "Cenas": reg["qtd_cenas"],
                "Tamanho": f"{reg['tamanho_mb']:.1f} MB",
                "YouTube": "✅ Publicado" if reg["youtube_url"] else "—",
                "Data": reg["criado_em"]
            })
        st.dataframe(tabela_dados, use_container_width=True, height=220)

        st.markdown("##### 🎬 Replay e Detalhes do Vídeo Selecionado")
        opcoes_map = {f"#{r['id']} - {r['titulo']} ({r['criado_em'][:10]})": r for r in historico}
        video_selecionado_label = st.selectbox(
            "Selecione um vídeo histórico:",
            options=list(opcoes_map.keys())
        )

        if video_selecionado_label:
            v_sel = opcoes_map[video_selecionado_label]
            v_col1, v_col2 = st.columns([3, 2])

            with v_col1:
                v_path = v_sel.get("caminho_video")
                if v_path and os.path.exists(v_path):
                    st.video(v_path)
                else:
                    st.info(f"Arquivo MP4 não localizado em: `{v_path}`")

                a_path = v_sel.get("caminho_audio")
                if a_path and os.path.exists(a_path):
                    st.audio(a_path)

            with v_col2:
                st.markdown(f"**Tema:** {v_sel.get('tema')}")
                st.markdown(f"**Descrição:**\n{v_sel.get('descricao')}")
                st.markdown(f"**Tags:** `{v_sel.get('tags')}`")
                st.markdown(f"**Tipo de Voz:** `{v_sel.get('voz_tipo')}` | **Voice ID:** `{v_sel.get('voice_id') or 'N/A'}`")
                
                yt_link = v_sel.get("youtube_url")
                if yt_link:
                    st.markdown(f"🔗 **YouTube:** [{yt_link}]({yt_link}) (Status: `{v_sel.get('youtube_status')}`)")

                st.write("")
                if st.button(f"🗑️ Excluir Registro #{v_sel['id']}", type="secondary"):
                    banco_dados.excluir_registro(v_sel["id"])
                    st.success("Registro removido do banco de dados!")
                    st.rerun()

        st.divider()
        st.markdown("##### 📋 Pautas Planejadas no Radar do YouTube")
        pautas_hist = banco_dados.listar_pautas_historico(limite=20)
        if pautas_hist:
            tabela_pautas = []
            for ph in pautas_hist:
                tabela_pautas.append({
                    "ID": ph["id"],
                    "Tema": ph["tema"],
                    "Nicho": ph["nicho_id"],
                    "Hook (5s)": ph["hook_inicial"][:50] + "..." if len(ph.get("hook_inicial", "")) > 50 else ph.get("hook_inicial", ""),
                    "Status": ph["status"],
                    "Data": ph["criado_em"]
                })
            st.dataframe(tabela_pautas, use_container_width=True)
        else:
            st.caption("Nenhuma pauta do radar salva ainda. Clique em '⚡ Usar Pauta' no Radar para adicionar novas ideias ao histórico.")


# =====================================================================
# TERMINAL DE LOGS PERSISTENTES
# =====================================================================
st.divider()
with st.expander("📜 Logs de Execução em Tempo Real (Persistidos)", expanded=esta_rodando):
    if st.session_state.logs:
        logs_formatados = "\n".join(st.session_state.logs)
        st.code(logs_formatados, language="bash")
    else:
        st.caption("Nenhum evento registrado até o momento.")


# =====================================================================
# AUTO-REFRESH REATIVO QUANDO HOUVER PROCESSO ATIVO
# =====================================================================
if esta_rodando:
    time.sleep(1.0)
    st.rerun()
