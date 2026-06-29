"""Custom template filters for GhanaHammer auctions"""
from django import template

register = template.Library()


@register.filter(name='split')
def split_string(value, delimiter=','):
    """Split a string by delimiter and return list."""
    return [v.strip() for v in str(value).split(delimiter)]


@register.filter(name='make_list')
def make_list(value):
    """Convert string to list of characters."""
    return list(str(value))


@register.filter(name='multiply')
def multiply(value, arg):
    """Multiply value by arg."""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter(name='currency_ghs')
def currency_ghs(value):
    """Format number as GHS currency."""
    try:
        return f"GHS {float(value):,.2f}"
    except (ValueError, TypeError):
        return f"GHS {value}"
