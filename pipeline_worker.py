"""
Módulo pipeline_worker.py
Executa as tarefas pesadas da pipeline em background threads desacopladas do ciclo de renderização do Streamlit.
Orquestra Roteiro (Gemini) -> Áudio (ElevenLabs) -> BGM (Mixagem) -> Sincronização (Whisper) -> Imagens IA (Pollinations/Gemini) -> Vídeo (MoviePy) -> Thumbnail -> Upload (YouTube).
"""

import os
import threading
import traceback
from typing import Optional, Dict, Any

import gerenciador_estado as estado
import banco_dados
from gerador_roteiro import gerar_roteiro
from gerador_audio import gerar_audio
from sincronizador import sincronizar_audio
from gerador_imagens import gerar_imagens_para_roteiro
from editor_video import renderizar_video_moviepy
from uploader_youtube import upload_video_youtube
from mixer_audio import mixar_audio_com_bgm, selecionar_trilha_automatica
from gerador_thumbnail import gerar_texto_thumbnail, gerar_thumbnail

_thread_ativa: Optional[threading.Thread] = None
_thread_lock = threading.Lock()


def _thread_esta_viva() -> bool:
    global _thread_ativa
    return _thread_ativa is not None and _thread_ativa.is_alive()


def iniciar_tarefa_background(alvo, args=(), kwargs=None):
    """Inicia uma função em background thread se não houver outra ativa."""
    global _thread_ativa
    if kwargs is None:
        kwargs = {}

    with _thread_lock:
        if _thread_esta_viva():
            _thread_ativa.join(timeout=2.0)
            if _thread_esta_viva():
                print("[pipeline_worker] Aviso: Tarefa já em andamento. Ignorando nova solicitação.")
                return False

        _thread_ativa = threading.Thread(target=alvo, args=args, kwargs=kwargs, daemon=True)
        _thread_ativa.start()
        return True


