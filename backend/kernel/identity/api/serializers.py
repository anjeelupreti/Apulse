from rest_framework import serializers

from ..models import User


class MeSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = ("id", "email", "phone", "full_name", "full_name_ne", "preferred_language")
        read_only_fields = fields
