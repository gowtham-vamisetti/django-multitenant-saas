from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    display_name = models.CharField(max_length=120, blank=True)

    def __str__(self) -> str:
        return self.display_name or self.username
