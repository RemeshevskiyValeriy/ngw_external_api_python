# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Common Plugins settings

 NextGIS WEB API
                             -------------------
        begin                : 2014-10-31
        git sha              : $Format:%H$
        copyright            : (C) 2014 by NextGIS
        email                : info@nextgis.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
import os
import glob
import shutil
import zipfile
import tempfile

from PyQt4.QtCore import *

from qgis.core import *
from qgis.gui import *

from ..qt.qt_ngw_resource_base_model import *
from ..qt.qt_ngw_resource_edit_model import *
from ..qt.qt_ngw_resource_model_job import *
from ..qt.qt_ngw_resource_model_job_error import *

from ..core.ngw_webmap import NGWWebMapLayer, NGWWebMapGroup, NGWWebMapRoot
from ..core.ngw_resource_creator import ResourceCreator
from ..core.ngw_vector_layer import NGWVectorLayer
from ..core.ngw_qgis_vector_style import NGWQGISVectorStyle
from ..core.ngw_feature import NGWFeature
from ..core.ngw_raster_layer import NGWRasterLayer
from ..core.ngw_wms_service import NGWWmsService
from ..core.ngw_wms_connection import NGWWmsConnection
from ..core.ngw_wms_layer import NGWWmsLayer
from ..utils import log

from ngw_plugin_settings import NgwPluginSettings


class QNGWResourcesModel4QGIS(QNGWResourcesModel):

    def __init__(self, parent):
        QNGWResourcesModel.__init__(self, parent)

    @modelRequest()
    def createNGWLayers(self, qgs_map_layers, parent_index):
        if not parent_index.isValid():
            parent_index = self.index(0, 0, parent_index)

        parent_index = self._nearest_ngw_group_resource_parent(parent_index)
        parent_item = parent_index.internalPointer()
        ngw_group = parent_item.data(0, Qt.UserRole)

        return self._startJob(
            QGISResourcesImporter(qgs_map_layers, ngw_group),
        )

    @modelRequest()
    def createOrUpdateQGISStyle(self, qgs_map_layer, index):
        if not index.isValid():
            index = self.index(0, 0, index)

        item = index.internalPointer()
        ngw_resource = item.data(0, Qt.UserRole)

        return self._startJob(
            QGISStyleImporter(qgs_map_layer, ngw_resource),
        )

    @modelRequest()
    def tryImportCurentQGISProject(self, ngw_group_name, index, iface):
        if not index.isValid():
            index = self.index(0, 0, index)

        index = self._nearest_ngw_group_resource_parent(index)

        item = index.internalPointer()
        ngw_resource = item.data(0, item.NGWResourceRole)

        return self._startJob(
            CurrentQGISProjectImporter(ngw_group_name, ngw_resource, iface),
        )

    @modelRequest()
    def createMapForLayer(self, index, ngw_style_id):
        if not index.isValid():
            index = self.index(0, 0, index)

        item = index.internalPointer()
        ngw_resource = item.data(0, Qt.UserRole)

        return self._startJob(
            MapForLayerCreater(ngw_resource, ngw_style_id)
        )

    @modelRequest()
    def createWMSForVector(self, index, ngw_resource_style_id):
        if not index.isValid():
            index = self.index(0, 0, index)

        parent_index = self._nearest_ngw_group_resource_parent(index)

        parent_item = parent_index.internalPointer()
        ngw_parent_resource = parent_item.data(0, Qt.UserRole)

        item = index.internalPointer()
        ngw_resource = item.data(0, Qt.UserRole)

        return self._startJob(
            NGWCreateWMSForVector(ngw_resource, ngw_parent_resource, ngw_resource_style_id),
        )

    @modelRequest()
    def updateNGWLayer(self, index, qgs_vector_layer):
        if not index.isValid():
            index = self.index(0, 0, index)

        item = index.internalPointer()
        ngw_vector_layer = item.data(0, Qt.UserRole)

        return self._startJob(
            NGWUpdateVectorLayer(ngw_vector_layer, qgs_vector_layer),
        )


