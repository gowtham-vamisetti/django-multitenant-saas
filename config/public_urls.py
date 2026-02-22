from django.contrib import admin
from django.http import JsonResponse
from django.urls import path


def health(_: object):
    return JsonResponse({'status': 'ok', 'scope': 'public'})


urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', health),
]
