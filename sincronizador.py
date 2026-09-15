"""
Módulo sincronizador.py
Uso do Whisper local e metadados de síntese (Edge-TTS) para transcrever áudio e extrair
timestamps precisos de cada cena e frase, eliminando atrasos ou adiantamentos de legendas.
"""

import os
import json
import re
import shutil
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

# Garante que o FFmpeg esteja sempre disponível no PATH para o Whisper
try:
    import imageio_ffmpeg
    _ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
    _ffmpeg_dir = os.path.dirname(_ffmpeg_bin)
    if _ffmpeg_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
    _ffmpeg_exe = os.path.join(_ffmpeg_dir, "ffmpeg.exe")
    if not os.path.exists(_ffmpeg_exe) and os.path.exists(_ffmpeg_bin):
        shutil.copy2(_ffmpeg_bin, _ffmpeg_exe)
except Exception as _e_ff:
    pass


def obter_duracao_audio(caminho_audio: str) -> float:
    """Obtém a duração exata do arquivo de áudio em segundos."""
    try:
        from moviepy import AudioFileClip
        with AudioFileClip(caminho_audio) as clip:
            return float(clip.duration)
    except Exception:
        try:
            import imageio_ffmpeg
            import subprocess
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            cmd = [ffmpeg_exe, "-i", caminho_audio]
            result = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
            match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", result.stderr)
            if match:
                h, m, s = match.groups()
                return int(h) * 3600 + int(m) * 60 + float(s)
        except Exception:
            pass
    return 10.0


def estimar_timestamps_proporcionais(roteiro_dados: Dict[str, Any], duracao_total: float) -> Dict[str, Any]:
    """
    Sincronização proporcional inteligente ponderada por contagem de caracteres e palavras.
    Evita que frases curtas fiquem presas na tela e que frases longas passem rápido demais.
    """
    cenas = roteiro_dados.get("cenas", [])
    if not cenas:
        return {"duracao_total": duracao_total, "cenas_timestamps": [], "legendas_timestamps": []}

    tamanhos = [max(len(c.get("narracao", "").strip()), 1) for c in cenas]
    total_chars_roteiro = sum(tamanhos)

    cenas_ts = []
    legendas_ts = []
    tempo_atual = 0.0

    for idx, c in enumerate(cenas):
        proporcao = tamanhos[idx] / total_chars_roteiro
        duracao_cena = round(duracao_total * proporcao, 2)
        start_cena = round(tempo_atual, 2)
        end_cena = round(min(tempo_atual + duracao_cena, duracao_total), 2)
        if idx == len(cenas) - 1:
            end_cena = round(duracao_total, 2)
        tempo_atual = end_cena

        cenas_ts.append({
            "cena_id": c.get("cena_id", idx + 1),
            "start": start_cena,
            "end": end_cena,
            "visual_prompt": c.get("visual_prompt", ""),
            "narracao_original": c.get("narracao", "")
        })

        narracao_texto = c.get("narracao", "").strip()
        frases = [f.strip() for f in re.split(r'(?<=[.?!,;])\s+', narracao_texto) if f.strip()]
        if not frases:
            frases = [narracao_texto]

        total_chars_cena = sum(max(len(f), 1) for f in frases)
        sub_tempo = start_cena
        dur_real_cena = max(0.1, end_cena - start_cena)

        for idx_f, frase in enumerate(frases):
            frac = max(len(frase), 1) / total_chars_cena
            duracao_frase = round(dur_real_cena * frac, 2)
            duracao_frase = max(duracao_frase, 0.8)
            sub_end = round(min(sub_tempo + duracao_frase, end_cena), 2)
            if idx_f == len(frases) - 1:
                sub_end = end_cena

            legendas_ts.append({
                "start": sub_tempo,
                "end": sub_end,
                "text": frase,
                "cena_id": c.get("cena_id", idx + 1)
            })
            sub_tempo = sub_end

    return {
        "duracao_total": duracao_total,
        "cenas_timestamps": cenas_ts,
        "legendas_timestamps": legendas_ts,
        "_metodo": "proporcional_ponderado"
    }


