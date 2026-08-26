from django.core.exceptions import ValidationError
from allauth.account.forms import LoginForm, SignupForm, ResetPasswordForm


class CustomLoginForm(LoginForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['login'].widget.attrs.update({
            'class': 'auth-input',
            'placeholder': 'Email or Username'
        })

        self.fields['password'].widget.attrs.update({
            'class': 'auth-input',
            'placeholder': 'Password'
        })

    def clean(self):
        cleaned_data = super().clean()
        user = getattr(self, 'user', None)
        if user and not user.is_staff:
            raise ValidationError('Only administrators can sign in to this system.')
        return cleaned_data


class CustomSignupForm(SignupForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['email'].widget.attrs.update({
            'class': 'auth-input',
            'placeholder': 'Email'
        })

        self.fields['username'].widget.attrs.update({
            'class': 'auth-input',
            'placeholder': 'Username'
        })

        self.fields['password1'].widget.attrs.update({
            'class': 'auth-input',
            'placeholder': 'Password'
        })

        self.fields['password2'].widget.attrs.update({
            'class': 'auth-input',
            'placeholder': 'Password (again)'
        })

class CustomResetPasswordForm(ResetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['email'].widget.attrs.update({
            'class': 'auth-input',
            'placeholder': 'Email'
        })