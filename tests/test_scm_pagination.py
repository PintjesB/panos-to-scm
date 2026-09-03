import unittest

from scm.process import SCMObjectManager


class FakeObject:
    _endpoint = "/sse/config/v1/objects?"

    @classmethod
    def get_endpoint(cls):
        return cls._endpoint


class FakeObjectModule:
    FakeObject = FakeObject


class FakeApiHandler:
    def __init__(self, objects):
        self.objects = objects
        self.get_calls = []
        self.put_calls = []

    def get(self, endpoint, params=None):
        params = dict(params or {})
        self.get_calls.append((endpoint, params))
        offset = int(params.get("offset", 0))
        limit = int(params.get("limit", len(self.objects)))
        return self.objects[offset:offset + limit]

    def put(self, endpoint, item_data):
        self.put_calls.append((endpoint, dict(item_data)))
        return {"status": "success", "message": "Object updated", "name": item_data.get("name")}


class PaginationTests(unittest.TestCase):
    def make_manager(self, api_handler, obj_types=None):
        return SCMObjectManager(
            api_handler=api_handler,
            scope_param="folder=Shared",
            obj_module=FakeObjectModule,
            obj_types=obj_types or [],
            sec_obj=None,
            nat_obj=None,
        )

    def test_fetch_objects_retrieves_full_total_limit_in_500_item_pages(self):
        objects = [{"name": f"object-{index}", "id": str(index)} for index in range(1200)]
        api_handler = FakeApiHandler(objects)
        manager = self.make_manager(api_handler)

        result = manager.fetch_objects(FakeObject, limit=1200)

        self.assertEqual(1200, len(result))
        self.assertEqual(
            [
                {"folder": "Shared", "limit": 500, "offset": 0},
                {"folder": "Shared", "limit": 500, "offset": 500},
                {"folder": "Shared", "limit": 200, "offset": 1000},
            ],
            [params for _, params in api_handler.get_calls],
        )

    def test_large_total_limit_does_not_reduce_page_size_or_truncate_results(self):
        objects = [{"name": f"object-{index}", "id": str(index)} for index in range(1200)]
        api_handler = FakeApiHandler(objects)
        manager = self.make_manager(api_handler)

        result = manager.fetch_objects(FakeObject, limit=100000, position="pre")

        self.assertEqual(1200, len(result))
        self.assertEqual([0, 500, 1000], [params["offset"] for _, params in api_handler.get_calls])
        self.assertTrue(all(params["limit"] <= 500 for _, params in api_handler.get_calls))
        self.assertTrue(all(params["position"] == "pre" for _, params in api_handler.get_calls))

    def test_fetch_objects_stops_after_last_partial_page_without_truncating(self):
        objects = [{"name": f"object-{index}", "id": str(index)} for index in range(750)]
        api_handler = FakeApiHandler(objects)
        manager = self.make_manager(api_handler)

        result = manager.fetch_objects(FakeObject, limit=10000)

        self.assertEqual(750, len(result))
        self.assertEqual([500, 500], [params["limit"] for _, params in api_handler.get_calls])
        self.assertEqual([0, 500], [params["offset"] for _, params in api_handler.get_calls])

    def test_update_lookup_uses_paginated_fetch_and_can_find_object_after_first_page(self):
        objects = [
            {"name": f"object-{index}", "id": str(index), "value": "old"}
            for index in range(600)
        ]
        api_handler = FakeApiHandler(objects)
        manager = self.make_manager(api_handler, obj_types=[FakeObject])

        manager.update_existing_entries(
            {
                "FakeObject": [
                    {"name": "object-550", "id": "550", "value": "new"}
                ]
            },
            scope_param="folder=Shared",
            device_group_name=None,
            limit=1000,
        )

        self.assertTrue(api_handler.get_calls)
        self.assertTrue(all(call[1]["limit"] <= 500 for call in api_handler.get_calls))
        self.assertEqual([0, 500], [params["offset"] for _, params in api_handler.get_calls])
        self.assertEqual(1, len(api_handler.put_calls))
        self.assertEqual("/sse/config/v1/objects/550", api_handler.put_calls[0][0])


if __name__ == "__main__":
    unittest.main()
