from __future__ import annotations

import pytest

from open_rando.poi_grid import PoiGrid, square_file_name

GRID = PoiGrid()


def test_point_inside_grid_maps_to_its_square():
    # Lyon. Steps: lon 1.2917, lat 1.3125.
    assert GRID.square_for_point(lat=45.76, lon=4.84) == (8, 3)


def test_point_on_south_west_corner_is_first_square():
    assert GRID.square_for_point(lat=41.0, lon=-5.5) == (0, 0)


def test_point_on_north_east_corner_is_last_square():
    assert GRID.square_for_point(lat=51.5, lon=10.0) == (11, 7)


def test_point_outside_grid_has_no_square():
    assert GRID.square_for_point(lat=40.0, lon=2.0) is None


def test_bounding_box_inside_one_square_returns_that_square():
    assert GRID.squares_for_bounding_box((4.9, 45.7, 5.0, 45.8)) == [(8, 3)]


def test_bounding_box_straddling_a_boundary_returns_both_squares():
    boundary_lon = GRID.square_bounding_box((7, 3))[2]
    squares = GRID.squares_for_bounding_box((boundary_lon - 0.01, 45.7, boundary_lon + 0.01, 45.8))
    assert squares == [(7, 3), (8, 3)]


def test_margin_widens_the_selection():
    boundary_lon = GRID.square_bounding_box((7, 3))[2]
    bounding_box = (boundary_lon - 0.5, 45.7, boundary_lon - 0.4, 45.8)
    assert GRID.squares_for_bounding_box(bounding_box) == [(7, 3)]
    assert GRID.squares_for_bounding_box(bounding_box, margin_degrees=0.5) == [
        (7, 3),
        (8, 3),
        (7, 4),
        (8, 4),
    ]


def test_bounding_box_outside_grid_returns_nothing():
    assert GRID.squares_for_bounding_box((20.0, 30.0, 21.0, 31.0)) == []


def test_every_point_belongs_to_a_square_whose_box_contains_it():
    lat, lon = 48.8566, 2.3522
    square = GRID.square_for_point(lat, lon)
    assert square is not None
    lon_min, lat_min, lon_max, lat_max = GRID.square_bounding_box(square)
    assert lon_min <= lon < lon_max
    assert lat_min <= lat < lat_max


@pytest.mark.parametrize(("square", "expected"), [((3, 4), "3_4.json"), ((11, 7), "11_7.json")])
def test_square_file_name(square, expected):
    assert square_file_name(square) == expected
