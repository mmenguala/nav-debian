#
# Copyright (C) 2007, 2010, 2011 UNINETT AS
#
# This file is part of Network Administration Visualized (NAV).
#
# NAV is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License version 2 as published by
# the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
# more details.  You should have received a copy of the GNU General Public
# License along with NAV. If not, see <http://www.gnu.org/licenses/>.
#
"""Netmap views"""
from django.db.models import Q
from django.http import Http404
from django.views.generic import TemplateView, ListView, View
from django.shortcuts import get_object_or_404

from rest_framework import status, generics, views
from rest_framework.response import Response
from rest_framework.renderers import UnicodeJSONRenderer as JSONRenderer

from nav.django.utils import get_account
from nav.models.profiles import (
    NetmapView,
    NetmapViewCategories,
    NetmapViewDefaultView,
    NetmapViewNodePosition,
    Account,
)
from nav.models.manage import Category, Netbox, Interface
from nav.netmap.traffic import get_traffic_data

from .mixins import DefaultNetmapViewMixin, AdminRequiredMixin
from .serializers import (
    NetmapViewSerializer,
    NetmapViewDefaultViewSerializer,
)
from .graph import get_topology_graph, get_traffic_gradient


class IndexView(DefaultNetmapViewMixin, TemplateView):
    template_name = 'netmap/netmap.html'

    def get_context_data(self, **kwargs):

        user = get_account(self.request)

        context = super(IndexView, self).get_context_data(user=user, **kwargs)

        netmap_views = NetmapView.objects.filter(
            Q(is_public=True) | Q(owner=user)
        ).select_related(
            'owner',
        )

        netmap_views_json = JSONRenderer().render(
            NetmapViewSerializer(netmap_views).data
        )

        categories = list(Category.objects.values_list('id', flat=True))
        categories.append('ELINK')

        context.update({
            'account': user,
            'netmap_views': netmap_views,
            'netmap_views_json': netmap_views_json,
            'categories': categories,
            'traffic_gradient': get_traffic_gradient(),
            'navpath': [('Home', '/'), ('Netmap', '/netmap')]
        })

        return context


class TrafficView(views.APIView):

    renderer_classes = (JSONRenderer,)

    def get(self, request, *args, **kwargs):

        layer = int(kwargs.pop('layer', 2))

        if layer is 3:
            traffic = self.get_layer3_traffic()
        else:
            traffic = self.get_layer2_traffic()

        return Response(traffic)

    def get_layer2_traffic(self):

        # TODO: Select related
        interfaces = Interface.objects.filter(
            to_netbox__isnull=False
        ).select_related('netbox', 'to_netbox', 'to_interface__netbox')
        edges = set([
            (
                interface.netbox_id,
                interface.to_netbox_id
            )
            for interface in interfaces
        ])

        traffic = []
        for source, target in edges:
            edge_interfaces = interfaces.filter(
                netbox_id=source,
                to_netbox_id=target
            )
            edge_traffic = []
            for interface in edge_interfaces:
                to_interface = interface.to_interface
                d = get_traffic_data((interface, to_interface)).to_json()
                d.update({
                    'source_ifname': interface.ifname if interface else '',
                    'target_ifname': to_interface.ifname if to_interface else ''
                })
                edge_traffic.append(d)
            traffic.append({
                'source': source,
                'target': target,
                'edges': edge_traffic,
            })

        return traffic

    def get_layer3_traffic(self):
        return {}


class NetmapAdminView(AdminRequiredMixin, ListView):
    context_object_name = 'views'
    model = NetmapView
    template_name = 'netmap/admin.html'

    def get_context_data(self, **kwargs):
        context = super(NetmapAdminView, self).get_context_data(**kwargs)

        try:
            global_default_view = NetmapViewDefaultView.objects.select_related(
                'view'
            ).get(
                owner=Account.DEFAULT_ACCOUNT
            )
        except NetmapViewDefaultView.DoesNotExist:
            global_default_view = None

        context.update({
            'navpath': [
                ('Home', '/'),
                ('Netmap', '/netmap'),
                ('Netmap admin', 'netmap/admin')
            ],
            'global_default_view': global_default_view
        })

        return context


