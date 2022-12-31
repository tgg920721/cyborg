# Copyright 2022 Inspur.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from http import HTTPStatus
import pecan
import wsme
from wsme import types as wtypes

from oslo_log import log

from cyborg.api.controllers import base
from cyborg.api.controllers import link
from cyborg.api.controllers import types
from cyborg.api import expose
from cyborg.common import authorize_wsgi
from cyborg import objects
LOG = log.getLogger(__name__)


class Attribute(base.APIBase):
    """API representation of a attribute.

    This class enforces type checking and value constraints, and converts
    between the internal object model and the API representation of
    a attribute. See module notes above.
    """

    """The UUID of the attribute"""
    uuid = types.uuid

    """The deployable_id of the attribute"""
    deployable_id = wtypes.IntegerType()

    """The key of the device attribute"""
    key = wtypes.text

    """The value of the attribute"""
    value = wtypes.text

    created_at = wtypes.datetime.datetime
    updated_at = wtypes.datetime.datetime

    """A list containing a self link"""
    links = wsme.wsattr([link.Link], readonly=True)

    def __init__(self, **kwargs):
        super(Attribute, self).__init__(**kwargs)
        self.fields = []
        for field in objects.Attribute.fields:
            self.fields.append(field)
            setattr(self, field, kwargs.get(field, wtypes.Unset))

    @classmethod
    def convert_with_links(cls, obj_attribute):
        api_attribute = cls(**obj_attribute.as_dict())
        api_attribute.links = [
            link.Link.make_link('self', pecan.request.public_url,
                                'attribute', api_attribute.uuid)
            ]
        return api_attribute

    def get_attribute(self, obj_attribute):
        api_obj = {}
        for field in ['uuid', 'deployable_id', 'key', 'value']:
            api_obj[field] = obj_attribute[field]
        for field in ['created_at', 'updated_at']:
            api_obj[field] = str(obj_attribute[field])
        api_obj['links'] = [
            link.Link.make_link_dict('attributes', api_obj['uuid'])
            ]
        return api_obj


class AttributeCollection(Attribute):
    """API representation of a collection of attributes."""

    """A list containing attribute objects"""
    attributes = [Attribute]

    @classmethod
    def convert_with_links(cls, obj_attributes):
        collection = cls()
        collection.attributes = [
            Attribute.convert_with_links(obj_attribute)
            for obj_attribute in obj_attributes]
        return collection

    def get_attributes(self, obj_attributes):
        api_obj_attributes = [
            self.get_attribute(obj_attribute)
            for obj_attribute in obj_attributes]
        return api_obj_attributes


class AttributesController(base.CyborgController,
                           AttributeCollection):
    """REST controller for Attributes."""

    @authorize_wsgi.authorize_wsgi("cyborg:attribute", "get_all", False)
    @expose.expose(AttributeCollection, wtypes.text)
    def get_all(self):
        """Retrieve a list of attributes."""

        LOG.info('[attributes] get_all.')
        context = pecan.request.context
        api_obj_attributes = objects.Attribute.get_by_filter(context, {})

        ret = AttributeCollection.convert_with_links(api_obj_attributes)
        LOG.info('[Attributes] get_all returned: %s', ret)
        return ret

    @authorize_wsgi.authorize_wsgi("cyborg:attribute", "get_one")
    @expose.expose('json', wtypes.text)
    def get_one(self, uuid):
        """Retrieve a single attribute by uuid."""
        LOG.info('[attributes] get_one.')
        context = pecan.request.context
        api_obj_attributes = objects.Attribute.get(context, uuid)
        ret = AttributeCollection.convert_with_links(api_obj_attributes)
        LOG.info('[attributes] get_one returned: %s', ret)
        return ret

    @authorize_wsgi.authorize_wsgi("cyborg:attribute",
                                   "get_attribute_by_deployable_id", False)
    @expose.expose('json', wtypes.IntegerType())
    def get_attribute_by_deployable_id(self, deployable_id):
        """Retrieve a single attribute by deployable_id."""
        LOG.info('[attributes] get_attribute_by_deployable_id: %s.',
                 deployable_id)
        context = pecan.request.context
        api_obj_attributes = objects.Attribute.get_by_deployable_id(
            context, deployable_id)
        ret = AttributeCollection.convert_with_links(api_obj_attributes)
        LOG.info('[attributes] get_attribute_by_deployable_id returned:'
                 ' %s', ret)
        return ret

    @authorize_wsgi.authorize_wsgi("cyborg:attribute", "delete")
    @expose.expose(None, wtypes.text, status_code=HTTPStatus.NO_CONTENT)
    def delete(self, uuid):
        """Delete one attribute.
            - UUID of a attribute.
        """
        LOG.info('[attributes] delete.')
        context = pecan.request.context
        objects.Attribute.destory(context, uuid)