def _worker_pipeline_completa(
    tema: str,
    aspect_ratio: str = "16:9",
    whisper_model: str = "base",
    modo_rapido: bool = False,
    provedor_imagens: str = "pollinations",
    estilo_id: str = "dark_cinematic",
    biblia_visual: Optional[Dict[str, Any]] = None,
    duracao_minima_minutos: float = 2.0,
    respostas_usuario: Optional[Dict[str, str]] = None,
    perfil_canal: Optional[Dict[str, Any]] = None,
    voice_id: Optional[str] = None,
    caminho_audio_proprio: Optional[str] = None,
    forcar_cpu: bool = False,
    ativar_flow_motion: bool = True,
    transicao_duracao: float = 0.5,
    transicao_tipo: str = 'fade',
    bgm_modo: Optional[str] = None,
    bgm_volume_db: float = -18.0,
    gerar_thumbnail_auto: bool = True
):
    """Executa todas as etapas sequenciais das Fases 1 & 2 em background."""
    try:
        if not perfil_canal:
            perfil_canal = banco_dados.obter_perfil_canal()

        estado.definir_status("running", etapa="completo")
        estado.definir_dados(tema=tema, estilo_visual=estilo_id, biblia_visual=biblia_visual)
        estado.adicionar_log(f"Iniciando pipeline completa para o tema: '{tema}' (Estilo: {estilo_id}, Duração mínima: {duracao_minima_minutos:.1f} min)")

        # 1. ROTEIRO
        estado.atualizar_progresso(0.08, f"Gerando roteiro ({duracao_minima_minutos:.1f}m) com IA para: '{tema}'...", etapa="roteiro")
        roteiro = gerar_roteiro(
            tema=tema,
            duracao_minima_minutos=duracao_minima_minutos,
            respostas_usuario=respostas_usuario,
            perfil_canal=perfil_canal
        )
        qtd_cenas = len(roteiro.get("cenas", []))
        estado.definir_dados(roteiro=roteiro)
        estado.atualizar_progresso(0.18, f"Roteiro gerado ({qtd_cenas} cenas estruturadas).")

        # 2. ÁUDIO
        msg_audio = "Usando áudio próprio do usuário..." if caminho_audio_proprio else "Sintetizando narração em áudio MP3..."
        estado.atualizar_progresso(0.22, msg_audio, etapa="audio")
        audio_path = gerar_audio(
            roteiro_dados=roteiro,
            voice_id=voice_id,
            caminho_audio_proprio=caminho_audio_proprio
        )
        estado.definir_dados(audio_path=audio_path)
        estado.atualizar_progresso(0.35, f"Áudio pronto: {audio_path}")

        # 2.5 MIXAGEM BGM (se ativado)
        audio_final = audio_path
        if bgm_modo and bgm_modo not in ("nenhuma", None, ""):
            try:
                estado.atualizar_progresso(0.37, "🎵 Selecionando e mixando trilha de fundo (BGM)...", etapa="audio")
                if bgm_modo == "auto":
                    nicho = (perfil_canal or {}).get("nicho", "")
                    caminho_bgm = selecionar_trilha_automatica(tema=tema, nicho=nicho)
                else:
                    # Busca trilha pelo nome do modo
                    from mixer_audio import listar_trilhas_disponiveis
                    trilhas = listar_trilhas_disponiveis()
                    caminho_bgm = None
                    for t in trilhas:
                        if bgm_modo.lower() in t["id"].lower():
                            caminho_bgm = t["arquivo"]
                            break
                    if not caminho_bgm and trilhas:
                        caminho_bgm = trilhas[0]["arquivo"]

                if caminho_bgm and os.path.exists(caminho_bgm):
                    saida_mix = audio_path.replace(".mp3", "_bgm.mp3")
                    audio_final = mixar_audio_com_bgm(
                        caminho_narracao=audio_path,
                        caminho_bgm=caminho_bgm,
                        caminho_saida=saida_mix,
                        volume_bgm_db=bgm_volume_db
                    )
                    estado.definir_dados(audio_path=audio_final)
                    estado.adicionar_log(f"🎵 BGM mixado com sucesso: {os.path.basename(caminho_bgm)}")
                else:
                    estado.adicionar_log("⚠️ Nenhuma trilha BGM encontrada em assets/bgm/ — usando narração pura.")
            except Exception as e_bgm:
                estado.adicionar_log(f"⚠️ BGM não aplicado (continuando sem trilha): {e_bgm}")

        estado.atualizar_progresso(0.40, "Áudio finalizado.")

        # 3. SINCRONIZAÇÃO
        estado.atualizar_progresso(0.42, "Processando transcrição e marcações de tempo...", etapa="sync")
        sync_dados = sincronizar_audio(
            caminho_audio=audio_path,  # Sincroniza com o áudio original (sem BGM) para timestamps precisos
            roteiro_dados=roteiro,
            whisper_model_size=whisper_model,
            forcar_fallback=modo_rapido
        )
        total_legendas = len(sync_dados.get("legendas_timestamps", []))
        estado.definir_dados(sync_dados=sync_dados)
        estado.atualizar_progresso(0.52, f"Sincronização concluída ({total_legendas} legendas sincronizadas).")

        # 4. IMAGENS IA (FASE 2 — Agora em paralelo!)
        estado.atualizar_progresso(0.55, f"Gerando imagens com IA ({estilo_id}) para as {qtd_cenas} cenas (paralelo)...", etapa="imagens")
        def cb_img(p, m):
            prog = round(0.55 + (p * 0.20), 2)
            estado.atualizar_progresso(prog, m, etapa="imagens")

        imagens_cenas = gerar_imagens_para_roteiro(
            roteiro_dados=roteiro,
            aspect_ratio=aspect_ratio,
            estilo_id=estilo_id,
            biblia_visual=biblia_visual,
            provedor=provedor_imagens,
            callback_progresso=cb_img
        )
        estado.definir_dados(imagens_cenas=imagens_cenas)
        estado.atualizar_progresso(0.76, f"Imagens geradas com sucesso para todas as {len(imagens_cenas)} cenas!")

        # 5. VÍDEO FINAL COM IMAGENS REAIS + TRANSIÇÕES + FLOW MOTION
        estado.atualizar_progresso(0.78, f"Renderizando vídeo MP4 final ({aspect_ratio}) com transições...", etapa="video")
        video_path = renderizar_video_moviepy(
            caminho_audio=audio_final,  # Usa áudio com BGM se disponível
            dados_sincronizacao=sync_dados,
            roteiro_dados=roteiro,
            aspect_ratio=aspect_ratio,
            callback_progresso=estado.atualizar_progresso,
            imagens_cenas=imagens_cenas,
            forcar_cpu=forcar_cpu,
            ativar_flow_motion=ativar_flow_motion,
            transicao_duracao=transicao_duracao,
            transicao_tipo=transicao_tipo
        )
        estado.definir_dados(video_path=video_path)
        estado.atualizar_progresso(0.92, f"Vídeo renderizado: {video_path}")

        # 5.5 THUMBNAIL AUTOMÁTICA
        caminho_thumb = None
        if gerar_thumbnail_auto and imagens_cenas:
            try:
                estado.atualizar_progresso(0.94, "🖼️ Gerando thumbnail automática...", etapa="video")
                titulo = roteiro.get("titulo", tema)
                texto_thumb = gerar_texto_thumbnail(titulo=titulo, tema=tema)
                slug = os.path.splitext(os.path.basename(video_path))[0]
                caminho_thumb = os.path.join("output", "thumbnails", f"{slug}_thumb.jpg")
                os.makedirs(os.path.dirname(caminho_thumb), exist_ok=True)
                gerar_thumbnail(
                    imagens_cenas=imagens_cenas,
                    texto_overlay=texto_thumb,
                    caminho_saida=caminho_thumb
                )
                estado.definir_dados(caminho_thumbnail=caminho_thumb)
                estado.adicionar_log(f"🖼️ Thumbnail gerada: {caminho_thumb}")
            except Exception as e_thumb:
                estado.adicionar_log(f"⚠️ Thumbnail não gerada (não crítico): {e_thumb}")

        estado.atualizar_progresso(0.97, f"Vídeo final concluído: {video_path}")

        # REGISTRO NO BANCO DE DADOS SQLITE
        try:
            duracao_seg = sync_dados.get("duracao_total", 0.0) if sync_dados else 0.0
            voz_tipo = "propria" if caminho_audio_proprio else ("clonada" if voice_id else "padrao")
            reg_id = banco_dados.salvar_video_historico({
                "tema": tema,
                "titulo": roteiro.get("titulo", "Sem título"),
                "descricao": roteiro.get("descricao", ""),
                "tags": roteiro.get("tags", []),
                "duracao_segundos": duracao_seg,
                "aspect_ratio": aspect_ratio,
                "voz_tipo": voz_tipo,
                "voice_id": voice_id or "",
                "qtd_cenas": qtd_cenas,
                "caminho_video": video_path,
                "caminho_audio": audio_final,
                "caminho_roteiro": roteiro.get("_caminho_arquivo", "")
            })
            estado.adicionar_log(f"💾 Registro salvo no banco SQLite (ID: {reg_id})")
        except Exception as e_bd:
            estado.adicionar_log(f"Aviso ao salvar no banco SQLite: {e_bd}")

        # Finalização com sucesso
        estado.definir_status("completed", etapa="completo")
        estado.adicionar_log("🎉 Pipeline completa v3.0 finalizada com êxito total!")

    except Exception as e:
        erro_msg = f"Erro durante a execução: {str(e)}"
        print(f"[pipeline_worker] {erro_msg}")
        traceback.print_exc()
        estado.adicionar_log(f"ERRO CRÍTICO: {str(e)}")
        estado.definir_status("error", erro=erro_msg)


