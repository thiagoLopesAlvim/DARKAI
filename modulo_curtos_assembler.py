"""
Módulo modulo_curtos_assembler.py
Motor de Junção e Montagem Automatizada para o Módulo de VÍDEOS CURTOS (Estilo Flow).

Responsabilidade única e direta:
- Não re-edita frame a frame os vídeos gerados.
- Pega os clipes MP4 animados (gerados no Google Flow para cada cena),
  ordena-os rigorosamente (Cena 1, 2, 3... N),
  padroniza a resolução em 9:16 (1080x1920),
  normaliza os volumes de áudio,
  aplica transições rápidas (slide/crossfade/corte seco) com efeitos sonoros (SFX whoosh/swoosh),
  adiciona marca d'água opcional (@perfil) e exporta o Shorts/TikTok final pronto para publicação.
"""

import os
import re
import math
import subprocess
import imageio_ffmpeg
from typing import List, Dict, Any, Optional, Callable
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

load_dotenv()

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()


def obter_duracao_video(caminho_video: str) -> float:
    """Retorna a duração em segundos de um vídeo usando ffprobe ou ffmpeg."""
    ffprobe_exe = os.path.join(os.path.dirname(FFMPEG_EXE), "ffprobe.exe")
    if not os.path.exists(ffprobe_exe):
        ffprobe_exe = "ffprobe"
    
    try:
        cmd = [
            ffprobe_exe, "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", caminho_video
        ]
        saida = subprocess.check_output(cmd, text=True, stderr=subprocess.PIPE).strip()
        return float(saida)
    except Exception:
        # Fallback via moviepy se ffprobe direto falhar
        try:
            from moviepy import VideoFileClip
            with VideoFileClip(caminho_video) as clip:
                return float(clip.duration)
        except Exception:
            return 5.0


def ordenar_arquivos_naturalmente(lista_caminhos: List[str]) -> List[str]:
    """Ordena caminhos de arquivos considerando números de cenas (ex: cena_1, cena_2, cena_10)."""
    def chave_ordenacao(caminho):
        nome = os.path.basename(caminho)
        numeros = re.findall(r'\d+', nome)
        if numeros:
            return [int(n) for n in numeros]
        return [nome.lower()]
    
    return sorted(lista_caminhos, key=chave_ordenacao)


def criar_overlay_marca_dagua(
    texto_arroba: str,
    largura: int = 1080,
    altura: int = 1920,
    caminho_saida_png: str = "temp/marca_dagua_curtos.png"
) -> str:
    """Cria uma imagem PNG transparente com a marca d'água (@perfil) estilizada."""
    os.makedirs(os.path.dirname(caminho_saida_png), exist_ok=True)
    img = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    tamanho_fonte = 38
    try:
        # Tenta carregar fonte do sistema
        caminhos_fonte = [
            "C:\\Windows\\Fonts\\arialbd.ttf",
            "C:\\Windows\\Fonts\\impact.ttf",
            "C:\\Windows\\Fonts\\segoeui.ttf"
        ]
        fonte = None
        for cf in caminhos_fonte:
            if os.path.exists(cf):
                fonte = ImageFont.truetype(cf, tamanho_fonte)
                break
        if not fonte:
            fonte = ImageFont.load_default()
    except Exception:
        fonte = ImageFont.load_default()

    texto = texto_arroba if texto_arroba.startswith("@") else f"@{texto_arroba}"
    
    # Posição: rodapé superior ou inferior com margem segura
    bbox = draw.textbbox((0, 0), texto, font=fonte)
    largura_texto = bbox[2] - bbox[0]
    altura_texto = bbox[3] - bbox[1]

    pos_x = (largura - largura_texto) // 2
    pos_y = altura - 280  # Margem segura para não colidir com a interface do TikTok

    # Fundo estilo pílula escura translúcida
    pad_x = 24
    pad_y = 10
    draw.rounded_rectangle(
        [pos_x - pad_x, pos_y - pad_y, pos_x + largura_texto + pad_x, pos_y + altura_texto + pad_y],
        radius=14,
        fill=(0, 0, 0, 160)
    )

    # Texto em branco com leve sombra
    draw.text((pos_x + 1, pos_y + 1), texto, font=fonte, fill=(0, 0, 0, 220))
    draw.text((pos_x, pos_y), texto, font=fonte, fill=(255, 255, 255, 245))

    img.save(caminho_saida_png, "PNG")
    return caminho_saida_png