class QGISResourceJob(NGWResourceModelJob):
    SUITABLE_LAYER = 0
    SUITABLE_LAYER_BAD_GEOMETRY = 1

    def __init__(self):
        NGWResourceModelJob.__init__(self)

        self.sanitize_fields_names = ["id", "geom"]

    def isSuitableLayer(self, qgs_map_layer):
        layer_type = qgs_map_layer.type()

        if layer_type == qgs_map_layer.VectorLayer:
            if qgs_map_layer.geometryType() in [QGis.NoGeometry, QGis.UnknownGeometry]:
                return self.SUITABLE_LAYER_BAD_GEOMETRY

        return self.SUITABLE_LAYER

    def importQGISMapLayer(self, qgs_map_layer, ngw_parent_resource):
        ngw_parent_resource.update()
        layer_name = qgs_map_layer.name()

        new_layer_name = self.unique_resource_name(layer_name, ngw_parent_resource)

        layer_type = qgs_map_layer.type()

        if layer_type == qgs_map_layer.VectorLayer:
            return self.importQgsVectorLayer(qgs_map_layer, ngw_parent_resource, new_layer_name)

        elif layer_type == QgsMapLayer.RasterLayer:
            layer_data_provider = qgs_map_layer.dataProvider().name()
            if layer_data_provider == "gdal":
                return self.importQgsRasterLayer(qgs_map_layer, ngw_parent_resource, new_layer_name)

            elif layer_data_provider == "wms":
                return self.importQgsWMSLayer(qgs_map_layer, ngw_parent_resource, new_layer_name)

        return None

    def importQgsWMSLayer(self, qgs_wms_layer, ngw_group, ngw_wfs_connection_name):
        self.statusChanged.emit(
            "%s - Import as WMS Connection " % (
                qgs_wms_layer.name(),
            )
        )

        layer_source = qgs_wms_layer.source()
        parameters = {}
        for parameter in layer_source.split('&'):
            key, value = parameter.split("=")
            parameters[key] = value

        wfs_connection = NGWWmsConnection.create_in_group(
            ngw_wfs_connection_name,
            ngw_group,
            parameters.get("url", "")
        )

        return wfs_connection

    def importQgsRasterLayer(self, qgs_raster_layer, ngw_parent_resource, new_layer_name):
        def uploadFileCallback(total_size, readed_size):
            self.statusChanged.emit(
                "%s - Upload (%d%%)" % (
                    qgs_raster_layer.name(),
                    readed_size * 100 / total_size
                )
            )
        layer_provider = qgs_raster_layer.providerType()
        if layer_provider == 'gdal':
            filepath = qgs_raster_layer.source()
            ngw_raster_layer = ResourceCreator.create_raster_layer(
                ngw_parent_resource,
                filepath,
                new_layer_name,
                uploadFileCallback
            )

            return ngw_raster_layer

    def importQgsVectorLayer(self, qgs_vector_layer, ngw_parent_resource, new_layer_name):
        def uploadFileCallback(total_size, readed_size):
            self.statusChanged.emit(
                "%s - Upload (%d%%)" % (
                    qgs_vector_layer.name(),
                    readed_size * 100 / total_size
                )
            )

        if self.isSuitableLayer(qgs_vector_layer) == self.SUITABLE_LAYER_BAD_GEOMETRY:
            self.errorOccurred.emit(
                JobError(
                    "Vector layer '%s' has no suitable geometry" % qgs_vector_layer.name()
                )
            )
            return None

        filepath, rename_fields_map = self.prepareImportFile(qgs_vector_layer)

        if filepath is None:
            self.errorOccurred.emit(
                JobError(
                    "Can't prepare layer'%s'. Skiped!" % qgs_vector_layer.name()
                )
            )
            return None

        ngw_vector_layer = ResourceCreator.create_vector_layer(
            ngw_parent_resource,
            filepath,
            new_layer_name,
            uploadFileCallback
        )

        aliases = {}
        src_layer_aliases = qgs_vector_layer.attributeAliases()
        for fn, rfn in rename_fields_map.items():
            if src_layer_aliases.has_key(fn):
               aliases[rfn] = src_layer_aliases[fn]

        if len(aliases) > 0:
            self.statusChanged.emit(
                "%s - Add aliases" % qgs_vector_layer.name()
            )
            ngw_vector_layer.add_aliases(aliases)

        self.statusChanged.emit(
            "%s - Finishing" % qgs_vector_layer.name()
        )

        os.remove(filepath)
        return ngw_vector_layer

    def prepareImportFile(self, qgs_vector_layer):
        self.statusChanged.emit(
            "%s - Prepare" % qgs_vector_layer.name()
        )

        layer_has_mixed_geoms = False
        layer_has_bad_fields = False
        if NgwPluginSettings.get_sanitize_fix_geometry():
            layer_has_mixed_geoms, fids_with_notvalid_geom = self.checkGeometry(qgs_vector_layer)
        if NgwPluginSettings.get_sanitize_rename_fields():
            if self.hasBadFields(qgs_vector_layer):
                layer_has_bad_fields = True

        rename_fields_map = {}
        if layer_has_mixed_geoms or layer_has_bad_fields or (len(fids_with_notvalid_geom) > 0):
            layer, rename_fields_map = self.createLayer4Upload(qgs_vector_layer, fids_with_notvalid_geom, layer_has_mixed_geoms, layer_has_bad_fields)
        else:
            layer = qgs_vector_layer

        import_format = u'ESRI Shapefile'
        if layer.featureCount() > 0:
            layer_provider = layer.dataProvider()
            if layer_provider.storageType() in [u'ESRI Shapefile']:
                import_format = layer_provider.storageType()
            else:
                import_format = u"GeoJSON"

        if import_format == u'ESRI Shapefile':
            return self.prepareAsShape(layer), rename_fields_map
        else:
            return self.prepareAsJSON(layer), rename_fields_map

    def checkGeometry(self, qgs_vector_layer):
        has_simple_geometries = False
        has_multipart_geometries = False

        fids_with_not_valid_geom = []

        features_count = qgs_vector_layer.featureCount()
        features_counter = 0
        progress = 0
        for feature in qgs_vector_layer.getFeatures():
            v = features_counter * 100 / features_count
            if progress < v:
                progress = v
                self.statusChanged.emit(
                    "%s - Check geometry (%d%%)" % (
                        qgs_vector_layer.name(),
                        features_counter * 100 / features_count
                    )
                )
            features_counter += 1
            if feature.geometry() is None:
                fids_with_not_valid_geom.append(feature.id())
                continue

            # isGeosValid excepted to some geometries
            # if not feature.geometry().isGeosValid():
            #     log("Feature %s has not valid geometry (geos)" % str(feature.id()))
            #     fids_with_not_valid_geom.append(feature.id())

            # Fix one point line. Method isGeosValid return true for same geometry.
            if feature.geometry().type() == QGis.Line:
                g = feature.geometry()
                if g.isMultipart():
                    for polyline in g.asMultiPolyline():
                        if len(polyline) < 2:
                            fids_with_not_valid_geom.append(feature.id())
                            break
                else:
                    if len(g.asPolyline()) < 2:
                        fids_with_not_valid_geom.append(feature.id())

            if feature.geometry().isMultipart():
                has_multipart_geometries = True
            else:
                has_simple_geometries = True

        self.statusChanged.emit(
            "%s - Check geometry (%d%%)" % (
                qgs_vector_layer.name(),
                100
            )
        )

        return (
            (has_multipart_geometries and has_simple_geometries),
            fids_with_not_valid_geom
        )

    def hasBadFields(self, qgs_vector_layer):
        exist_fields_names = [field.name().lower() for field in qgs_vector_layer.fields()]
        common_fields = list(set(exist_fields_names).intersection(self.sanitize_fields_names))

        return len(common_fields) > 0

    def createLayer4Upload(self, qgs_vector_layer_src, fids_with_notvalid_geom, has_mixed_geoms, has_bad_fields):
        geometry_type = self.determineGeometry4MemoryLayer(qgs_vector_layer_src, has_mixed_geoms)

        field_name_map = {}
        if has_bad_fields:
            field_name_map = self.getFieldsForRename(qgs_vector_layer_src)

            if len(field_name_map) != 0:
                msg = QCoreApplication.translate(
                    "QGISResourceJob",
                    "We've renamed fields {0} for layer '{1}'. Style for this layer may become invalid."
                ).format(
                    field_name_map.keys(),
                    qgs_vector_layer_src.name()
                )

                self.warningOccurred.emit(
                    JobError(msg)
                )

        import_crs = QgsCoordinateReferenceSystem(4326, QgsCoordinateReferenceSystem.EpsgCrsId)
        qgs_vector_layer_dst = QgsVectorLayer(
            "%s?crs=%s" % (geometry_type, import_crs.authid()),
            "temp",
            "memory"
        )

        qgs_vector_layer_dst.startEditing()

        for field in qgs_vector_layer_src.fields():
            field.setName(
                field_name_map.get(field.name(), field.name())
            )
            qgs_vector_layer_dst.addAttribute(field)

        qgs_vector_layer_dst.commitChanges()
        qgs_vector_layer_dst.startEditing()
        features_count = qgs_vector_layer_src.featureCount()
        features_counter = 1
        progress = 0
        for feature in qgs_vector_layer_src.getFeatures():
            if feature.id() in fids_with_notvalid_geom:
                continue

            new_geometry = feature.geometry()
            new_geometry.transform(QgsCoordinateTransform(qgs_vector_layer_src.crs(), import_crs))

            if has_mixed_geoms:
                new_geometry.convertToMultiType()
            
            feature.setGeometry(
                new_geometry
            )

            qgs_vector_layer_dst.addFeature(feature)

            tmp_progress = features_counter * 100 / features_count
            if  tmp_progress > progress:
                progress = tmp_progress
                self.statusChanged.emit(
                    "%s - Prepare layer for import (%d%%)" % (
                        qgs_vector_layer_src.name(),
                        features_counter * 100 / features_count
                    )
                )
            features_counter += 1

        qgs_vector_layer_dst.commitChanges()

        if len(fids_with_notvalid_geom) != 0:
                msg = QCoreApplication.translate(
                    "QGISResourceJob",
                    "We've excluded features with id {0} for layer '{1}'. Reason: invalid geometry."
                ).format(
                    fids_with_notvalid_geom,
                    qgs_vector_layer_src.name()
                )

                self.warningOccurred.emit(
                    JobError(msg)
                )

        return qgs_vector_layer_dst, field_name_map

    def determineGeometry4MemoryLayer(self, qgs_vector_layer, has_mixed_geoms):
        geometry_type = None
        if qgs_vector_layer.geometryType() == QGis.Point:
            geometry_type = "point"
        elif qgs_vector_layer.geometryType() == QGis.Line:
            geometry_type = "linestring"
        elif qgs_vector_layer.geometryType() == QGis.Polygon:
            geometry_type = "polygon"

        # if has_multipart_geometries:
        if has_mixed_geoms:
            geometry_type = "multi" + geometry_type

        return geometry_type

    def getFieldsForRename(self, qgs_vector_layer):
        field_name_map = {}

        exist_fields_names = [field.name() for field in qgs_vector_layer.fields()]
        for field in qgs_vector_layer.fields():
            if field.name().lower() in self.sanitize_fields_names:
                new_field_name = field.name()
                suffix = 1
                while new_field_name in exist_fields_names:
                    new_field_name = field.name() + str(suffix)
                    suffix += 1
                field_name_map.update({field.name(): new_field_name})

        return field_name_map

    def prepareAsShape(self, qgs_vector_layer):
        tmp_dir = tempfile.mkdtemp('ngw_api_prepare_import')
        tmp_shp = os.path.join(tmp_dir, '4import.shp')

        import_crs = QgsCoordinateReferenceSystem(4326, QgsCoordinateReferenceSystem.EpsgCrsId)
        QgsVectorFileWriter.writeAsVectorFormat(
            qgs_vector_layer,
            tmp_shp,
            'utf-8',
            import_crs,
        )

        tmp = tempfile.mktemp('.zip')
        basePath = os.path.splitext(tmp_shp)[0]
        baseName = os.path.splitext(os.path.basename(tmp_shp))[0]

        self.statusChanged.emit(
            "%s - Packing" % qgs_vector_layer.name()
        )

        zf = zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED)
        for i in glob.iglob(basePath + '.*'):
            ext = os.path.splitext(i)[1]
            zf.write(i, baseName + ext)

        zf.close()
        shutil.rmtree(tmp_dir)

        return tmp

    def prepareAsJSON(self, qgs_vector_layer):
        tmp = tempfile.mktemp('.geojson')
        import_crs = QgsCoordinateReferenceSystem(4326, QgsCoordinateReferenceSystem.EpsgCrsId)
        QgsVectorFileWriter.writeAsVectorFormat(
            qgs_vector_layer,
            tmp,
            'utf-8',
            import_crs,
            'GeoJSON'
        )

        return tmp

    def addQMLStyle(self, qml, ngw_layer_resource):
        def uploadFileCallback(total_size, readed_size):
            self.statusChanged.emit(
                "Style for %s - Upload (%d%%)" % (
                    ngw_layer_resource.common.display_name,
                    readed_size * 100 / total_size
                )
            )

        ngw_style = ngw_layer_resource.create_qml_style(
            qml,
            uploadFileCallback
        )
        return ngw_style

    def addStyle(self, qgs_map_layer, ngw_layer_resource):
        layer_type = qgs_map_layer.type()
        if layer_type == QgsMapLayer.VectorLayer:
            tmp = tempfile.mktemp('.qml')
            self.statusChanged.emit(
                "Style for %s - Save as qml" % qgs_map_layer.name()
            )
            msg, saved = qgs_map_layer.saveNamedStyle(tmp)
            ngw_resource = self.addQMLStyle(tmp, ngw_layer_resource)
            os.remove(tmp)
            return ngw_resource
        elif layer_type == QgsMapLayer.RasterLayer:
            layer_provider = qgs_map_layer.providerType()
            if layer_provider == 'gdal':
                ngw_resource = ngw_layer_resource.create_style()
                return ngw_resource

        return None

    def updateQMLStyle(self, qml, ngw_qgis_vector_resource):
        def uploadFileCallback(total_size, readed_size):
            self.statusChanged.emit(
                "Style for %s - Upload (%d%%)" % (
                    ngw_qgis_vector_resource.common.display_name,
                    readed_size * 100 / total_size
                )
            )

        ngw_qgis_vector_resource.update_qml(
            qml,
            uploadFileCallback
        )

    def updateStyle(self, qgs_map_layer, ngw_qgis_vector_resource):
        layer_type = qgs_map_layer.type()
        if layer_type == QgsMapLayer.VectorLayer:
            tmp = tempfile.mktemp('.qml')
            self.statusChanged.emit(
                "Style for %s - Save as qml" % qgs_map_layer.name()
            )
            msg, saved = qgs_map_layer.saveNamedStyle(tmp)
            self.updateQMLStyle(tmp, ngw_qgis_vector_resource)
            os.remove(tmp)

    def getQMLDefaultStyle(self):
        gtype = self.ngw_layer._json[self.ngw_layer.type_id]["geometry_type"]

        if gtype in ["LINESTRING", "MULTILINESTRING"]:
            return os.path.join(
                os.path.dirname(__file__),
                "qgis_styles",
                "line_style.qml"
            )
        if gtype in ["POINT", "MULTIPOINT"]:
            return os.path.join(
                os.path.dirname(__file__),
                "qgis_styles",
                "point_style.qml"
            )
        if gtype in ["POLYGON", "MULTIPOLYGON"]:
            return os.path.join(
                os.path.dirname(__file__),
                "qgis_styles",
                "polygon_style.qml"
            )

        return None

    def _defStyleForVector(self, ngw_layer):
        qml = self.getQMLDefaultStyle()

        if qml is None:
            self.errorOccurred.emit("There is no defalut style description for create new style.")
            return

        ngw_style = self.addQMLStyle(qml, ngw_layer)

        return ngw_style

    def _defStyleForRaster(self, ngw_layer):
        ngw_style = ngw_layer.create_style()
        return ngw_style

    def overwriteQGISMapLayer(self, qgs_map_layer, ngw_layer_resource):
        layer_type = qgs_map_layer.type()

        if layer_type == qgs_map_layer.VectorLayer:
            return self.overwriteQgsVectorLayer(qgs_map_layer, ngw_layer_resource)

        return None

    def overwriteQgsVectorLayer(self, qgs_map_layer, ngw_layer_resource):
        block_size = 10
        total_count = qgs_map_layer.featureCount()
        current_count = 0
        done = 0
        
        self.statusChanged.emit(
            "%s - Remove all feature" % (
                ngw_layer_resource.common.display_name,
            )
        )
        ngw_layer_resource.delete_all_features()

        self.statusChanged.emit(
            "%s - Add features" % (
                ngw_layer_resource.common.display_name,
            )
        )
        for features in self.getFeaturesPart(qgs_map_layer, ngw_layer_resource, block_size):
            ngw_layer_resource.patch_features(features)
            current_count += len(features)

            d = current_count * 100 / total_count
            if done < d:
                done = d
                self.statusChanged.emit(
                    "%s - Add features (%d%%)" % (
                        ngw_layer_resource.common.display_name ,
                        done
                    )
                )
    
    def getFeaturesPart(self, qgs_map_layer, ngw_layer_resource, pack_size):
        ngw_features=[]
        for qgsFeature in qgs_map_layer.getFeatures():
            ngw_features.append(
                NGWFeature(self.createNGWFeatureDictFromQGSFeature(ngw_layer_resource, qgsFeature, qgs_map_layer), ngw_layer_resource)
            )

            if len(ngw_features) == pack_size:
                yield ngw_features
                ngw_features = []

        if len(ngw_features) > 0:
                yield ngw_features

    def createNGWFeatureDictFromQGSFeature(self, ngw_layer_resource, qgs_feature, qgs_map_layer):
        feature_dict = {}

        # id need only for update not for create
        # feature_dict["id"] = qgs_feature.id() + 1 # Fix NGW behavior
        g = qgs_feature.constGeometry()
        g.transform(
            QgsCoordinateTransform(
                qgs_map_layer.crs(),
                QgsCoordinateReferenceSystem(ngw_layer_resource.srs(), QgsCoordinateReferenceSystem.EpsgCrsId)
            )
        )
        if ngw_layer_resource.is_geom_multy():
            g.convertToMultiType()
        feature_dict["geom"] = g.exportToWkt()

        feature_dict["fields"] = {}

        for qgsField in qgs_feature.fields().toList():
            field_type = ngw_layer_resource.fieldType(qgsField.name())
            # value = unicode(qgs_feature.attribute(qgsField.name()))
            if field_type == NGWVectorLayer.FieldTypeString:
                value = unicode(qgs_feature.attribute(qgsField.name()))
            elif field_type == NGWVectorLayer.FieldTypeReal:
                value = float(qgs_feature.attribute(qgsField.name()))
            else:
                value = unicode(qgs_feature.attribute(qgsField.name()))

            feature_dict["fields"][qgsField.name()] = value

        return feature_dict