def _worker_etapa_roteiro(
    tema: str,
    duracao_minima_minutos: float = 2.0,
    respostas_usuario: Optional[Dict[str, str]] = None,
    perfil_canal: Optional[Dict[str, Any]] = None
):
    """Executa individualmente a etapa de roteiro."""
    try:
        if not perfil_canal:
            perfil_canal = banco_dados.obter_perfil_canal()

        estado.definir_status("running", etapa="roteiro")
        estado.definir_dados(tema=tema)
        estado.atualizar_progresso(0.15, f"Solicitando roteiro ({duracao_minima_minutos:.1f}m) ao Google Gemini...", etapa="roteiro")
        roteiro = gerar_roteiro(
            tema=tema,
            duracao_minima_minutos=duracao_minima_minutos,
            respostas_usuario=respostas_usuario,
            perfil_canal=perfil_canal
        )
        estado.definir_dados(roteiro=roteiro)
        qtd = len(roteiro.get("cenas", []))
        estado.atualizar_progresso(0.25, f"Roteiro estruturado gerado com sucesso ({qtd} cenas)!")
        estado.definir_status("idle", etapa="roteiro")
    except Exception as e:
        estado.adicionar_log(f"ERRO ROTEIRO: {str(e)}")
        estado.definir_status("error", erro=str(e), etapa="roteiro")


