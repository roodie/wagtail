from django.http import HttpResponseForbidden
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import ugettext_lazy

from wagtail.admin import messages
from wagtail.admin.forms.collections import CollectionForm
from wagtail.admin.forms.search import SearchForm
from wagtail.admin.navigation import get_manageable_root_collection, get_collections_with_management_permission
from wagtail.admin.views.generic import CreateView, DeleteView, EditView, IndexView
from wagtail.core import hooks
from wagtail.core.models import Collection


class CollectionPermissionMixin(object):
    def check_permissions(self, collection_perms):
        """All classes using this mixin must implement this function.
        Called for every dispatch event to check if the user has access to the collection view.
        :param wagtail.wagtailcore.models.CollectionPermissionTester collection_perms: The collection permission tester
            object used to determine the level of access the user should be given.
        """
        raise NotImplementedError

    def dispatch(self, request, instance_id, *args, **kwargs):
        collection = get_object_or_404(Collection, pk=instance_id)
        collection_perms = collection.permissions_for_user(request.user)
        if not self.check_permissions(collection_perms):
            raise PermissionDenied
        return super(CollectionPermissionMixin, self).dispatch(request, instance_id, *args, **kwargs)


class Index(IndexView):
    model = Collection
    context_object_name = 'collections'
    template_name = 'wagtailadmin/collections/index.html'
    header_icon = 'folder-open-1'

    def __init__(self):
        super(Index, self).__init__()
        self.parent_collection = None
        self.is_searching = False

    @property
    def page_title(self):
        if not self.parent_collection:
            return ugettext_lazy("Collections")
        return ugettext_lazy(self.parent_collection.name)

    def get_paginate_by(self, queryset):
        return 50

    def get_queryset(self):
        # Only return children of the root node, so that the root is not editable
        if not self.parent_collection:
            # Find the root collection that the user has access to
            self.parent_collection = get_manageable_root_collection(self.request.user)
            if not self.parent_collection:
                raise HttpResponseForbidden

        return get_collections_with_management_permission(user=self.request.user, parent=self.parent_collection)


    def get_context_data(self):
        if self.args:
            parent_collection_id = self.args[0]
            # TODO: Make sure user cannot get to a collection if they have the URL but not the perms
            self.parent_collection = get_object_or_404(Collection, pk=parent_collection_id)

        context = super(Index, self).get_context_data(object_list=self.get_queryset())

        context.update({
            'parent_collection': self.parent_collection,
            'parent_perms': self.parent_collection.permissions_for_user(self.request.user),
        })

        return context


class Create(CreateView):
    form_class = CollectionForm
    page_title = ugettext_lazy("Add collection")
    success_message = ugettext_lazy("Collection '{0}' created.")
    add_url_name = 'wagtailadmin_collections:add_child'
    edit_url_name = 'wagtailadmin_collections:edit'
    header_icon = 'folder-open-1'

    def save_instance(self):
        # Always create new collections as children of root
        instance = self.form.save(commit=False)
        self.parent_collection.add_child(instance=instance)
        return instance

    def __init__(self):
        super(Create, self).__init__()
        self._parent_collection = None

    def get_success_url(self):
        return reverse('wagtailadmin_collections:parent_index', args=(self.parent_collection.pk,))

    @property
    def parent_collection(self):
        # Convenience method for getting the correct parent collection object, will fallback to
        # using the root collection
        if not self._parent_collection:
            self._parent_collection = Collection.get_first_root_node()
        return self._parent_collection

    @parent_collection.setter
    def parent_collection(self, parent_id):
        # Take the parent collection id and get the collection object
        self._parent_collection = get_object_or_404(Collection, pk=parent_id)

    def check_permissions(self, collection_perms):
        return collection_perms.can_add()

    # TODO: Look at removing post/get overrides
    def post(self, request, parent_id=None, *args, **kwargs):
        if parent_id:
            self.parent_collection = parent_id
        return super(Create, self).post(request=request)

    def get(self, request, parent_id=None, *args, **kwargs):
        if parent_id:
            self.parent_collection = parent_id
        return super(Create, self).get(request=request)

    def get_add_url(self):
        return reverse(self.add_url_name, args=(self.parent_collection.pk,))

