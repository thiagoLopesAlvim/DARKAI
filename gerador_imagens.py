"""
Módulo gerador_imagens.py
Responsável por gerar imagens cinematográficas via Inteligência Artificial para cada cena do roteiro.

Recursos principais:
1. 5 Estilos Visuais Fixos com modulação de iluminação, lentes e paletas de cor.
2. Bíblia de Consistência Visual (Storytelling): Extração e injeção de fichas imutáveis
   de personagens e cenários recorrentes entre cenas.
3. Refinamento de Prompts com Gemini & Injeção de Prompts Negativos.
4. Suporte nativo a Proporções 16:9 (Documentário Longo) e 9:16 (Shorts Verticais).
5. Múltiplos Provedores:
   - Pollinations AI (Flux) — Gratuito, rápido, ilimitado e alta qualidade Dark.
   - Google Gemini Image / "Nano Banana" (gemini-2.5-flash-image) com fallback transparente.
"""

import os
import re
import json
import urllib.parse
import requests
import concurrent.futures
import threading
from typing import Dict, Any, Optional, List, Tuple
from PIL import Image
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()


# ==============================================================================
# 🎨 1. PRESETS DE ESTILOS VISUAIS FIXOS
# ==============================================================================

ESTILOS_VISUAIS: Dict[str, Dict[str, str]] = {
    "dark_cinematic": {
        "id": "dark_cinematic",
        "nome": "Dark Cinematic",
        "emoji": "🎬",
        "descricao": "Contraste dramático, chiaroscuro, lente anamórfica 35mm e atmosfera sombria de suspense",
        "modificador_positivo": "cinematic film still, 35mm anamorphic lens, dramatic chiaroscuro lighting, deep mysterious shadows, volumetric fog, Kodak Vision3 color grading, 8k resolution, photorealistic masterpiece, moody atmosphere, ultra realistic",
        "prompt_negativo": "cartoon, anime, 3d render, oversaturated, bright daylight, bad anatomy, deformed face, blurry hands, text, watermark, signature, ugly, low resolution, plastic skin"
    },
    "analog_horror": {
        "id": "analog_horror",
        "nome": "Analog Horror (VHS 90s)",
        "emoji": "📼",
        "descricao": "Estética de fita VHS perturbadora, aberração cromática, ruído magnético e filmagem estilo CCTV",
        "modificador_positivo": "analog horror aesthetic, VHS tape artifact, chromatic aberration, 1990s videotape grain, CCTV camera surveillance angle, eerie liminal atmosphere, scanlines, found footage, low-key dim lighting, unsettling ambiance, authentic retro look",
        "prompt_negativo": "clean digital photo, modern cgi, vibrant shiny colors, text, subtitles, watermark, distorted faces, duplicate bodies, glossy, 3d render"
    },
    "hiper_realista": {
        "id": "hiper_realista",
        "nome": "Hiper-Realista 4K Documental",
        "emoji": "📷",
        "descricao": "Fotografia macro documental 8k, textura ultra-detalhada de pele e materiais, iluminação natural difusa",
        "modificador_positivo": "documentary photograph, Hasselblad 100MP camera, hyperdetailed textures, pores and dust particles, atmospheric natural dim lighting, high dynamic range, National Geographic investigative documentary style, sharp focus, RAW photo, realistic depth of field",
        "prompt_negativo": "cgi, render, cartoon, plastic skin, oversmoothed, low quality, extra fingers, watermark, logo, text, painting, illustration, doll"
    },
    "dark_vintage": {
        "id": "dark_vintage",
        "nome": "Ilustração Dark Vintage (Gravura Gótica)",
        "emoji": "📜",
        "descricao": "Estilo xilogravura, nanquim gótico e ilustração de arquivo confidencial antigo em pergaminho escurecido",
        "modificador_positivo": "dark vintage gothic engraving, Victorian dark illustration, detailed ink hatching, woodcut print style, aged sepia and charcoal parchment, mysterious occult grimoire aesthetic, Gustav Doré style, ominous line art, historical engraving",
        "prompt_negativo": "modern photography, neon colors, glossy 3d, bright vibrant colors, plastic, digital anime, watermark, text, low quality"
    },
    "cyberpunk_noir": {
        "id": "cyberpunk_noir",
        "nome": "Dystopian Cyberpunk Noir",
        "emoji": "🤖",
        "descricao": "Chuva ácida constante, néon decadente refletido em asfalto molhado e sombras opressivas",
        "modificador_positivo": "dystopian cyberpunk noir, relentless rain, flickering dim neon reflections on wet asphalt, steam rising from grates, towering oppressive megastructures, moody blade runner aesthetic, cinematic depth of field, high contrast night scene",
        "prompt_negativo": "bright happy daytime, cartoon, low polygon, blurry textures, deformed limbs, text, logo, oversaturated pink, amateur"
    }
}


