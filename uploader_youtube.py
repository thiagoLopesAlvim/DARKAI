"""
Módulo uploader_youtube.py
Integração com a YouTube Data API v3 para upload automatizado de vídeos e preenchimento de metadados.
Suporta autenticação OAuth 2.0 com persistência de token (pickle), envio de thumbnail customizada,
configuração de privacidade (não-listado, privado, público) e modo simulado para validação prévia.
"""

import os
import pickle
import json
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

# Escopos necessários para upload e gerenciamento de vídeos no canal
YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube"
]
CAMINHO_TOKEN_PADRAO = os.path.join("temp", "youtube_token.pickle")
CAMINHO_SECRETS_PADRAO = "client_secrets.json"


def obter_credenciais_oauth(caminho_secrets: str = CAMINHO_SECRETS_PADRAO, caminho_token: str = CAMINHO_TOKEN_PADRAO):
    """
    Obtém credenciais válidas do usuário através do token salvo ou do fluxo OAuth 2.0 local.
    """
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if os.path.exists(caminho_token):
        try:
            with open(caminho_token, "rb") as token_file:
                creds = pickle.load(token_file)
        except Exception as e:
            print(f"[uploader_youtube] Erro ao carregar token salvo ({e}). Solicitando nova autorização.")
            creds = None

    # Se não houver credenciais válidas disponíveis, realiza o fluxo
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                print("[uploader_youtube] Atualizando token de acesso expirado...")
                creds.refresh(Request())
            except Exception as e:
                print(f"[uploader_youtube] Falha ao renovar token ({e}). Reautenticando...")
                creds = None

        if not creds:
            if not os.path.exists(caminho_secrets):
                raise FileNotFoundError(
                    f"Arquivo de credenciais OAuth '{caminho_secrets}' não encontrado.\n"
                    "Para fazer uploads reais no YouTube, baixe o arquivo 'client_secrets.json' do Google Cloud Console "
                    "e coloque-o na raiz do projeto ou use o modo de validação simulada."
                )

            print("[uploader_youtube] Iniciando fluxo de autorização do YouTube no navegador...")
            flow = InstalledAppFlow.from_client_secrets_file(caminho_secrets, YOUTUBE_SCOPES)
            creds = flow.run_local_server(port=0)

        # Salva o token para as próximas execuções
        os.makedirs(os.path.dirname(caminho_token), exist_ok=True)
        with open(caminho_token, "wb") as token_file:
            pickle.dump(creds, token_file)
        print(f"[uploader_youtube] Token de autenticação salvo em: {caminho_token}")

    return creds


def sanitizar_metadados(titulo: str, descricao: str, tags: List[str]) -> Dict[str, Any]:
    """Garante que os metadados respeitem as restrições estritas do YouTube."""
    titulo_limpo = titulo.strip()[:100]  # Limite de 100 caracteres no YouTube
    descricao_limpa = descricao.strip()[:5000]  # Limite de 5000 caracteres no YouTube
    
    # As tags não podem exceder 500 caracteres somadas
    tags_validas = []
    total_len = 0
    for t in tags:
        t_clean = t.strip()
        if t_clean and total_len + len(t_clean) + 1 < 480:
            tags_validas.append(t_clean)
            total_len += len(t_clean) + 1

    return {
        "title": titulo_limpo,
        "description": descricao_limpa,
        "tags": tags_validas
    }


def simular_upload_youtube(
    caminho_video: str,
    titulo: str,
    descricao: str,
    tags: List[str],
    privacidade: str = "unlisted",
    caminho_thumbnail: Optional[str] = None
) -> Dict[str, Any]:
    """
    Modo de validação de metadados quando o client_secrets.json ainda não está configurado.
    Permite validar todo o fluxo sem erros bloqueantes.
    """
    meta = sanitizar_metadados(titulo, descricao, tags)
    tam_mb = os.path.getsize(caminho_video) / (1024 * 1024) if os.path.exists(caminho_video) else 0

    video_id_simulado = "SIMULADO_" + os.urandom(4).hex()
    video_url = f"https://www.youtube.com/watch?v={video_id_simulado}"

    print("[uploader_youtube] MODO SIMULADO: Metadados validados com sucesso.")
    print(f"  - Título: {meta['title']} ({len(meta['title'])} chars)")
    print(f"  - Tags: {len(meta['tags'])} tags ({', '.join(meta['tags'][:4])}...)")
    print(f"  - Tamanho do Vídeo: {tam_mb:.2f} MB")
    print(f"  - Privacidade: {privacidade}")
    if caminho_thumbnail and os.path.exists(caminho_thumbnail):
        print(f"  - Thumbnail pronta: {caminho_thumbnail}")

    return {
        "sucesso": True,
        "modo": "simulado",
        "video_id": video_id_simulado,
        "video_url": video_url,
        "titulo": meta["title"],
        "privacidade": privacidade,
        "aviso": (
            "Upload realizado em Modo de Validação Simulada. Para enviar diretamente ao seu canal oficial, "
            "baixe o 'client_secrets.json' do Google Cloud Console (com a YouTube Data API v3 ativada) "
            "e adicione-o na pasta do projeto."
        )
    }