def _worker_etapa_audio(
    roteiro: Dict[str, Any],
    voice_id: Optional[str] = None,
    caminho_audio_proprio: Optional[str] = None
):
    """Executa individualmente a etapa de áudio."""
    try:
        estado.definir_status("running", etapa="audio")
        msg = "Processando áudio próprio do usuário..." if caminho_audio_proprio else "Sintetizando narração em áudio MP3..."
        estado.atualizar_progresso(0.40, msg, etapa="audio")
        audio_path = gerar_audio(
            roteiro_dados=roteiro,
            voice_id=voice_id,
            caminho_audio_proprio=caminho_audio_proprio
        )
        estado.definir_dados(audio_path=audio_path)
        estado.atualizar_progresso(0.50, f"Áudio pronto: {audio_path}")
        estado.definir_status("idle", etapa="audio")
    except Exception as e:
        estado.adicionar_log(f"ERRO ÁUDIO: {str(e)}")
        estado.definir_status("error", erro=str(e), etapa="audio")


def _worker_etapa_sync(audio_path: str, roteiro: Dict[str, Any], whisper_model: str, modo_rapido: bool):
    """Executa individualmente a etapa de sincronização."""
    try:
        estado.definir_status("running", etapa="sync")
        estado.atualizar_progresso(0.65, "Extraindo timestamps com Whisper...", etapa="sync")
        sync_dados = sincronizar_audio(
            caminho_audio=audio_path,
            roteiro_dados=roteiro,
            whisper_model_size=whisper_model,
            forcar_fallback=modo_rapido
        )
        estado.definir_dados(sync_dados=sync_dados)
        estado.atualizar_progresso(0.75, "Sincronização concluída com sucesso!")
        estado.definir_status("idle", etapa="sync")
    except Exception as e:
        estado.adicionar_log(f"ERRO SYNC: {str(e)}")
        estado.definir_status("error", erro=str(e), etapa="sync")


