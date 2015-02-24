from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import translation

from email_user.tests.factories import EmailUserFactory
from services.models import ServiceType, ProviderType, Provider, Service
from services.tests.factories import ProviderFactory, ServiceFactory


class ProviderTest(TestCase):
    def test_related_name(self):
        # Just make sure we can get to the provider using user.provider
        user = EmailUserFactory()
        provider = ProviderFactory(
            user=user,
        )
        self.assertEqual(user.provider, provider)

    def test_str(self):
        # str returns name_en
        provider = Provider(name_en="Frederick")
        self.assertEqual("Frederick", str(provider))

    @override_settings(PHONE_NUMBER_REGEX=r'^\d{2}-\d{6}$')
    def test_phone_number_validation(self):
        with self.assertRaises(ValidationError):
            ProviderFactory(phone_number='9').full_clean()
        with self.assertRaises(ValidationError):
            ProviderFactory(phone_number='ab-cdefgh').full_clean()
        with self.assertRaises(ValidationError):
            ProviderFactory(phone_number='12-3456789').full_clean()
        with self.assertRaises(ValidationError):
            ProviderFactory(phone_number='12345678').full_clean()
        ProviderFactory(phone_number='12-345678').full_clean()


class ProviderTypeTest(TestCase):
    def test_str(self):
        # str() returns name in current language
        obj = ProviderType(name_en="English", name_ar="Arabic", name_fr="French")
        translation.activate('fr')
        self.assertEqual("French", str(obj))
        translation.activate('ar')
        self.assertEqual("Arabic", str(obj))
        translation.activate('en')
        self.assertEqual("English", str(obj))
        translation.activate('de')
        self.assertEqual("English", str(obj))


class ServiceTypeTest(TestCase):
    def test_str(self):
        # str() returns name in current language
        obj = ServiceType(name_en="English", name_ar="Arabic", name_fr="French")
        translation.activate('fr')
        self.assertEqual("French", str(obj))
        translation.activate('ar')
        self.assertEqual("Arabic", str(obj))
        translation.activate('en')
        self.assertEqual("English", str(obj))
        translation.activate('de')
        self.assertEqual("English", str(obj))


class ServiceTest(TestCase):
    def test_str(self):
        # str returns name_en
        service = Service(name_en="Frederick")
        self.assertEqual("Frederick", str(service))

    def test_email_provider_about_approval(self):
        service = ServiceFactory()
        with patch('services.models.email_provider_about_service_approval_task') as mock_task:
            service.email_provider_about_approval()
        mock_task.delay.assert_called_with(service.pk)
