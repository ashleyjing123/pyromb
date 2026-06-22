from ...math import geometry
from ..attributes.basin import Basin
from ..attributes.confluence import Confluence
from ..attributes.reach import Reach, ReachType
from ..geometry.line import pointVector
from ..geometry.point import Point
from ..gis.vector_layer import VectorLayer


class Builder:
    """Build the entities of the catchment.

    The Builder is responsible for creating the entities (geometry, attributes) that 
    the catchment will be built from. Building must take place before the 
    catchment is connected and traversed. 

    The objects returned from the Builder are to be passed to the Catcment. 
    """

    def _qgis_error(self, layer_name: str, message: str, fix: str, feature: str = None) -> ValueError:
        location = f"{layer_name}"
        if feature:
            location = f"{location}, {feature}"
        return ValueError(f"\n\n{location}: {message}\nFix in QGIS: {fix}\n\n")

    def _feature_label(self, vector: VectorLayer, i: int) -> str:
        try:
            record = vector.record(i)
            feature_id = record["id"]
        except Exception:
            feature_id = None

        if feature_id is None or (isinstance(feature_id, str) and feature_id.strip() == ""):
            return f"feature index {i}"
        return f"feature index {i}, id {feature_id!r}"

    def _record(self, vector: VectorLayer, i: int, layer_name: str):
        try:
            return vector.record(i)
        except Exception as exc:
            raise self._qgis_error(
                layer_name,
                "feature attributes could not be read.",
                "Export the layer to a new Shapefile or GeoPackage, then run Build RORB again.",
                f"feature index {i}",
            ) from exc

    def _geometry(self, vector: VectorLayer, i: int, layer_name: str) -> list:
        feature = self._feature_label(vector, i)
        try:
            shape = vector.geometry(i)
        except Exception as exc:
            raise self._qgis_error(
                layer_name,
                "geometry could not be read.",
                "Run Fix geometries, check the layer geometry type, and export a clean layer.",
                feature,
            ) from exc

        if shape is None or len(shape) == 0:
            raise self._qgis_error(
                layer_name,
                "geometry is empty or null.",
                "Delete or repair this feature, run Fix geometries, and export the cleaned layer.",
                feature,
            )
        return shape

    def _required_field(self, record, field_name: str, vector: VectorLayer, i: int, layer_name: str):
        try:
            value = record[field_name]
        except Exception as exc:
            raise self._qgis_error(
                layer_name,
                f"required field {field_name!r} is missing.",
                f"Add or rename the {field_name!r} field and populate it for every feature.",
                self._feature_label(vector, i),
            ) from exc

        if value is None or (isinstance(value, str) and value.strip() == ""):
            raise self._qgis_error(
                layer_name,
                f"required field {field_name!r} is blank or null.",
                f"Populate {field_name!r} for this feature.",
                self._feature_label(vector, i),
            )
        return value

    def _required_number(self, value, field_name: str, vector: VectorLayer, i: int, layer_name: str) -> float:
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise self._qgis_error(
                layer_name,
                f"field {field_name!r} must be numeric, but the value is {value!r}.",
                f"Edit {field_name!r} so it contains numbers only.",
                self._feature_label(vector, i),
            ) from exc

    def _required_int(self, value, field_name: str, vector: VectorLayer, i: int, layer_name: str) -> int:
        number = self._required_number(value, field_name, vector, i, layer_name)
        if not number.is_integer():
            raise self._qgis_error(
                layer_name,
                f"field {field_name!r} must be a whole number, but the value is {value!r}.",
                f"Edit {field_name!r} so it contains whole numbers only.",
                self._feature_label(vector, i),
            )
        return int(number)

    def _point(self, vector: VectorLayer, i: int, layer_name: str) -> tuple[float, float]:
        shape = self._geometry(vector, i, layer_name)
        try:
            x = float(shape[0][0])
            y = float(shape[0][1])
        except (IndexError, TypeError, ValueError) as exc:
            raise self._qgis_error(
                layer_name,
                "feature could not be read as point geometry.",
                "Check that the input is a Point layer, then run Fix geometries and export a clean layer.",
                self._feature_label(vector, i),
            ) from exc
        return x, y

    def _line(self, vector: VectorLayer, i: int, layer_name: str) -> list:
        shape = self._geometry(vector, i, layer_name)
        if len(shape) < 2:
            raise self._qgis_error(
                layer_name,
                "reach geometry has fewer than two vertices.",
                "Repair or redraw the reach as a valid line with at least two vertices.",
                self._feature_label(vector, i),
            )

        try:
            for point in shape:
                float(point[0])
                float(point[1])
        except (IndexError, TypeError, ValueError) as exc:
            raise self._qgis_error(
                layer_name,
                "reach geometry has invalid coordinates.",
                "Repair or redraw this reach, run Fix geometries, and export a clean layer.",
                self._feature_label(vector, i),
            ) from exc
        return shape

    def _polygon_points(self, vector: VectorLayer, i: int, layer_name: str) -> list:
        shape = self._geometry(vector, i, layer_name)
        try:
            points = pointVector(shape)
        except (IndexError, TypeError, ValueError) as exc:
            raise self._qgis_error(
                layer_name,
                "feature could not be read as polygon geometry.",
                "Check that the basin input is a Polygon layer, then run Fix geometries.",
                self._feature_label(vector, i),
            ) from exc

        if len(points) < 3:
            raise self._qgis_error(
                layer_name,
                "basin polygon has fewer than three vertices.",
                "Delete or redraw this basin polygon, then export a clean layer.",
                self._feature_label(vector, i),
            )

        area = geometry.polygon_area(points)
        if area == 0:
            raise self._qgis_error(
                layer_name,
                "basin polygon has zero area.",
                "Check $area, delete or repair collapsed/sliver polygons, run Fix geometries, "
                "and export a clean layer.",
                self._feature_label(vector, i),
            )
        return points

    def _check_layer_has_features(self, vector: VectorLayer, layer_name: str) -> None:
        if len(vector) == 0:
            raise self._qgis_error(
                layer_name,
                "layer has no features.",
                "Select a populated input layer or export the intended features to a new layer.",
            )

    def _check_duplicate_ids(self, vector: VectorLayer, layer_name: str) -> None:
        seen = {}
        for i in range(len(vector)):
            record = self._record(vector, i, layer_name)
            feature_id = self._required_field(record, "id", vector, i, layer_name)
            if feature_id in seen:
                first = self._feature_label(vector, seen[feature_id])
                second = self._feature_label(vector, i)
                raise self._qgis_error(
                    layer_name,
                    f"duplicate id {feature_id!r} found at {first} and {second}.",
                    "Make every id unique before running Build RORB again.",
                )
            seen[feature_id] = i

    def reach(self, reach: VectorLayer) -> list:
        """Build the reach objects.

        Parameters
        ----------
        reach : VectorLayer
            The vector layer which the reaches are in.

        Returns:
        -------
        list
            A list of the reache objects.
        """
        layer_name = "Reach layer"
        self._check_layer_has_features(reach, layer_name)
        self._check_duplicate_ids(reach, layer_name)

        reaches = []
        for i in range(len(reach)):
            s = self._line(reach, i, layer_name)
            r = self._record(reach, i, layer_name)
            reach_id = self._required_field(r, "id", reach, i, layer_name)
            reach_type_value = self._required_field(r, "t", reach, i, layer_name)
            slope_value = self._required_field(r, "s", reach, i, layer_name)
            reach_type_number = self._required_int(reach_type_value, "t", reach, i, layer_name)
            slope = self._required_number(slope_value, "s", reach, i, layer_name)
            try:
                reach_type = ReachType(reach_type_number)
            except ValueError as exc:
                raise self._qgis_error(
                    layer_name,
                    f"field 't' has unsupported reach type {reach_type_value!r}.",
                    "Use a supported reach type value: 1, 2, 3, or 4.",
                    self._feature_label(reach, i),
                ) from exc
            reaches.append(Reach(reach_id, s, reach_type, slope))
        return reaches

    def basin(self, centroid: VectorLayer, basin: VectorLayer) -> list:
        """Build the basin objects.

        Parameters
        ----------
        centroid : VectorLayer
            The vector layer which the centroids are in.
        basin : VectorLayer
            The vector layer which the basins are in.

        Returns:
        -------
        list
            A list of the basin objects.
        """
        centroid_layer_name = "Centroid layer"
        basin_layer_name = "Basin layer"
        self._check_layer_has_features(centroid, centroid_layer_name)
        self._check_layer_has_features(basin, basin_layer_name)
        self._check_duplicate_ids(centroid, centroid_layer_name)

        basins = []
        for i in range(len(centroid)):
            min_index = 0
            d = 999
            x, y = self._point(centroid, i, centroid_layer_name)
            r = self._record(centroid, i, centroid_layer_name)
            basin_id = self._required_field(r, "id", centroid, i, centroid_layer_name)
            fi_value = self._required_field(r, "fi", centroid, i, centroid_layer_name)
            fi = self._required_number(fi_value, "fi", centroid, i, centroid_layer_name)
            for j in range(len(basin)):
                polygon = self._polygon_points(basin, j, basin_layer_name)
                try:
                    c = geometry.polygon_centroid(polygon)
                except ZeroDivisionError as exc:
                    raise self._qgis_error(
                        basin_layer_name,
                        "basin polygon centroid could not be calculated.",
                        "Repair invalid or self-intersecting polygons with Fix geometries, then export a clean layer.",
                        self._feature_label(basin, j),
                    ) from exc
                l = geometry.length([Point(x, y), c])
                if l < d:
                    d = l
                    min_index = j
            a = geometry.polygon_area(self._polygon_points(basin, min_index, basin_layer_name))
            basins.append(Basin(basin_id, x, y, (a / 1E6), fi))
        return basins

    def confluence(self, confluence: VectorLayer) -> list:
        """Build the confluence objects

        Parameters
        ----------
        confluence : VectorLayer
            The vector layer the confluences are on. 

        Returns:
        -------
        list
            A list of confluence objects.
        """
        layer_name = "Confluence layer"
        self._check_layer_has_features(confluence, layer_name)
        self._check_duplicate_ids(confluence, layer_name)

        confluences = []
        outlets = []
        for i in range(len(confluence)):
            x, y = self._point(confluence, i, layer_name)
            r = self._record(confluence, i, layer_name)
            confluence_id = self._required_field(r, "id", confluence, i, layer_name)
            out_value = self._required_field(r, "out", confluence, i, layer_name)
            out_number = self._required_int(out_value, "out", confluence, i, layer_name)
            if out_number not in (0, 1):
                raise self._qgis_error(
                    layer_name,
                    f"field 'out' must be 0 or 1, but the value is {out_value!r}.",
                    "Set exactly one outlet confluence to out = 1 and all others to out = 0.",
                    self._feature_label(confluence, i),
                )
            is_outlet = bool(out_number)
            if is_outlet:
                outlets.append(self._feature_label(confluence, i))
            confluences.append(Confluence(confluence_id, x, y, is_outlet))
        if len(outlets) == 0:
            raise self._qgis_error(
                layer_name,
                "no outlet confluence was found.",
                "Set exactly one confluence feature to out = 1.",
            )
        if len(outlets) > 1:
            raise self._qgis_error(
                layer_name,
                f"multiple outlet confluences were found: {', '.join(outlets)}.",
                "Keep one outlet feature with out = 1 and set the others to out = 0.",
            )
        return confluences
