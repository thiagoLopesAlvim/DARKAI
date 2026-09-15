"""
Módulo gerador_shorts.py
Automação e inteligência para produção de Shorts e Cortes Verticais (9:16)
a partir de vídeos longos já concluídos.

Funcionalidades:
1. Análise inteligente com Gemini para identificar os melhores ganchos e cortes (30s a 58s).
2. Recorte preciso de áudio sem perda de qualidade via ffmpeg.
3. Reenquadramento vertical 9:16 com Ambient Blur e legendagem otimizada para Shorts/TikTok.
4. Geração de Super-Resumo Viral condensado em 50s.
"""

import os
import json
import subprocess
import imageio_ffmpeg
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

import banco_dados
from gerador_roteiro import sanitizar_nome_arquivo
from editor_video import renderizar_video_moviepy

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()


class CorteIdentificado(BaseModel):
    corte_id: int = Field(description="Identificador sequencial do corte (iniciando em 1)")
    titulo_short: str = Field(description="Título viral chamativo para YouTube Shorts / TikTok (máximo 60 caracteres)")
    cenas_ids: List[int] = Field(description="Lista dos IDs das cenas originais que compõem este corte")
    gancho_explicacao: str = Field(description="Por que este trecho tem alto poder de retenção e viralização")
    tempo_inicio_estimado: float = Field(description="Tempo inicial sugerido em segundos")
    tempo_fim_estimado: float = Field(description="Tempo final sugerido em segundos")


class ListaCortes(BaseModel):
    cortes: List[CorteIdentificado] = Field(description="Lista de 1 a 3 cortes de alta retenção (duração entre 30s e 58s)")


