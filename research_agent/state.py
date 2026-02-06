import os
import json

class StateStore:
    def __init__(self) -> None:
        base = os.path.join(os.getcwd(), "state_store")
        try:
            os.makedirs(base, exist_ok=True)
        except Exception:
            pass
        self.base = base

    def save(self, cid: str, state: dict) -> None:
        try:
            p = os.path.join(self.base, f"{cid}.json")
            with open(p, "w", encoding="utf-8") as f:
                f.write(json.dumps(state, ensure_ascii=False))
        except Exception:
            pass