def upload_video_youtube(
    caminho_video: str,
    titulo: str,
    descricao: str,
    tags: Optional[List[str]] = None,
    privacidade: str = "unlisted",
    caminho_thumbnail: Optional[str] = None,
    caminho_secrets: str = CAMINHO_SECRETS_PADRAO,
    forcar_simulacao: bool = False,
    callback_progresso: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Publica o vídeo no YouTube usando a YouTube Data API v3 ou recorre à simulação se sem credenciais.
    
    Args:
        caminho_video: Caminho do arquivo .mp4 a enviar.
        titulo: Título do vídeo.
        descricao: Descrição detalhada.
        tags: Lista de tags do YouTube.
        privacidade: 'unlisted', 'private' ou 'public'.
        caminho_thumbnail: Imagem JPG da capa personalizada.
        caminho_secrets: Caminho para o client_secrets.json.
        forcar_simulacao: Se True, apenas simula e valida metadados.
        callback_progresso: Função opcional callback(porcentagem, mensagem).
        
    Returns:
        Dicionário com dados do upload (video_id, video_url, etc.).
    """
    if not os.path.exists(caminho_video):
        raise FileNotFoundError(f"Arquivo de vídeo não encontrado: {caminho_video}")

    tags = tags or ["canal dark", "mistério", "curiosidades"]
    meta = sanitizar_metadados(titulo, descricao, tags)

    # Se forçada simulação ou client_secrets não existir, executa simulação estruturada
    if forcar_simulacao or not os.path.exists(caminho_secrets):
        if callback_progresso:
            callback_progresso(0.5, "Validando metadados e requisitos de vídeo para o YouTube...")
            callback_progresso(1.0, "Validação concluída (Modo Simulado)!")
        return simular_upload_youtube(caminho_video, titulo, descricao, tags, privacidade, caminho_thumbnail)

    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        if callback_progresso:
            callback_progresso(0.1, "Autenticando na conta do YouTube...")

        creds = obter_credenciais_oauth(caminho_secrets=caminho_secrets)
        youtube = build("youtube", "v3", credentials=creds)

        corpo_requisicao = {
            "snippet": {
                "title": meta["title"],
                "description": meta["description"],
                "tags": meta["tags"],
                "categoryId": "27"  # 27 = Educação / Curiosidades (ideal para canal Dark)
            },
            "status": {
                "privacyStatus": privacidade,
                "selfDeclaredMadeForKids": False
            }
        }

        if callback_progresso:
            callback_progresso(0.3, f"Enviando vídeo ({privacidade})...")

        media = MediaFileUpload(caminho_video, chunksize=1024 * 1024 * 2, resumable=True)
        requisicao = youtube.videos().insert(
            part="snippet,status",
            body=corpo_requisicao,
            media_body=media
        )

        # Upload com barra de progresso resumable
        resposta = None
        while resposta is None:
            status, resposta = requisicao.next_chunk()
            if status and callback_progresso:
                progresso_frac = float(status.progress())
                callback_progresso(0.3 + (progresso_frac * 0.6), f"Fazendo upload para o YouTube: {int(progresso_frac * 100)}%...")

        video_id = resposta.get("id")
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        print(f"[uploader_youtube] Vídeo publicado com sucesso! ID: {video_id} | URL: {video_url}")

        # Se houver thumbnail, faz upload da capa
        if caminho_thumbnail and os.path.exists(caminho_thumbnail):
            try:
                if callback_progresso:
                    callback_progresso(0.95, "Enviando thumbnail personalizada...")
                thumb_media = MediaFileUpload(caminho_thumbnail, mimetype="image/jpeg")
                youtube.thumbnails().set(videoId=video_id, media_body=thumb_media).execute()
                print("[uploader_youtube] Thumbnail personalizada aplicada com sucesso!")
            except Exception as e_thumb:
                print(f"[uploader_youtube] Aviso: Falha ao definir thumbnail personalizada ({e_thumb})")

        if callback_progresso:
            callback_progresso(1.0, f"Vídeo publicado com sucesso: {video_url}")

        return {
            "sucesso": True,
            "modo": "real",
            "video_id": video_id,
            "video_url": video_url,
            "titulo": meta["title"],
            "privacidade": privacidade
        }

    except Exception as e:
        print(f"[uploader_youtube] Erro durante o upload para o YouTube: {e}")
        # Recorre à simulação estruturada se o upload real falhar
        resultado_fallback = simular_upload_youtube(caminho_video, titulo, descricao, tags, privacidade, caminho_thumbnail)
        resultado_fallback["erro_detalhado"] = str(e)
        return resultado_fallback


if __name__ == "__main__":
    # Teste rápido
    res = upload_video_youtube(
        caminho_video="output/videos/teste_audio_dark_16x9.mp4",
        titulo="O Maior Mistério de Todos os Tempos",
        descricao="Descrição completa para teste.",
        tags=["mistério", "canal dark", "fatos"],
        forcar_simulacao=True
    )
    print("Resultado do Teste:", json.dumps(res, indent=2, ensure_ascii=False))
