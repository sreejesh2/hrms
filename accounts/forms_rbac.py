from django import forms

from accounts.models import AppPermission, Role, User


class RoleForm(forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(
        queryset=AppPermission.objects.filter(is_active=True).order_by("module", "codename"),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Permissions",
    )

    class Meta:
        model = Role
        fields = ("name", "description", "is_active", "permissions")
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class AppPermissionForm(forms.ModelForm):
    class Meta:
        model = AppPermission
        fields = ("module", "codename", "name", "description", "is_active")
        help_texts = {
            "codename": "Use module.action format, e.g. people.view_employees",
            "module": "Group name, e.g. people, setup, access, payroll",
        }


class UserRolesForm(forms.ModelForm):
    roles = forms.ModelMultipleChoiceField(
        queryset=Role.objects.filter(is_active=True),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Roles",
    )

    class Meta:
        model = User
        fields = ("roles",)
