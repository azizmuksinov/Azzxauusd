from rest_framework.permissions import BasePermission


class HasRole(BasePermission):
    """Foydalanuvchi ko'rsatilgan rollardan biriga ega bo'lsa ruxsat. `admin` roli va superuser — hamma joyda.

    Ishlatish: permission_classes = [HasRole.of("content_manager")]
    """

    roles: tuple[str, ...] = ()

    @classmethod
    def of(cls, *roles: str):
        return type(f"HasRole_{'_'.join(roles)}", (cls,), {"roles": roles})

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated and user.is_active):
            return False
        if user.is_superuser:
            return True
        names = set(user.groups.values_list("name", flat=True))
        return "admin" in names or bool(names.intersection(self.roles))