# ==============================================================================
# 👤 2. MODELOS DA BÍBLIA VISUAL (CONSISTÊNCIA DE STORYTELLING)
# ==============================================================================

class PersonagemBiblia(BaseModel):
    nome: str = Field(description="Nome ou arquétipo do personagem (ex: 'Detetive Viktor', 'Cientista Enigmático')")
    descricao_visual_fixa: str = Field(description="Ficha física e vestimenta imutável detalhada em inglês (ex: '45-year-old tall Caucasian man, deep scar across left brow, sharp jawline, messy dark graying hair, wearing a worn charcoal trench coat with turned-up collar and black leather gloves')")
    cenas_recorrentes: List[int] = Field(default_factory=list, description="IDs das cenas onde o personagem aparece")

class EntornoBiblia(BaseModel):
    nome: str = Field(description="Nome do cenário ou ambiente (ex: 'Bunker Subterrâneo 7', 'Laboratório Abandonado')")
    descricao_visual_fixa: str = Field(description="Elementos arquitetônicos e iluminação imutáveis em inglês (ex: 'Decaying brutalist Soviet concrete bunker, rusted overhead pipes leaking dark moisture, flickering red emergency floodlights, heavy reinforced blast door in background, eerie low-lying cold mist')")
    cenas_recorrentes: List[int] = Field(default_factory=list, description="IDs das cenas que se passam neste local")

class BibliaVisualRoteiro(BaseModel):
    personagens: List[PersonagemBiblia] = Field(default_factory=list, description="Lista de personagens recorrentes detectados")
    entornos: List[EntornoBiblia] = Field(default_factory=list, description="Lista de cenários recorrentes detectados")


def sanitizar_nome_arquivo(texto: str) -> str:
    """Converte um texto em uma string segura para nome de arquivo."""
    texto = texto.lower()
    texto = re.sub(r'[^\w\s-]', '', texto)
    return re.sub(r'[-\s]+', '_', texto).strip('_')[:50]


# ==============================================================================
# 🧠 3. EXTRAÇÃO DE BÍBLIA VISUAL E REFINAMENTO COM GEMINI
# ==============================================================================

