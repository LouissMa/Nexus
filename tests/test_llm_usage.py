import json
from unittest.mock import Mock

from nexus.llm import LLMConfig, OpenAICompatibleLLM


def test_usage_is_per_response_and_old_interface_still_returns_text(monkeypatch):
    from nexus import llm
    bodies = [{"choices": [{"message": {"content": "first"}}], "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}},
              {"choices": [{"message": {"content": "second"}}]},
              {"choices": [{"message": {"content": "third"}}]}]
    def response(*args, **kwargs):
        item = Mock()
        item.read.return_value = json.dumps(bodies.pop(0)).encode()
        context = Mock()
        context.__enter__ = Mock(return_value=item)
        context.__exit__ = Mock(return_value=False)
        return context
    monkeypatch.setattr(llm.urllib.request, "urlopen", response)
    model = OpenAICompatibleLLM(LLMConfig("fake"))
    assert model.generate_result("s", "u").usage["total_tokens"] == 3
    assert model.generate_result("s", "u").usage["status"] == "unavailable"
    assert model.generate("s", "u") == "third"