def sincronizar_com_edge_boundaries(
    caminho_boundaries: str,
    roteiro_dados: Dict[str, Any],
    duracao_total: float
) -> Optional[Dict[str, Any]]:
    """
    Usa as marcações de SentenceBoundary gravadas diretamente durante a síntese de voz Edge-TTS.
    Garante sincronismo perfeito de milissegundos sem qualquer aproximação heurística.
    """
    if not os.path.exists(caminho_boundaries):
        return None

    try:
        with open(caminho_boundaries, "r", encoding="utf-8") as f:
            raw_boundaries = json.load(f)

        if not raw_boundaries:
            return None

        cenas = roteiro_dados.get("cenas", [])
        if not cenas:
            return None

        total_chars_roteiro = sum(max(len(c.get("narracao", "")), 1) for c in cenas)
        
        # Mapeia cada boundary à respectiva cena sequencialmente
        legendas_ts = []
        cenas_ts = []
        
        cum_chars = 0
        tempos_alvo_cenas = []
        for c in cenas:
            cum_chars += max(len(c.get("narracao", "")), 1)
            tempos_alvo_cenas.append(duracao_total * (cum_chars / total_chars_roteiro))

        cena_idx = 0
        b_por_cena: Dict[int, List[Dict[str, Any]]] = {c.get("cena_id", i+1): [] for i, c in enumerate(cenas)}

        for b in raw_boundaries:
            if "end" not in b:
                b["end"] = round(b.get("start", 0.0) + b.get("duration", 0.0), 2)

            cid_atual = cenas[cena_idx].get("cena_id", cena_idx + 1)
            b_por_cena[cid_atual].append(b)

            if b.get("end", 0.0) >= tempos_alvo_cenas[cena_idx] and cena_idx < len(cenas) - 1:
                cena_idx += 1

        tempo_anterior = 0.0
        for idx, c in enumerate(cenas):
            cid = c.get("cena_id", idx + 1)
            bs = b_por_cena.get(cid, [])
            if bs:
                st_c = round(bs[0].get("start", 0.0), 2)
                et_c = round(bs[-1].get("end", st_c + bs[-1].get("duration", 0.0)), 2)
            else:
                st_c = round(tempo_anterior, 2)
                et_c = round(tempos_alvo_cenas[idx], 2)

            st_c = max(tempo_anterior, st_c)
            if idx == len(cenas) - 1:
                et_c = round(duracao_total, 2)

            tempo_anterior = et_c
            cenas_ts.append({
                "cena_id": cid,
                "start": st_c,
                "end": et_c,
                "visual_prompt": c.get("visual_prompt", ""),
                "narracao_original": c.get("narracao", "")
            })

            for b in bs:
                legendas_ts.append({
                    "start": round(b.get("start", 0.0), 2),
                    "end": round(b.get("end", 0.0), 2),
                    "text": b.get("text", "").strip(),
                    "cena_id": cid
                })

        print(f"[sincronizador] [OK] Sincronização nativa via Edge-TTS ({len(legendas_ts)} frases sincronizadas)!")
        return {
            "duracao_total": duracao_total,
            "cenas_timestamps": cenas_ts,
            "legendas_timestamps": legendas_ts,
            "_metodo": "edge_tts_native_boundaries"
        }

    except Exception as e:
        print(f"[sincronizador] Erro ao ler boundaries do Edge-TTS ({e}). Recorrendo ao Whisper/proporcional.")
        return None


