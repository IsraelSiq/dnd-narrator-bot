import asyncio
import json
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
            database.salvar_personagem(
                2, 1, "Kira", "Ladina", "Elfica",
                {"Destreza": 16}, "historia"
            )
            self.assertEqual(database.obter_sessao(1)["contexto"], "contexto")
            self.assertEqual(
                database.obter_personagem(2, 1)["atributos"], {"Destreza": 16}
            )


if __name__ == "__main__":
    unittest.main()
