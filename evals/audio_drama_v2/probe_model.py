"""One tiny availability probe, restricted to the user's two authorized models."""
import argparse
import json
import re
import sqlite3
from pathlib import Path

from openai import OpenAI
from run_evaluation import ALLOWED_MODELS, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=ALLOWED_MODELS, default="qwen3.8-27b")
    parser.add_argument("--provider-id", type=int, default=1)
    parser.add_argument("--config-dir", default=str(ROOT / ".local-data"))
    args = parser.parse_args()
    path = Path(args.config_dir).resolve() / "app_test.db"
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        row = db.execute("SELECT api_key,api_base_url FROM llm_provider WHERE id=?", (args.provider_id,)).fetchone()
    if not row or not row[0]:
        parser.error("Configured provider or credentials are missing; no fallback")
    client = OpenAI(api_key=row[0], base_url=row[1], timeout=30, max_retries=0)
    try:
        result = client.chat.completions.create(
            model=args.model, messages=[{"role": "user", "content": "只回复OK。"}],
            max_tokens=16, extra_body={"enable_thinking": False},
        )
        if result.model != args.model:
            raise ValueError("Provider returned a different model; refusing implicit fallback")
        print(json.dumps({"requested_model": args.model, "response_model": result.model,
                          "status": "available", "text": result.choices[0].message.content,
                          "usage": result.usage.model_dump() if result.usage else None}, ensure_ascii=False))
    except Exception as error:
        code = str(getattr(error, "code", "") or "")
        print(json.dumps({"requested_model": args.model, "status": "failed",
                          "http_status": getattr(error, "status_code", None),
                          "provider_code": code if re.fullmatch(r"[\w.-]{1,100}", code) else "",
                          "exception": type(error).__name__}, ensure_ascii=False))
        raise SystemExit(1)
    finally:
        client.close()


if __name__ == "__main__":
    main()