class QGISResourcesImporter(QGISResourceJob):
    def __init__(self, qgs_map_layers, ngw_group):
        QGISResourceJob.__init__(self)
        self.qgs_map_layers = qgs_map_layers
        self.ngw_group = ngw_group

    def _do(self):
        result = NGWResourceModelJobResult()

        for qgs_map_layer in self.qgs_map_layers:
            ngw_resource = self.importQGISMapLayer(
                qgs_map_layer,
                self.ngw_group
            )
            result.putAddedResource(ngw_resource, is_main=True)

            if ngw_resource.type_id in [NGWVectorLayer.type_id, NGWRasterLayer.type_id]:
                ngw_style = self.addStyle(
                    qgs_map_layer,
                    ngw_resource
                )
                result.putAddedResource(ngw_style)
                ngw_resource.update()

            if ngw_resource.type_id == NGWWmsConnection.type_id:
                self.statusChanged.emit(
                    "%s - Import as WMS Layer " % (
                        qgs_map_layer.name(),
                    )
                )
                ngw_wfs_layer_name = self.unique_resource_name(
                    ngw_resource.common.display_name + "_layer",
                    self.ngw_group
                )
                wfs_layer = NGWWmsLayer.create_in_group(
                    ngw_wfs_layer_name,
                    self.ngw_group,
                    ngw_resource.common.id,
                    ngw_resource.layers()
                )
                result.putAddedResource(wfs_layer)

        self.ngw_group.update()

        self.dataReceived.emit(result)


