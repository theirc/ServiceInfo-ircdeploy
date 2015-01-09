import json
from django.contrib.auth.models import User
from django.test import TestCase
from services.models import Provider
from services.tests.factories import ProviderFactory


OK = 200
CREATED = 201


class ProviderAPITest(TestCase):
    def setUp(self):
        # Just using Django auth for now
        self.user = User.objects.create_superuser(
            username='joe',
            password='password',
            email='joe@example.com',
        )
        self.client.login(username='joe', password='password')

    def test_create_provider(self):
        url = '/api/providers/'
        data = {
            'name': 'Joe Provider',
            'type': 1,
            'phone_number': '12345',
            'description': 'Test provider',
        }
        rsp = self.client.post(url, data=data)
        self.assertEqual(CREATED, rsp.status_code, msg=rsp.content.decode('utf-8'))

        # Make sure they gave us back the id of the new record
        result = json.loads(rsp.content.decode('utf-8'))
        provider = Provider.objects.get(id=result['id'])
        self.assertEqual('Joe Provider', provider.name)

    def test_get_provider_list(self):
        p1 = ProviderFactory()
        p2 = ProviderFactory()
        url = '/api/providers/'
        rsp = self.client.get(url)
        self.assertEqual(OK, rsp.status_code, msg=rsp.content.decode('utf-8'))
        result = json.loads(rsp.content.decode('utf-8'))
        for item in result['results']:
            provider = Provider.objects.get(id=item['id'])
            self.assertIn(provider.name, [p1.name, p2.name])

    def test_get_one_provider(self):
        p1 = ProviderFactory()
        url = '/api/providers/%d/' % p1.id
        rsp = self.client.get(url)
        self.assertEqual(OK, rsp.status_code, msg=rsp.content.decode('utf-8'))
        result = json.loads(rsp.content.decode('utf-8'))
        self.assertEqual(p1.name, result['name'])