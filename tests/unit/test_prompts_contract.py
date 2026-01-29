from Atlas.prompts import ORCHESTRATOR_PROMPT, SYNTHESIZER_PROMPT

def test_orchestrator_prompt_contract():
    assert "{context}" in ORCHESTRATOR_PROMPT
    assert "{history}" in ORCHESTRATOR_PROMPT
    assert "{message}" in ORCHESTRATOR_PROMPT

def test_synthesizer_prompt_contract():
    assert "{history}" in SYNTHESIZER_PROMPT
    assert "{raw_data}" in SYNTHESIZER_PROMPT
    assert "{user_message}" in SYNTHESIZER_PROMPT
