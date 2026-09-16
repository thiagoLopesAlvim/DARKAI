import modulo_curtos_roteiro as mr

print("Testando geração de roteiro curto...")
roteiro = mr.gerar_roteiro_curto(
    tema="Cachorro salsicha chef de cozinha que se estressa com o cliente",
    genero_id="humor_nonsense",
    qtd_cenas=3
)

print("\n--- SUCESSO NA GERAÇÃO ---")
print("Título:", roteiro.get("titulo"))
print("Hook:", roteiro.get("hook_inicial"))
print("Personagens Âncora:", len(roteiro.get("personagens_ancora", [])))
for p in roteiro.get("personagens_ancora", []):
    print(f" - {p['nome']}: {p['prompt_imagem_ancora'][:60]}...")

print("\nCenas:")
for c in roteiro.get("cenas", []):
    print(f" [Cena {c['numero']} - {c['duracao_segundos']}s] {c['descricao_acao']}")
    print(f"  Fala: {c.get('dialogo_fala')}")
    print(f"  Anim Flow: {c.get('prompt_animacao_flow')[:70]}...")
