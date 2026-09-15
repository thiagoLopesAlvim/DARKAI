"""
Módulo main.py
Orquestrador unificado da Pipeline Canal Dark (Fase 1 e Fase 2).
Conecta todos os módulos:
1. Roteiro (Google Gemini)
2. Áudio (ElevenLabs / Contingência)
3. Sincronização (Whisper Local)
4. Imagens IA (Pollinations Flux / Gemini)
5. Vídeo Final (MoviePy + Pillow)
6. Upload YouTube (YouTube Data API v3)
"""

import os
import sys
import json
import argparse
from typing import Optional, Dict, Any, Callable
from dotenv import load_dotenv

load_dotenv()

import banco_dados
from gerador_roteiro import gerar_roteiro
from gerador_audio import gerar_audio
from sincronizador import sincronizar_audio
from gerador_imagens import gerar_imagens_para_roteiro
from editor_video import renderizar_video_moviepy
from uploader_youtube import upload_video_youtube


class DarkVideoPipeline:
    """Orquestrador principal para geração automatizada completa de vídeos Dark."""

    def __init__(
        self,
        callback_progresso: Optional[Callable[[float, str], None]] = None,
        callback_log: Optional[Callable[[str], None]] = None
    ):
        self.callback_progresso = callback_progresso or (lambda p, m: None)
        self.callback_log = callback_log or (lambda msg: print(f"[Pipeline] {msg}"))

    def log(self, mensagem: str):
        self.callback_log(mensagem)

    def progresso(self, porcentagem: float, status: str):
        self.log(f"[{int(porcentagem * 100)}%] {status}")
        self.callback_progresso(porcentagem, status)

    def etapa_1_roteiro(
        self,
        tema: str,
        duracao_minima_minutos: float = 2.0,
        respostas_usuario: Optional[Dict[str, str]] = None,
        api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Etapa 1: Gera o roteiro estruturado com o Google Gemini."""
        self.progresso(0.08, f"Gerando roteiro ({duracao_minima_minutos:.1f}m) com IA para: '{tema}'...")
        roteiro = gerar_roteiro(
            tema=tema,
            duracao_minima_minutos=duracao_minima_minutos,
            respostas_usuario=respostas_usuario,
            api_key=api_key
        )
        qtd_cenas = len(roteiro.get("cenas", []))
        self.progresso(0.20, f"Roteiro gerado ({qtd_cenas} cenas estruturadas).")
        return roteiro

    def etapa_2_audio(
        self,
        roteiro_dados: Dict[str, Any],
        api_key: Optional[str] = None,
        voice_id: Optional[str] = None,
        caminho_audio_proprio: Optional[str] = None
    ) -> str:
        """Etapa 2: Gera o áudio da narração com a ElevenLabs ou usa gravação própria."""
        msg = "Carregando gravação própria do criador..." if caminho_audio_proprio else "Sintetizando narração em áudio MP3..."
        self.progresso(0.25, msg)
        caminho_audio = gerar_audio(
            roteiro_dados=roteiro_dados,
            api_key=api_key,
            voice_id=voice_id,
            caminho_audio_proprio=caminho_audio_proprio
        )
        self.progresso(0.40, f"Áudio gerado: {os.path.basename(caminho_audio)}")
        return caminho_audio

    def etapa_3_sincronizacao(
        self,
        caminho_audio: str,
        roteiro_dados: Optional[Dict[str, Any]] = None,
        whisper_model: Optional[str] = None,
        forcar_fallback: bool = False
    ) -> Dict[str, Any]:
        """Etapa 3: Sincroniza áudio e extrai timestamps com Whisper."""
        self.progresso(0.45, "Processando transcrição e marcações de tempo...")
        dados_sync = sincronizar_audio(
            caminho_audio=caminho_audio,
            roteiro_dados=roteiro_dados,
            whisper_model_size=whisper_model,
            forcar_fallback=forcar_fallback
        )
        total_legendas = len(dados_sync.get("legendas_timestamps", []))
        self.progresso(0.55, f"Sincronização concluída ({total_legendas} legendas sincronizadas).")
        return dados_sync

    def etapa_4_imagens(
        self,
        roteiro_dados: Dict[str, Any],
        aspect_ratio: str = "16:9",
        provedor: str = "pollinations"
    ) -> Dict[int, str]:
        """Etapa 4: Gera imagens com IA cinematográfica para cada cena."""
        self.progresso(0.60, "Gerando imagens das cenas com IA (Pollinations Flux)...")
        def cb_img(p, m):
            self.progresso(0.60 + (p * 0.20), m)

        imagens = gerar_imagens_para_roteiro(
            roteiro_dados=roteiro_dados,
            aspect_ratio=aspect_ratio,
            provedor=provedor,
            callback_progresso=cb_img
        )
        self.progresso(0.80, f"Todas as {len(imagens)} imagens foram geradas!")
        return imagens

    def etapa_5_video(
        self,
        caminho_audio: str,
        dados_sync: Dict[str, Any],
        roteiro_dados: Optional[Dict[str, Any]] = None,
        aspect_ratio: str = "16:9",
        imagens_cenas: Optional[Dict[int, str]] = None
    ) -> str:
        """Etapa 5: Monta e renderiza o vídeo final com MoviePy."""
        self.progresso(0.82, f"Renderizando vídeo MP4 final ({aspect_ratio})...")
        caminho_video = renderizar_video_moviepy(
            caminho_audio=caminho_audio,
            dados_sincronizacao=dados_sync,
            roteiro_dados=roteiro_dados,
            aspect_ratio=aspect_ratio,
            callback_progresso=self.progresso,
            imagens_cenas=imagens_cenas
        )
        self.progresso(0.95, f"Vídeo final concluído: {os.path.basename(caminho_video)}")
        return caminho_video

    def etapa_6_youtube(
        self,
        caminho_video: str,
        roteiro_dados: Dict[str, Any],
        privacidade: str = "unlisted",
        caminho_thumbnail: Optional[str] = None,
        forcar_simulacao: bool = False
    ) -> Dict[str, Any]:
        """Etapa 6: Publica o vídeo no YouTube."""
        self.progresso(0.96, "Iniciando publicação no canal do YouTube...")
        def cb_yt(p, m):
            self.progresso(0.96 + (p * 0.04), m)

        resultado = upload_video_youtube(
            caminho_video=caminho_video,
            titulo=roteiro_dados.get("titulo", "Vídeo Canal Dark"),
            descricao=roteiro_dados.get("descricao", ""),
            tags=roteiro_dados.get("tags", []),
            privacidade=privacidade,
            caminho_thumbnail=caminho_thumbnail,
            forcar_simulacao=forcar_simulacao,
            callback_progresso=cb_yt
        )
        self.progresso(1.00, f"YouTube: {resultado.get('video_url', 'Concluído')}")
        return resultado

    def executar_completo(
        self,
        tema: str,
        aspect_ratio: str = "16:9",
        whisper_model: Optional[str] = None,
        provedor_imagens: str = "pollinations",
        duracao_minima_minutos: float = 2.0,
        respostas_usuario: Optional[Dict[str, str]] = None,
        voice_id: Optional[str] = None,
        caminho_audio_proprio: Optional[str] = None,
        publicar_youtube: bool = False,
        privacidade_yt: str = "unlisted"
    ) -> Dict[str, Any]:
        """Executa todas as etapas das Fases 1 & 2 de forma sequencial."""
        self.log(f"Iniciando pipeline completa para: '{tema}' (Mínimo: {duracao_minima_minutos:.1f}m)")
        
        # 1. Roteiro
        roteiro = self.etapa_1_roteiro(
            tema=tema,
            duracao_minima_minutos=duracao_minima_minutos,
            respostas_usuario=respostas_usuario
        )
        # 2. Áudio
        audio_path = self.etapa_2_audio(
            roteiro_dados=roteiro,
            voice_id=voice_id,
            caminho_audio_proprio=caminho_audio_proprio
        )
        # 3. Sincronização
        sync_dados = self.etapa_3_sincronizacao(audio_path, roteiro, whisper_model=whisper_model)
        # 4. Imagens IA
        imagens_cenas = self.etapa_4_imagens(roteiro, aspect_ratio=aspect_ratio, provedor=provedor_imagens)
        # 5. Vídeo Final com Imagens
        video_path = self.etapa_5_video(audio_path, sync_dados, roteiro, aspect_ratio=aspect_ratio, imagens_cenas=imagens_cenas)

        # Salva no banco de dados SQLite
        try:
            duracao_seg = sync_dados.get("duracao_total", 0.0) if sync_dados else 0.0
            voz_tipo = "propria" if caminho_audio_proprio else ("clonada" if voice_id else "padrao")
            banco_dados.salvar_video_historico({
                "tema": tema,
                "titulo": roteiro.get("titulo", "Sem título"),
                "descricao": roteiro.get("descricao", ""),
                "tags": roteiro.get("tags", []),
                "duracao_segundos": duracao_seg,
                "aspect_ratio": aspect_ratio,
                "voz_tipo": voz_tipo,
                "voice_id": voice_id or "",
                "qtd_cenas": len(roteiro.get("cenas", [])),
                "caminho_video": video_path,
                "caminho_audio": audio_path,
                "caminho_roteiro": roteiro.get("_caminho_arquivo", "")
            })
            self.log("Registro de histórico salvo no SQLite.")
        except Exception as e_bd:
            self.log(f"Aviso SQLite: {e_bd}")

        yt_resultado = None
        if publicar_youtube:
            thumb = imagens_cenas.get(1) if imagens_cenas else None
            yt_resultado = self.etapa_6_youtube(video_path, roteiro, privacidade=privacidade_yt, caminho_thumbnail=thumb)
            try:
                banco_dados.salvar_video_historico({
                    "tema": tema,
                    "titulo": roteiro.get("titulo", "Sem título"),
                    "caminho_video": video_path,
                    "youtube_url": yt_resultado.get("video_url", ""),
                    "youtube_status": privacidade_yt
                })
            except Exception:
                pass

        resultado = {
            "tema": tema,
            "roteiro": roteiro,
            "audio_path": audio_path,
            "sync_dados": sync_dados,
            "imagens_cenas": imagens_cenas,
            "video_path": video_path,
            "youtube": yt_resultado
        }
        self.log("Pipeline completa concluída com sucesso!")
        return resultado


def main():
    parser = argparse.ArgumentParser(description="DarkAI - Pipeline Canal Dark (Fases 1 & 2)")
    parser.add_argument("--tema", type=str, required=True, help="Tema do vídeo")
    parser.add_argument("--duracao", type=float, default=2.0, help="Duração mínima do vídeo em minutos")
    parser.add_argument("--voice_id", type=str, default=None, help="ID da voz ElevenLabs (clonada ou padrão)")
    parser.add_argument("--audio_proprio", type=str, default=None, help="Caminho para áudio próprio gravado")
    parser.add_argument("--aspect", type=str, default="16:9", choices=["16:9", "9:16"], help="Formato")
    parser.add_argument("--whisper", type=str, default="base", help="Modelo Whisper")
    parser.add_argument("--provedor_img", type=str, default="pollinations", choices=["pollinations", "gemini"], help="Provedor de IA para imagens")
    parser.add_argument("--youtube", action="store_true", help="Publicar no YouTube")
    parser.add_argument("--privacidade", type=str, default="unlisted", choices=["unlisted", "private", "public"], help="Privacidade no YouTube")
    args = parser.parse_args()

    pipeline = DarkVideoPipeline()
    resultado = pipeline.executar_completo(
        tema=args.tema,
        aspect_ratio=args.aspect,
        whisper_model=args.whisper,
        provedor_imagens=args.provedor_img,
        duracao_minima_minutos=args.duracao,
        voice_id=args.voice_id,
        caminho_audio_proprio=args.audio_proprio,
        publicar_youtube=args.youtube,
        privacidade_yt=args.privacidade
    )
    print("\n" + "="*50)
    print("VÍDEO FINAL CONCLUÍDO (FASES 1 & 2):")
    print(f"Arquivo MP4: {resultado['video_path']}")
    if resultado.get("youtube"):
        print(f"YouTube URL: {resultado['youtube'].get('video_url')}")
    print("="*50)


if __name__ == "__main__":
    main()
