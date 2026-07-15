"""
Tests for Sprint M1 — Multi-Provider LLM Router Foundation.
"""

import json
import os
import unittest
from unittest.mock import MagicMock, patch

from backend.llm import router
from backend.llm.config import MODEL_NAMES, MODEL_ROUTING, PROVIDER_CONFIG


class LLMRouterConfigTests(unittest.TestCase):
    """Configuration sanity checks."""

    def test_every_routed_provider_has_a_model_name(self):
        for module, providers in MODEL_ROUTING.items():
            for provider in providers:
                self.assertIn(
                    provider,
                    MODEL_NAMES,
                    f"Provider {provider!r} for module {module!r} has no model name.",
                )

    def test_every_routed_provider_has_config(self):
        for module, providers in MODEL_ROUTING.items():
            for provider in providers:
                self.assertIn(
                    provider,
                    PROVIDER_CONFIG,
                    f"Provider {provider!r} for module {module!r} has no config.",
                )

    def test_provider_config_has_api_key_env(self):
        for provider, config in PROVIDER_CONFIG.items():
            self.assertIn("api_key_env", config)
            self.assertIn("client", config)


class LLMRouterProviderTests(unittest.TestCase):
    """Provider selection, success, fallback, retry, and JSON normalization."""

    def setUp(self):
        router.reset_module_provider_cache()
        router.clear_router_context()
        # Tests must be isolated from any real API keys in the environment.
        # Clear every provider key that the router knows about.
        env_vars_to_clear = set()
        for config in PROVIDER_CONFIG.values():
            vars_ = config["api_key_env"]
            if isinstance(vars_, str):
                vars_ = [vars_]
            env_vars_to_clear.update(vars_)
        self._env_patch = patch.dict(
            os.environ, {var: "" for var in env_vars_to_clear}, clear=False
        )
        self._env_patch.start()

    def tearDown(self):
        self._env_patch.stop()
        router.reset_module_provider_cache()
        router.clear_router_context()

    def _set_api_keys(self, *providers):
        """Set dummy API keys for the given providers."""
        env = {}
        for provider in providers:
            config = PROVIDER_CONFIG[provider]
            env_vars = config["api_key_env"]
            if isinstance(env_vars, str):
                env_vars = [env_vars]
            for env_var in env_vars:
                env[env_var] = "dummy-key"
        return patch.dict(os.environ, env, clear=False)

    def _valid_json(self, obj) -> str:
        return json.dumps(obj)

    def _make_provider_mock(self, return_text):
        """Return a provider class mock whose instances return ``return_text``."""
        mock_class = MagicMock()
        instance = MagicMock()
        instance.generate.return_value = return_text
        mock_class.return_value = instance
        return mock_class

    # ------------------------------------------------------------------
    # Provider success paths
    # ------------------------------------------------------------------

    def test_gemini_success(self):
        mock_class = self._make_provider_mock(self._valid_json({"result": "ok"}))
        with self._set_api_keys("gemini"):
            with patch("backend.llm.router.GeminiProvider", mock_class):
                response = router.generate_json("presentation_planner", "prompt")
        self.assertEqual(response, {"result": "ok"})

    def test_openai_success(self):
        mock_class = self._make_provider_mock(self._valid_json({"result": "openai"}))
        with self._set_api_keys("openai"):
            with patch("backend.llm.router.OpenAICompatibleProvider", mock_class):
                response = router.generate_json("validator", "prompt")
        self.assertEqual(response, {"result": "openai"})

    def test_groq_success(self):
        mock_class = self._make_provider_mock(self._valid_json({"result": "groq"}))
        with self._set_api_keys("groq"):
            with patch("backend.llm.router.OpenAICompatibleProvider", mock_class):
                response = router.generate_json("intent", "prompt")
        self.assertEqual(response, {"result": "groq"})

    def test_cerebras_success(self):
        mock_class = self._make_provider_mock(self._valid_json({"result": "cerebras"}))
        with self._set_api_keys("cerebras"):
            with patch("backend.llm.router.OpenAICompatibleProvider", mock_class):
                response = router.generate_json("content_generator", "prompt")
        self.assertEqual(response, {"result": "cerebras"})

    def test_openrouter_success(self):
        mock_class = self._make_provider_mock(self._valid_json({"result": "openrouter"}))
        with self._set_api_keys("openrouter"):
            with patch("backend.llm.router.OpenAICompatibleProvider", mock_class):
                response = router.generate_json("content_generator", "prompt")
        self.assertEqual(response, {"result": "openrouter"})

    # ------------------------------------------------------------------
    # Provider priority / fallback
    # ------------------------------------------------------------------

    def test_provider_priority_order(self):
        """The first configured provider is used when its key is available."""
        openai_class = self._make_provider_mock(self._valid_json({"provider": "openai"}))
        groq_class = self._make_provider_mock(self._valid_json({"provider": "groq"}))
        with self._set_api_keys("openai", "groq"):
            with patch(
                "backend.llm.router.OpenAICompatibleProvider",
                side_effect=[openai_class.return_value, groq_class.return_value],
            ):
                response = router.generate_json("content_generator", "prompt")
        self.assertEqual(response["provider"], "openai")

    def test_fallback_when_primary_fails(self):
        """If the primary provider fails with a non-transient error, router falls back."""
        openai_instance = MagicMock()
        openai_instance.generate.side_effect = RuntimeError("boom")

        groq_instance = MagicMock()
        groq_instance.generate.return_value = self._valid_json({"provider": "groq"})
        groq_class = MagicMock(return_value=groq_instance)

        with self._set_api_keys("openai", "groq"):
            with patch(
                "backend.llm.router.OpenAICompatibleProvider",
                side_effect=[openai_instance, groq_class.return_value],
            ):
                response = router.generate_json("content_generator", "prompt")

        self.assertEqual(response["provider"], "groq")
        openai_instance.generate.assert_called_once()
        groq_instance.generate.assert_called_once()

    def test_skips_provider_without_api_key(self):
        """If the first provider has no key, the router tries the next."""
        gemini_class = self._make_provider_mock(self._valid_json({"provider": "gemini"}))
        with self._set_api_keys("gemini"):
            with patch("backend.llm.router.GeminiProvider", gemini_class):
                response = router.generate_json("clarification", "prompt")
        self.assertEqual(response["provider"], "gemini")

    def test_no_provider_available_error(self):
        """If no provider has an API key, raise NoProviderAvailableError."""
        with patch.dict(os.environ, {}, clear=False):
            with self.assertRaises(router.NoProviderAvailableError):
                router.generate_json("validator", "prompt")

    # ------------------------------------------------------------------
    # Retry behavior
    # ------------------------------------------------------------------

    def test_retry_on_429(self):
        """Transient 429 errors should be retried on the same provider."""
        instance = MagicMock()
        instance.generate.side_effect = [
            RuntimeError("429 Too Many Requests"),
            self._valid_json({"ok": True}),
        ]
        with self._set_api_keys("gemini"):
            with patch("backend.llm.router.GeminiProvider", return_value=instance):
                response = router.generate_json("presentation_planner", "prompt", max_retries=1)
        self.assertEqual(response, {"ok": True})
        self.assertEqual(instance.generate.call_count, 2)

    def test_retry_on_timeout(self):
        """Transient timeout errors should be retried on the same provider."""
        instance = MagicMock()
        instance.generate.side_effect = [
            TimeoutError("Request timed out"),
            self._valid_json({"ok": True}),
        ]
        with self._set_api_keys("openai"):
            with patch("backend.llm.router.OpenAICompatibleProvider", return_value=instance):
                response = router.generate_json("validator", "prompt", max_retries=1)
        self.assertEqual(response, {"ok": True})
        self.assertEqual(instance.generate.call_count, 2)

    def test_no_retry_on_non_transient_error(self):
        """Non-transient errors should not retry."""
        instance = MagicMock()
        instance.generate.side_effect = RuntimeError("Invalid API key")
        with self._set_api_keys("gemini"):
            with patch("backend.llm.router.GeminiProvider", return_value=instance):
                with self.assertRaises(router.NoProviderAvailableError):
                    router.generate_json("presentation_planner", "prompt", max_retries=1)
        self.assertEqual(instance.generate.call_count, 1)

    # ------------------------------------------------------------------
    # JSON handling
    # ------------------------------------------------------------------

    def test_strips_markdown_fence(self):
        mock_class = self._make_provider_mock('```json\n{"ok": true}\n```')
        with self._set_api_keys("gemini"):
            with patch("backend.llm.router.GeminiProvider", mock_class):
                response = router.generate_json("presentation_planner", "prompt")
        self.assertEqual(response, {"ok": True})

    def test_invalid_json_raises(self):
        mock_class = self._make_provider_mock("not json")
        with self._set_api_keys("gemini"):
            with patch("backend.llm.router.GeminiProvider", mock_class):
                with self.assertRaises(router.LLMJSONParseError):
                    router.generate_json("presentation_planner", "prompt")

    def test_non_object_json_raises(self):
        mock_class = self._make_provider_mock("[1, 2, 3]")
        with self._set_api_keys("gemini"):
            with patch("backend.llm.router.GeminiProvider", mock_class):
                with self.assertRaises(router.LLMJSONParseError):
                    router.generate_json("presentation_planner", "prompt")

    # ------------------------------------------------------------------
    # Deck-level consistency
    # ------------------------------------------------------------------

    def test_deck_context_uses_same_provider(self):
        """Within a router context, the same provider is reused for a module."""
        groq_instance = MagicMock()
        groq_instance.generate.return_value = self._valid_json({"provider": "groq"})
        groq_class = MagicMock(return_value=groq_instance)

        with self._set_api_keys("groq", "cerebras"):
            with patch("backend.llm.router.OpenAICompatibleProvider", return_value=groq_instance):
                router.set_router_context(deck_id="deck-1")
                try:
                    r1 = router.generate_json("content_generator", "prompt 1")
                    r2 = router.generate_json("content_generator", "prompt 2")
                finally:
                    router.clear_router_context()

        self.assertEqual(r1["provider"], "groq")
        self.assertEqual(r2["provider"], "groq")

    def test_module_provider_cache_without_context(self):
        """Without a context, module-level cache still reuses providers."""
        instance = MagicMock()
        instance.generate.return_value = self._valid_json({"ok": True})
        with self._set_api_keys("groq"):
            with patch("backend.llm.router.OpenAICompatibleProvider", return_value=instance):
                router.generate_json("intent", "prompt 1")
                router.generate_json("intent", "prompt 2")
        self.assertEqual(instance.generate.call_count, 2)


if __name__ == "__main__":
    unittest.main()
