import unittest

from toolkit.llm_service import get_corrections_from_llm


class _FakeUsage:
    def __init__(self, prompt_tokens=0, completion_tokens=0):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content, prompt_tokens=0, completion_tokens=0):
        self.choices = [_FakeChoice(content)]
        self.usage = _FakeUsage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)


class _FakeCompletions:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise RuntimeError("No fake responses left")
        return self._responses.pop(0)


class _FakeChat:
    def __init__(self, responses):
        self.completions = _FakeCompletions(responses)


class _FakeClient:
    def __init__(self, responses):
        self.chat = _FakeChat(responses)


class EmptyResultRetryTests(unittest.TestCase):
    def _base_config(self):
        return {
            "active_prompt": "default",
            "language": "en-US",
            "llm_provider": "ollama",
            "llm_model": "local-model",
            "llm_temperature": 0.7,
            "llm_max_tokens": 2000,
            "ai_only_corrections": True,
            "retry_on_empty_corrections": True,
        }

    def test_retries_once_with_temperature_zero_on_empty_nontrivial_result(self):
        text = "\n".join(
            [
                "Why did degradation start at a specific time?",
                "Does a specific transaction behave differently under peak load?",
                "Is there a hidden relationship between throughput and failures?",
                "These types of questions require custom prompts for investigation.",
                "What changed at that point?",
                "Which metrics deviated simultaneously?",
                "This is useful for analyzing spikes or sudden instability.",
                "Performance engineers validate assumptions across multiple metrics.",
                "Compare behavior across runs and evaluate regressions.",
                "Time-focused investigations often need correlation between response time, throughput, and host metrics.",
                "Transaction-specific deep analysis helps isolate problematic flows under load and verify tail latency behavior.",
                "Hypothesis validation requires checking whether error rates, saturation, and latency shifts occur together.",
            ]
        )

        first = _FakeResponse("[]", prompt_tokens=10, completion_tokens=2)
        second = _FakeResponse(
            '[{"explanation":"Missing period.","original":"Define scope","corrected":"Define scope."}]',
            prompt_tokens=11,
            completion_tokens=3,
        )
        client = _FakeClient([first, second])

        result, prompt_tokens, completion_tokens, _llm_time = get_corrections_from_llm(text, self._base_config(), client)

        self.assertEqual(1, len(result))
        self.assertEqual("Define scope.", result[0]["corrected"])
        self.assertEqual(21, prompt_tokens)
        self.assertEqual(5, completion_tokens)
        self.assertEqual(2, len(client.chat.completions.calls))
        self.assertEqual(0.7, client.chat.completions.calls[0]["temperature"])
        self.assertEqual(0.0, client.chat.completions.calls[1]["temperature"])

    def test_short_input_does_not_trigger_empty_retry(self):
        text = "Short text with no issues."
        client = _FakeClient([_FakeResponse("[]", prompt_tokens=4, completion_tokens=1)])

        result, _prompt_tokens, _completion_tokens, _llm_time = get_corrections_from_llm(text, self._base_config(), client)

        self.assertEqual([], result)
        self.assertEqual(1, len(client.chat.completions.calls))


if __name__ == "__main__":
    unittest.main()
