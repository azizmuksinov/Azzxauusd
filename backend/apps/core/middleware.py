from django.conf import settings


class FrameAncestorsMiddleware:
    """Sahifani faqat ruxsat etilgan saytlar iframe ichida ko'rsatishi mumkin (CSP frame-ancestors).

    Demo: Hugging Face Space ilovani huggingface.co sahifasi ichida iframe'da ochadi.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        origins = " ".join(getattr(settings, "FRAME_ANCESTORS", []))
        self.header = f"frame-ancestors 'self' {origins}".strip()

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", self.header)
        return response
