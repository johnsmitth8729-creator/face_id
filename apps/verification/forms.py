"""AKHU AFIVS — Verification Forms"""
from django import forms
from django.utils.translation import gettext_lazy as _


class PersonalInfoForm(forms.Form):
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
        choices=[],
        widget=forms.Select(attrs={'class': 'form-control'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.accounts.models import ExamVenueConfig
        choices = [('', _('-- Select Exam Region --'))]
        for config in ExamVenueConfig.objects.all().order_by('region'):
            choices.append((config.region, config.region))
        self.fields['selected_region'].choices = choices
