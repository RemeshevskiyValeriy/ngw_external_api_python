"""
/***************************************************************************
    NextGIS WEB API
                              -------------------
        begin                : 2014-11-19
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

import re
from urllib.parse import parse_qs, unquote, urlparse

from .ngw_connection import NGWConnection
from .ngw_connection_settings import NGWConnectionSettings
from .ngw_error import NGWError
from .ngw_resource_factory import NGWResourceFactory


# TODO: move to Identify plus
def ngw_resource_from_qgs_map_layer(qgs_map_layer):
    layer_source = qgs_map_layer.source()
    layer_source = layer_source.lstrip("/vsicurl/")

    url_components = urlparse(layer_source)

    match = re.search(r"^.*/resource/\d+/", url_components.path)
    if match is None:
        return None

    # o.path is '.../resource/<resource id>/.......'
    # m.group() is '.../resource/<resource id>/'
    basePathStructure = match.group().strip("/").split("/")

    baseURL = (
        url_components.scheme
        + "://"
        + url_components.netloc.split("@")[-1]
        + "/"
        + "/".join(basePathStructure[:-3])
    )
    ngw_resources_id = int(basePathStructure[-1])
    requestAttrs = parse_qs(url_components.query)

    ngw_username = None
    ngw_password = None

    if qgs_map_layer.providerType() == "WFS":
        if "username" in requestAttrs:
            ngw_username = requestAttrs.get("username")[0]
        if "password" in requestAttrs:
            ngw_password = requestAttrs.get("password")[0]
    elif qgs_map_layer.providerType() == "ogr":
        if url_components.username and url_components.password:
            ngw_username = unquote(url_components.username)
            ngw_password = unquote(url_components.password)
    else:
        return None
    # additionAttrs = {}
    # if requestAttrs.get(u'TYPENAME') is not None:
    #    additionAttrs.update({u'LayerName': requestAttrs[u'TYPENAME'][0]})
    layer_name = ""
    if requestAttrs.get("TYPENAME") is not None:
        layer_name = requestAttrs["TYPENAME"][0]
    # additionAttrs.update({u'auth':(ngw_username, ngw_password)})
    # additionAttrs.update({u'baseURL':baseURL})
    # additionAttrs.update({u'resourceId':ngw_resources_id})

    ngwConnectionSettings = NGWConnectionSettings(
        "ngw", baseURL, ngw_username, ngw_password
    )
    ngwConnection = NGWConnection(ngwConnectionSettings)

    ngwResourceFactory = NGWResourceFactory(ngwConnection)

    try:
        ngw_resource = ngwResourceFactory.get_resource(ngw_resources_id)

        if ngw_resource is None:
            return None

        if ngw_resource.type_id == "wfsserver_service":
            layers = ngw_resource.get_layers()
            for layer in layers:
                if layer["keyname"] == layer_name:
                    ngw_resources_id = layer["resource_id"]
                    break
            return ngwResourceFactory.get_resource(ngw_resources_id)
        else:
            return ngw_resource
        # return NGWVectorLayer(ngwResourceFactory, NGWResource.receive_resource_obj(ngwConnection, ngw_resources_id))
    except NGWError:
        return None
