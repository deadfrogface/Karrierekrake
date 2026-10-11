"""Use the model's own chat template with its explicit reasoning switch off."""
from __future__ import annotations


def configure_non_thinking_chat(llm) -> bool:
    """Keep generation and CV prefill on exactly the same rendered template.

    /no_think in the user text is not sufficient for Qwen 3.8. The packaged
    Jinja template exposes enable_thinking, so bind it explicitly before use.
    Models/test doubles without that switch are left alone.
    """
    metadata = getattr(llm, "metadata", None) or {}
    template = metadata.get("tokenizer.chat_template")
    if not isinstance(template, str) or "enable_thinking" not in template:
        return False
    from llama_cpp.llama_chat_format import Jinja2ChatFormatter

    template = "{% set enable_thinking = false %}" + template
    eos_id, bos_id = int(llm.token_eos()), int(llm.token_bos())
    model = llm._model
    formatter = Jinja2ChatFormatter(
        template=template,
        eos_token=model.token_get_text(eos_id) if eos_id != -1 else "",
        bos_token=model.token_get_text(bos_id) if bos_id != -1 else "",
        stop_token_ids=[eos_id],
    )
    llm.chat_handler = formatter.to_chat_handler()
    # CV prompt counting/prefill reads this same metadata template.
    llm.metadata = dict(metadata, **{"tokenizer.chat_template": template})
    return True