class Edit(CollectionPermissionMixin, EditView):
    model = Collection
    form_class = CollectionForm
    template_name = 'wagtailadmin/collections/edit.html'
    success_message = ugettext_lazy("Collection '{0}' updated.")
    error_message = ugettext_lazy("The collection could not be saved due to errors.")
    delete_item_label = ugettext_lazy("Delete collection")
    edit_url_name = 'wagtailadmin_collections:edit'
    index_url_name = 'wagtailadmin_collections:index'
    delete_url_name = 'wagtailadmin_collections:delete'
    add_url_name = 'wagtailadmin_collections:add_child'
    context_object_name = 'collection'
    header_icon = 'folder-open-1'

    def get_success_url(self):
        # Redirect to the index view of the parent collection
        return reverse('wagtailadmin_collections:parent_index', args=(self.object.get_parent().pk,))

    def check_permissions(self, collection_perms):
        return collection_perms.can_edit()

    def get_queryset(self):
        # Return all collections except the root collection to prevent it from being editable
        return Collection.objects.exclude(pk=Collection.get_first_root_node().pk)


class Delete(DeleteView):
    model = Collection
    success_message = ugettext_lazy("Collection '{0}' deleted.")
    delete_url_name = 'wagtailadmin_collections:delete'
    page_title = ugettext_lazy("Delete collection")
    confirmation_message = ugettext_lazy("Are you sure you want to delete this collection?")
    header_icon = 'folder-open-1'

    def get_success_url(self):
        # Redirect to the index view of the parent collection
        return reverse('wagtailadmin_collections:parent_index', args=(self.object.get_parent().pk,))

    def check_permissions(self, collection_perms):
        return collection_perms.can_delete()

    def get_queryset(self):
        # Return all collections except the root collection to prevent it from being editable
        return Collection.objects.exclude(pk=Collection.get_first_root_node().pk)

    def get_collection_contents(self, collection):
        collection_contents = [
            hook(collection)
            for hook in hooks.get_hooks('describe_collection_contents')
        ]

        # filter out any hook responses that report that the collection is empty
        # (by returning None, or a dict with 'count': 0)
        def is_nonempty(item_type):
            return item_type and item_type['count'] > 0

        return list(filter(is_nonempty, collection_contents))

    def get_children_collection_contents(self):
        """Get the content information for every collection nested under the collection to be deleted.
        The format for the content under each of the children collections is:
        .. code-block:: python
            [
                {
                    'collection': <wagtail.wagtailcore.models.Collection>,  # the child collection
                    'items': [{}, ],  # list of dictionaries returned from the 'describe_collection_contents' hook
                },
                ...
            ]
        :returns: A list of dictionaries for every child collection containing any content. Will return an empty list
            if none of its descendants contain any content.
        """
        collection_to_delete = self.object
        descendant_contents = []
        # If this collection contains any children collections, then we only want to delete it
        # if none of its children have any contents.
        if not collection_to_delete.is_leaf():
            descendant_collections = collection_to_delete.get_descendants()
            for collection in descendant_collections:
                # Check if the collection has anything in it
                contents = self.get_collection_contents(collection)
                if contents:
                    descendant_contents.append({
                        'collection': collection,
                        'items': contents,
                    })

        return descendant_contents

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        collection_contents = self.get_collection_contents(self.object)
        descendant_contents = self.get_children_collection_contents()

        if descendant_contents:
            context['descendant_contents'] = descendant_contents

        if collection_contents:
            context['collection_contents'] = collection_contents

        if collection_contents or descendant_contents:
            # collection is non-empty; render the 'not allowed to delete' response
            self.template_name = 'wagtailadmin/collections/delete_not_empty.html'

        return context

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        collection_contents = self.get_collection_contents(self.object)
        descendant_contents = self.get_children_collection_contents()

        if collection_contents or descendant_contents:
            # collection or one of its descendants is non-empty; refuse to delete it
            raise PermissionDenied

        self.object.delete()
        messages.success(request, self.success_message.format(self.object))
        return redirect(self.get_success_url())
