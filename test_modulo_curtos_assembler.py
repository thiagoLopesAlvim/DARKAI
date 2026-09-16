import os
import subprocess
import imageio_ffmpeg
import modulo_curtos_assembler as ma

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
os.makedirs("temp/test_clips", exist_ok=True)

# Gera 2 pequenos clipes de teste coloridos (3 segundos cada, com áudio de tom)
clip1 = "temp/test_clips/cena_1.mp4"
clip2 = "temp/test_clips/cena_2.mp4"

cmd1 = [
    FFMPEG, "-y",
    "-f", "lavfi", "-i", "color=c=navy:s=720x1280:d=3:r=30",
    "-f", "lavfi", "-i", "sine=f=440:d=3",
    "-c:v", "libx264", "-c:a", "aac",
    clip1
]
cmd2 = [
    FFMPEG, "-y",
    "-f", "lavfi", "-i", "color=c=darkred:s=720x1280:d=3:r=30",
    "-f", "lavfi", "-i", "sine=f=660:d=3",
    "-c:v", "libx264", "-c:a", "aac",
    clip2
]
subprocess.run(cmd1, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
subprocess.run(cmd2, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

print("Clipes de teste gerados:", clip1, clip2)

assembler = ma.ShortsAssembler()
resultado = assembler.montar_video_curto(
    lista_clipes=[clip1, clip2],
    titulo_projeto="teste_assembler_viral",
    tipo_transicao="crossfade",
    duracao_transicao=0.3,
    efeito_sonoro_transicao="whoosh",
    marca_dagua="@darkai_studio"
)

print("\n--- TESTE DO ASSEMBLER CONCLUÍDO COM SUCESSO! ---")
print("Vídeo:", resultado["caminho_video"])
print("Duração:", resultado["duracao_segundos"])
print("Tamanho:", resultado["tamanho_mb"], "MB")
assert os.path.exists(resultado["caminho_video"])
