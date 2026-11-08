"""AI provayder sozlamalarini tekshirish (ishga tushishda log uchun): kalit, model, kichik so'rov."""

import time

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.ai_cards import client, gemini


class Command(BaseCommand):
    help = "AI provayder (AI_PROVIDER) kaliti va modeli ishlashini tekshiradi."

    def handle(self, *args, **opts):
        provider, model = client.provider(), client.model_name()
        self.stdout.write(
            f"AI: provayder {provider}, model {model or '—'}, internet qidiruvi: {client.has_search()}"
        )
        if provider == "gemini":
            if not settings.GEMINI["API_KEY"]:
                self.stdout.write("AI: Gemini kaliti sozlanmagan (GEMINI_API_KEY).")
                return
            self._list_gemini_models()
        started = time.monotonic()
        try:
            res = client.generate("Faqat OK deb javob ber.", search=False)
            self.stdout.write(
                f"AI: model ishlaydi ({res.model}), {time.monotonic() - started:.1f} s: {res.text[:40]!r}"
            )
        except client.AiError as exc:
            self.stdout.write(f"AI: model ISHLAMAYDI ({time.monotonic() - started:.1f} s): {exc.message}")

    def _list_gemini_models(self) -> None:
        cfg = settings.GEMINI
        try:
            with gemini.client(timeout=20) as c:
                r = c.get(
                    f"{cfg['BASE_URL'].rstrip('/')}/models?pageSize=200",
                    headers={"x-goog-api-key": cfg["API_KEY"]},
                )
        except httpx.HTTPError as exc:
            self.stdout.write(f"AI: Gemini bilan aloqa yo'q: {exc}")
            return
        if r.status_code != 200:
            self.stdout.write(f"AI: Gemini modellar ro'yxati olinmadi ({r.status_code}).")
            return
        names = [
            m["name"].removeprefix("models/")
            for m in r.json().get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])
        ]
        flash = [
            n for n in names if "flash" in n and not any(x in n for x in ("image", "tts", "live", "audio"))
        ]
        self.stdout.write(f"AI: Gemini flash modellar: {', '.join(flash)}")