class CurrentQGISProjectImporter(QGISResourceJob):
    """
        if new_group_name is None  -- Update mode

        Update:
        1. Add new
        2. Rewrite current (vector only)
        3. Remove
        4. Update map

        Update Ext (future):
        Calculate mapping of qgislayer to ngw resource
        Show map for user to edit anf cofirm it
    """
    def __init__(self, new_group_name, ngw_resource, iface):
        QGISResourceJob.__init__(self)
        self.new_group_name = new_group_name
        self.ngw_resource = ngw_resource
        self.iface = iface

    def _do(self):
        current_project = QgsProject.instance()
        result = NGWResourceModelJobResult()

        update_mode = self.new_group_name is None

        if update_mode:
            ngw_group_resource = self.ngw_resource
            result.putEditedResource(ngw_group_resource)
        else:
            new_group_name = self.unique_resource_name(self.new_group_name, self.ngw_resource)
            ngw_group_resource = ResourceCreator.create_group(
                self.ngw_resource,
                new_group_name
            )
            result.putAddedResource(ngw_group_resource)

        ngw_webmap_root_group = NGWWebMapRoot()

        self.process_one_level_of_layers_tree(
            current_project.layerTreeRoot().children(),
            ngw_group_resource,
            ngw_webmap_root_group,
            result
        )

        if not update_mode:
            self.statusChanged.emit("Import curent qgis project: create webmap")
            ngw_webmap = self.add_webmap(
                ngw_group_resource,
                self.new_group_name + u"-webmap",
                ngw_webmap_root_group.children
            )
            result.putAddedResource(ngw_webmap, is_main=True)

        # The group was attached resources,  therefore, it is necessary to upgrade for get children flag
        ngw_group_resource.update()

        self.dataReceived.emit(result)

    def process_one_level_of_layers_tree(self, qgs_layer_tree_items, ngw_resource_group, ngw_webmap_item, result):
        exist_resourse_names = {}
        for r in ngw_resource_group.get_children():
            exist_resourse_names[r.common.display_name] = r

        for item in qgs_layer_tree_items:
            if isinstance(item, QgsLayerTreeLayer):
                if self.isSuitableLayer(item.layer()) != self.SUITABLE_LAYER:
                    continue

                if item.layer().name() not in exist_resourse_names:
                    self.add_layer(ngw_resource_group, item, ngw_webmap_item, result)
                elif item.layer().name() in exist_resourse_names:
                    self.update_layer(item, exist_resourse_names[item.layer().name()], result)
                    exist_resourse_names.pop(item.layer().name())

            if isinstance(item, QgsLayerTreeGroup):
                if item.name() not in exist_resourse_names:
                    self.add_group(ngw_resource_group, item, ngw_webmap_item, result)
                elif item.name() in exist_resourse_names:
                    exist_resourse_names.pop(item.name())
        
        for exist_resourse_name in exist_resourse_names:
            # need to delete
            pass

    def add_layer(self, ngw_resource_group, qgsLayerTreeItem, ngw_webmap_item, result):
        try:
            ngw_layer_resource = self.importQGISMapLayer(
                qgsLayerTreeItem.layer(),
                ngw_resource_group
            )
        except Exception as e:
            if NgwPluginSettings.get_force_qgis_project_import():
                self.warningOccurred.emit(
                    JobError(
                        self.tr("Import '%s' failed.") % qgsLayerTreeItem.layer().name(),
                        e
                    )
                )
                return
            else:
                raise e

        if ngw_layer_resource is None:
            return

        log(">>> resource creation Finish")
        result.putAddedResource(ngw_layer_resource)

        if ngw_layer_resource.type_id in [NGWVectorLayer.type_id, NGWRasterLayer.type_id]:
            log(">>> style creation Start")
            ngw_style = self.addStyle(
                qgsLayerTreeItem.layer(),
                ngw_layer_resource
            )

            if ngw_style is None:
                return
            result.putAddedResource(ngw_style)

            ngw_webmap_item.appendChild(
                NGWWebMapLayer(
                    ngw_style.common.id,
                    qgsLayerTreeItem.layer().name(),
                    qgsLayerTreeItem.isVisible() == Qt.Checked
                )
            )

            # Add style to layer, therefore, it is necessary to upgrade layer resource for get children flag
            ngw_layer_resource.update()
            log(">>> style creation Finish")

        if ngw_layer_resource.type_id == NGWWmsConnection.type_id:
            self.statusChanged.emit(
                "%s - Import as WMS Layer " % (
                    qgsLayerTreeItem.layer().name(),
                )
            )
            ngw_wfs_layer_name = self.unique_resource_name(
                ngw_layer_resource.common.display_name + "_layer",
                ngw_resource_group
            )
            wfs_layer = NGWWmsLayer.create_in_group(
                ngw_wfs_layer_name,
                ngw_resource_group,
                ngw_layer_resource.common.id,
                ngw_layer_resource.layers()
            )

            if wfs_layer is None:
                return
            result.putAddedResource(wfs_layer)

            ngw_webmap_item.appendChild(
                NGWWebMapLayer(
                    wfs_layer.common.id,
                    wfs_layer.common.display_name,
                    qgsLayerTreeItem.isVisible() == Qt.Checked
                )
            )

    def update_layer(self, qgsLayerTreeItem, ngwVectorLayer, result):
        self.overwriteQGISMapLayer(qgsLayerTreeItem.layer(), ngwVectorLayer)
        result.putEditedResource(ngwVectorLayer)
        
        for child in  ngwVectorLayer.get_children():
            if isinstance(child, NGWQGISVectorStyle):
                self.updateStyle(qgsLayerTreeItem.layer(), child)

    def add_group(self, ngw_resource_group, qgsLayerTreeGroup, ngw_webmap_item, result):
        chd_names = [ch.common.display_name for ch in ngw_resource_group.get_children()]

        group_name = qgsLayerTreeGroup.name()
        self.statusChanged.emit("Import folder %s" % group_name)

        if group_name in chd_names:
            id = 1
            while(group_name + str(id) in chd_names):
                id += 1
            group_name += str(id)

        ngw_resource_child_group = ResourceCreator.create_group(
            ngw_resource_group,
            group_name
        )
        result.putAddedResource(ngw_resource_child_group)

        ngw_webmap_child_group = NGWWebMapGroup(
            group_name,
            qgsLayerTreeGroup.isExpanded()
        )
        ngw_webmap_item.appendChild(
            ngw_webmap_child_group
        )

        self.process_one_level_of_layers_tree(
            qgsLayerTreeGroup.children(),
            ngw_resource_child_group,
            ngw_webmap_child_group,
            result
        )

    def add_webmap(self, ngw_resource, ngw_webmap_name, ngw_webmap_items):
        rectangle = self.iface.mapCanvas().extent()
        ct = QgsCoordinateTransform(
            self.iface.mapCanvas().mapSettings().destinationCrs(),
            QgsCoordinateReferenceSystem(4326, QgsCoordinateReferenceSystem.EpsgCrsId)
        )

        # log(">>> rectangle: " + str(rectangle.asPolygon()))
        # bbox = ct.transform(QgsRectangle(-179.9, -89.9, 179.9, 89.9), QgsCoordinateTransform.ReverseTransform)
        # log(">>> bbox: " + str(bbox.asPolygon()))
        # rectangle = rectangle.intersect(bbox)
        # log(">>> rectangle 1: " + str(rectangle.asPolygon()))
        rectangle = ct.transform(rectangle)
        # log(">>> rectangle 2: " + str(rectangle.asPolygon()))
        ngw_webmap_items_as_dicts = [item.toDict() for item in ngw_webmap_items]
        ngw_resource = ResourceCreator.create_webmap(
            ngw_resource,
            ngw_webmap_name,
            ngw_webmap_items_as_dicts,
            [
                rectangle.xMinimum(),
                rectangle.xMaximum(),
                rectangle.yMaximum(),
                rectangle.yMinimum(),
            ]
        )

        return ngw_resource


