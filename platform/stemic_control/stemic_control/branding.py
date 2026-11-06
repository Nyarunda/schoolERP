"""Stemic's name and icons on the admin site's web pages (login, set-password), instead of ERPNext's."""

FOOTER = ('Powered by <a href="https://stemic.cloud" target="_blank" rel="noopener" class="text-muted">'
          "Stemic Technologies</a>")


def website_context(context):
    return {"footer_powered": FOOTER, "favicon": "/assets/stemic_control/images/stemic-favicon.svg",
            "splash_image": "/assets/stemic_control/images/stemic-wordmark.svg"}
