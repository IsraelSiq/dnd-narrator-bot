import asyncio
import tempfile
import unittest
from pathlib import Path

from dnd_bot.database import Database
from dnd_bot.dice import realizar_teste
from dnd_bot.narrator import Narrator


class NarratorTests(unittest.TestCase):
    def test_offline_narrator_starts_adventure(self):
        intro = asyncio.run(Narrator("").iniciar_aventura(123))
        self.assertTrue(intro["titulo"])
        self.assertTrue(intro["narrativa"])
        self.assertTrue(intro["contexto"])

    def test_json_parser_accepts_markdown_fence(self):
        parsed = Narrator("")._parse_json("```json\n{\"ok\": true}\n```")
        self.assertEqual(parsed, {"ok": True})

    def test_offline_action_advances_context_and_scene(self):
        narrator = Narrator("")
        session = {"contexto": "Localização: Farol Antigo. Ameaça: ruínas despertas."}
        character = {
            "nome": "Kira",
            "classe": "Ladina",
            "raca": "Elfa",
            "atributos": {"Destreza": 16},
        }
        result = asyncio.run(narrator.narrar_acao_com_dado(session, character, [character], "examino as pegadas", None))
        self.assertIn("Progressão: ação 1", result["novo_contexto"])
        scene = asyncio.run(narrator.gerar_cena({"contexto": result["novo_contexto"]}))
        self.assertIn("etapa 1", scene["descricao"])

    def test_simple_actions_do_not_require_dice(self):
        narrator = Narrator("")
        session = {"contexto": "Localização: Farol Antigo. Ameaça: ruínas."}
        for action in ("caminho até a entrada", "avanço até o balcão", "se aproximar andando lentamente", "aproximar-se da porta"):
            with self.subTest(action=action):
                result = asyncio.run(narrator.avaliar_acao(session, action))
                self.assertFalse(result["precisa_teste"])

    def test_provider_quota_enters_cooldown(self):
        narrator = Narrator("")
        narrator._cooldown_provider("alternate", RuntimeError("HTTP 429 quota exceeded"))
        self.assertFalse(narrator._provider_available("alternate"))

    def test_suggestions_follow_current_scene(self):
        narrator = Narrator("")
        session = {"contexto": "Localização: balcão do Farol. Ameaça: inimigos imobilizados. Objetivo: dispersar os inimigos. Progressão: ação 3 concluída."}
        character = {"nome": "Artheal", "classe": "Mago", "raca": "Elfo", "atributos": {"Inteligência": 16, "Destreza": 14}}
        result = asyncio.run(narrator.sugerir_acoes(session, character))
        actions = " ".join(item["acao"] for item in result["sugestoes"])
        self.assertIn("inimigos", actions)
        self.assertIn("balcão", actions)

    def test_character_details_shape_offline_fallback(self):
        ficha = asyncio.run(Narrator("").criar_personagem("Kira", "Ladina", "Elfo", "coleciona chaves e teme espaços fechados"))
        self.assertIn("coleciona chaves", ficha["historia"])


class DiceTests(unittest.TestCase):
    def test_attribute_modifier_and_result_shape(self):
        result = realizar_teste({"Força": 14}, "Força", dificuldade=10)
        self.assertEqual(result["modificador"], 2)
        self.assertIn("sucesso", result)
        self.assertEqual(len(result["dados_rolados"]), 1)


class DatabaseTests(unittest.TestCase):
    def test_session_and_character_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(str(Path(directory) / "test.db"))
            database.criar_sessao(1, "contexto")
            database.salvar_personagem(2, 1, "Kira", "Ladina", "Elfica", {"Destreza": 16}, "historia")
            self.assertEqual(database.obter_sessao(1)["contexto"], "contexto")
            self.assertEqual(database.obter_personagem(2, 1)["atributos"], {"Destreza": 16})

    def test_public_operations_and_new_session_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(str(Path(directory) / "test.db"))
            database.criar_sessao(1, "primeiro")
            database.salvar_personagem(2, 1, "Kira", "Ladina", "Elfica", {"Destreza": 16}, "historia")
            database.registrar_acao(2, 1, "explorar", "Encontrou uma porta")
            database.atualizar_contexto(1, "contexto atualizado")
            self.assertEqual(database.obter_sessao(1)["contexto"], "contexto atualizado")
            self.assertEqual(len(database.listar_jogadores(1)), 1)
            self.assertEqual(database.historico_recente(1)[0]["acao"], "explorar")
            database.criar_sessao(1, "segundo")
            self.assertEqual(database.listar_jogadores(1), [])
            self.assertEqual(database.historico_recente(1), [])


if __name__ == "__main__":
    unittest.main()