def _worker_etapa_imagens(
    roteiro: Dict[str, Any],
    aspect_ratio: str = "16:9",
    provedor: str = "pollinations",
    estilo_id: str = "dark_cinematic",
    biblia_visual: Optional[Dict[str, Any]] = None
):
    """Executa individualmente a geração de imagens por cena com IA."""
    try:
        estado.definir_status("running", etapa="imagens")
        qtd = len(roteiro.get("cenas", []))
        estado.atualizar_progresso(0.10, f"Iniciando geração de {qtd} imagens ({estilo_id})...", etapa="imagens")

        def cb(p, m):
            estado.atualizar_progresso(round(p, 2), m, etapa="imagens")

        imagens_cenas = gerar_imagens_para_roteiro(
            roteiro_dados=roteiro,
            aspect_ratio=aspect_ratio,
            estilo_id=estilo_id,
            biblia_visual=biblia_visual,
            provedor=provedor,
            callback_progresso=cb
        )
        estado.definir_dados(imagens_cenas=imagens_cenas, estilo_visual=estilo_id, biblia_visual=biblia_visual)
        estado.atualizar_progresso(1.00, f"Todas as {len(imagens_cenas)} imagens geradas com sucesso!")
        estado.definir_status("idle", etapa="imagens")
    except Exception as e:
        estado.adicionar_log(f"ERRO IMAGENS: {str(e)}")
        estado.definir_status("error", erro=str(e), etapa="imagens")


def _worker_etapa_video(
    audio_path: str,
    sync_dados: Dict[str, Any],
    roteiro: Dict[str, Any],
    aspect_ratio: str,
    imagens_cenas: Optional[Dict[int, str]] = None,
    forcar_cpu: bool = False,
    ativar_flow_motion: bool = True,
    transicao_duracao: float = 0.5,
    transicao_tipo: str = 'fade'
):
    """Executa individualmente a etapa de renderização de vídeo."""
    try:
        estado.definir_status("running", etapa="video")
        estado.atualizar_progresso(0.85, f"Renderizando vídeo final ({aspect_ratio})...", etapa="video")
        video_path = renderizar_video_moviepy(
            caminho_audio=audio_path,
            dados_sincronizacao=sync_dados,
            roteiro_dados=roteiro,
            aspect_ratio=aspect_ratio,
            callback_progresso=estado.atualizar_progresso,
            imagens_cenas=imagens_cenas,
            forcar_cpu=forcar_cpu,
            ativar_flow_motion=ativar_flow_motion,
            transicao_duracao=transicao_duracao,
            transicao_tipo=transicao_tipo
        )
        estado.definir_dados(video_path=video_path)
        estado.atualizar_progresso(1.00, f"Vídeo renderizado com sucesso: {video_path}")

        # Salva no banco SQLite
        try:
            duracao_seg = sync_dados.get("duracao_total", 0.0) if sync_dados else 0.0
            banco_dados.salvar_video_historico({
                "tema": roteiro.get("titulo", "Vídeo Canal Dark"),
                "titulo": roteiro.get("titulo", "Sem título"),
                "descricao": roteiro.get("descricao", ""),
                "tags": roteiro.get("tags", []),
                "duracao_segundos": duracao_seg,
                "aspect_ratio": aspect_ratio,
                "qtd_cenas": len(roteiro.get("cenas", [])),
                "caminho_video": video_path,
                "caminho_audio": audio_path,
                "caminho_roteiro": roteiro.get("_caminho_arquivo", "")
            })
            estado.adicionar_log("💾 Histórico do vídeo salvo no SQLite.")
        except Exception as e_bd:
            estado.adicionar_log(f"Aviso SQLite: {e_bd}")

        estado.definir_status("completed", etapa="video")
    except Exception as e:
        estado.adicionar_log(f"ERRO VÍDEO: {str(e)}")
        estado.definir_status("error", erro=str(e), etapa="video")


