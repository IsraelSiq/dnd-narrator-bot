import asyncio
import json
import logging
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    import google.generativeai as genai
except Exception:  # pragma: no cover - SDK optional in offline environments
    genai = None

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """Você é um Mestre de RPG experiente e criativo especializado em D&D 5e.
Você narra aventuras imersivas em português do Brasil com descrições vívidas e tensão dramática.
Sempre mantenha consistência com o contexto da aventura e as ações anteriores.
Seja criativo, mas não invente fatos que contradigam o estado atual da sessão.
Retorne sempre JSON válido, sem markdown, sem explicações extras.
"""


class Narrator:
    def __init__(self, api_key: str):
        self.api_key = api_key or ""
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.alt_api_key = os.getenv("AI_API_KEY", "")
        self.alt_base_url = (os.getenv("AI_BASE_URL", "") or "").rstrip("/")
        self.alt_model = os.getenv("AI_MODEL", "")
        self.bastiao_base_url = (os.getenv("BASTIAO_BASE_URL", "") or "").rstrip("/")
        self.bastiao_api_key = os.getenv("BASTIAO_API_KEY", "")
        self.bastiao_model = os.getenv("BASTIAO_MODEL", "")
        self._provider_cooldowns = {}
        self._cooldown_seconds = int(os.getenv("AI_PROVIDER_COOLDOWN", "300"))
        self.model = None
        self.image_model = None
        self.provider_status = "offline"

        if self.api_key and genai is not None:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=SYSTEM_PROMPT,
            )
            self.image_model = genai.GenerativeModel(
                os.getenv("GEMINI_IMAGE_MODEL", "imagen-3.0-generate-002")
            )
            self.provider_status = f"gemini:{self.model_name}"
        elif self.api_key:
            self.provider_status = f"gemini-rest:{self.model_name}"
        else:
            log.warning("Gemini indisponível; usando narrador offline por padrão.")

        if self.alt_api_key and self.alt_base_url and self.alt_model:
            log.info("Provedor alternativo configurado: %s", self.alt_model)
        if self.bastiao_api_key and self.bastiao_base_url and self.bastiao_model:
            log.info("Bastião local configurado: %s", self.bastiao_model)

    def _cooldown_provider(self, provider: str, exc: Exception):
        self._provider_cooldowns[provider] = time.time() + self._cooldown_seconds
        log.warning("Provider %s entrou em cooldown por erro: %s", provider, exc)

    def _provider_available(self, provider: str) -> bool:
        until = self._provider_cooldowns.get(provider)
        if until and time.time() < until:
            return False
        return True

    def _parse_json(self, raw: str):
        if raw is None:
            raise ValueError("Resposta vazia da IA")
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
            text = re.sub(r"\s*```\s*$", "", text, flags=re.I)
        text = text.strip()
        if not text:
            raise ValueError("Resposta vazia depois do parse")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Heurística para extrair um JSON embutido de blocos de texto
            match = re.search(r"\{.*\}", text, flags=re.S)
            if match:
                return json.loads(match.group(0))
            raise

    def _offline_scene_seed(self, chat_id: int) -> dict:
        seed = (chat_id if chat_id else 1) % 4
        templates = [
            {
                "titulo": "As Cinzas do Farol Antigo",
                "narrativa": "Um farol abandonado treme ao longo da tempestade. Pegadas recentes cruzam o chão de pedra, e a porta de ferro da torre parece estar parcialmente aberta. O silêncio pesa mais que o vento.",
                "contexto": "Localização: Farol Antigo. Ameaça: ruínas despertas. Objetivo: investigar a torre e descobrir por que as pegadas voltaram a aparecer.",
            },
            {
                "titulo": "O Juramento da Floresta Sombria",
                "narrativa": "A floresta emudeceu quando a lua apareceu acima das copas. Entre as árvores, uma clareira se abre com um altar coberto por musgo e runas antigas, como se a natureza estivesse esperando alguém ser corajoso o bastante para despertar a promessa.",
                "contexto": "Localização: Floresta Sombria. Ameaça: matilha de criaturas e altar antigo. Objetivo: descobrir o que a clareira guarda e por que a magia está despertando.",
            },
            {
                "titulo": "A Cripta de Pedra Viva",
                "narrativa": "Uma câmara sepulcral respira por baixo da cidade. O ar cheira a poeira de túmulos e a magia antiga. Alguém já esteve ali antes, e o eco da descoberta parece levar o grupo em direção a um segredo enterrado.",
                "contexto": "Localização: Cripta de Pedra Viva. Ameaça: guardas mortos e portas seladas. Objetivo: explorar o interior e quebrar o selo que prende a memória da cidade.",
            },
            {
                "titulo": "O Templo do Vento Silencioso",
                "narrativa": "Pilares quebrados cercam um templo abandonado em meio ao deserto. Há música no vento, mas não é natural. Cada passo ecoa como um aviso: a lenda ainda não terminou, e algo dorme sob o altar central.",
                "contexto": "Localização: Templo do Vento Silencioso. Ameaça: ventos encantados e guardianas anciãs. Objetivo: entrar no templo e revelar a verdade sobre o sussurro do vento.",
            },
        ]
        return templates[seed]

    def _offline_personagem(self, nome: str, classe: str, raca: str, detalhes: str = "") -> dict:
        racas_bonus = {
            "Humano": {"Força": 1, "Destreza": 1, "Constituição": 1, "Inteligência": 1, "Sabedoria": 1, "Carisma": 1},
            "Elfo": {"Destreza": 2, "Inteligência": 1},
            "Anão": {"Constituição": 2, "Sabedoria": 1},
            "Halfling": {"Destreza": 2, "Carisma": 1},
            "Tiefling": {"Inteligência": 1, "Carisma": 2},
            "Meio-Orc": {"Força": 2, "Constituição": 1},
        }
        base = {"Força": 12, "Destreza": 12, "Constituição": 12, "Inteligência": 12, "Sabedoria": 12, "Carisma": 12}
        for attr, bonus in racas_bonus.get(raca, {}).items():
            base[attr] = base.get(attr, 10) + bonus
        if classe == "Guerreiro":
            base["Força"] += 2
            base["Constituição"] += 1
        elif classe == "Bárbaro":
            base["Força"] += 3
            base["Constituição"] += 1
        elif classe == "Ladino":
            base["Destreza"] += 2
            base["Inteligência"] += 1
        elif classe == "Mago":
            base["Inteligência"] += 3
            base["Destreza"] += 1
        elif classe == "Clérigo":
            base["Sabedoria"] += 2
            base["Constituição"] += 1
        elif classe == "Ranger":
            base["Destreza"] += 2
            base["Sabedoria"] += 1

        hist = f"{nome} é um {classe.lower()} de {raca.lower()} que nasceu para seguir em direção ao desconhecido."
        if detalhes and detalhes.strip().lower() not in {"nenhum", "nenhuma", "n/a", "nao", "não"}:
            hist = hist + f" Seus detalhes pessoais incluem: {detalhes.strip()}"
        hist += " No momento, o personagem busca um propósito claro e enfrenta o mundo com coragem, disciplina e curiosidade."
        return {"atributos": base, "historia": hist}

    def _offline_sugestoes(self, sessao: dict, personagem: dict) -> list:
        contexto = (sessao or {}).get("contexto", "")
        base = [
            "Investigar o ponto mais ameaçador da cena",
            "Conversar com o NPC mais suspeito",
            "Procurar uma rota ou passagem secreta",
        ]
        if "balcão" in contexto.lower():
            base.insert(0, "Examinar atentamente o balcão em busca de pistas")
        if "inimigos" in contexto.lower() or "ameaça" in contexto.lower():
            base.insert(0, "Avaliar a melhor forma de enfrentar os inimigos")
        if "porta" in contexto.lower() or "passagem" in contexto.lower():
            base.insert(0, "Explorar a passagem ou porta escondida")
        return [{"acao": item, "atributo": "Destreza", "cd": 12, "risco": "médio"} for item in base[:3]]

    def _call_gemini_json(self, prompt: str):
        if not self.api_key or genai is None or not self.model:
            raise RuntimeError("Gemini não configurado")
        response = self.model.generate_content(prompt)
        text = response.text if hasattr(response, "text") else str(response)
        return self._parse_json(text)

    def _call_openai_compatible_json(self, base_url: str, api_key: str, model: str, prompt: str, provider: str):
        if not base_url or not api_key or not model:
            raise RuntimeError(f"{provider} não configurado")
        url = base_url if base_url.endswith("/chat/completions") else f"{base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.8,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"{provider} HTTP {exc.code}: {exc.reason}") from exc
        except Exception as exc:  # pragma: no cover - network path
            raise RuntimeError(f"Falha de rede em {provider}: {exc}") from exc
        data = json.loads(body)
        try:
            return self._parse_json(data["choices"][0]["message"]["content"])
        except Exception:
            # algumas APIs retornam uma string simples em content
            content = data.get("choices", [{}])[0].get("message", {}).get("content")
            if isinstance(content, str):
                return self._parse_json(content)
            raise

    async def _request_json(self, prompt: str):
        providers = []
        if self.api_key and genai is not None and self.model:
            providers.append(("gemini", lambda: self._call_gemini_json(prompt)))
        if self.alt_api_key and self.alt_base_url and self.alt_model and self._provider_available("alternative"):
            providers.append(("alternative", lambda: self._call_openai_compatible_json(self.alt_base_url, self.alt_api_key, self.alt_model, prompt, "alternative")))
        if self.bastiao_api_key and self.bastiao_base_url and self.bastiao_model and self._provider_available("bastiao"):
            providers.append(("bastiao", lambda: self._call_openai_compatible_json(self.bastiao_base_url, self.bastiao_api_key, self.bastiao_model, prompt, "bastiao")))

        if not providers:
            raise RuntimeError("Nenhum provedor ativo disponível")

        last_error = None
        for name, worker in providers:
            try:
                return await asyncio.to_thread(worker)
            except Exception as exc:
                last_error = exc
                self._cooldown_provider(name, exc)
                log.warning("Falha no provider %s: %s", name, exc)
        raise last_error or RuntimeError("Falha ao obter resposta da IA")

    async def iniciar_aventura(self, chat_id: int) -> dict:
        aventura = self._offline_scene_seed(chat_id)
        prompt = (
            "Crie uma aventura de D&D 5e em português do Brasil em formato JSON: "
            "{\"titulo\": \"...\", \"narrativa\": \"...\", \"contexto\": \"...\"}. "
            "Mantenha a narrativa envolvente, com local, ameaça, objetivo e senso de mistério."
        )
        try:
            data = await self._request_json(prompt)
            if isinstance(data, dict) and data.get("titulo") and data.get("narrativa") and data.get("contexto"):
                return data
        except Exception as exc:
            log.warning("IA indisponível para iniciar aventura; usando fallback offline: %s", exc)
        return aventura

    async def criar_personagem(self, nome: str, classe: str, raca: str, detalhes: str = "") -> dict:
        prompt = (
            "Crie uma ficha de personagem de D&D 5e em JSON com chaves 'atributos' e 'historia'. "
            "Use valores entre 8 e 18. Mantenha fidelidade à classe, raça e detalhes. "
            f"Nome: {nome}. Classe: {classe}. Raça: {raca}. Detalhes: {detalhes or 'nenhum'}."
        )
        try:
            data = await self._request_json(prompt)
            if isinstance(data, dict) and isinstance(data.get("atributos"), dict) and data.get("historia"):
                return {
                    "atributos": {str(k): int(v) for k, v in data["atributos"].items()},
                    "historia": data["historia"],
                }
        except Exception as exc:
            log.warning("IA indisponível para criar personagem; usando fallback offline: %s", exc)
        return self._offline_personagem(nome, classe, raca, detalhes)

    async def avaliar_acao(self, sessao: dict, acao: str) -> dict:
        prompt = (
            "Avalie se esta ação exige teste de atributo e em qual atributo. "
            "Retorne JSON: {'precisa_teste': true/false, 'atributo': 'Força', 'cd': 12, 'motivo': '...'} "
            f"Contexto: {sessao.get('contexto', '')}. Ação: {acao}"
        )
        try:
            data = await self._request_json(prompt)
            if isinstance(data, dict):
                if "precisa_teste" in data:
                    return data
        except Exception as exc:
            log.warning("IA indisponível ao avaliar ação; usando fallback offline: %s", exc)

        texto = (acao or "").lower()
        simples = [
            "caminho", "andar", "avanço", "aproximar", "aproximar-se", "se aproximar",
            "entrar", "andar lentamente", "caminho até a entrada", "balcão"
        ]
        if any(item in texto for item in simples):
            return {"precisa_teste": False, "atributo": "Destreza", "cd": 10, "motivo": "Ação simples"}
        return {"precisa_teste": True, "atributo": "Destreza", "cd": 12, "motivo": "Ação arriscada"}

    async def narrar_acao_com_dado(self, sessao: dict, personagem: dict, jogadores: list, acao: str, teste: dict | None) -> dict:
        prompt = (
            "Narre a ação de um personagem em D&D em português do Brasil. "
            "Retorne JSON com chaves 'narrativa', 'novo_contexto' e 'sugestoes'. "
            f"Contexto atual: {sessao.get('contexto', '')}. Personagem: {personagem.get('nome')} "
            f"({personagem.get('classe')}, {personagem.get('raca')}). Ação: {acao}. "
            f"Teste: {teste}."
        )
        try:
            data = await self._request_json(prompt)
            if isinstance(data, dict) and data.get("narrativa"):
                novo_contexto = data.get("novo_contexto") or sessao.get("contexto", "")
                sugestoes = data.get("sugestoes") or []
                return {"narrativa": data["narrativa"], "novo_contexto": novo_contexto, "sugestoes": sugestoes}
        except Exception as exc:
            log.warning("IA indisponível para narrar ação; usando fallback offline: %s", exc)

        contexto = sessao.get("contexto", "")
        narr = (
            f"{personagem.get('nome')} tenta: {acao}. A ação se desenrola com tensão, improviso e atenção ao ambiente. "
            "O ritmo da cena se altera, e o que antes era apenas um risco agora se torna um momento decisivo."
        )
        novo_contexto = f"{contexto} Progressão: ação 1. Última ação de {personagem.get('nome')}: {acao}. Resultado: {narr}"
        sugestoes = [
            "Inspecionar a área em busca de pistas",
            "Confrontar o inimigo mais próximo",
            "Explorar a passagem oculta indicada pela cena",
        ]
        return {"narrativa": narr, "novo_contexto": novo_contexto, "sugestoes": sugestoes}

    async def sugerir_acoes(self, sessao: dict, personagem: dict) -> dict:
        prompt = (
            "Sugira 3 ações úteis para um personagem em D&D. Retorne JSON {'sugestoes': [{...}]}. "
            f"Contexto: {sessao.get('contexto', '')}. Personagem: {personagem.get('nome')}."
        )
        try:
            data = await self._request_json(prompt)
            if isinstance(data, dict) and isinstance(data.get("sugestoes"), list):
                return data
        except Exception as exc:
            log.warning("IA indisponível para sugerir ações; usando fallback offline: %s", exc)
        return {"sugestoes": self._offline_sugestoes(sessao, personagem)}

    async def gerar_cena(self, sessao: dict) -> dict:
        prompt = (
            "Descreva uma cena visual em estilo de RPG em JSON: {'descricao': '...', 'imagem_bytes': null}. "
            f"Contexto: {sessao.get('contexto', '')}"
        )
        try:
            data = await self._request_json(prompt)
            if isinstance(data, dict) and data.get("descricao"):
                return {"descricao": data["descricao"], "imagem_bytes": data.get("imagem_bytes")}
        except Exception as exc:
            log.warning("IA indisponível para gerar cena; usando fallback offline: %s", exc)
        ctx = sessao.get("contexto", "")
        desc = f"Cena atual: a tensão aumenta ao redor dos limites da aventura. O ambiente parece vivo, e a atenção se concentra em cada detalhe relevante. etapa 1 da cena principal. {ctx}"
        return {"descricao": desc, "imagem_bytes": None}

    async def gerar_imagem(self, sessao: dict):
        if not self.api_key or not self.image_model:
            return {"imagem_bytes": None, "descricao": "Sem imagem disponível."}
        try:
            prompt = f"Crie uma cena épica de fantasia para esta situação: {sessao.get('contexto', '')}"
            response = self.image_model.generate_content(prompt)
            if hasattr(response, "images") and response.images:
                return {"imagem_bytes": response.images[0], "descricao": "Cena gerada"}
        except Exception as exc:
            log.warning("Imagem falhou; usando fallback textual: %s", exc)
        return {"imagem_bytes": None, "descricao": "Cena textual disponível."}

    def _choose_provider(self):
        providers = [
            ("gemini", self.api_key and genai is not None and self.model is not None),
            ("alternative", bool(self.alt_api_key and self.alt_base_url and self.alt_model)),
            ("bastiao", bool(self.bastiao_api_key and self.bastiao_base_url and self.bastiao_model)),
        ]
        for name, enabled in providers:
            if enabled and self._provider_available(name):
                return name
        return "offline"


__all__ = ["Narrator", "SYSTEM_PROMPT"]