class MapForLayerCreater(QGISResourceJob):
    def __init__(self, ngw_layer, ngw_style_id):
        NGWResourceModelJob.__init__(self)
        self.ngw_layer = ngw_layer
        self.ngw_style_id = ngw_style_id

    def _do(self):
        result = NGWResourceModelJobResult()

        if self.ngw_style_id is None:
            if self.ngw_layer.type_id == NGWVectorLayer.type_id:
                ngw_style = self._defStyleForVector(self.ngw_layer)
                result.putAddedResource(ngw_style)
                self.ngw_style_id = ngw_style.common.id

            if self.ngw_layer.type_id == NGWRasterLayer.type_id:
                ngw_style = self._defStyleForRaster(self.ngw_layer)
                result.putAddedResource(ngw_style)
                self.ngw_style_id = ngw_style.common.id

        ngw_webmap_root_group = NGWWebMapRoot()
        ngw_webmap_root_group.appendChild(
            NGWWebMapLayer(
                self.ngw_style_id,
                self.ngw_layer.common.display_name,
                True
            )
        )

        ngw_group = self.ngw_layer.get_parent()

        ngw_map_name = self.unique_resource_name(
            self.ngw_layer.common.display_name + "-map",
            ngw_group
        )

        ngw_resource = ResourceCreator.create_webmap(
            ngw_group,
            ngw_map_name,
            [item.toDict() for item in ngw_webmap_root_group.children],
            bbox=self.ngw_layer.extent()
        )

        result.putAddedResource(ngw_resource, is_main=True)

        self.dataReceived.emit(result)