def _worker_etapa_youtube(
    video_path: str,
    roteiro: Dict[str, Any],
    privacidade: str = "unlisted",
    caminho_thumbnail: Optional[str] = None,
    forcar_simulacao: bool = False
):
    """Executa individualmente o upload para o canal do YouTube."""
    try:
        estado.definir_status("running", etapa="youtube")
        estado.atualizar_progresso(0.10, "Iniciando publicação no YouTube...", etapa="youtube")

        def cb_yt(p, m):
            estado.atualizar_progresso(round(p, 2), m, etapa="youtube")

        resultado = upload_video_youtube(
            caminho_video=video_path,
            titulo=roteiro.get("titulo", "Vídeo Canal Dark"),
            descricao=roteiro.get("descricao", ""),
            tags=roteiro.get("tags", []),
            privacidade=privacidade,
            caminho_thumbnail=caminho_thumbnail,
            forcar_simulacao=forcar_simulacao,
            callback_progresso=cb_yt
        )
        estado.definir_dados(youtube_dados=resultado)
        url = resultado.get("video_url", "")
        estado.adicionar_log(f"Upload concluído! Link do vídeo: {url}")

        # Atualiza histórico SQLite com o link do YouTube
        try:
            banco_dados.salvar_video_historico({
                "tema": roteiro.get("titulo", "Vídeo Canal Dark"),
                "titulo": roteiro.get("titulo", "Vídeo Canal Dark"),
                "descricao": roteiro.get("descricao", ""),
                "tags": roteiro.get("tags", []),
                "caminho_video": video_path,
                "youtube_url": url,
                "youtube_status": privacidade
            })
            estado.adicionar_log(f"💾 Registro no SQLite atualizado com link do YouTube.")
        except Exception as e_bd:
            estado.adicionar_log(f"Aviso SQLite YouTube: {e_bd}")

        estado.atualizar_progresso(1.00, f"Publicado no YouTube: {url}")
        estado.definir_status("completed", etapa="youtube")
    except Exception as e:
        estado.adicionar_log(f"ERRO YOUTUBE: {str(e)}")
        estado.definir_status("error", erro=str(e), etapa="youtube")


def _worker_etapa_shorts(
    audio_path: str,
    sync_dados: Dict[str, Any],
    roteiro: Dict[str, Any],
    imagens_cenas: Optional[Dict[int, str]] = None,
    max_cortes: int = 3,
    forcar_cpu: bool = False
):
    """Executa a identificação e renderização dos cortes verticais (Shorts 9:16) em background."""
    try:
        from gerador_shorts import processar_multi_shorts
        estado.definir_status("running", etapa="shorts")
        estado.atualizar_progresso(0.10, "Analisando roteiro com IA para identificar os melhores cortes...", etapa="shorts")

        def cb_shorts(prog, msg):
            estado.atualizar_progresso(round(0.10 + (prog * 0.85), 2), msg, etapa="shorts")

        shorts = processar_multi_shorts(
            caminho_audio_longo=audio_path,
            sync_dados_longo=sync_dados,
            roteiro_longo=roteiro,
            imagens_cenas=imagens_cenas,
            max_cortes=max_cortes,
            callback_progresso=cb_shorts,
            forcar_cpu=forcar_cpu
        )
        estado.definir_dados(shorts_gerados=shorts)
        estado.adicionar_log(f"🎉 {len(shorts)} Shorts verticais gerados com sucesso!")
        estado.atualizar_progresso(1.00, f"{len(shorts)} Shorts verticais (9:16) gerados com sucesso!", etapa="shorts")
        estado.definir_status("completed", etapa="shorts")
    except Exception as e:
        estado.adicionar_log(f"ERRO SHORTS: {str(e)}")
        estado.definir_status("error", erro=str(e), etapa="shorts")


