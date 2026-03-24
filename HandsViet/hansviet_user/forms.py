from django import forms
from hansviet_admin.models import Lead


class LeadForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = ["name", "phone", "email", "message", "page"]
        widgets = {
            "page": forms.HiddenInput(),
        }
