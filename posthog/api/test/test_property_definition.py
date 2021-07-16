import random
from typing import Dict

from rest_framework import status

from posthog.demo import create_demo_team
from posthog.models import Organization, PropertyDefinition, Team
from posthog.tasks.calculate_event_property_usage import calculate_event_property_usage_for_team
from posthog.test.base import APIBaseTest


class TestPropertyDefinitionAPI(APIBaseTest):

    demo_team: Team = None  # type: ignore

    EXPECTED_PROPERTY_DEFINITIONS = [
        {"name": "$browser", "query_usage_30_day": 0, "is_numerical": False},
        {"name": "$current_url", "query_usage_30_day": 0, "is_numerical": False},
        {"name": "is_first_movie", "query_usage_30_day": 0, "is_numerical": False},
        {"name": "app_rating", "query_usage_30_day": 0, "is_numerical": True},
        {"name": "plan", "query_usage_30_day": 0, "is_numerical": False},
        {"name": "purchase", "query_usage_30_day": 0, "is_numerical": True},
        {"name": "purchase_value", "query_usage_30_day": 0, "is_numerical": True},
        {"name": "first_visit", "query_usage_30_day": 0, "is_numerical": False},
    ]

    @classmethod
    def setUpTestData(cls):
        random.seed(900)
        super().setUpTestData()
        cls.demo_team = create_demo_team(cls.organization)
        calculate_event_property_usage_for_team(cls.demo_team.pk)
        cls.user.current_team = cls.demo_team
        cls.user.save()

    def test_list_property_definitions(self):

        response = self.client.get("/api/projects/@current/property_definitions/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["count"], len(self.EXPECTED_PROPERTY_DEFINITIONS))

        self.assertEqual(len(response.json()["results"]), len(self.EXPECTED_PROPERTY_DEFINITIONS))

        volume_usage_cursor = 9999999999

        for item in self.EXPECTED_PROPERTY_DEFINITIONS:
            response_item: Dict = next((_i for _i in response.json()["results"] if _i["name"] == item["name"]), {})
            self.assertEqual(response_item["query_usage_30_day"], item["query_usage_30_day"])
            self.assertEqual(response_item["is_numerical"], item["is_numerical"])

        for response_item in response.json()["results"]:
            # We test that queries are ordered too based on highest usage
            # Normally we return objects with higher query usage first, then with higher event volume
            # As all test objects have query_usage_30_day=0, we test with volume_usage_cursor
            self.assertGreaterEqual(volume_usage_cursor, response_item["volume_30_day"])
            volume_usage_cursor = response_item["volume_30_day"]

    def test_pagination_of_property_definitions(self):
        PropertyDefinition.objects.bulk_create(
            [PropertyDefinition(team=self.demo_team, name="z_property_{}".format(i)) for i in range(1, 301)]
        )

        response = self.client.get("/api/projects/@current/property_definitions/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["count"], 308)
        self.assertEqual(len(response.json()["results"]), 100)  # Default page size
        self.assertEqual(response.json()["results"][0]["name"], "$browser")  # Order by name (ascending)

        property_checkpoints = [
            182,
            272,
            92,
        ]  # Because Postgres's sorter does this: property_1; property_100, ..., property_2, property_200, ..., it's
        # easier to deterministically set the expected events

        for i in range(0, 3):
            response = self.client.get(response.json()["next"])
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            self.assertEqual(response.json()["count"], 308)
            self.assertEqual(
                len(response.json()["results"]), 100 if i < 2 else 8,
            )  # Each page has 100 except the last one
            self.assertEqual(response.json()["results"][0]["name"], f"z_property_{property_checkpoints[i]}")

    def test_cant_see_property_definitions_for_another_team(self):
        org = Organization.objects.create(name="Separate Org")
        team = Team.objects.create(organization=org, name="Default Project")
        team.event_properties = self.demo_team.event_properties + [f"should_be_invisible_{i}" for i in range(0, 5)]
        team.save()

        response = self.client.get("/api/projects/@current/property_definitions/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for item in response.json()["results"]:
            self.assertNotIn("should_be_invisible", item["name"])

        # Also can't fetch for a team to which the user doesn't have permissions
        response = self.client.get(f"/api/projects/{team.pk}/property_definitions/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.json(), self.permission_denied_response())

    def test_search_property_definitions(self):

        # Regular search
        response = self.client.get("/api/projects/@current/property_definitions/?search=firs")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(response_data["count"], 2)
        # We test ordering too (best matches go first, regardless of other attributes)
        # note that is_first_movie has more events, yet first_visit is returned first because it has a higher match
        self.assertEqual(response_data["results"][0]["name"], "first_visit")  # this has similarity 0.31
        self.assertEqual(response_data["results"][1]["name"], "is_first_movie")  # this has similarity 0.25

        # Fuzzy search 1
        response = self.client.get("/api/projects/@current/property_definitions/?search=rting")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["count"], 1)
        for item in response.json()["results"]:
            self.assertIn(item["name"], ["app_rating"])

        # Handles URL encoding properly
        response = self.client.get("/api/projects/@current/property_definitions/?search=%24cur")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["count"], 1)
        for item in response.json()["results"]:
            self.assertIn(item["name"], ["$current_url"])

        # Fuzzy search 2
        response = self.client.get("/api/projects/@current/property_definitions/?search=hase%20")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.json()["count"], 2)
        for item in response.json()["results"]:
            self.assertIn(item["name"], ["purchase", "purchase_value"])

    def test_filter_numerical_property_definitions(self):

        response = self.client.get("/api/projects/@current/property_definitions/?is_numerical=true")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["count"], 3)
        for item in response.json()["results"]:
            self.assertIn(item["name"], ["purchase", "purchase_value", "app_rating"])

        response = self.client.get("/api/projects/@current/property_definitions/?is_numerical=0")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["count"], 4)
        for item in response.json()["results"]:
            self.assertIn(item["name"], ["$current_url", "is_first_movie", "plan", "first_visit"])
