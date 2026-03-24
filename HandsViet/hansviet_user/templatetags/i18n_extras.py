from django import template
from django.utils.translation import get_language

register = template.Library()


@register.simple_tag
def tr(vi_text, en_text):
    lang = (get_language() or "en").lower()
    return en_text if lang.startswith("en") else vi_text