def extrair_biblia_visual(roteiro_dados: Dict[str, Any], api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Analisa o roteiro com o Gemini e extrai uma Bíblia de Personagens e Entornos
    recorrentes para manter consistência visual absoluta nas imagens.
    """
    chave = api_key or os.getenv("GEMINI_API_KEY", "").strip()
    cenas = roteiro_dados.get("cenas", [])
    titulo = roteiro_dados.get("titulo", "História Dark")

    # Fallback básico caso o Gemini não esteja configurado
    fallback_biblia = {
        "personagens": [
            {
                "nome": "Protagonista Oculto",
                "descricao_visual_fixa": "Mysterious investigator in dark silhouette, 40s, sharp features, wearing an unbuttoned vintage dark overcoat, illuminated by faint ambient light",
                "cenas_recorrentes": [1, 2]
            }
        ],
        "entornos": [
            {
                "nome": "Cenário Principal",
                "descricao_visual_fixa": "Dimly lit decaying historic room with damp stone walls, heavy mahogany desk covered in classified papers, dramatic shadows",
                "cenas_recorrentes": [1, 2, 3]
            }
        ]
    }

    if not chave or "sua_chave" in chave.lower() or not cenas:
        return fallback_biblia

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=chave)

        resumo_cenas = []
        for c in cenas:
            resumo_cenas.append(f"Cena {c.get('cena_id')}: {c.get('narracao', '')} | Visual: {c.get('visual_prompt', '')}")

        prompt = f"""
Você é um Diretor de Arte Cinematográfica para produções audiovisuais do YouTube.
Analise este roteiro de storytelling/documentário dark:

TÍTULO: "{titulo}"
CENAS:
{chr(10).join(resumo_cenas)}

Sua missão:
1. Identificar até 2 PERSONAGENS principais ou recorrentes que aparecem na história.
   - Forneça uma ficha visual hiper-detalhada em INGLÊS com traços físicos permanentes (idade aparente, etnia, cabelo, cicatrizes, vestimentas específicas e cores de roupa imutáveis).
   - Indique em quais cenas_recorrentes eles atuam.
2. Identificar até 2 ENTORNOS/CENÁRIOS recorrentes (ex: sala de interrogatório, bunker, arquivo secreto).
   - Forneça uma ficha arquitetônica e de iluminação detalhada em INGLÊS com materiais, iluminação de fundo e elementos imutáveis.
   - Indique em quais cenas_recorrentes esse cenário é o fundo.

Retorne em formato JSON estrito conforme o schema.
"""
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=BibliaVisualRoteiro,
            temperature=0.4
        )
        resposta = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip(),
            contents=prompt,
            config=config
        )
        dados = json.loads(resposta.text)
        print(f"[gerador_imagens] Bíblia Visual extraída com sucesso: {len(dados.get('personagens', []))} personagens e {len(dados.get('entornos', []))} cenários.")
        return dados
    except Exception as e:
        print(f"[gerador_imagens] Aviso: Erro ao extrair Bíblia Visual via Gemini ({e}). Usando padrão.")
        return fallback_biblia


def refinar_prompt_com_ia(
    prompt_original: str,
    estilo_id: str = "dark_cinematic",
    biblia_visual: Optional[Dict[str, Any]] = None,
    cena_id: int = 1,
    narracao: str = "",
    api_key: Optional[str] = None
) -> Dict[str, str]:
    """
    Refina o prompt visual de uma cena combinando o estilo visual escolhido,
    as fichas de personagens/cenários da Bíblia Visual e termos cinematográficos.
    
    Retorna:
        {"prompt_positivo": str, "prompt_negativo": str}
    """
    estilo_info = ESTILOS_VISUAIS.get(estilo_id, ESTILOS_VISUAIS["dark_cinematic"])
    modificador_estilo = estilo_info["modificador_positivo"]
    prompt_negativo = estilo_info["prompt_negativo"]

    # Injeção contextual da Bíblia Visual para esta cena
    detalhes_consistencia = []
    if biblia_visual:
        for p in biblia_visual.get("personagens", []):
            cenas_p = p.get("cenas_recorrentes", [])
            if not cenas_p or cena_id in cenas_p:
                detalhes_consistencia.append(f"Character '{p.get('nome')}': {p.get('descricao_visual_fixa')}")

        for e in biblia_visual.get("entornos", []):
            cenas_e = e.get("cenas_recorrentes", [])
            if not cenas_e or cena_id in cenas_e:
                detalhes_consistencia.append(f"Environment '{e.get('nome')}': {e.get('descricao_visual_fixa')}")

    bloco_consistencia = " | ".join(detalhes_consistencia) if detalhes_consistencia else ""

    # Tentativa de expansão avançada com Gemini se a chave estiver configurada
    chave = api_key or os.getenv("GEMINI_API_KEY", "").strip()
    if chave and "sua_chave" not in chave.lower() and len(prompt_original) > 5:
        try:
            from google import genai
            client = genai.Client(api_key=chave)

            instrucao = f"""
Refine this visual scene prompt for a high-end Dark YouTube video generator.
Original scene prompt: "{prompt_original}"
Narration context: "{narracao[:150]}"
Visual Style: {estilo_info['nome']} ({modificador_estilo})
Character/Environment Bible (MUST KEEP CONSISTENT): {bloco_consistencia}

Output ONLY a single optimized, detailed English prompt (max 90 words). Include camera framing, volumetric lighting, specific focal depth, and scene action without markdown or quotation marks.
"""
            resp = client.models.generate_content(
                model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip(),
                contents=instrucao
            )
            prompt_expandido = resp.text.strip().replace('"', '').replace('\n', ' ')
            if len(prompt_expandido) > 15:
                prompt_final = f"{prompt_expandido}, {modificador_estilo}"
                return {
                    "prompt_positivo": prompt_final,
                    "prompt_negativo": prompt_negativo
                }
        except Exception:
            pass  # Fallback gracioso para montagem algorítmica

    # Montagem algorítmica direta (rápida e sem latência)
    componentes = [prompt_original.strip()]
    if bloco_consistencia:
        componentes.append(bloco_consistencia)
    componentes.append(modificador_estilo)

    prompt_positivo = ", ".join([c for c in componentes if c])
    return {
        "prompt_positivo": prompt_positivo,
        "prompt_negativo": prompt_negativo
    }


# ==============================================================================
# 🎨 4. GERADORES DE IMAGEM (POLLINATIONS FLUX & GEMINI NANO BANANA)
# ==============================================================================

def gerar_imagem_pollinations(
    prompt: str,
    caminho_saida: str,
    aspect_ratio: str = "16:9",
    prompt_negativo: Optional[str] = None,
    timeout: int = 45,
    seed: Optional[int] = None
) -> bool:
    """
    Gera imagem via Pollinations AI utilizando o modelo Flux.
    Totalmente gratuito, rápido e sem dependência de cotas.
    """
    if aspect_ratio == "9:16":
        largura, altura = 720, 1280
    else:
        largura, altura = 1280, 720

    seed_val = seed if seed is not None else int(os.urandom(2).hex(), 16)
    prompt_codificado = urllib.parse.quote(prompt.strip())

    url = (
        f"https://image.pollinations.ai/prompt/{prompt_codificado}"
        f"?width={largura}&height={altura}&model=flux&nologo=true&seed={seed_val}"
    )
    if prompt_negativo:
        neg_codificado = urllib.parse.quote(prompt_negativo.strip())
        url += f"&negative={neg_codificado}"

    try:
        resposta = requests.get(url, timeout=timeout)
        if resposta.status_code == 200 and len(resposta.content) > 5000:
            with open(caminho_saida, "wb") as f:
                f.write(resposta.content)
            # Valida que o arquivo é uma imagem válida
            with Image.open(caminho_saida) as img:
                img.verify()
            return True
        else:
            print(f"[gerador_imagens] Pollinations retornou HTTP {resposta.status_code}")
    except Exception as e:
        print(f"[gerador_imagens] Erro na requisição ao Pollinations: {e}")

    return False


def gerar_imagem_gemini(
    prompt: str,
    caminho_saida: str,
    api_key: Optional[str] = None,
    aspect_ratio: str = "16:9"
) -> bool:
    """
    Gera imagem via Google Gemini ("Nano Banana" / gemini-2.5-flash-image / gemini-3.1-flash-image).
    Se houver erro de cota (429) ou ausência de suporte no plano, retorna False para acionar fallback.
    """
    chave = api_key or os.getenv("GEMINI_API_KEY", "").strip()
    if not chave or "sua_chave" in chave.lower():
        return False

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=chave)

        # Mapeia proporção para formato do SDK
        proporcao_sdk = "9:16" if aspect_ratio == "9:16" else "16:9"

        # Modelos Nano Banana no Gemini
        modelos_tentar = ["gemini-3.1-flash-image", "gemini-3.1-flash-lite-image", "gemini-2.5-flash-image"]
        for mod in modelos_tentar:
            try:
                resposta = client.models.generate_content(
                    model=mod,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE"],
                        image_config=types.ImageConfig(aspect_ratio=proporcao_sdk)
                    )
                )
                if resposta and resposta.parts:
                    for part in resposta.parts:
                        if getattr(part, "inline_data", None):
                            img = part.as_image()
                            img.save(caminho_saida)
                            print(f"[gerador_imagens] [OK] Imagem gerada com sucesso via Google Nano Banana ({mod})!")
                            return True
            except Exception as e_mod:
                if "RESOURCE_EXHAUSTED" in str(e_mod) or "429" in str(e_mod):
                    print(f"[gerador_imagens] Cota gratuita atingida no Google Gemini Image ({mod}). Acionando provedor Flux...")
                    return False
                continue

    except Exception as e:
        print(f"[gerador_imagens] Erro ao chamar Google Gemini Image ({e}). Recorrendo ao Flux.")
        return False

    return False


# Alias explícito para o gerador Google Nano Banana
gerar_imagem_gemini_nano_banana = gerar_imagem_gemini


def gerar_imagem_fallback(caminho_saida: str, aspect_ratio: str = "16:9") -> bool:
    """Gera um frame sombrio de contingência caso a conexão com todos os provedores falhe."""
    largura, altura = (720, 1280) if aspect_ratio == "9:16" else (1280, 720)
    img = Image.new("RGB", (largura, altura), (15, 23, 42))
    img.save(caminho_saida, quality=90)
    return True


# ==============================================================================
# 🚀 5. ORQUESTRADOR DE GERAÇÃO POR CENA E BATCH
# ==============================================================================

def gerar_imagem_cena_individual(
    prompt: str,
    cena_id: int,
    slug: str,
    aspect_ratio: str = "16:9",
    estilo_id: str = "dark_cinematic",
    biblia_visual: Optional[Dict[str, Any]] = None,
    narracao: str = "",
    provedor_preferido: str = "pollinations",
    api_key: Optional[str] = None
) -> str:
    """
    Gera ou regenera a imagem de uma cena individual com refinamento de prompt,
    consistência de storytelling e proporção nativa.
    """
    os.makedirs("output/imagens", exist_ok=True)
    caminho_saida = os.path.join("output", "imagens", f"{slug}_cena_{cena_id}.jpg")

    # 1. Refina o prompt e obtém o prompt negativo correspondente ao estilo
    prompts_refinados = refinar_prompt_com_ia(
        prompt_original=prompt,
        estilo_id=estilo_id,
        biblia_visual=biblia_visual,
        cena_id=cena_id,
        narracao=narracao,
        api_key=api_key
    )
    prompt_pos = prompts_refinados["prompt_positivo"]
    prompt_neg = prompts_refinados["prompt_negativo"]

    sucesso = False

    # 2. Executa a geração no provedor preferido com fallback automático
    if provedor_preferido in ["gemini", "nano_banana"]:
        sucesso = gerar_imagem_gemini(prompt_pos, caminho_saida, api_key=api_key, aspect_ratio=aspect_ratio)
        if not sucesso:
            sucesso = gerar_imagem_pollinations(
                prompt=prompt_pos,
                caminho_saida=caminho_saida,
                aspect_ratio=aspect_ratio,
                prompt_negativo=prompt_neg
            )
    else:
        sucesso = gerar_imagem_pollinations(
            prompt=prompt_pos,
            caminho_saida=caminho_saida,
            aspect_ratio=aspect_ratio,
            prompt_negativo=prompt_neg
        )
        if not sucesso:
            sucesso = gerar_imagem_gemini(prompt_pos, caminho_saida, api_key=api_key, aspect_ratio=aspect_ratio)

    if not sucesso or not os.path.exists(caminho_saida):
        gerar_imagem_fallback(caminho_saida, aspect_ratio=aspect_ratio)

    print(f"[gerador_imagens] Imagem Cena {cena_id} finalizada em: {caminho_saida}")
    return caminho_saida


def gerar_imagens_para_roteiro(
    roteiro_dados: Dict[str, Any],
    aspect_ratio: str = "16:9",
    estilo_id: str = "dark_cinematic",
    biblia_visual: Optional[Dict[str, Any]] = None,
    provedor: str = "pollinations",
    callback_progresso: Optional[Any] = None,
    api_key: Optional[str] = None
) -> Dict[int, str]:
    """
    Lê as cenas do roteiro e gera todas as imagens de forma consistente.
    
    Args:
        roteiro_dados: Dicionário do roteiro gerado pelo Gemini.
        aspect_ratio: '16:9' ou '9:16'.
        estilo_id: Chave de estilo em ESTILOS_VISUAIS (ex: 'dark_cinematic', 'analog_horror').
        biblia_visual: Fichas de personagens e cenários para storytelling consistente.
        provedor: 'pollinations' ou 'gemini'.
        callback_progresso: Função callback(porcentagem, mensagem).
        api_key: Chave opcional do Gemini.
        
    Returns:
        Dicionário mapeando {cena_id: caminho_imagem}.
    """
    cenas = roteiro_dados.get("cenas", [])
    if not cenas:
        raise ValueError("O roteiro fornecido não contém cenas.")

    titulo = roteiro_dados.get("titulo", "video_dark")
    slug = sanitizar_nome_arquivo(titulo)
    total_cenas = len(cenas)
    imagens_mapeadas: Dict[int, str] = {}
    
    lock_progresso = threading.Lock()
    cenas_concluidas = 0

    nome_estilo = ESTILOS_VISUAIS.get(estilo_id, {}).get("nome", "Dark Cinematic")
    print(f"[gerador_imagens] Iniciando geração de {total_cenas} imagens em paralelo (Estilo: {nome_estilo}, Provedor: {provedor}, Formato: {aspect_ratio})...")

    # Se a Bíblia Visual não foi fornecida, extrai automaticamente do roteiro
    if not biblia_visual:
        if callback_progresso:
            callback_progresso(0.05, "Extraindo Bíblia Visual de Personagens e Cenários com IA...")
        biblia_visual = extrair_biblia_visual(roteiro_dados, api_key=api_key)

    def processar_cena(idx: int, c: Dict[str, Any]) -> Tuple[int, str]:
        nonlocal cenas_concluidas
        cena_id = c.get("cena_id", idx + 1)
        prompt_bruto = c.get("visual_prompt", "")
        narracao_cena = c.get("narracao", "")

        caminho_img = gerar_imagem_cena_individual(
            prompt=prompt_bruto,
            cena_id=cena_id,
            slug=slug,
            aspect_ratio=aspect_ratio,
            estilo_id=estilo_id,
            biblia_visual=biblia_visual,
            narracao=narracao_cena,
            provedor_preferido=provedor,
            api_key=api_key
        )
        
        if callback_progresso:
            with lock_progresso:
                cenas_concluidas += 1
                pct = round(0.1 + (cenas_concluidas / total_cenas) * 0.85, 2)
                callback_progresso(pct, f"Gerando imagens em paralelo: {cenas_concluidas}/{total_cenas} prontas...")
                
        return cena_id, caminho_img

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futuros = [executor.submit(processar_cena, idx, c) for idx, c in enumerate(cenas)]
        
        for futuro in concurrent.futures.as_completed(futuros):
            try:
                cena_id, caminho_img = futuro.result()
                imagens_mapeadas[cena_id] = caminho_img
            except Exception as e:
                print(f"[gerador_imagens] Erro ao processar cena: {e}")

    if callback_progresso:
        with lock_progresso:
            callback_progresso(1.0, f"Todas as {total_cenas} imagens geradas com sucesso!")

    return imagens_mapeadas


if __name__ == "__main__":
    teste_roteiro = {
        "titulo": "O Mistério do Bunker 7",
        "cenas": [
            {
                "cena_id": 1,
                "visual_prompt": "Detetive Viktor segurando uma lanterna fraca em frente à pesada porta de ferro do bunker",
                "narracao": "Em 1986, o detetive Viktor recebeu uma fita de áudio que nunca deveria ter existido."
            },
            {
                "cena_id": 2,
                "visual_prompt": "Detetive Viktor examinando documentos confidenciais com carimbos vermelhos sobre a mesa de aço",
                "narracao": "Ao entrar na instalação subterrânea, ele percebeu que as ordens de evacuação eram falsas."
            }
        ]
    }
    print("Testando extração de Bíblia Visual e estilos...")
    biblia = extrair_biblia_visual(teste_roteiro)
    print("Bíblia:", biblia)
    res = gerar_imagens_para_roteiro(teste_roteiro, estilo_id="dark_cinematic", biblia_visual=biblia)
    print("Resultado Imagens:", res)
