"""Chronos, any checkpoint, isolated in .venv-ml.

Uses BaseChronosPipeline so the original T5 models and the newer Bolt models
are both callable the same way, and asks for quantiles directly rather than
sampling paths: a reorder decision needs a distribution, and Bolt gives one
without sampling.

  echo '{"items":[{"id":"x","series":[...]}],"horizon":14,"model":"..."}' \
      | .venv-ml/bin/python engines/chronos_worker.py
"""
import json
import sys
import warnings

warnings.filterwarnings("ignore")

LEVELS = [0.1, 0.5, 0.9]


def main():
    req = json.loads(sys.stdin.read())
    items = req.get("items") or []
    horizon = int(req.get("horizon") or 14)
    model_name = req.get("model") or "amazon/chronos-bolt-small"

    import torch
    from chronos import BaseChronosPipeline

    pipe = BaseChronosPipeline.from_pretrained(model_name, device_map="cpu",
                                               torch_dtype=torch.float32)
    out = {}
    for item in items:
        series = item.get("series") or []
        if len(series) < 8:
            out[item["id"]] = {"error": "only %d points" % len(series)}
            continue
        ctx = torch.tensor(series, dtype=torch.float32)
        q, _mean = pipe.predict_quantiles(context=ctx, prediction_length=horizon,
                                          quantile_levels=LEVELS)
        arr = q[0].numpy()                      # (horizon, levels)
        p10 = [float(v) for v in arr[:, 0]]
        p50 = [float(v) for v in arr[:, 1]]
        p90 = [float(v) for v in arr[:, 2]]
        out[item["id"]] = {"p10": p10, "p50": p50, "p90": p90,
                           "total_p50": float(sum(p50)), "total_p90": float(sum(p90)),
                           "total_p10": float(sum(p10))}
    print(json.dumps({"model": model_name, "horizon": horizon, "forecasts": out}))


if __name__ == "__main__":
    main()