class ShortsAssembler:
    """Orquestrador da montagem automatizada de clipes de vídeos curtos."""

    def __init__(self, callback_progresso: Optional[Callable[[float, str], None]] = None):
        self.callback_progresso = callback_progresso or (lambda p, m: None)

    def progresso(self, pct: float, msg: str):
        print(f"[ShortsAssembler] [{int(pct * 100)}%] {msg}")
        self.callback_progresso(pct, msg)

    def montar_video_curto(
        self,
        lista_clipes: List[str],
        titulo_projeto: str = "short_viral",
        tipo_transicao: str = "crossfade",  # 'corte_seco', 'crossfade', 'slide_left'
        duracao_transicao: float = 0.3,
        efeito_sonoro_transicao: Optional[str] = "whoosh",  # 'whoosh', 'swoosh', 'punch' ou None
        ganho_audio_db: float = 2.0,
        marca_dagua: Optional[str] = None,
        trilha_bgm: Optional[str] = None,
        volume_bgm: float = 0.15,
        fps: int = 30
    ) -> Dict[str, Any]:
        """
        Executa a junção dos clipes sequenciais em um único vídeo vertical 9:16 (1080x1920).
        """
        if not lista_clipes:
            raise ValueError("A lista de clipes para montagem está vazia.")

        self.progresso(0.05, "Validando e ordenando clipes das cenas...")
        clipes_ordenados = ordenar_arquivos_naturalmente(lista_clipes)

        for c in clipes_ordenados:
            if not os.path.exists(c):
                raise FileNotFoundError(f"Arquivo de clipe não encontrado: {c}")

        os.makedirs(os.path.join("output", "curtos", "videos"), exist_ok=True)
        os.makedirs("temp", exist_ok=True)

        nome_sanitizado = re.sub(r'[^\w\-_\.]', '_', titulo_projeto)[:35]
        caminho_saida_final = os.path.join("output", "curtos", "videos", f"{nome_sanitizado}_9x16.mp4")

        # 1. Padronizar cada clipe individual para 1080x1920 (9:16), mesmo FPS e áudio estéreo
        clipes_padronizados = []
        qtd = len(clipes_ordenados)

        for i, caminho_clipe in enumerate(clipes_ordenados):
            pct = 0.10 + (0.40 * (i / qtd))
            self.progresso(pct, f"Padronizando clipe da Cena {i+1} de {qtd} (9:16)...")

            clipe_temp = os.path.join("temp", f"clipe_padrao_{i+1}.mp4")

            # Filtro FFmpeg para ajuste perfeito de proporção:
            # Re-escala para preencher 1080x1920 preservando aspecto, centralizando e cortando excesso suavemente
            filtro_video = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
            
            # Filtro de áudio com normalização e ganho
            filtro_audio = f"volume={ganho_audio_db}dB,aformat=sample_rates=44100:channel_layouts=stereo"

            # Verifica se o clipe de entrada tem áudio
            tem_audio = True
            try:
                probe_cmd = [
                    os.path.join(os.path.dirname(FFMPEG_EXE), "ffprobe.exe"),
                    "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type",
                    "-of", "default=noprint_wrappers=1:nokey=1", caminho_clipe
                ]
                res_audio = subprocess.check_output(probe_cmd, text=True, stderr=subprocess.PIPE).strip()
                if not res_audio:
                    tem_audio = False
            except Exception:
                tem_audio = True

            cmd_padrao = [
                FFMPEG_EXE, "-y",
                "-i", caminho_clipe
            ]

            if not tem_audio:
                # Se o clipe gerado não veio com som, insere silêncio correspondente à duração
                cmd_padrao += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]

            cmd_padrao += [
                "-vf", filtro_video,
                "-r", str(fps),
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-pix_fmt", "yuv420p"
            ]

            if tem_audio:
                cmd_padrao += ["-af", filtro_audio, "-c:a", "aac", "-b:a", "192k"]
            else:
                cmd_padrao += ["-c:a", "aac", "-shortest"]

            cmd_padrao.append(clipe_temp)

            proc = subprocess.run(cmd_padrao, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if proc.returncode != 0:
                raise RuntimeError(f"Erro ao padronizar clipe {caminho_clipe}: {proc.stderr.decode('utf-8', errors='ignore')}")

            clipes_padronizados.append(clipe_temp)

        # 2. Junção dos clipes (Concatenação)
        self.progresso(0.55, f"Unindo {len(clipes_padronizados)} clipes com transições...")
        
        caminho_intermediario = os.path.join("temp", "juncao_clipes.mp4")

        # Concatenação inteligente
        if tipo_transicao == "corte_seco" or len(clipes_padronizados) == 1:
            # Concat demuxer rápido
            lista_txt = os.path.join("temp", "lista_concat.txt")
            with open(lista_txt, "w", encoding="utf-8") as f:
                for cp in clipes_padronizados:
                    caminho_abs = os.path.abspath(cp).replace("\\", "/")
                    f.write(f"file '{caminho_abs}'\n")

            cmd_concat = [
                FFMPEG_EXE, "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", lista_txt,
                "-c", "copy",
                caminho_intermediario
            ]
            subprocess.run(cmd_concat, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        elif tipo_transicao == "crossfade":
            # Usando MoviePy / xfade para transição suave de vídeo e áudio
            from moviepy import VideoFileClip, concatenate_videoclips
            clips_objs = [VideoFileClip(cp) for cp in clipes_padronizados]
            try:
                final_obj = concatenate_videoclips(clips_objs, method="compose", padding=-duracao_transicao)
                final_obj.write_videofile(
                    caminho_intermediario,
                    fps=fps,
                    codec="libx264",
                    audio_codec="aac",
                    preset="ultrafast",
                    logger=None
                )
            finally:
                for c in clips_objs:
                    c.close()
        else:
            # Fallback para concat demuxer
            lista_txt = os.path.join("temp", "lista_concat.txt")
            with open(lista_txt, "w", encoding="utf-8") as f:
                for cp in clipes_padronizados:
                    caminho_abs = os.path.abspath(cp).replace("\\", "/")
                    f.write(f"file '{caminho_abs}'\n")
            cmd_concat = [
                FFMPEG_EXE, "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", lista_txt,
                "-c", "copy",
                caminho_intermediario
            ]
            subprocess.run(cmd_concat, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # 3. Adicionar Efeitos Sonoros de Transição (SFX) e BGM
        self.progresso(0.75, "Aplicando efeitos sonoros e ajustes finais de áudio...")

        caminho_com_audio = os.path.join("temp", "audio_final_curtos.mp4")
        
        # Calcular timestamps onde ocorrem as transições
        timestamps_transicoes = []
        tempo_acumulado = 0.0
        for cp in clipes_padronizados[:-1]:
            d = obter_duracao_video(cp)
            tempo_acumulado += d
            timestamps_transicoes.append(tempo_acumulado)

        caminho_sfx = None
        if efeito_sonoro_transicao and efeito_sonoro_transicao != "nenhum":
            possivel_sfx = os.path.join("assets", "sfx", f"{efeito_sonoro_transicao}.wav")
            if os.path.exists(possivel_sfx):
                caminho_sfx = possivel_sfx

        # Se houver SFX ou BGM, mixamos via MoviePy / FFmpeg
        if caminho_sfx or (trilha_bgm and os.path.exists(trilha_bgm)):
            from moviepy import VideoFileClip, AudioFileClip, CompositeAudioClip
            v_clip = VideoFileClip(caminho_intermediario)
            audios_a_misturar = [v_clip.audio]

            # SFX nas transições
            if caminho_sfx:
                for ts in timestamps_transicoes:
                    sfx_clip = AudioFileClip(caminho_sfx).with_volume_scaled(0.5).with_start(max(0.0, ts - 0.15))
                    audios_a_misturar.append(sfx_clip)

            # Trilha BGM
            if trilha_bgm and os.path.exists(trilha_bgm):
                bgm_clip = AudioFileClip(trilha_bgm).with_volume_scaled(volume_bgm)
                # Loop se o vídeo for mais longo que a música
                if bgm_clip.duration < v_clip.duration:
                    vezes = math.ceil(v_clip.duration / bgm_clip.duration)
                    from moviepy import concatenate_audioclips
                    bgm_clip = concatenate_audioclips([bgm_clip] * vezes)
                bgm_clip = bgm_clip.subclipped(0, v_clip.duration)
                audios_a_misturar.append(bgm_clip)

            audio_composto = CompositeAudioClip(audios_a_misturar)
            video_mixado = v_clip.with_audio(audio_composto)
            video_mixado.write_videofile(
                caminho_com_audio,
                fps=fps,
                codec="libx264",
                audio_codec="aac",
                preset="ultrafast",
                logger=None
            )
            v_clip.close()
            arquivo_base = caminho_com_audio
        else:
            arquivo_base = caminho_intermediario

        # 4. Adicionar Marca d'Água (se configurada)
        if marca_dagua and marca_dagua.strip():
            self.progresso(0.90, f"Inserindo marca d'água '{marca_dagua}'...")
            overlay_png = criar_overlay_marca_dagua(marca_dagua.strip())
            cmd_marca = [
                FFMPEG_EXE, "-y",
                "-i", arquivo_base,
                "-i", overlay_png,
                "-filter_complex", "[0:v][1:v]overlay=0:0[v]",
                "-map", "[v]",
                "-map", "0:a?",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "18",
                "-c:a", "copy",
                caminho_saida_final
            ]
            subprocess.run(cmd_marca, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        else:
            # Apenas move/renomeia para o arquivo final
            import shutil
            shutil.copyfile(arquivo_base, caminho_saida_final)

        duracao_total = obter_duracao_video(caminho_saida_final)
        tamanho_mb = os.path.getsize(caminho_saida_final) / (1024 * 1024)

        self.progresso(1.0, f"Vídeo final concluído: {os.path.basename(caminho_saida_final)} ({duracao_total:.1f}s, {tamanho_mb:.1f}MB)")

        return {
            "sucesso": True,
            "caminho_video": caminho_saida_final,
            "titulo": titulo_projeto,
            "duracao_segundos": duracao_total,
            "tamanho_mb": round(tamanho_mb, 2),
            "qtd_cenas": len(clipes_ordenados)
        }
