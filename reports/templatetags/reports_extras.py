from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Cho phép tra cứu dict trong template: {{ mydict|get_item:key }}"""
    if not dictionary:
        return 0
    return dictionary.get(key, 0)