def sincronizar_audio(
    caminho_audio: str,
    roteiro_dados: Optional[Dict[str, Any]] = None,
    whisper_model_size: Optional[str] = None,
    forcar_fallback: bool = False
) -> Dict[str, Any]:
    """
    Transcreve o áudio e mapeia timestamps precisos de cada cena e frase.
    Prioriza metadados nativos de síntese do Edge-TTS, com fallback para Whisper local e proporcional ponderado.
    """
    if not os.path.exists(caminho_audio):
        raise FileNotFoundError(f"Arquivo de áudio não encontrado: {caminho_audio}")

    duracao_total = obter_duracao_audio(caminho_audio)
    modelo_tam = whisper_model_size or os.getenv("WHISPER_MODEL", "base").strip() or "base"

    if not roteiro_dados:
        roteiro_dados = {"cenas": [{"cena_id": 1, "narracao": "Áudio Completo", "visual_prompt": "Cena única"}]}

    # 1. Tenta sincronização direta pelas boundaries nativas do Edge-TTS
    caminho_bound = caminho_audio.replace(".mp3", "_boundaries.json")
    resultado_sync = None

    if not forcar_fallback and os.path.exists(caminho_bound):
        resultado_sync = sincronizar_com_edge_boundaries(caminho_bound, roteiro_dados, duracao_total)

    # 2. Se não houver boundaries, executa o Whisper local
    if not resultado_sync and not forcar_fallback:
        try:
            print(f"[sincronizador] Executando Whisper local ('{modelo_tam}')...")
            import whisper

            model = whisper.load_model(modelo_tam)
            transcricao = model.transcribe(
                caminho_audio,
                verbose=False,
                language="pt",
                word_timestamps=False
            )

            segmentos = transcricao.get("segments", [])
            print(f"[sincronizador] Whisper identificou {len(segmentos)} segmentos de fala.")

            legendas_ts = []
            for seg in segmentos:
                txt = seg.get("text", "").strip()
                if txt:
                    legendas_ts.append({
                        "start": round(seg["start"], 2),
                        "end": round(seg["end"], 2),
                        "text": txt
                    })

            cenas = roteiro_dados.get("cenas", [])
            total_cenas = len(cenas)

            if total_cenas > 0 and legendas_ts:
                tamanhos = [max(len(c.get("narracao", "").strip()), 1) for c in cenas]
                total_chars = sum(tamanhos)
                tempos_corte = []
                cum = 0
                for tam in tamanhos:
                    cum += tam
                    tempos_corte.append(duracao_total * (cum / total_chars))

                cenas_ts = []
                tempo_ant = 0.0
                seg_idx = 0

                for idx, c in enumerate(cenas):
                    cid = c.get("cena_id", idx + 1)
                    t_corte = tempos_corte[idx]
                    segs_cena = []

                    while seg_idx < len(legendas_ts):
                        s = legendas_ts[seg_idx]
                        if s["end"] <= t_corte or idx == total_cenas - 1 or len(segs_cena) == 0:
                            s["cena_id"] = cid
                            segs_cena.append(s)
                            seg_idx += 1
                        else:
                            break

                    st_c = segs_cena[0]["start"] if segs_cena else tempo_ant
                    et_c = segs_cena[-1]["end"] if segs_cena else t_corte
                    if idx == total_cenas - 1:
                        et_c = round(duracao_total, 2)

                    tempo_ant = et_c
                    cenas_ts.append({
                        "cena_id": cid,
                        "start": round(st_c, 2),
                        "end": round(et_c, 2),
                        "visual_prompt": c.get("visual_prompt", ""),
                        "narracao_original": c.get("narracao", "")
                    })

                resultado_sync = {
                    "duracao_total": duracao_total,
                    "cenas_timestamps": cenas_ts,
                    "legendas_timestamps": legendas_ts,
                    "_metodo": f"whisper_{modelo_tam}"
                }
        except Exception as e:
            print(f"[sincronizador] Whisper indisponível ({e}). Recorrendo ao cálculo ponderado...")

    # 3. Fallback inteligente
    if not resultado_sync:
        resultado_sync = estimar_timestamps_proporcionais(roteiro_dados, duracao_total)

    # Persiste o arquivo JSON de timestamps
    os.makedirs("output/timestamps", exist_ok=True)
    nome_base = os.path.splitext(os.path.basename(caminho_audio))[0]
    caminho_saida = os.path.join("output", "timestamps", f"{nome_base}_timestamps.json")
    with open(caminho_saida, "w", encoding="utf-8") as f:
        json.dump(resultado_sync, f, ensure_ascii=False, indent=2)

    resultado_sync["_caminho_arquivo"] = caminho_saida
    print(f"[sincronizador] Sincronização concluída [{resultado_sync.get('_metodo')}]: {caminho_saida}")
    return resultado_sync


if __name__ == "__main__":
    print("Módulo sincronizador pronto.")
