import pytest

from pyromb import Builder, VectorLayer


class FakeLayer(VectorLayer):
    def __init__(self, records=None, geometries=None):
        self.records = records or []
        self.geometries = geometries or []

    def geometry(self, i: int) -> list:
        return self.geometries[i]

    def record(self, i: int) -> dict:
        return self.records[i]

    def __len__(self) -> int:
        return len(self.records)


def assert_qgis_error(exc_info, layer, text, fix):
    message = str(exc_info.value)
    assert message.startswith("\n\n")
    assert message.endswith("\n\n")
    assert layer in message
    assert text in message
    assert fix in message


def test_reach_duplicate_ids_show_layer_features_and_fix():
    layer = FakeLayer(
        records=[
            {"id": "r12", "t": 1, "s": 0.01},
            {"id": "r12", "t": 1, "s": 0.02},
        ],
        geometries=[
            [(0, 0), (1, 1)],
            [(1, 1), (2, 2)],
        ],
    )

    with pytest.raises(ValueError) as exc_info:
        Builder().reach(layer)

    assert_qgis_error(exc_info, "Reach layer", "duplicate id 'r12'", "Make every id unique")
    assert "feature index 0" in str(exc_info.value)
    assert "feature index 1" in str(exc_info.value)


def test_confluence_empty_geometry_has_visible_fix_message():
    layer = FakeLayer(records=[{"id": "c1", "out": 1}], geometries=[[]])

    with pytest.raises(ValueError) as exc_info:
        Builder().confluence(layer)

    assert_qgis_error(exc_info, "Confluence layer", "geometry is empty or null", "Fix geometries")
    assert "feature index 0, id 'c1'" in str(exc_info.value)


def test_basin_zero_area_polygon_reports_qgis_cleanup():
    centroids = FakeLayer(records=[{"id": "b1", "fi": 0.1}], geometries=[[(0, 0)]])
    basins = FakeLayer(records=[{}], geometries=[[(0, 0), (1, 1), (2, 2)]])

    with pytest.raises(ValueError) as exc_info:
        Builder().basin(centroids, basins)

    assert_qgis_error(exc_info, "Basin layer", "basin polygon has zero area", "Check $area")


def test_basin_polygon_with_too_few_vertices_is_clear():
    centroids = FakeLayer(records=[{"id": "b1", "fi": 0.1}], geometries=[[(0, 0)]])
    basins = FakeLayer(records=[{}], geometries=[[(0, 0), (1, 1)]])

    with pytest.raises(ValueError) as exc_info:
        Builder().basin(centroids, basins)

    assert_qgis_error(exc_info, "Basin layer", "fewer than three vertices", "redraw this basin polygon")


@pytest.mark.parametrize(
    "records, geometries, expected",
    [
        ([{"id": "r1", "s": 0.01}], [[(0, 0), (1, 1)]], "required field 't' is missing"),
        ([{"id": "r1", "t": 1, "s": ""}], [[(0, 0), (1, 1)]], "required field 's' is blank or null"),
        ([{"id": "r1", "t": 1, "s": "flat"}], [[(0, 0), (1, 1)]], "field 's' must be numeric"),
        ([{"id": "r1", "t": 1, "s": 0.01}], [[(0, 0)]], "fewer than two vertices"),
    ],
)
def test_reach_input_errors_are_user_facing(records, geometries, expected):
    layer = FakeLayer(records=records, geometries=geometries)

    with pytest.raises(ValueError) as exc_info:
        Builder().reach(layer)

    assert_qgis_error(exc_info, "Reach layer", expected, "Fix in QGIS")


def test_confluence_requires_exactly_one_outlet():
    layer = FakeLayer(
        records=[
            {"id": "c1", "out": 0},
            {"id": "c2", "out": 0},
        ],
        geometries=[
            [(0, 0)],
            [(1, 1)],
        ],
    )

    with pytest.raises(ValueError) as exc_info:
        Builder().confluence(layer)

    assert_qgis_error(exc_info, "Confluence layer", "no outlet confluence", "out = 1")


def test_confluence_rejects_non_numeric_outlet_flag():
    layer = FakeLayer(records=[{"id": "c1", "out": "yes"}], geometries=[[(0, 0)]])

    with pytest.raises(ValueError) as exc_info:
        Builder().confluence(layer)

    assert_qgis_error(exc_info, "Confluence layer", "field 'out' must be numeric", "numbers only")
