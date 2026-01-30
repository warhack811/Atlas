from atlas.utils.resource_loader import ResourceLoader

def test_orchestrator_prompt_contract():
    ORCHESTRATOR_PROMPT = ResourceLoader.get_prompt("orchestrator_prompt")
    assert "{context}" in ORCHESTRATOR_PROMPT
    assert "{history}" in ORCHESTRATOR_PROMPT
    assert "{message}" in ORCHESTRATOR_PROMPT

def test_synthesizer_prompt_contract():
    SYNTHESIZER_PROMPT = ResourceLoader.get_prompt("synthesizer_prompt")
    assert "{history}" in SYNTHESIZER_PROMPT
    assert "{raw_data}" in SYNTHESIZER_PROMPT
    assert "{user_message}" in SYNTHESIZER_PROMPT
