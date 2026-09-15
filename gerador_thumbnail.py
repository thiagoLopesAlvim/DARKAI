"""
Módulo para geração automática de thumbnails.
"""

import os
from typing import Dict, Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from google import genai

def gerar_texto_thumbnail(titulo: str, tema: str, api_key: Optional[str] = None) -> str:
    """Usa Gemini para gerar um texto curto e impactante para a thumbnail (2-5 palavras)"""
    try:
        chave = api_key or os.environ.get("GEMINI_API_KEY")
        if not chave:
            return "VÍDEO INCRÍVEL"
            
        client = genai.Client(api_key=chave)
        
        prompt = f"""
Crie um texto CURTO e IMPACTANTE para a capa (thumbnail) de um vídeo do YouTube.
Título do vídeo: {titulo}
Tema: {tema}

Regras:
- O texto deve ter de 2 a 5 palavras no máximo.
- Deve chamar a atenção, instigar a curiosidade ou ser chocante.
- Todas as letras em MAIÚSCULAS.
- Retorne apenas o texto, sem aspas, sem pontuação extra.
"""
        resposta = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        
        texto = resposta.text.strip().replace('"', '').upper()
        if len(texto.split()) > 6:
            # Fallback se a IA falhar em manter curto
            texto = " ".join(texto.split()[:4])
            
        return texto
    except Exception as e:
        print(f"Erro ao gerar texto de thumbnail: {e}")
        return "ASSISTA AGORA"

def gerar_thumbnail(
    imagens_cenas: Dict[int, str],
    texto_overlay: str,
    caminho_saida: str,
    largura: int = 1280,
    altura: int = 720
) -> str:
    """Gera thumbnail combinando a melhor imagem com texto overlay"""
    if not imagens_cenas:
        raise ValueError("Nenhuma imagem fornecida para a thumbnail.")
        
    # 1. Seleciona a imagem (primeira da lista)
    id_imagem_base = list(imagens_cenas.keys())[0]
    caminho_imagem = imagens_cenas[id_imagem_base]
    
    # Garante que o diretório de saída exista
    os.makedirs(os.path.dirname(caminho_saida) or ".", exist_ok=True)
    
    try:
        # Abre a imagem
        img = Image.open(caminho_imagem).convert("RGBA")
        
        # 2. Redimensiona/corta para 1280x720 (Aspect ratio 16:9)
        aspect_ratio_alvo = largura / altura
        aspect_ratio_img = img.width / img.height
        
        if aspect_ratio_img > aspect_ratio_alvo:
            # Imagem mais larga, corta nas laterais
            nova_largura = int(img.height * aspect_ratio_alvo)
            x_offset = (img.width - nova_largura) // 2
            img = img.crop((x_offset, 0, x_offset + nova_largura, img.height))
        else:
            # Imagem mais alta, corta em cima e embaixo
            nova_altura = int(img.width / aspect_ratio_alvo)
            y_offset = (img.height - nova_altura) // 2
            img = img.crop((0, y_offset, img.width, y_offset + nova_altura))
            
        img = img.resize((largura, altura), Image.Resampling.LANCZOS)
        
        # Saturação e contraste um pouco maiores para thumbnail
        enhancer = ImageEnhance.Color(img)
        img = enhancer.enhance(1.2)
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.1)
        
        # 3. Adiciona gradiente (vignette e parte inferior)
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        # Gradiente na parte inferior para o texto ficar legível
        for y in range(int(altura * 0.5), altura):
            alpha = int(255 * ((y - altura * 0.5) / (altura * 0.5)) * 0.8)  # Max 80% opacity
            draw.line([(0, y), (largura, y)], fill=(0, 0, 0, alpha))
            
        # Aplica vignette sutil nas bordas
        vignette = Image.new("RGBA", img.size, (0, 0, 0, 0))
        v_draw = ImageDraw.Draw(vignette)
        margin = -100
        v_draw.ellipse((margin, margin, largura - margin, altura - margin), fill=(0, 0, 0, 0), outline=(0, 0, 0, 150), width=150)
        vignette = vignette.filter(ImageFilter.GaussianBlur(50))
        
        img = Image.alpha_composite(img, overlay)
        img = Image.alpha_composite(img, vignette)
        
        # 4. Adiciona texto bold amarelo com contorno preto
        draw = ImageDraw.Draw(img)
        
        # Tenta carregar uma fonte impactante, senão usa padrão
        try:
            # No Windows: impact.ttf ou arialbd.ttf
            fonte = ImageFont.truetype("impact.ttf", 96)
        except OSError:
            try:
                fonte = ImageFont.truetype("arialbd.ttf", 96)
            except OSError:
                fonte = ImageFont.load_default(size=96)
                
        # Calcula posição do texto (centralizado na metade inferior)
        bbox = draw.textbbox((0, 0), texto_overlay, font=fonte)
        w_texto = bbox[2] - bbox[0]
        h_texto = bbox[3] - bbox[1]
        
        x_texto = (largura - w_texto) / 2
        y_texto = altura - h_texto - 80
        
        cor_borda = "black"
        espessura_borda = 6
        cor_texto = "#FFE135"
        sombra_offset = 8
        
        # Sombra
        draw.text((x_texto + sombra_offset, y_texto + sombra_offset), texto_overlay, font=fonte, fill=(0, 0, 0, 180))
        
        # Contorno
        for dx in range(-espessura_borda, espessura_borda + 1):
            for dy in range(-espessura_borda, espessura_borda + 1):
                if dx*dx + dy*dy <= espessura_borda*espessura_borda:
                    draw.text((x_texto + dx, y_texto + dy), texto_overlay, font=fonte, fill=cor_borda)
                    
        # Texto principal
        draw.text((x_texto, y_texto), texto_overlay, font=fonte, fill=cor_texto)
        
        # Converte de volta para RGB para salvar como JPG
        img = img.convert("RGB")
        img.save(caminho_saida, "JPEG", quality=95)
        
        return caminho_saida
    except Exception as e:
        print(f"Erro ao gerar thumbnail: {e}")
        # Em caso de falha, tenta apenas copiar a imagem base
        try:
            img_backup = Image.open(caminho_imagem).convert("RGB")
            img_backup = img_backup.resize((largura, altura))
            img_backup.save(caminho_saida, "JPEG", quality=90)
            return caminho_saida
        except Exception:
            raise RuntimeError(f"Falha total ao gerar thumbnail: {e}")