class QGISStyleImporter(QGISResourceJob):
    def __init__(self, qgs_map_layer, ngw_resource):
        QGISResourceJob.__init__(self)
        self.qgs_map_layer = qgs_map_layer
        self.ngw_resource = ngw_resource

    def _do(self):
        result = NGWResourceModelJobResult()

        if self.ngw_resource.type_id == NGWVectorLayer.type_id:
            ngw_style = self.addStyle(self.qgs_map_layer, self.ngw_resource)
            result.putAddedResource(ngw_style)
        elif self.ngw_resource.type_id == NGWQGISVectorStyle.type_id:
            self.updateStyle(self.qgs_map_layer, self.ngw_resource)
            result.putEditedResource(self.ngw_resource)

        self.dataReceived.emit(result)


class NGWCreateWMSForVector(QGISResourceJob):
    def __init__(self, ngw_vector_layer, ngw_group_resource, ngw_style_id):
        NGWResourceModelJob.__init__(self)
        self.ngw_layer = ngw_vector_layer
        self.ngw_group_resource = ngw_group_resource
        self.ngw_style_id = ngw_style_id

    def _do(self):
        result = NGWResourceModelJobResult()

        if self.ngw_style_id is None:
            if self.ngw_layer.type_id == NGWVectorLayer.type_id:
                ngw_style = self._defStyleForVector(self.ngw_layer)
                result.putAddedResource(ngw_style)
                self.ngw_style_id = ngw_style.common.id

            if self.ngw_layer.type_id == NGWRasterLayer.type_id:
                ngw_style = self._defStyleForRaster(self.ngw_layer)
                result.putAddedResource(ngw_style)
                self.ngw_style_id = ngw_style.common.id

        ngw_wms_service_name = self.unique_resource_name(
            self.ngw_layer.common.display_name + "-wms-service",
            self.ngw_group_resource)

        ngw_wfs_resource = NGWWmsService.create_in_group(
            ngw_wms_service_name,
            self.ngw_group_resource,
            [(self.ngw_layer, self.ngw_style_id)],
        )

        result.putAddedResource(ngw_wfs_resource, is_main=True)

        self.dataReceived.emit(result)