# -------------------------------------------------------------
# DISPARADORES PÚBLICOS
# -------------------------------------------------------------
def disparar_pipeline_completa(
    tema: str,
    aspect_ratio: str = "16:9",
    whisper_model: str = "base",
    modo_rapido: bool = False,
    provedor_imagens: str = "pollinations",
    estilo_id: str = "dark_cinematic",
    biblia_visual: Optional[Dict[str, Any]] = None,
    duracao_minima_minutos: float = 2.0,
    respostas_usuario: Optional[Dict[str, str]] = None,
    perfil_canal: Optional[Dict[str, Any]] = None,
    voice_id: Optional[str] = None,
    caminho_audio_proprio: Optional[str] = None,
    forcar_cpu: bool = False,
    ativar_flow_motion: bool = True,
    transicao_duracao: float = 0.5,
    transicao_tipo: str = 'fade',
    bgm_modo: Optional[str] = None,
    bgm_volume_db: float = -18.0,
    gerar_thumbnail_auto: bool = True
) -> bool:
    return iniciar_tarefa_background(
        _worker_pipeline_completa,
        args=(tema, aspect_ratio, whisper_model, modo_rapido, provedor_imagens, estilo_id, biblia_visual, duracao_minima_minutos, respostas_usuario, perfil_canal, voice_id, caminho_audio_proprio, forcar_cpu, ativar_flow_motion, transicao_duracao, transicao_tipo, bgm_modo, bgm_volume_db, gerar_thumbnail_auto)
    )


def disparar_etapa_roteiro(
    tema: str,
    duracao_minima_minutos: float = 2.0,
    respostas_usuario: Optional[Dict[str, str]] = None,
    perfil_canal: Optional[Dict[str, Any]] = None
) -> bool:
    return iniciar_tarefa_background(
        _worker_etapa_roteiro,
        args=(tema, duracao_minima_minutos, respostas_usuario, perfil_canal)
    )


def disparar_etapa_audio(
    roteiro: Dict[str, Any],
    voice_id: Optional[str] = None,
    caminho_audio_proprio: Optional[str] = None
) -> bool:
    return iniciar_tarefa_background(
        _worker_etapa_audio,
        args=(roteiro, voice_id, caminho_audio_proprio)
    )


def disparar_etapa_sync(audio_path: str, roteiro: Dict[str, Any], whisper_model: str = "base", modo_rapido: bool = False) -> bool:
    return iniciar_tarefa_background(_worker_etapa_sync, args=(audio_path, roteiro, whisper_model, modo_rapido))


def disparar_etapa_imagens(
    roteiro: Dict[str, Any],
    aspect_ratio: str = "16:9",
    provedor: str = "pollinations",
    estilo_id: str = "dark_cinematic",
    biblia_visual: Optional[Dict[str, Any]] = None
) -> bool:
    return iniciar_tarefa_background(
        _worker_etapa_imagens,
        args=(roteiro, aspect_ratio, provedor, estilo_id, biblia_visual)
    )


def disparar_etapa_video(
    audio_path: str,
    sync_dados: Dict[str, Any],
    roteiro: Dict[str, Any],
    aspect_ratio: str = "16:9",
    imagens_cenas: Optional[Dict[int, str]] = None,
    forcar_cpu: bool = False,
    ativar_flow_motion: bool = True,
    transicao_duracao: float = 0.5,
    transicao_tipo: str = 'fade'
) -> bool:
    return iniciar_tarefa_background(_worker_etapa_video, args=(audio_path, sync_dados, roteiro, aspect_ratio, imagens_cenas, forcar_cpu, ativar_flow_motion, transicao_duracao, transicao_tipo))


def disparar_etapa_youtube(
    video_path: str,
    roteiro: Dict[str, Any],
    privacidade: str = "unlisted",
    caminho_thumbnail: Optional[str] = None,
    forcar_simulacao: bool = False
) -> bool:
    return iniciar_tarefa_background(
        _worker_etapa_youtube,
        args=(video_path, roteiro, privacidade, caminho_thumbnail, forcar_simulacao)
    )


def disparar_etapa_shorts(
    audio_path: str,
    sync_dados: Dict[str, Any],
    roteiro: Dict[str, Any],
    imagens_cenas: Optional[Dict[int, str]] = None,
    max_cortes: int = 3,
    forcar_cpu: bool = False
) -> bool:
    return iniciar_tarefa_background(
        _worker_etapa_shorts,
        args=(audio_path, sync_dados, roteiro, imagens_cenas, max_cortes, forcar_cpu)
    )
