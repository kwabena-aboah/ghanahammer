"""
apps/gh_auctions/forms.py
Django forms for the GhanaHammer auctions app.
"""
from django import forms
from django.utils.text import slugify

from apps.gh_auctions.models import Category


class CategoryForm(forms.ModelForm):
    """Form for creating and editing auction categories."""

    class Meta:
        model = Category
        fields = [
            "name",
            "slug",
            "parent",
            "icon",
            "image",
            "description",
            "is_active",
            "sort_order",
        ]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "e.g. Vehicles, Electronics",
            }),
            "slug": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "auto-generated from name if left blank",
            }),
            "parent": forms.Select(attrs={"class": "form-select"}),
            "icon": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Bootstrap icon class e.g. bi-car-front",
            }),
            "image": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Short description of this category (optional)",
            }),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "sort_order": forms.NumberInput(attrs={
                "class": "form-control",
                "min": 0,
            }),
        }
        help_texts = {
            "slug": "URL-friendly identifier. Leave blank to auto-generate from name.",
            "icon": "Bootstrap Icons class name, e.g. bi-car-front, bi-phone, bi-house.",
            "sort_order": "Lower numbers appear first in navigation.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Exclude the category itself from parent choices when editing
        if self.instance and self.instance.pk:
            self.fields["parent"].queryset = Category.objects.exclude(pk=self.instance.pk)
        else:
            self.fields["parent"].queryset = Category.objects.all()
        self.fields["parent"].empty_label = "— None (top-level category) —"

    def clean_slug(self):
        slug = self.cleaned_data.get("slug", "").strip()
        name = self.cleaned_data.get("name", "")
        if not slug:
            slug = slugify(name)
        return slug

    def clean(self):
        cleaned = super().clean()
        slug = cleaned.get("slug")
        name = cleaned.get("name")
        if not slug and name:
            cleaned["slug"] = slugify(name)
        return cleaned
