from django.utils.deprecation import MiddlewareMixin

THEME_COOKIE = "hrms_theme"
VALID_THEMES = {"light", "dark"}


class ThemeMiddleware(MiddlewareMixin):
    """Attach request.theme from cookie (default: light)."""

    def process_request(self, request):
        theme = request.COOKIES.get(THEME_COOKIE, "light")
        if theme not in VALID_THEMES:
            theme = "light"
        request.theme = theme
