from http.client import FOUND
import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.urlresolvers import reverse
from django.test import TestCase

from rest_framework.authtoken.models import Token

from services.models import Provider, Service
from services.tests.factories import ProviderFactory, ProviderTypeFactory, ServiceAreaFactory


OK = 200
CREATED = 201


class ProviderAPITest(TestCase):
    def setUp(self):
        # Just using Django auth for now
        self.user = get_user_model().objects.create_superuser(
            password='password',
            email='joe@example.com',
        )
        assert self.client.login(email='joe@example.com', password='password')

        # Get the URL of the user for the API
        self.user_url = reverse('user-detail', args=[self.user.id])

    def test_create_provider_and_user(self):
        # User is NOT logged in when creating a new provider/user
        self.client.logout()

        url = '/api/providers/create_provider/'
        data = {
            'name_en': 'Joe Provider',
            'type': ProviderTypeFactory().get_api_url(),
            'phone_number': '12345',
            'description_en': 'Test provider',
            'email': 'fred@example.com',
            'password': 'foobar',
            'number_of_monthly_beneficiaries': '37',
        }
        rsp = self.client.post(url, data=data)
        self.assertEqual(CREATED, rsp.status_code, msg=rsp.content.decode('utf-8'))

        # Make sure they gave us back the id of the new record
        result = json.loads(rsp.content.decode('utf-8'))
        provider = Provider.objects.get(id=result['id'])
        self.assertEqual('Joe Provider', provider.name_en)
        self.assertEqual(37, provider.number_of_monthly_beneficiaries)
        user = get_user_model().objects.get(id=provider.user_id)
        self.assertFalse(user.is_active)
        self.assertTrue(user.activation_key)
        # We should have sent an activation email
        self.assertEqual(len(mail.outbox), 1)
        # with a link
        link = provider.user.get_activation_link()
        self.assertIn(link, mail.outbox[0].body)
        # user is not active
        self.assertFalse(provider.user.is_active)
        # Try activating them
        rsp = self.client.get(link, follow=False)
        self.assertEqual(FOUND, rsp.status_code, msg=rsp.content.decode('utf-8'))
        redirect_url = rsp['Location']
        if redirect_url.startswith('http://testserver'):
            redirect_url = redirect_url[len('http://testserver'):]
        self.assertEqual(settings.ACCOUNT_ACTIVATION_REDIRECT_URL, redirect_url)
        user = get_user_model().objects.get(id=provider.user_id)
        self.assertTrue(user.is_active)

    def test_get_provider_list(self):
        p1 = ProviderFactory()
        p2 = ProviderFactory()
        url = reverse('provider-list')
        rsp = self.client.get(url)
        self.assertEqual(OK, rsp.status_code, msg=rsp.content.decode('utf-8'))
        result = json.loads(rsp.content.decode('utf-8'))
        for item in result['results']:
            provider = Provider.objects.get(id=item['id'])
            self.assertIn(provider.name_en, [p1.name_en, p2.name_en])

    def test_get_one_provider(self):
        p1 = ProviderFactory()
        url = reverse('provider-detail', args=[p1.id])
        rsp = self.client.get(url)
        self.assertEqual(OK, rsp.status_code, msg=rsp.content.decode('utf-8'))
        result = json.loads(rsp.content.decode('utf-8'))
        self.assertEqual(p1.name_en, result['name_en'])


class TokenAuthTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            password='password',
            email='joe@example.com',
        )
        self.user_url = reverse('user-detail', args=[self.user.id])
        self.token = Token.objects.get(user=self.user).key

    def get_with_token(self, url):
        """
        Make a GET to a url, passing the token in the request headers.
        Return the response.
        """
        return self.client.get(
            url,
            HTTP_AUTHORIZATION="Token %s" % self.token
        )

    def post_with_token(self, url, data):
        return self.client.post(
            url,
            data=data,
            HTTP_AUTHORIZATION="Token %s" % self.token
        )

    def test_get_one_provider(self):
        p1 = ProviderFactory()
        url = reverse('provider-detail', args=[p1.id])
        rsp = self.get_with_token(url)
        self.assertEqual(OK, rsp.status_code, msg=rsp.content.decode('utf-8'))
        result = json.loads(rsp.content.decode('utf-8'))
        self.assertEqual(p1.name_en, result['name_en'])

    def test_create_provider(self):
        url = reverse('provider-list')
        data = {
            'name': 'Joe Provider',
            'type': ProviderTypeFactory().get_api_url(),
            'phone_number': '12345',
            'description': 'Test provider',
            'user': self.user_url,
            'number_of_monthly_beneficiaries': '37',
        }
        rsp = self.post_with_token(url, data=data)
        self.assertEqual(CREATED, rsp.status_code, msg=rsp.content.decode('utf-8'))


class ServiceAPITest(TestCase):
    def setUp(self):
        # Just using Django auth for now
        self.user = get_user_model().objects.create_superuser(
            password='password',
            email='joe@example.com',
        )
        assert self.client.login(email='joe@example.com', password='password')
        self.provider = ProviderFactory()

    def test_create_service(self):
        area = ServiceAreaFactory()
        data = {
            'provider': self.provider.get_api_url(),
            'name_en': 'Some service',
            'area_of_service': area.get_api_url(),
            'description_en': "Awesome\nService"
        }
        rsp = self.client.post(reverse('service-list'), data=data)
        self.assertEqual(CREATED, rsp.status_code, msg=rsp.content.decode('utf-8'))
        result = json.loads(rsp.content.decode('utf-8'))
        service = Service.objects.get(id=result['id'])
        self.assertEqual('Some service', service.name_en)


class ServiceAreaAPITest(TestCase):
    def setUp(self):
        # Just using Django auth for now
        self.user = get_user_model().objects.create_superuser(
            password='password',
            email='joe@example.com',
        )
        assert self.client.login(email='joe@example.com', password='password')
        self.area1 = ServiceAreaFactory()
        self.area2 = ServiceAreaFactory(parent=self.area1)
        self.area3 = ServiceAreaFactory(parent=self.area1)

    def test_get_areas(self):
        rsp = self.client.get(reverse('servicearea-list'))
        self.assertEqual(OK, rsp.status_code)
        result = json.loads(rsp.content.decode('utf-8'))
        results = result['results']
        names = [area.name_en for area in [self.area1, self.area2, self.area3]]
        for item in results:
            self.assertIn(item['name_en'], names)

    def test_get_area(self):
        rsp = self.client.get(self.area1.get_api_url())
        result = json.loads(rsp.content.decode('utf-8'))
        self.assertEqual(self.area1.id, result['id'])
        self.assertIn('http://testserver%s' % self.area2.get_api_url(), result['children'])
        self.assertIn('http://testserver%s' % self.area3.get_api_url(), result['children'])
        rsp = self.client.get(self.area2.get_api_url())
        result = json.loads(rsp.content.decode('utf-8'))
        self.assertEqual('http://testserver%s' % self.area1.get_api_url(), result['parent'])
