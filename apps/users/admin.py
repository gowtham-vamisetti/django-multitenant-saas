from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class TenantUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Profile", {"fields": ('display_name',)}),)
    list_display = ('username', 'email', 'display_name', 'is_staff', 'is_active')
