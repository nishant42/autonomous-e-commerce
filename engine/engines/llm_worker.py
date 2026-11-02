"""A local open-source LLM, for when the hosted one cannot be reached.

The judgment calls are deliberately small: pick one option from a fixed list
and say why in a sentence. That does not need a frontier model, and a local one
removes the last external dependency from the decision path. The harness checks
the answer against the permitted options either way, so a weak model degrades
to the default rather than doing damage.

  echo '{"prompt":"..."}' | .venv-ml/bin/python engines/llm_worker.py
"""
import json
import sys
import warnings

warnings.filterwarnings("ignore")

MODEL = "Qwen/Qwen2.5-0.5B-Instruct"


def main():
    req = json.loads(sys.stdin.read())
    prompt = req.get("prompt") or ""
    model_name = req.get("model") or MODEL
    max_new = int(req.get("max_tokens") or 160)

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    # Small CPU models spend more time coordinating a large thread pool than
    # generating tokens. Keep interactive demo turns responsive.
    torch.set_num_threads(2)

    tok = AutoTokenizer.from_pretrained(model_name)
    mdl = AutoModelForCausalLM.from_pretrained(model_name, dtype=torch.float32)
    mdl.eval()
    messages = [{"role": "system",
                 "content": "You answer with one JSON object and nothing else."},
                {"role": "user", "content": prompt}]
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tok([text], return_tensors="pt")
    with torch.no_grad():
        out = mdl.generate(**inputs, max_new_tokens=max_new, do_sample=False,
                           pad_token_id=tok.eos_token_id)
    reply = tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    print(json.dumps({"model": model_name, "text": reply,
                      "tokens_in": int(inputs["input_ids"].shape[1]),
                      "tokens_out": int(out.shape[1] - inputs["input_ids"].shape[1])}))


if __name__ == "__main__":
    main()
