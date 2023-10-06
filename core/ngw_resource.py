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
from os import path
from typing import Any, Tuple, Optional, TYPE_CHECKING

import urllib.parse

from ..utils import ICONS_DIR

API_RESOURCE_URL = lambda res_id: '/api/resource/%d' % res_id
API_COLLECTION_URL = '/api/resource/'
RESOURCE_URL = lambda res_id: '/resource/%d' % res_id

API_LAYER_EXTENT = lambda res_id: '/api/resource/%d/extent' % res_id


class Wrapper:
    def __init__(self, **params):
        self.__dict__.update(params)

    if TYPE_CHECKING:
        def __setattr__(self, __name: str, __value: Any) -> None: ...
        def __getattr__(self, __name: str) -> Any: ...


DICT_TO_OBJ = lambda d: Wrapper(**d)
LIST_DICT_TO_LIST_OBJ = lambda l: [Wrapper(**el) for el in l]


class NGWResource:

    type_id = 'resource'
    icon_path = path.join(ICONS_DIR, 'resource.svg')
    type_title = 'NGW Resource'

    # STATIC
    @classmethod
    def receive_resource_obj(cls, ngw_con, res_id):
        """
        :rtype : json obj
        """
        return ngw_con.get(API_RESOURCE_URL(res_id))

    @classmethod
    def receive_resource_children(cls, ngw_con, res_id):
        """
        :rtype : json obj
        """
        return ngw_con.get("%s?parent=%s" % (API_COLLECTION_URL, res_id))

    @classmethod
    def delete_resource(cls, ngw_resource):
        ngw_con = ngw_resource._res_factory.connection
        url = API_RESOURCE_URL(ngw_resource.common.id)
        ngw_con.delete(url)

    # INSTANCE
    def __init__(self, resource_factory, resource_json):
        """
        Init resource from json representation
        :param ngw_resource: any ngw_resource
        """
        self._res_factory = resource_factory
        self._json = resource_json
        self._construct()
        self.children_count = None

    def set_children_count(self, children_count):
        self.children_count = children_count

    def _construct(self):
        """
        Construct resource from self._json
        Can be overridden in a derived class
        """
        # resource
        self.common = DICT_TO_OBJ(self._json['resource'])
        if self.common.parent:
            self.common.parent = DICT_TO_OBJ(self.common.parent)
        if self.common.owner_user:
            self.common.owner_user = DICT_TO_OBJ(self.common.owner_user)
        # resmeta
        if 'resmeta' in self._json:
            self.metadata = DICT_TO_OBJ(self._json['resmeta'])

    def get_parent(self):
        if self.common.parent:
            return self._res_factory.get_resource(self.common.parent.id)
        else:
            return None

    def get_children(self):
        children = []
        if self.common.children:
            children_json = NGWResource.receive_resource_children(
                self._res_factory.connection, self.common.id
            )
            for child_json in children_json:
                children.append(
                    self._res_factory.get_resource_by_json(child_json)
                )
        return children

    def get_absolute_url(self):
        base_url = self._res_factory.connection.server_url
        return urllib.parse.urljoin(base_url, RESOURCE_URL(self.common.id))

    def get_absolute_api_url(self):
        base_url = self._res_factory.connection.server_url
        return urllib.parse.urljoin(base_url, API_RESOURCE_URL(self.common.id))

    def get_absolute_api_url_with_auth(self):
        base_url = self._res_factory.connection.server_url
        creds = self.get_creds()
        if creds[0] and creds[1]:
            login = urllib.parse.quote_plus(creds[0])
            password = urllib.parse.quote_plus(creds[1])
            base_url = base_url.replace('://', f'://{login}:{password}@')
        url = urllib.parse.urljoin(base_url, API_RESOURCE_URL(self.common.id))
        return f'/vsicurl/{url}'

    def get_relative_url(self):
        return RESOURCE_URL(self.common.id)

    def get_relative_api_url(self):
        return API_RESOURCE_URL(self.common.id)

    def get_creds(self) -> Tuple[Optional[str], Optional[str]]:
        return self._res_factory.connection.get_auth()

    @classmethod
    def get_api_collection_url(cls):
        return API_COLLECTION_URL

    def change_name(self, name):
        new_name = self.generate_unique_child_name(name)
        params = dict(
            resource=dict(
                display_name=new_name,
            ),
        )

        connection = self._res_factory.connection
        url = self.get_relative_api_url()
        connection.put(url, params=params)
        self.update()

    def update_metadata(self, metadata):
        params = dict(
            resmeta=dict(
                items=metadata,
            ),
        )

        connection = self._res_factory.connection
        url = self.get_relative_api_url()
        connection.put(url, params=params)
        self.update()

    def update(self):
        self._json = self.receive_resource_obj(
            self._res_factory.connection,
            self.common.id
        )

        self._construct()

        children = self.get_children()
        self.set_children_count(len(children))

    def generate_unique_child_name(self, name: str):
        chd_names = [ch.common.display_name for ch in self.get_children()]
        if name not in chd_names:
            return name

        if re.search(r'\(\d\)$', name):
            name = name[:-3]
        new_name = name
        new_name_with_space = None
        id = 1
        while (new_name in chd_names or new_name_with_space in chd_names):
            new_name = f'{name}({id})'
            new_name_with_space = f'{name} ({id})'
            id += 1
        return new_name if new_name_with_space is None else new_name_with_space
