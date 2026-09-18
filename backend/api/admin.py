from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Conversation, Memory, Turn, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'display_name', 'email', 'is_staff', 'date_joined']
    fieldsets = BaseUserAdmin.fieldsets + (('Zer', {'fields': ('display_name',)}),)


class TurnInline(admin.TabularInline):
    model = Turn
    extra = 0
    readonly_fields = ['role', 'text', 'lang', 'source', 'created']


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'title', 'lang', 'updated', 'turn_count']
    list_filter = ['lang']
    search_fields = ['title', 'user__username']
    inlines = [TurnInline]

    @admin.display(description='turns')
    def turn_count(self, obj):
        return obj.turns.count()


@admin.register(Memory)
class MemoryAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'fact', 'updated']
    search_fields = ['fact', 'user__username']