class NGWUpdateVectorLayer(QGISResourceJob):
    def __init__(self, ngw_vector_layer, qgs_map_layers):
        NGWResourceModelJob.__init__(self)
        self.ngw_layer = ngw_vector_layer
        self.qgis_layer = qgs_map_layers

    def createNGWFeatureDictFromQGSFeature(self, qgs_feature):
        feature_dict = {}

        # id need only for update not for create
        # feature_dict["id"] = qgs_feature.id() + 1 # Fix NGW behavior
        feature_dict["geom"] = qgs_feature.constGeometry().exportToWkt()
        feature_dict["fields"] = {}

        for qgsField in qgs_feature.fields().toList():
            field_type = self.ngw_layer.fieldType(qgsField.name())
            # value = unicode(qgs_feature.attribute(qgsField.name()))
            if field_type == NGWVectorLayer.FieldTypeString:
                value = unicode(qgs_feature.attribute(qgsField.name()))
            elif field_type == NGWVectorLayer.FieldTypeReal:
                value = float(qgs_feature.attribute(qgsField.name()))
            else:
                value = unicode(qgs_feature.attribute(qgsField.name()))

            feature_dict["fields"][qgsField.name()] = value

        return feature_dict

    def getFeaturesPart(self, pack_size):
        ngw_features=[]
        for qgsFeature in self.qgis_layer.getFeatures():
            ngw_features.append(
                NGWFeature(self.createNGWFeatureDictFromQGSFeature(qgsFeature), self.ngw_layer)
            )

            if len(ngw_features) == pack_size:
                yield ngw_features
                ngw_features = []

        if len(ngw_features) > 0:
                yield ngw_features
                
    def _do(self):
        log(">>> NGWUpdateVectorLayer _do")
        result = NGWResourceModelJobResult()
        
        block_size = 10
        total_count = self.qgis_layer.featureCount()
        current_count = 0
        done = 0
        
        self.statusChanged.emit(
            "%s - Remove all feature" % (
                self.qgis_layer ,
            )
        )
        self.ngw_layer.delete_all_features()

        self.statusChanged.emit(
            "%s - Add features" % (
                self.qgis_layer ,
            )
        )
        for features in self.getFeaturesPart(block_size):
            self.ngw_layer.patch_features(features)
            current_count += len(features)

            d = current_count * 100 / total_count
            if done < d:
                done = d
                self.statusChanged.emit(
                    "%s - Add features (%d%%)" % (
                        self.qgis_layer ,
                        done
                    )
                )
        self.dataReceived.emit(result)