class NetmapViewList(generics.ListAPIView):

    serializer_class = NetmapViewSerializer

    def get_queryset(self):
        user = get_account(self.request)
        return NetmapView.objects.filter(
            Q(is_public=True) | Q(owner=user)
        )


class NetmapViewCreate(generics.CreateAPIView):

    serializer_class = NetmapViewSerializer

    def pre_save(self, obj):
        user = get_account(self.request)
        obj.owner = user

    def post_save(self, obj, created=False):
        if created:
            for category in obj.categories:
                # Since a new NetmapView object is always created
                # there is no need for further checks.
                # FIXME: User bulk_create?
                NetmapViewCategories.objects.create(
                    view=obj,
                    category=Category.objects.get(id=category)
                )


class NetmapViewEdit(generics.RetrieveUpdateDestroyAPIView):

    lookup_field = 'viewid'
    serializer_class = NetmapViewSerializer

    def get_queryset(self):
        user = get_account(self.request)
        return NetmapView.objects.filter(
            Q(is_public=True) | Q(owner=user)
        )

    def post_save(self, obj, created=False):
        old_categories = set(
            obj.categories_set.values_list('category', flat=True))
        new_categories = set(obj.categories)
        to_delete = old_categories - new_categories
        to_save = new_categories - old_categories

        # Delete removed categories
        obj.categories_set.filter(category__in=to_delete).delete()

        # Create added categories
        NetmapViewCategories.objects.bulk_create([
            NetmapViewCategories(view=obj, category=Category(id=category))
            for category in to_save
        ])

    def get_object_or_none(self):
        try:
            return self.get_object()
        except Http404:
            # Models should not be created in this view.
            # Overridden to raise exception on PUT requests
            # as well as on PATCH
            raise


class NetmapViewDefaultViewUpdate(generics.RetrieveUpdateAPIView):

    lookup_field = 'owner'
    queryset = NetmapViewDefaultView.objects.all()
    serializer_class = NetmapViewDefaultViewSerializer

    def pre_save(self, obj):
        # For some reason beyond my understanding, using a lookup_field
        # that is a foreign key relation causes the parent implementation
        # of this method to raise an exception.
        pass

    def update(self, request, *args, **kwargs):

        if not self._is_owner_or_admin():
            return Response(status.HTTP_401_UNAUTHORIZED)

        return super(NetmapViewDefaultViewUpdate, self).update(
            request,
            args,
            kwargs,
        )

    def retrieve(self, request, *args, **kwargs):

        if not self._is_owner_or_admin():
            return Response(status.HTTP_401_UNAUTHORIZED)

        return super(NetmapViewDefaultViewUpdate, self).retrieve(
            request,
            args,
            kwargs,
        )

    def _is_owner_or_admin(self):

        user = get_account(self.request)
        ownerid = self.kwargs.get(self.lookup_field, Account.DEFAULT_ACCOUNT)

        return user.id == ownerid or user.is_admin()


class NodePositionUpdate(generics.UpdateAPIView):
    """View for updating node positions"""
    def update(self, request, *args, **kwargs):

        viewid = kwargs.pop('viewid')
        data = request.DATA.get('data', [])

        for d in data:
            defaults = {
                'x': int(d['x']),
                'y': int(d['y']),
            }
            obj, created = NetmapViewNodePosition.objects.get_or_create(
                viewid=NetmapView(pk=viewid),
                netbox=Netbox(pk=int(d['netbox'])),
                defaults=defaults
            )
            if not created:
                obj.x = defaults['x']
                obj.y = defaults['y']
                obj.save()
        return Response()


class NetmapGraph(views.APIView):
    """View for building and providing topology data in graph form"""
    def get(self, request, **kwargs):

        load_traffic = 'traffic' in request.GET
        layer = int(kwargs.get('layer', 2))
        viewid = kwargs.get('viewid')
        view = None

        if viewid is not None:
            view = get_object_or_404(NetmapView, pk=viewid)

        return Response(get_topology_graph(layer, load_traffic, view))
