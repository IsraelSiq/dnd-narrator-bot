"""
dice.py — Motor de dados D&D com modificadores de atributo
"""

import random


# Mapa de qual atributo rola para cada tipo de teste
TESTES = {
    # Combate
    "ataque":       "Força",
    "luta":         "Força",
    "força":        "Força",
    "empurrar":     "Força",
    "derrubar":     "Força",
    # Furtividade / Destreza
    "furtividade":  "Destreza",
    "roubo":        "Destreza",
    "furto":        "Destreza",
    "esquivar":     "Destreza",
    "acrobacia":    "Destreza",
    "reflexo":      "Destreza",
    "iniciativa":   "Destreza",
    "destreza":     "Destreza",
    # Resistência
    "resistência":  "Constituição",
    "resistencia":  "Constituição",
    "concentração": "Constituição",
    "concentracao": "Constituição",
    "constituição": "Constituição",
    # Magia / Conhecimento
    "magia":        "Inteligência",
    "inteligência": "Inteligência",
    "inteligencia": "Inteligência",
    "arcano":       "Inteligência",
    "investigação": "Inteligência",
    "investigacao": "Inteligência",
    # Percepção / Sobrevivência
    "percepção":    "Sabedoria",
    "percepcao":    "Sabedoria",
    "sabedoria":    "Sabedoria",
    "sobrevivência":"Sabedoria",
    "sobrevivencia":"Sabedoria",
    "medicina":     "Sabedoria",
    "insight":      "Sabedoria",
    # Social
    "persuasão":    "Carisma",
    "persuasao":    "Carisma",
    "intimidação":  "Carisma",
    "intimidacao":  "Carisma",
    "carisma":      "Carisma",
    "enganação":    "Carisma",
    "enganacao":    "Carisma",
    "atuação":      "Carisma",
    "atuacao":      "Carisma",
}

EMOJI_DADO = {4: "🔷", 6: "🎲", 8: "🔶", 10: "🔵", 12: "🟣", 20: "⚔️"}
ATTR_EMOJI = {
    "Força": "💪", "Destreza": "🏃", "Constituição": "❤️",
    "Inteligência": "🧠", "Sabedoria": "👁️", "Carisma": "✨"
}


def modificador(valor: int) -> int:
    """Converte valor de atributo D&D no modificador padrão."""
    return (valor - 10) // 2


def rolar(lados: int, quantidade: int = 1) -> list[int]:
    return [random.randint(1, lados) for _ in range(quantidade)]


def detectar_atributo(acao: str) -> str | None:
    """Tenta detectar qual atributo testar com base nas palavras da ação."""
    acao_lower = acao.lower()
    for palavra, atributo in TESTES.items():
        if palavra in acao_lower:
            return atributo
    return None


def realizar_teste(
    atributos: dict,
    atributo: str,
    dificuldade: int = 12,
    vantagem: bool = False,
    desvantagem: bool = False
) -> dict:
    """
    Realiza um teste de atributo D20 + modificador vs dificuldade (CD).
    Retorna tudo que precisa para montar o display do dado.
    """
    # Rola os dados
    if vantagem:
        d1, d2 = random.randint(1, 20), random.randint(1, 20)
        resultado_bruto = max(d1, d2)
        dados_rolados = [d1, d2]
        tipo_rolagem = "vantagem"
    elif desvantagem:
        d1, d2 = random.randint(1, 20), random.randint(1, 20)
        resultado_bruto = min(d1, d2)
        dados_rolados = [d1, d2]
        tipo_rolagem = "desvantagem"
    else:
        resultado_bruto = random.randint(1, 20)
        dados_rolados = [resultado_bruto]
        tipo_rolagem = "normal"

    mod = modificador(atributos.get(atributo, 10))
    total = resultado_bruto + mod

    # Determina o resultado
    critico_sucesso = resultado_bruto == 20
    falha_critica  = resultado_bruto == 1
    sucesso = critico_sucesso or (not falha_critica and total >= dificuldade)

    return {
        "atributo":       atributo,
        "valor_atributo": atributos.get(atributo, 10),
        "modificador":    mod,
        "dados_rolados":  dados_rolados,
        "resultado_bruto":resultado_bruto,
        "total":          total,
        "dificuldade":    dificuldade,
        "tipo_rolagem":   tipo_rolagem,
        "critico_sucesso":critico_sucesso,
        "falha_critica":  falha_critica,
        "sucesso":        sucesso,
    }


def formatar_resultado_dado(teste: dict, nome_personagem: str) -> str:
    """
    Monta a mensagem visual do lançamento de dado para o Telegram (MarkdownV2).
    """
    attr       = teste["atributo"]
    attr_emoji = ATTR_EMOJI.get(attr, "🎲")
    mod        = teste["modificador"]
    mod_str    = f"\\+{mod}" if mod >= 0 else f"\\-{abs(mod)}"
    bruto      = teste["resultado_bruto"]
    total      = teste["total"]
    cd         = teste["dificuldade"]
    dados      = teste["dados_rolados"]

    # Linha do dado
    if len(dados) == 2:
        d1, d2 = dados
        escolhido = max(dados) if teste["tipo_rolagem"] == "vantagem" else min(dados)
        tipo_label = "vantagem ↑" if teste["tipo_rolagem"] == "vantagem" else "desvantagem ↓"
        linha_dado = f"🎲 `d20` \\({tipo_label}\\): `{d1}` e `{d2}` → usa `{escolhido}`"
    else:
        linha_dado = f"🎲 `d20`: `{bruto}`"

    # Resultado final
    if teste["critico_sucesso"]:
        icone_resultado = "🌟 *SUCESSO CRÍTICO\\!*"
    elif teste["falha_critica"]:
        icone_resultado = "💀 *FALHA CRÍTICA\\!*"
    elif teste["sucesso"]:
        icone_resultado = "✅ *Sucesso*"
    else:
        icone_resultado = "❌ *Falha*"

    total_str = str(total).replace("-", "\\-")
    cd_str    = str(cd)

    return (
        f"╔═══ 🎲 *ROLAGEM DE DADOS* ═══╗\n"
        f"👤 *{escapa(nome_personagem)}*\n"
        f"{attr_emoji} Teste de *{attr}* \\(valor: {teste['valor_atributo']}\\)\n"
        f"─────────────────────\n"
        f"{linha_dado}\n"
        f"{mod_str} modificador de {attr}\n"
        f"─────────────────────\n"
        f"📊 Total: *{total_str}* vs CD {cd_str}\n"
        f"╚══ {icone_resultado} ══╝"
    )


def escapa(texto: str) -> str:
    """Escapa caracteres especiais do MarkdownV2."""
    for ch in r"\_*[]()~`>#+-=|{}.!":
        texto = texto.replace(ch, f"\\{ch}")
    return texto
