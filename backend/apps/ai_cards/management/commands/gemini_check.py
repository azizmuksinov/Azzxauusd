"""Gemini kaliti va model mavjudligini tekshirish (ishga tushishda log uchun). Generatsiyasiz — bepul."""

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.ai_cards import gemini


class Command(BaseCommand):
    help = "Gemini kaliti ishlashini va GEMINI_MODEL mavjudligini tekshiradi."

    def handle(self, *args, **opts):
        cfg = settings.GEMINI
        if not cfg["API_KEY"]:
            self.stdout.write("Gemini: kalit sozlanmagan (GEMINI_API_KEY).")
            return
        url = f"{cfg['BASE_URL'].rstrip('/')}/models?pageSize=200"
        try:
            with gemini.client(timeout=20) as c:
                r = c.get(url, headers={"x-goog-api-key": cfg["API_KEY"]})
        except httpx.HTTPError as exc:
            self.stdout.write(f"Gemini: aloqa yo'q: {exc}")
            return
        if r.status_code != 200:
            msg = (
                r.json().get("error", {}).get("message", "")
                if r.headers.get("content-type", "").startswith("application/json")
                else ""
            )
            self.stdout.write(f"Gemini: kalit ishlamadi ({r.status_code}): {msg}")
            return
        names = [
            m["name"].removeprefix("models/")
            for m in r.json().get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])
        ]
        ok = cfg["MODEL"] in names
        flash = [n for n in names if "flash" in n and "image" not in n and "tts" not in n and "live" not in n]
        self.stdout.write(
            f"Gemini: kalit ishlaydi. Model {cfg['MODEL']}: {'bor' if ok else 'YO`Q'}. "
            f"Flash modellar: {', '.join(flash[:12])}"
        )
