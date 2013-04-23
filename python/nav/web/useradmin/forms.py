#
# Copyright (C) 2008 UNINETT AS
#
# This file is part of Network Administration Visualized (NAV).
#
# NAV is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License version 2 as published by
# the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
# more details.  You should have received a copy of the GNU General Public
# License along with NAV. If not, see <http://www.gnu.org/licenses/>.
#
# pylint: disable=R0903
"""Forms for the user admin system"""
from django import forms

from nav.models.profiles import Account, AccountGroup, PrivilegeType
from nav.models.manage import Organization


class AccountGroupForm(forms.ModelForm):
    """Form for adding an account to a group from account page"""
    name = forms.CharField(required=True)
    description = forms.CharField(required=True)

    class Meta:
        model = AccountGroup
        fields = ('name', 'description')


class AccountForm(forms.ModelForm):
    """Form for creating and editing an account"""
    password1 = forms.CharField(label='New password',
                                min_length=Account.MIN_PASSWD_LENGTH,
                                widget=forms.widgets.PasswordInput)
    password2 = forms.CharField(label='Repeat password',
                                min_length=Account.MIN_PASSWD_LENGTH,
                                widget=forms.widgets.PasswordInput,
                                required=False)
    login = forms.CharField(required=True)
    name = forms.CharField(required=True)

    def __init__(self, *args, **kwargs):
        super(AccountForm, self).__init__(*args, **kwargs)

        if kwargs.get('instance', False):
            self.fields['password1'].required = False

            # Remove password and login from external accounts
            if kwargs['instance'].ext_sync:
                del self.fields['password1']
                del self.fields['password2']
                del self.fields['login']

    def clean_password1(self):
        """Validate password"""
        password1 = self.data.get('password1')
        password2 = self.data.get('password2')

        if password1 != password2:
            raise forms.ValidationError('Passwords did not match')
        return password1

    def is_valid(self):
        if not super(AccountForm, self).is_valid():
            self.data = self.data.copy()
            if 'password1' in self.data:
                del self.data['password1']
            if 'password2' in self.data:
                del self.data['password2']
            return False
        return True

    class Meta:
        model = Account
        exclude = ('password', 'ext_sync', 'organizations')


class ChangePasswordForm(forms.Form):
    """Form for changing password for an account"""
    old_password = forms.CharField(label='Old password',
                                   widget=forms.widgets.PasswordInput)
    new_password1 = forms.CharField(label='New password',
                                    min_length=Account.MIN_PASSWD_LENGTH,
                                    widget=forms.widgets.PasswordInput)
    new_password2 = forms.CharField(label='Repeat password',
                                    min_length=Account.MIN_PASSWD_LENGTH,
                                    widget=forms.widgets.PasswordInput,
                                    required=False)

    def clean_password1(self):
        """Validate password for an account"""
        password1 = self.data.get('new_password1')
        password2 = self.data.get('new_password2')

        if password1 != password2:
            raise forms.ValidationError('Passwords did not match')
        return password1

    def clear_passwords(self):
        """Clear passwords from the form"""
        self.data = self.data.copy()
        if 'new_password1' in self.data:
            del self.data['new_password1']
        if 'new_password2' in self.data:
            del self.data['new_password2']
        if 'old_password' in self.data:
            del self.data['old_password']

    def is_valid(self):
        if not super(ChangePasswordForm, self).is_valid():
            self.clear_passwords()
            return False
        return True


class PrivilegeForm(forms.Form):
    """Form for adding a privilege to a group"""
    type = forms.models.ModelChoiceField(PrivilegeType.objects.all(),
                                         widget=forms.RadioSelect(),
                                         empty_label=None)
    target = forms.CharField(required=True)


class OrganizationAddForm(forms.Form):
    """Form for adding an organization to an account"""
    def __init__(self, account, *args, **kwargs):
        super(OrganizationAddForm, self).__init__(*args, **kwargs)
        if account:
            query = Organization.objects.exclude(
                id__in=account.organizations.all())
        else:
            query = Organization.objects.all()

        self.fields['organization'] = forms.models.ModelChoiceField(
            queryset=query, required=True)


class GroupAddForm(forms.Form):
    """Form for adding or editing a group"""
    group = forms.models.ModelChoiceField(AccountGroup.objects.all(),
                                          required=True)


class AccountAddForm(forms.Form):
    """Form for adding a user to a group from the group page"""
    account = forms.models.ModelChoiceField(Account.objects.all(),
                                            required=True)
