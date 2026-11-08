"""AI xizmatlarini tekshirish (ishga tushishda log uchun): qaysilari ulangan va modellar ro'yxati.

Standart holda generatsiya qilinmaydi (kvota sarflanmaydi); `--generate` — har biriga kichik so'rov.
"""

import time

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.ai_cards import client, gemini, openai_compat


class Command(BaseCommand):
    help = "Ulangan AI xizmatlari, ularning tartibi va modellarini tekshiradi."

    def add_arguments(self, parser):
        parser.add_argument(
            "--generate", action="store_true", help="Har biriga kichik so'rov (kvota sarflaydi)"
        )

    def handle(self, *args, generate=False, **opts):
        for p in client.providers():
            state = "ulangan" if p.configured else "kalit yo'q"
            self.stdout.write(
                f"AI: {p.name} ({p.label}) — {state}; model {p.model or '—'}; qidiruv: {p.search}"
            )
            if not p.configured:
                continue
            self._models(p)
            if generate:
                started = time.monotonic()
                try:
                    if p.name == "gemini":
                        res = gemini.generate("Faqat OK deb javob ber.", search=False, max_tokens=16)
                    else:
                        res = openai_compat.generate(
                            "Faqat OK deb javob ber.", client._config(p.name), max_tokens=16
                        )
                    self.stdout.write(
                        f"AI: {p.name} ishlaydi ({res.model}), {time.monotonic() - started:.1f} s"
                    )
                except client.AiError as exc:
                    self.stdout.write(
                        f"AI: {p.name} ISHLAMAYDI ({time.monotonic() - started:.1f} s): {exc.message}"
                    )
        if not client.active():
            self.stdout.write("AI: hech bir xizmat ulanmagan.")
        if settings.AI_CARDS.get("FREE_RESEARCH"):
            from apps.ai_cards import research

            started = time.monotonic()
            hits = research.web_search("Samsung RB38T676FSA", max_results=5)
            text = research.read_page(hits[0]["href"]) if hits else ""
            self.stdout.write(
                f"AI: bepul qidiruv — {len(hits)} ta natija"
                + (f" (birinchisi: {hits[0]['href'][:80]})" if hits else "")
                + f"; sahifa matni: {len(text)} belgi; {time.monotonic() - started:.1f} s"
            )

    def _models(self, p) -> None:
        if p.name == "gemini":
            cfg = settings.GEMINI
            url, headers = (
                f"{cfg['BASE_URL'].rstrip('/')}/models?pageSize=200",
                {"x-goog-api-key": cfg["API_KEY"]},
            )
        else:
            cfg = client._config(p.name)
            url = f"{cfg['base_url'].rstrip('/')}/models"
            headers = {**(cfg.get("headers") or {})}
            if cfg.get("api_key"):
                headers["Authorization"] = f"Bearer {cfg['api_key']}"
        try:
            with gemini.client(timeout=20) as c:
                r = c.get(url, headers=headers)
        except httpx.HTTPError as exc:
            self.stdout.write(f"AI: {p.name}: aloqa yo'q: {exc}")
            return
        if r.status_code != 200:
            self.stdout.write(f"AI: {p.name}: modellar ro'yxati olinmadi ({r.status_code})")
            return
        data = r.json()
        items = data.get("models") or data.get("data") or []
        names = [
            str(m.get("name") or m.get("id") or "").removeprefix("models/")
            for m in items
            if isinstance(m, dict)
        ]
        if p.name == "gemini":
            names = [
                n
                for n in names
                if "flash" in n and not any(x in n for x in ("image", "tts", "live", "audio"))
            ]
        self.stdout.write(f"AI: {p.name} modellar: {', '.join(names[:40])}")
