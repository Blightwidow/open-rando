from __future__ import annotations

from open_rando.fetchers.descriptions import RouteDescription, load_route_descriptions


class TestLoadRouteDescriptions:
    def test_returns_non_empty_dict(self) -> None:
        descriptions = load_route_descriptions()
        assert len(descriptions) > 0

    def test_values_are_route_description_instances(self) -> None:
        descriptions = load_route_descriptions()
        for value in descriptions.values():
            assert isinstance(value, RouteDescription)

    def test_known_route_is_present(self) -> None:
        descriptions = load_route_descriptions()
        assert "GR 13" in descriptions

    def test_known_route_has_non_empty_fields(self) -> None:
        descriptions = load_route_descriptions()
        route = descriptions["GR 13"]
        assert route.ref == "GR 13"
        assert len(route.tagline) > 0
        assert len(route.description) > 0

    def test_all_entries_have_non_empty_fields(self) -> None:
        descriptions = load_route_descriptions()
        for ref, route in descriptions.items():
            assert route.ref == ref
            assert route.tagline, f"{ref} has empty tagline"
            assert route.description, f"{ref} has empty description"
