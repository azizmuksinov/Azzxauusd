from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.core.phone import normalize_phone


class Language(models.TextChoices):
    UZ = "uz", "O'zbekcha"
    UZ_CYRL = "uz_cyrl", "Ўзбекча"
    RU = "ru", "Русский"


class Role(models.TextChoices):
    """Xodim rollari Django guruhlari sifatida yaratiladi (migratsiya 0002)."""

    COURIER = "courier", "Kuryer"
    WAREHOUSE = "warehouse", "Omborchi"
    LOGISTICS_MANAGER = "logistics_manager", "Logistika menejeri"
    CONTENT_MANAGER = "content_manager", "Kontent menejeri"
    SUPPORT = "support", "Qo'llab-quvvatlash"
    FINANCE = "finance", "Moliya"
    ADMIN = "admin", "Administrator"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, phone: str, password: str | None = None, **extra):
        user = self.model(phone=normalize_phone(phone), **extra)
        if password:
            user.set_password(password)
        else:
            # Xaridorlar faqat SMS-kod bilan kiradi.
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, phone: str, password: str, **extra):
        extra.update(is_staff=True, is_superuser=True)
        return self.create_user(phone, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    phone = models.CharField(max_length=16, unique=True)
    # Xodim logini (xaridorlarda bo'sh): xodim panelga login va parol bilan kiradi, uni administrator beradi.
    login = models.CharField(max_length=32, unique=True, null=True, blank=True)
    first_name = models.CharField(max_length=64, blank=True)
    last_name = models.CharField(max_length=64, blank=True)
    email = models.EmailField(blank=True)
    language = models.CharField(max_length=8, choices=Language.choices, default=Language.UZ)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS: list[str] = []

    def __str__(self):
        return self.phone

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def has_role(self, role: str) -> bool:
        return self.is_superuser or self.groups.filter(name=role).exists()

    def anonymize(self):
        """Akkaunt o'chirilganda: shaxsiy ma'lumotlar o'chiriladi, buyurtmalar tarixi qoladi."""
        self.phone = f"deleted-{self.pk}"
        self.login = None
        self.first_name = ""
        self.last_name = ""
        self.email = ""
        self.is_active = False
        self.deleted_at = timezone.now()
        self.set_unusable_password()
        self.save()
        self.addresses.all().delete()


class Address(TimeStampedModel):
    class Elevator(models.TextChoices):
        NONE = "none", "Lift yo'q"
        PASSENGER = "passenger", "Yo'lovchi lifti"
        FREIGHT = "freight", "Yuk lifti"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=32, blank=True)
    district = models.ForeignKey("geo.District", on_delete=models.PROTECT, related_name="+")
    settlement = models.CharField("mahalla / qishloq", max_length=128, blank=True)
    street = models.CharField(max_length=128)
    house = models.CharField(max_length=32)
    apartment = models.CharField(max_length=16, blank=True)
    entrance = models.CharField(max_length=8, blank=True)
    floor = models.SmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(-2), MaxValueValidator(60)]
    )
    elevator = models.CharField(max_length=10, choices=Elevator.choices, default=Elevator.NONE)
    intercom = models.CharField(max_length=16, blank=True)
    landmark = models.CharField("mo'ljal", max_length=255, blank=True)
    # MVP: oddiy koordinatalar. Logistika modulida PostGIS geography(Point) ga o'tkaziladi.
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    recipient_name = models.CharField(max_length=128)
    recipient_phone = models.CharField(max_length=16)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_default", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"], condition=models.Q(is_default=True), name="one_default_address_per_user"
            )
        ]

    def __str__(self):
        return f"{self.district}, {self.street} {self.house}"