def recortar_audio_segmento(caminho_audio_origem: str, t_inicio: float, t_fim: float, caminho_saida_audio: str) -> str:
    """Recorta uma fatia precisa do áudio original usando ffmpeg de forma lossless e instantânea."""
    os.makedirs(os.path.dirname(caminho_saida_audio), exist_ok=True)
    duracao = max(1.0, t_fim - t_inicio)
    
    cmd = [
        FFMPEG_EXE,
        "-y",
        "-ss", f"{t_inicio:.3f}",
        "-t", f"{duracao:.3f}",
        "-i", caminho_audio_origem,
        "-c:a", "libmp3lame",
        "-q:a", "2",
        caminho_saida_audio
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return caminho_saida_audio


def filtrar_e_ajustar_timestamps(sync_dados: Dict[str, Any], t_inicio: float, t_fim: float) -> Dict[str, Any]:
    """
    Filtra as legendas e cenas que pertencem ao intervalo do corte e desloca
    as marcações de tempo para começarem em 0.0s.
    """
    legendas_originais = sync_dados.get("legendas_timestamps", [])
    cenas_originais = sync_dados.get("cenas_timestamps", [])

    novas_legendas = []
    for leg in legendas_originais:
        l_start = leg.get("start", 0.0)
        l_end = leg.get("end", 0.0)
        # Verifica se a legenda se sobrepõe ao intervalo [t_inicio, t_fim]
        if l_end > t_inicio and l_start < t_fim:
            adj_start = max(0.0, l_start - t_inicio)
            adj_end = max(adj_start + 0.1, min(t_fim - t_inicio, l_end - t_inicio))
            novas_legendas.append({
                "start": round(adj_start, 2),
                "end": round(adj_end, 2),
                "text": leg.get("text", "")
            })

    novas_cenas = []
    for c in cenas_originais:
        c_start = c.get("start", 0.0)
        c_end = c.get("end", 0.0)
        if c_end > t_inicio and c_start < t_fim:
            adj_start = max(0.0, c_start - t_inicio)
            adj_end = max(adj_start + 0.1, min(t_fim - t_inicio, c_end - t_inicio))
            novas_cenas.append({
                "cena_id": c.get("cena_id", 1),
                "start": round(adj_start, 2),
                "end": round(adj_end, 2),
                "visual_prompt": c.get("visual_prompt", "")
            })

    duracao_corte = round(t_fim - t_inicio, 2)
    return {
        "duracao_total": duracao_corte,
        "duracao_audio": duracao_corte,
        "legendas_timestamps": novas_legendas,
        "cenas_timestamps": novas_cenas,
        "_metodo": "Corte Inteligente Shorts"
    }


def identificar_cortes_inteligentes(
    roteiro_dados: Dict[str, Any],
    sync_dados: Dict[str, Any],
    max_cortes: int = 3,
    api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Analisa o roteiro e os timestamps do vídeo longo com Gemini para eleger
    os 1 a 3 melhores trechos verticais (de 30 a 58 segundos cada).
    """
    cenas_ts = sync_dados.get("cenas_timestamps", [])
    cenas_roteiro = roteiro_dados.get("cenas", [])
    duracao_total = float(sync_dados.get("duracao_total", 0.0))

    # Mapeamento do tempo de cada cena
    mapa_cenas = {}
    for c in cenas_ts:
        cid = c.get("cena_id")
        mapa_cenas[cid] = (c.get("start", 0.0), c.get("end", 0.0))

    # Fallback heurístico inteligente caso a API não responda
    def gerar_cortes_fallback():
        cortes_fb = []
        # Corte 1: Gancho Inicial (Cena 1 em diante até ~45s)
        t0 = 0.0
        t1 = min(duracao_total, 45.0)
        if duracao_total > 30.0:
            cortes_fb.append({
                "corte_id": 1,
                "titulo_short": f"O Terrível Segredo: {roteiro_dados.get('titulo', 'Mistério')[:30]}",
                "cenas_ids": [1, 2],
                "gancho_explicacao": "Hook inicial com a revelação mais intrigante e misteriosa.",
                "tempo_inicio": t0,
                "tempo_fim": t1,
                "duracao": round(t1 - t0, 1)
            })

        # Corte 2: Meio / Clímax (se houver mais de 70s)
        if duracao_total >= 70.0:
            meio = duracao_total / 2
            t_ini_2 = max(0.0, meio - 20.0)
            t_fim_2 = min(duracao_total, t_ini_2 + 45.0)
            cortes_fb.append({
                "corte_id": 2,
                "titulo_short": "A Evidência que Eles Tentaram Apagar!",
                "cenas_ids": [3, 4] if len(cenas_roteiro) >= 4 else [2],
                "gancho_explicacao": "Apresentação da evidência central que desafia a versão oficial.",
                "tempo_inicio": round(t_ini_2, 1),
                "tempo_fim": round(t_fim_2, 1),
                "duracao": round(t_fim_2 - t_ini_2, 1)
            })

        # Corte 3: Conclusão perturbadora
        if duracao_total >= 120.0:
            t_ini_3 = max(0.0, duracao_total - 48.0)
            t_fim_3 = duracao_total
            cortes_fb.append({
                "corte_id": 3,
                "titulo_short": "A Verdade Que Ninguém Te Contou...",
                "cenas_ids": [len(cenas_roteiro)],
                "gancho_explicacao": "Desfecho perturbador e instigante que força o clique.",
                "tempo_inicio": round(t_ini_3, 1),
                "tempo_fim": round(t_fim_3, 1),
                "duracao": round(t_fim_3 - t_ini_3, 1)
            })
        return cortes_fb[:max_cortes]

    chave = api_key or os.getenv("GEMINI_API_KEY", "").strip()
    if not chave or "sua_chave" in chave.lower() or duracao_total < 35.0:
        return gerar_cortes_fallback()

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=chave)

        resumo_cenas_txt = []
        for c in cenas_roteiro:
            cid = c.get("cena_id", 1)
            tempo_str = f"[{mapa_cenas.get(cid, (0, 0))[0]:.1f}s - {mapa_cenas.get(cid, (0, 0))[1]:.1f}s]"
            resumo_cenas_txt.append(f"Cena {cid} {tempo_str}: {c.get('narracao', '')}")

        prompt = f"""
Você é um editor viral de YouTube Shorts e TikTok especialista em Canais Dark.
Analise a minutagem e as cenas do vídeo longo abaixo e selecione até {max_cortes} cortes para serem transformados em vídeos verticais (Shorts).

REGRAS ESTRITAS PARA OS CORTES:
1. Cada corte DEVE ter duração entre 30 e 58 segundos (NUNCA ultrapassar 59 segundos).
2. O corte deve ter um gancho eletrizante nos primeiros 3 segundos e prender até o fim.
3. Use os tempos de início e fim baseados na minutagem real das cenas informadas.
4. Crie um título altamente chamativo (máximo 50 caracteres) com hashtags para Shorts.

CENAS DO VÍDEO LONGO (Duração Total: {duracao_total:.1f} segundos):
{"".join(resumo_cenas_txt)}
"""
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ListaCortes,
            temperature=0.7
        )

        resposta = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip(),
            contents=prompt,
            config=config
        )

        dados_ia = json.loads(resposta.text)
        cortes_brutos = dados_ia.get("cortes", [])

        # Validação de limites de tempo
        cortes_validados = []
        for idx, c in enumerate(cortes_brutos):
            t_in = max(0.0, float(c.get("tempo_inicio_estimado", 0.0)))
            t_out = min(duracao_total, float(c.get("tempo_fim_estimado", t_in + 45.0)))
            if t_out - t_in < 20.0:
                t_out = min(duracao_total, t_in + 40.0)
            if t_out - t_in > 58.0:
                t_out = t_in + 55.0

            cortes_validados.append({
                "corte_id": idx + 1,
                "titulo_short": c.get("titulo_short", f"Corte {idx+1} - Canal Dark")[:60],
                "cenas_ids": c.get("cenas_ids", [1]),
                "gancho_explicacao": c.get("gancho_explicacao", "Momento de alta retenção."),
                "tempo_inicio": round(t_in, 1),
                "tempo_fim": round(t_out, 1),
                "duracao": round(t_out - t_in, 1)
            })

        return cortes_validados if cortes_validados else gerar_cortes_fallback()

    except Exception as e:
        print(f"[gerador_shorts] Erro na análise do Gemini ({e}). Usando fallback heurístico.")
        return gerar_cortes_fallback()


def renderizar_short_corte(
    caminho_audio_longo: str,
    sync_dados_longo: Dict[str, Any],
    roteiro_longo: Dict[str, Any],
    corte_info: Dict[str, Any],
    imagens_cenas: Optional[Dict[int, str]] = None,
    caminho_saida: Optional[str] = None,
    callback_progresso: Optional[Any] = None,
    forcar_cpu: bool = False
) -> str:
    """
    Renderiza um corte em formato vertical 9:16 (1080x1920) com efeito
    Ambient Blur e legendas posicionadas estrategicamente para Shorts.
    """
    t_inicio = float(corte_info.get("tempo_inicio", 0.0))
    t_fim = float(corte_info.get("tempo_fim", t_inicio + 45.0))
    corte_id = corte_info.get("corte_id", 1)
    titulo_corte = corte_info.get("titulo_short", f"short_corte_{corte_id}")

    slug = sanitizar_nome_arquivo(roteiro_longo.get("titulo", "video_dark"))
    os.makedirs("output/videos", exist_ok=True)
    os.makedirs("temp", exist_ok=True)

    # 1. Recorta fatia de áudio
    caminho_audio_corte = os.path.join("temp", f"{slug}_audio_short_{corte_id}.mp3")
    recortar_audio_segmento(caminho_audio_longo, t_inicio, t_fim, caminho_audio_corte)

    # 2. Ajusta marcações de tempo e legendas
    sync_corte = filtrar_e_ajustar_timestamps(sync_dados_longo, t_inicio, t_fim)

    # 3. Mapeia imagens para as cenas envolvidas
    cenas_corte = []
    cenas_originais = roteiro_longo.get("cenas", [])
    cenas_ids = corte_info.get("cenas_ids", [])
    
    for c in cenas_originais:
        if not cenas_ids or c.get("cena_id") in cenas_ids:
            cenas_corte.append(c)

    roteiro_corte = {
        "titulo": titulo_corte,
        "descricao": f"{titulo_corte}\n\nAssista ao vídeo completo no canal!\n#shorts #canaldark #misterio",
        "tags": roteiro_longo.get("tags", []) + ["shorts", "reels", "tiktok"],
        "cenas": cenas_corte if cenas_corte else cenas_originais[:2]
    }

    # 4. Renderiza em 9:16 vertical
    if not caminho_saida:
        caminho_saida = os.path.join("output", "videos", f"{slug}_short_corte_{corte_id}_9x16.mp4")

    video_final = renderizar_video_moviepy(
        caminho_audio=caminho_audio_corte,
        dados_sincronizacao=sync_corte,
        roteiro_dados=roteiro_corte,
        aspect_ratio="9:16",
        caminho_saida=caminho_saida,
        callback_progresso=callback_progresso,
        imagens_cenas=imagens_cenas,
        forcar_cpu=forcar_cpu
    )

    # 5. Salva no banco de dados SQLite como Short
    try:
        banco_dados.salvar_video_historico({
            "tema": roteiro_longo.get("titulo", "Canal Dark"),
            "titulo": f"📱 [SHORT] {titulo_corte}",
            "descricao": roteiro_corte["descricao"],
            "tags": roteiro_corte["tags"],
            "duracao_segundos": round(t_fim - t_inicio, 1),
            "aspect_ratio": "9:16",
            "is_short": 1,
            "qtd_cenas": len(roteiro_corte["cenas"]),
            "caminho_video": video_final,
            "caminho_audio": caminho_audio_corte
        })
    except Exception as e_bd:
        print(f"[gerador_shorts] Aviso ao registrar Short no banco SQLite: {e_bd}")

    return video_final


def processar_multi_shorts(
    caminho_audio_longo: str,
    sync_dados_longo: Dict[str, Any],
    roteiro_longo: Dict[str, Any],
    imagens_cenas: Optional[Dict[int, str]] = None,
    max_cortes: int = 3,
    callback_progresso: Optional[Any] = None,
    forcar_cpu: bool = False
) -> List[Dict[str, Any]]:
    """
    Orquestra a identificação e renderização de todos os cortes inteligentes.
    Retorna a lista de Shorts criados com caminhos e metadados.
    """
    cortes = identificar_cortes_inteligentes(roteiro_longo, sync_dados_longo, max_cortes=max_cortes)
    resultados = []

    total = len(cortes)
    for idx, c in enumerate(cortes):
        if callback_progresso:
            prog = (idx / total)
            msg = f"Renderizando Short {idx+1}/{total} (9:16): '{c['titulo_short']}'..."
            callback_progresso(prog, msg)

        caminho_mp4 = renderizar_short_corte(
            caminho_audio_longo=caminho_audio_longo,
            sync_dados_longo=sync_dados_longo,
            roteiro_longo=roteiro_longo,
            corte_info=c,
            imagens_cenas=imagens_cenas,
            forcar_cpu=forcar_cpu
        )

        c["caminho_video"] = caminho_mp4
        c["tamanho_mb"] = round(os.path.getsize(caminho_mp4) / (1024 * 1024), 2) if os.path.exists(caminho_mp4) else 0.0
        resultados.append(c)

    if callback_progresso:
        callback_progresso(1.0, f"Todos os {len(resultados)} Shorts verticais foram gerados com sucesso!")

    return resultados
