"""AKHU AFIVS — Verification Forms"""
from django import forms
from django.utils.translation import gettext_lazy as _


class PersonalInfoForm(forms.Form):
    REGION_CHOICES = [
        ('', _('-- Select Exam Region --')),
        ('Xorazm', 'Xorazm'),
        ('Qoraqalpogʻiston Respublikasi', 'Qoraqalpogʻiston Respublikasi'),
        ('Toshkent shahri', 'Toshkent shahri'),
        ('Fargʻona', 'Fargʻona'),
        ('Samarqand', 'Samarqand'),
        ('Surxondaryo', 'Surxondaryo'),
    ]

    surname = forms.CharField(
        label=_('Surname'),
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Enter surname')}),
    )
    given_name = forms.CharField(
        label=_('Given Name'),
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Enter given name')}),
    )
    passport_number = forms.CharField(
        label=_('Card / Passport Number'),
        max_length=50,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'AD8921445', 'style': 'text-transform: uppercase;'}),
    )
    selected_region = forms.ChoiceField(
        label=_('Exam Region'),
        choices=REGION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
