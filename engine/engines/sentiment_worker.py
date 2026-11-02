"""distilbert sentiment over review text. Runs in .venv-ml, like Chronos.

Reading what customers wrote is a language problem, so a language model does it.
Classifying it in the browser was a demo; doing it here means the verdict agent
can actually use the result.
"""
import json
import sys
import warnings

warnings.filterwarnings("ignore")

MODEL = "distilbert-base-uncased-finetuned-sst-2-english"


def main():
    req = json.loads(sys.stdin.read())
    items = req.get("items") or []
    if not items:
        print(json.dumps({"results": []}))
        return
    from transformers import pipeline
    clf = pipeline("sentiment-analysis", model=req.get("model") or MODEL, device=-1)
    texts = [i["text"] for i in items]
    out = clf(texts, truncation=True, batch_size=16)
    results = [{"id": items[n]["id"], "label": out[n]["label"], "score": float(out[n]["score"])}
               for n in range(len(items))]
    print(json.dumps({"model": req.get("model") or MODEL, "results": results}))


if __name__ == "__main__":
    main()
